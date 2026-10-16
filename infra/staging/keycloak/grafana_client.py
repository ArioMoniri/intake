"""Bring the live staff realm's `grafana` client into its committed shape (INT-481).

The staff Grafana sits behind oauth2-proxy-grafana, which signs staff in through
the realm's own `grafana` client: confidential, standard flow only, PKCE S256,
redirecting to ``https://grafana.<host>/oauth2/callback`` and nowhere else. The
committed realm (``intake-realm.json``) carries it, but Keycloak imports a realm
once: ``start --import-realm`` skips a realm that already exists, so a host whose
realm predates INT-481 has no such client. This script creates it, or brings
every field it governs back to the committed value, and fails unless the client
ends in that shape. ``--check`` only reads.

It governs exactly the fields of :func:`desired` and nothing else: no mapper, no
role, no scope is touched, so the client gets the realm's default scopes (the
realm roles oauth2-proxy-grafana checks among them) and no `api` audience.

It runs in a one-off api container (stdlib only) on the internal network. The
bootstrap admin password and the client secret arrive on stdin, one per line,
so neither reaches an argv, an environment or a log. It prints field NAMES that
differ, never a value.

Usage: ``python grafana_client.py [--check] <base-url> <realm> <admin-user> <host>``,
password and client secret on stdin.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CLIENT_ID = "grafana"
NAME = "Önvizit staff Grafana (behind oauth2-proxy-grafana, confidential, metrics only)"
#: The attributes this script governs; any other attribute is left alone.
GOVERNED_ATTRIBUTES = ("pkce.code.challenge.method", "post.logout.redirect.uris")
_HOST_RE = re.compile(r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SECRET_RE = re.compile(r"^[0-9a-f]{64}$")


class ClientRefused(Exception):
    """The live realm is in a state this script will not edit: a human looks first."""


@dataclass(frozen=True)
class Step:
    """``create``, ``update`` (with the differing field names) or ``done``."""

    action: str
    fields: tuple[str, ...] = ()


def desired(host: str, secret: str) -> dict[str, Any]:
    """The committed client, with the host and the host-generated secret filled in."""
    if _HOST_RE.match(host) is None:
        raise ValueError("not a public hostname")
    if _SECRET_RE.match(secret) is None:
        raise ValueError("the client secret is not a generated secret")
    origin = f"https://grafana.{host}"
    return {
        "clientId": CLIENT_ID,
        "name": NAME,
        "enabled": True,
        "protocol": "openid-connect",
        "bearerOnly": False,
        "publicClient": False,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "redirectUris": [f"{origin}/oauth2/callback"],
        "webOrigins": [origin],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": f"{origin}/",
        },
        "clientAuthenticatorType": "client-secret",
        "secret": secret,
    }


def drift(live: Mapping[str, Any], live_secret: str | None, want: Mapping[str, Any]) -> list[str]:
    """The governed field names whose live value differs from the committed one."""
    differing: list[str] = []
    for field, value in want.items():
        if field == "secret":
            if live_secret != value:
                differing.append("secret")
        elif field == "attributes":
            attributes = live.get("attributes") or {}
            for key in GOVERNED_ATTRIBUTES:
                if attributes.get(key) != value[key]:
                    differing.append(f"attributes.{key}")
        elif isinstance(value, list):
            if sorted(live.get(field) or []) != sorted(value):
                differing.append(field)
        elif live.get(field) != value:
            differing.append(field)
    return differing


def plan(
    live: Sequence[Mapping[str, Any]], live_secret: str | None, want: Mapping[str, Any]
) -> Step:
    """The one change that moves the live realm toward the committed client."""
    if len(live) > 1:
        raise ClientRefused("the realm holds more than one client with this id")
    if not live:
        return Step("create")
    differing = drift(live[0], live_secret, want)
    return Step("update", tuple(differing)) if differing else Step("done")


def merged(live: Mapping[str, Any], want: Mapping[str, Any]) -> dict[str, Any]:
    """The live representation with every governed field set to its committed value."""
    out = dict(live)
    for field, value in want.items():
        if field == "attributes":
            attributes = dict(live.get("attributes") or {})
            attributes.update(value)
            out["attributes"] = attributes
        else:
            out[field] = value
    return out


def checked_base(base_url: str) -> str:
    """The admin API base, http(s) only: every URL below is built on it."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("the Keycloak base URL must be http(s)://host[:port]")
    return base_url.rstrip("/")


class Admin:
    """The Keycloak admin REST API for one realm, over the internal network."""

    def __init__(self, base_url: str, realm: str, bearer: str) -> None:
        self._base = checked_base(base_url)
        self._realm = urllib.parse.quote(realm, safe="")
        self._bearer = bearer

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 — checked_base admits http(s) only
            f"{self._base}/admin/realms/{self._realm}{path}", data=data, method=method
        )
        request.add_header("Authorization", f"Bearer {self._bearer}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None

    def find(self) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"clientId": CLIENT_ID})
        found: list[dict[str, Any]] = self._call("GET", f"/clients?{query}")
        return found

    def secret(self, client_uuid: str) -> str | None:
        answer = self._call(
            "GET", f"/clients/{urllib.parse.quote(client_uuid, safe='')}/client-secret"
        )
        value = answer.get("value") if isinstance(answer, dict) else None
        return value if isinstance(value, str) else None

    def create(self, representation: Mapping[str, Any]) -> None:
        self._call("POST", "/clients", dict(representation))

    def update(self, client_uuid: str, representation: Mapping[str, Any]) -> None:
        self._call(
            "PUT", f"/clients/{urllib.parse.quote(client_uuid, safe='')}", dict(representation)
        )


def admin_bearer(base_url: str, user: str, password: str) -> str:
    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": user, "password": password}
    ).encode("ascii")
    request = urllib.request.Request(  # noqa: S310 — checked_base admits http(s) only
        f"{checked_base(base_url)}/realms/master/protocol/openid-connect/token",
        data=form,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        token: str = json.loads(response.read())["access_token"]
    return token


def _live(admin: Admin) -> tuple[list[dict[str, Any]], str | None]:
    found = admin.find()
    secret = admin.secret(str(found[0]["id"])) if len(found) == 1 else None
    return found, secret


def run(admin: Admin, want: Mapping[str, Any], *, check_only: bool) -> list[Step]:
    """Apply at most one change, then require the committed shape; return what was done."""
    taken: list[Step] = []
    found, secret = _live(admin)
    step = plan(found, secret, want)
    if step.action != "done":
        if check_only:
            detail = ", ".join(step.fields) if step.fields else "absent"
            raise ClientRefused(f"the live client is not in the committed shape ({detail})")
        if step.action == "create":
            admin.create(want)
        else:
            admin.update(str(found[0]["id"]), merged(found[0], want))
        taken.append(step)
        found, secret = _live(admin)
        settled = plan(found, secret, want)
        if settled.action != "done":
            raise ClientRefused(f"the client did not settle ({', '.join(settled.fields)})")
    return taken


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    check_only = "--check" in args
    if check_only:
        args.remove("--check")
    if len(args) != 4:
        print(
            "usage: grafana_client.py [--check] <base-url> <realm> <admin-user> <host>",
            file=sys.stderr,
        )
        return 2
    base_url, realm, user, host = args
    password = sys.stdin.readline().rstrip("\n")
    secret = sys.stdin.readline().rstrip("\n")
    if not password or not secret:
        print(
            "grafana client: the admin password and the client secret come on stdin",
            file=sys.stderr,
        )
        return 2
    try:
        want = desired(host, secret)
        admin = Admin(base_url, realm, admin_bearer(base_url, user, password))
        taken = run(admin, want, check_only=check_only)
    except urllib.error.HTTPError as err:
        # a status and a reason only: a response body is never printed
        print(f"grafana client: the admin API answered {err.code} {err.reason}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"grafana client: refused or unreachable ({type(err).__name__})", file=sys.stderr)
        return 1
    except ClientRefused as refused:
        print(f"grafana client: refused: {refused}", file=sys.stderr)
        return 3
    for step in taken:
        changed = f" ({', '.join(step.fields)})" if step.fields else ""
        print(f"grafana client: {step.action}{changed}")
    print(f"grafana client: realm {realm} has the committed {CLIENT_ID} client")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
