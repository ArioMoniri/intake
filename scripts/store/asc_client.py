"""INT-495 — the App Store Connect client: credentials, token, guard, draft writer.

**Credentials are read at run time only.** :meth:`Credentials.from_eas_json`
reads the four ``submit.production.ios`` fields of the owner's own eas.json
(the key file path, key id, issuer id and app id) and the key file it names.
Nothing is copied, cached, logged or printed; ``repr`` shows no field.

**Every request passes :func:`guard` before it is sent.** Only the reads and
draft edits this writer needs are on the allow-list, and each edit may carry
only its own attributes. Submitting for review, releasing, pricing,
availability, agreements, deleting anything, creating a version and the App
Review contact and sign-in fields are refused before a byte leaves the machine.

**The log carries field names and HTTP statuses, never a value.**
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from asc_plan import AGE_RATING_KEYS, Plan, Step
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

__all__ = [
    "API",
    "ApplyError",
    "Credentials",
    "CredentialsError",
    "ForbiddenRequest",
    "HttpTransport",
    "Transport",
    "apply_plan",
    "guard",
    "make_token",
    "pick_editable",
]

API: Final[str] = "https://api.appstoreconnect.apple.com"
#: Apple caps a token's life at 20 minutes; a shorter one leaks less.
TOKEN_SECONDS: Final[int] = 15 * 60

EDITABLE_STATES: Final[frozenset[str]] = frozenset(
    {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED"}
)

_ID = r"[^/?]+"
#: (method, path pattern, attributes the body may carry, relationships it may carry)
_ALLOWED: Final[tuple[tuple[str, re.Pattern[str], frozenset[str], frozenset[str]], ...]] = (
    # The read-back reads the app record (primaryLocale, contentRightsDeclaration).
    ("GET", re.compile(rf"/v1/apps/{_ID}"), frozenset(), frozenset()),
    ("GET", re.compile(rf"/v1/apps/{_ID}/appInfos"), frozenset(), frozenset()),
    ("GET", re.compile(rf"/v1/apps/{_ID}/appStoreVersions"), frozenset(), frozenset()),
    ("GET", re.compile(rf"/v1/appInfos/{_ID}/appInfoLocalizations"), frozenset(), frozenset()),
    (
        "GET",
        re.compile(rf"/v1/appStoreVersions/{_ID}/appStoreVersionLocalizations"),
        frozenset(),
        frozenset(),
    ),
    ("GET", re.compile(rf"/v1/appInfos/{_ID}/ageRatingDeclaration"), frozenset(), frozenset()),
    (
        "GET",
        re.compile(rf"/v1/appStoreVersions/{_ID}/appStoreReviewDetail"),
        frozenset(),
        frozenset(),
    ),
    ("GET", re.compile(r"/v1/appAssetLibraryRefData"), frozenset(), frozenset()),
    *(
        (
            method,
            re.compile(path),
            frozenset({"locale", "name", "subtitle", "privacyPolicyUrl"}),
            frozenset({"appInfo"}),
        )
        for method, path in (
            ("PATCH", rf"/v1/appInfoLocalizations/{_ID}"),
            ("POST", r"/v1/appInfoLocalizations"),
        )
    ),
    *(
        (
            method,
            re.compile(path),
            frozenset(
                {"locale", "description", "keywords", "promotionalText", "supportUrl"}
                | {"marketingUrl"}
            ),
            frozenset({"appStoreVersion"}),
        )
        for method, path in (
            ("PATCH", rf"/v1/appStoreVersionLocalizations/{_ID}"),
            ("POST", r"/v1/appStoreVersionLocalizations"),
        )
    ),
    ("PATCH", re.compile(rf"/v1/appInfos/{_ID}"), frozenset(), frozenset({"primaryCategory"})),
    ("PATCH", re.compile(rf"/v1/apps/{_ID}"), frozenset({"contentRightsDeclaration"}), frozenset()),
    (
        "PATCH",
        re.compile(rf"/v1/ageRatingDeclarations/{_ID}"),
        frozenset(AGE_RATING_KEYS),
        frozenset(),
    ),
    ("PATCH", re.compile(rf"/v1/appStoreVersions/{_ID}"), frozenset({"copyright"}), frozenset()),
    (
        "POST",
        re.compile(r"/v1/appStoreReviewDetails"),
        frozenset({"notes"}),
        frozenset({"appStoreVersion"}),
    ),
    ("PATCH", re.compile(rf"/v1/appStoreReviewDetails/{_ID}"), frozenset({"notes"}), frozenset()),
)


class CredentialsError(Exception):
    """The owner's eas.json or key file cannot be read. Names fields, never values."""


class ForbiddenRequest(Exception):
    """A request outside the draft edits this writer may make."""


class ApplyError(Exception):
    """App Store Connect refused, or holds nothing editable."""


@dataclass(frozen=True, repr=False)
class Credentials:
    key_id: str
    issuer_id: str
    app_id: str
    private_key_pem: bytes

    def __repr__(self) -> str:
        return "Credentials(<read at run time; not shown>)"

    @classmethod
    def from_eas_json(cls, path: Path) -> Credentials:
        try:
            ios = json.loads(path.read_text(encoding="utf-8"))["submit"]["production"]["ios"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CredentialsError(f"{path}: no submit.production.ios block") from exc
        names = ("ascApiKeyPath", "ascApiKeyId", "ascApiKeyIssuerId", "ascAppId")
        missing = [name for name in names if not str(ios.get(name, "")).strip()]
        if missing:
            raise CredentialsError(f"{path}: submit.production.ios is missing {missing}")
        key_path = Path(str(ios["ascApiKeyPath"])).expanduser()
        if not key_path.is_absolute():
            key_path = path.parent / key_path
        try:
            pem = key_path.read_bytes()
        except OSError as exc:
            raise CredentialsError(f"{path}: the ascApiKeyPath file cannot be read") from exc
        return cls(
            str(ios["ascApiKeyId"]), str(ios["ascApiKeyIssuerId"]), str(ios["ascAppId"]), pem
        )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_token(creds: Credentials, *, now: int) -> str:
    """An ES256 App Store Connect token, valid for :data:`TOKEN_SECONDS`."""
    key = serialization.load_pem_private_key(creds.private_key_pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise CredentialsError("the ascApiKeyPath file is not an EC private key")
    header = _b64(json.dumps({"alg": "ES256", "kid": creds.key_id, "typ": "JWT"}).encode())
    claims = {
        "iss": creds.issuer_id,
        "iat": now,
        "exp": now + TOKEN_SECONDS,
        "aud": "appstoreconnect-v1",
    }
    payload = _b64(json.dumps(claims).encode())
    der = key.sign(f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"{header}.{payload}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def guard(method: str, path: str, body: Mapping[str, Any] | None) -> None:
    """Refuse anything that is not a read or a draft edit this writer makes."""
    base = path.split("?", 1)[0]
    for allowed_method, pattern, attributes, relationships in _ALLOWED:
        if allowed_method == method and pattern.fullmatch(base):
            data = (body or {}).get("data") or {}
            extra = set(data.get("attributes") or {}) - attributes
            extra |= set(data.get("relationships") or {}) - relationships
            if extra:
                raise ForbiddenRequest(f"{method} {base} may not carry {sorted(extra)}")
            return
    raise ForbiddenRequest(f"{method} {base} is not a draft edit this writer makes")


class Transport(Protocol):
    def request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> tuple[int, Any]: ...


class HttpTransport:
    """httpx over the live API. Guards every request; never logs a body."""

    def __init__(self, creds: Credentials) -> None:
        import httpx

        self._creds = creds
        self._client = httpx.Client(base_url=API, timeout=60.0)
        self._token = ""
        self._minted = 0

    def request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> tuple[int, Any]:
        guard(method, path, body)
        now = int(time.time())
        if now - self._minted > TOKEN_SECONDS - 60:
            self._token, self._minted = make_token(self._creds, now=now), now
        response = self._client.request(
            method, path, json=body, headers={"Authorization": f"Bearer {self._token}"}
        )
        return response.status_code, (response.json() if response.content else None)


def pick_editable(data: Any, state_key: str, what: str) -> str:
    """The id of the first row in an editable state, or the refusal."""
    for row in data or []:
        if row.get("attributes", {}).get(state_key) in EDITABLE_STATES:
            return str(row["id"])
    raise ApplyError(
        f"no editable {what}; create the next version in App Store Connect, then run again"
    )


def _why(data: Any) -> str:
    """Apple's error codes and pointers; never its detail, which may quote a value."""
    errors = data.get("errors") if isinstance(data, Mapping) else None
    parts = [
        f"{error.get('code', '?')} at {(error.get('source') or {}).get('pointer', '?')}"
        for error in errors or []
        if isinstance(error, Mapping)
    ]
    return f" ({'; '.join(parts)})" if parts else ""


def apply_plan(
    plan: Plan, transport: Transport, *, app_id: str, log: Callable[[str], None]
) -> None:
    """Write the plan's draft edits.

    The editable app info and version are found before the first write. A version's
    localizations are read again just before each is written: App Store Connect
    creates one when a language joins the app info, so a list read earlier would
    send a POST that answers 409 DUPLICATE (live run, 31 Oct 2026)."""

    def call(method: str, path: str, body: Mapping[str, Any] | None, what: str) -> Any:
        status, data = transport.request(method, path, body)
        log(f"{method} {what} -> {status}")
        if status >= 300:
            raise ApplyError(
                f"{method} {what} answered {status}{_why(data)}; stopped, nothing further sent"
            )
        return (data or {}).get("data")

    info = pick_editable(
        call("GET", f"/v1/apps/{app_id}/appInfos", None, "appInfos"), "state", "appInfo"
    )
    versions = call(
        "GET", f"/v1/apps/{app_id}/appStoreVersions?filter[platform]=IOS", None, "appStoreVersions"
    )
    version = pick_editable(versions, "appVersionState", "App Store version")
    info_locs = {
        row["attributes"]["locale"]: row["id"]
        for row in call("GET", f"/v1/appInfos/{info}/appInfoLocalizations", None, "locales") or []
    }

    def version_locs() -> dict[str, str]:
        rows = call(
            "GET", f"/v1/appStoreVersions/{version}/appStoreVersionLocalizations", None, "locales"
        )
        return {row["attributes"]["locale"]: row["id"] for row in rows or []}

    version_locs()  # a refused lookup still stops the run before the first write

    def localization(
        step: Step, kind: str, parent: tuple[str, str], existing: Mapping[str, str]
    ) -> None:
        if step.locale is None:
            raise ApplyError(f"{kind} needs a locale")
        values = dict(plan.values[(kind, step.locale)])
        what = f"{kind}[{step.locale}] {','.join(step.fields)}"
        if step.locale in existing:
            row_id = existing[step.locale]
            body = {"data": {"type": kind, "id": row_id, "attributes": values}}
            call("PATCH", f"/v1/{kind}/{row_id}", body, what)
        else:
            rel = {parent[0]: {"data": {"type": f"{parent[0]}s", "id": parent[1]}}}
            attrs = {"locale": step.locale, **values}
            body = {"data": {"type": kind, "attributes": attrs, "relationships": rel}}
            call("POST", f"/v1/{kind}", body, what)

    for step in plan.steps:
        values = dict(plan.values[(step.resource, step.locale)])
        what = f"{step.resource} {','.join(step.fields)}"
        if step.resource == "appInfoLocalizations":
            localization(step, step.resource, ("appInfo", info), info_locs)
        elif step.resource == "appStoreVersionLocalizations":
            localization(step, step.resource, ("appStoreVersion", version), version_locs())
        elif step.resource == "appInfos":
            category = {"data": {"type": "appCategories", "id": values["primaryCategory"]}}
            body = {
                "data": {
                    "type": "appInfos",
                    "id": info,
                    "relationships": {"primaryCategory": category},
                }
            }
            call("PATCH", f"/v1/appInfos/{info}", body, what)
        elif step.resource == "apps":
            body = {"data": {"type": "apps", "id": app_id, "attributes": values}}
            call("PATCH", f"/v1/apps/{app_id}", body, what)
        elif step.resource == "ageRatingDeclarations":
            rating = call("GET", f"/v1/appInfos/{info}/ageRatingDeclaration", None, "ageRating")
            body = {"data": {"type": step.resource, "id": rating["id"], "attributes": values}}
            call("PATCH", f"/v1/ageRatingDeclarations/{rating['id']}", body, what)
        elif step.resource == "appStoreVersions":
            body = {"data": {"type": step.resource, "id": version, "attributes": values}}
            call("PATCH", f"/v1/appStoreVersions/{version}", body, what)
        elif step.resource == "appStoreReviewDetails":
            detail = call(
                "GET", f"/v1/appStoreVersions/{version}/appStoreReviewDetail", None, "reviewDetail"
            )
            if detail:
                body = {"data": {"type": step.resource, "id": detail["id"], "attributes": values}}
                call("PATCH", f"/v1/appStoreReviewDetails/{detail['id']}", body, what)
            else:
                rel = {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version}}}
                body = {"data": {"type": step.resource, "attributes": values, "relationships": rel}}
                call("POST", "/v1/appStoreReviewDetails", body, what)
        else:
            raise ApplyError(f"no writer for {step.resource}")
