"""Bring the live realm's four-eyes step-up client onto the committed shape (INT-563, ADR-043).

The API approves a four-eyes action only with a grant earned through a fresh re-authentication
at the realm's public client ``admin-web-stepup`` (PKCE S256, the console's ``/step-up/callback``
alone, ``aaguid``/``credential_id``/``amr`` in the ID token and nowhere else). The committed
realm (``intake-realm.json``) declares it, but Keycloak imports a realm once: ``start
--import-realm`` skips a realm that already exists. So this script makes the live realm carry
that client, and nothing else:

- an absent client is **added**, whole, with its three mappers, in one ``POST /clients``;
- a present client is **verified** against the committed one: its flags (``fullScopeAllowed``
  off included), redirect URIs, web origins, PKCE attribute, default client scopes, every
  mapper, and **no per-client authentication-flow override** (a browser-flow override to a
  password-only flow would make the step-up a password check). A difference is refused with
  its name and changed by nobody: a live client that differs is either an operator's
  deliberate edit or an attack, and either way a human looks.

It never reads or writes an authentication flow or an execution. A ``PUT`` on the staff
browser flow without each execution's priority zeroes them (deploy e19640d2); the step-up
needs no flow change at all, because ``prompt=login`` re-runs the realm's own staff browser
flow. It is idempotent, ends by re-reading the client and checking it, and ``--check`` only
reads. It runs in a one-off api container (stdlib only) on the internal network and reads the
bootstrap admin password on stdin, so the secret never reaches an argv, an environment or a
log. It prints the client id and the names of what differs, never a value from a credential.

Usage: ``python step_up_client.py [--check] <base-url> <realm> <admin-user> <hostname>``,
password on stdin. ``<hostname>`` is the staging hostname the realm's
``${STAGING_HOSTNAME}`` stands for.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

CLIENT_ID = "admin-web-stepup"
NAME = "Önvizit admin console step-up (public, PKCE, re-authentication only)"
CALLBACK = "https://admin.{hostname}/step-up/callback"
NOTE_MAPPER = "oidc-usersessionmodel-note-mapper"
AMR_MAPPER = "oidc-amr-mapper"
#: The committed client's flags. A live client must carry each with this value.
FLAGS: Mapping[str, Any] = {
    "enabled": True,
    "protocol": "openid-connect",
    "bearerOnly": False,
    "publicClient": True,
    "standardFlowEnabled": True,
    "implicitFlowEnabled": False,
    "directAccessGrantsEnabled": False,
    "serviceAccountsEnabled": False,
    # its tokens carry no realm role: the step-up reads none, and a role in an ID token
    # is a claim nobody verified (INT-563 review)
    "fullScopeAllowed": False,
}
#: The one client scope the step-up needs: Keycloak's `basic` (``sub`` and ``auth_time``).
DEFAULT_SCOPES: tuple[str, ...] = ("basic",)
ATTRIBUTES: Mapping[str, str] = {"pkce.code.challenge.method": "S256"}
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _note_mapper(name: str, note: str) -> dict[str, Any]:
    return {
        "name": name,
        "protocol": "openid-connect",
        "protocolMapper": NOTE_MAPPER,
        "consentRequired": False,
        "config": {
            "user.session.note": note,
            "claim.name": name,
            "jsonType.label": "String",
            "access.token.claim": "false",
            "introspection.token.claim": "false",
            "id.token.claim": "true",
            "userinfo.token.claim": "false",
        },
    }


#: The committed mappers, by name (tests hold these equal to intake-realm.json).
MAPPERS: Mapping[str, dict[str, Any]] = {
    "aaguid": _note_mapper("aaguid", "intake.webauthn.aaguid"),
    "credential_id": _note_mapper("credential_id", "intake.webauthn.credential_id"),
    "amr": {
        "name": "amr",
        "protocol": "openid-connect",
        "protocolMapper": AMR_MAPPER,
        "consentRequired": False,
        "config": {
            "id.token.claim": "true",
            "access.token.claim": "false",
            "introspection.token.claim": "false",
        },
    },
}


class ClientRefused(Exception):
    """The live realm's client is in a state this script will not edit: a human looks first."""


class ClientAdmin(Protocol):
    def find(self) -> list[Mapping[str, Any]]: ...

    def create(self, representation: Mapping[str, Any]) -> None: ...


def checked_base(base_url: str) -> str:
    """The admin API base, http(s) only: every URL below is built on it (ruff S310)."""
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("the Keycloak base URL must be http(s)://host[:port]")
    return base_url.rstrip("/")


def committed(hostname: str) -> dict[str, Any]:
    """The client exactly as ``intake-realm.json`` declares it, for one hostname."""
    if _HOSTNAME.fullmatch(hostname) is None:
        raise ValueError("the staging hostname is not a DNS name")
    return {
        "clientId": CLIENT_ID,
        "name": NAME,
        **FLAGS,
        "redirectUris": [CALLBACK.format(hostname=hostname)],
        "webOrigins": [],
        "attributes": dict(ATTRIBUTES),
        "protocolMappers": [dict(mapper) for mapper in MAPPERS.values()],
        "defaultClientScopes": list(DEFAULT_SCOPES),
        # no per-client flow: the staff browser flow, whose WebAuthn step is REQUIRED,
        # is the only one this client can run (INT-563 review B1)
        "authenticationFlowBindingOverrides": {},
    }


def differences(live: Mapping[str, Any], hostname: str) -> list[str]:
    """What in a live client differs from the committed one — names only, never values."""
    wanted = committed(hostname)
    found: list[str] = [key for key, value in FLAGS.items() if live.get(key) != value]
    if sorted(live.get("redirectUris") or []) != wanted["redirectUris"]:
        found.append("redirectUris")
    if list(live.get("webOrigins") or []) != []:
        found.append("webOrigins")
    # review B1: a browser-flow override (a password-only flow) would let a stolen
    # bearer plus a password approve; absent or empty is the only committed state
    if dict(live.get("authenticationFlowBindingOverrides") or {}) != {}:
        found.append("authenticationFlowBindingOverrides")
    if sorted(live.get("defaultClientScopes") or []) != sorted(DEFAULT_SCOPES):
        found.append("defaultClientScopes")
    attributes = live.get("attributes") or {}
    found += [f"attributes.{k}" for k, v in ATTRIBUTES.items() if attributes.get(k) != v]
    mappers = {m.get("name"): m for m in live.get("protocolMappers") or []}
    if set(mappers) != set(MAPPERS):
        found.append("protocolMappers")
    for name, mapper in MAPPERS.items():
        have = mappers.get(name)
        if have is None:
            continue
        if have.get("protocolMapper") != mapper["protocolMapper"]:
            found.append(f"protocolMappers.{name}")
            continue
        config = have.get("config") or {}
        found += [
            f"protocolMappers.{name}.{key}"
            for key, value in mapper["config"].items()
            if config.get(key) != value
        ]
    return found


def run(admin: ClientAdmin, hostname: str, *, check_only: bool) -> str:
    """Add the client if it is absent, then verify it. Returns ``added`` or ``present``."""
    clients = [c for c in admin.find() if c.get("clientId") == CLIENT_ID]
    if len(clients) > 1:
        raise ClientRefused(f"the realm declares {CLIENT_ID} more than once")
    taken = "present"
    if not clients:
        if check_only:
            raise ClientRefused(f"the realm has no {CLIENT_ID} client")
        admin.create(committed(hostname))
        taken = "added"
        clients = [c for c in admin.find() if c.get("clientId") == CLIENT_ID]
        if len(clients) != 1:
            raise ClientRefused(f"{CLIENT_ID} was created but does not read back")
    drift = differences(clients[0], hostname)
    if drift:
        raise ClientRefused(f"{CLIENT_ID} differs from the committed client: {', '.join(drift)}")
    return taken


class Admin:
    """The Keycloak admin REST API, over the internal network, with one bearer."""

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

    def find(self) -> list[Mapping[str, Any]]:
        query = urllib.parse.urlencode({"clientId": CLIENT_ID})
        found: list[Mapping[str, Any]] = self._call("GET", f"/clients?{query}") or []
        return found

    def create(self, representation: Mapping[str, Any]) -> None:
        self._call("POST", "/clients", representation)


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


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    check_only = "--check" in args
    if check_only:
        args.remove("--check")
    if len(args) != 4:
        print(
            "usage: step_up_client.py [--check] <base-url> <realm> <admin-user> <hostname>",
            file=sys.stderr,
        )
        return 2
    base_url, realm, user, hostname = args
    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("step-up client: no admin password on stdin", file=sys.stderr)
        return 2
    try:
        admin = Admin(base_url, realm, admin_bearer(base_url, user, password))
        taken = run(admin, hostname, check_only=check_only)
    except urllib.error.HTTPError as err:
        # a status and a reason only: a response body is never printed
        print(f"step-up client: the admin API answered {err.code} {err.reason}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"step-up client: Keycloak unreachable ({type(err).__name__})", file=sys.stderr)
        return 1
    except ClientRefused as refused:
        print(f"step-up client: refused: {refused}", file=sys.stderr)
        return 3
    print(f"step-up client: realm {realm} {taken} {CLIENT_ID}, in the committed shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
