#!/usr/bin/env python3
"""INT-613: upload Önvizit's App Store metadata and screenshots, and create the version.

The script uses the App Store Connect API. It authenticates with an ES256 JWT
built from three environment variables, read when the live run starts:

    ASC_KEY_ID      the API key's id (the JWT ``kid``)
    ASC_ISSUER_ID   the team's issuer id (the JWT ``iss``)
    ASC_PRIVATE_KEY the key's PEM text (the .p8 file's contents)

**Dry run by default.** ``--dry-run`` (or no flag) validates everything
offline and touches no network:

* the metadata file (docs/release/app-store-metadata.yaml): each field's
  length limit, the no-accuracy-claim gate (invariant 20, the patterns of
  scripts/ci/claims_scan.sh through intake_platform.legal.claims), the
  device-function gate (intake_platform.store.listing), and one
  ``approval:human-legal`` entry for every listing string;
* the identity: the bundle id against apps/mobile/app.json, the app id
  against apps/mobile/eas.json, and the version string from app.json;
* every screenshot file: a PNG, the slot's exact pixel size, and no alpha.

It prints the plan of requests a live run would send, then every blocker that
stops a live run. A blocker is something only a human or a credential can
supply. The exit code is 0 when the files are valid, blockers or not, and 1
when anything is invalid.

**``--live`` is the owner's command.** No agent runs it. It refuses to start
while any blocker stands. Every request passes :func:`guard` first. The guard
refuses submitting for review, releasing, deleting anything, and the App
Review demo-account and contact fields (D39: the owner pastes the reviewer
sign-in, and no agent types it into Apple's service). The log carries field
names and HTTP statuses, never a value or a credential.

The INT-495 writer (scripts/store/asc_client.py on PR #860) edits the draft
and deliberately never creates a version. This script is the INT-613 step
that creates one. Once both are on main, they should share one transport and
one guard.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

REPO: Final[Path] = Path(__file__).resolve().parents[2]
METADATA: Final[Path] = REPO / "docs" / "release" / "app-store-metadata.yaml"
APP_JSON: Final[Path] = REPO / "apps" / "mobile" / "app.json"
EAS_JSON: Final[Path] = REPO / "apps" / "mobile" / "eas.json"

API: Final[str] = "https://api.appstoreconnect.apple.com"
AUDIENCE: Final[str] = "appstoreconnect-v1"
#: Apple caps a token at 20 minutes. A shorter one leaks less.
TOKEN_SECONDS: Final[int] = 15 * 60
ENV_KEYS: Final[tuple[str, str, str]] = ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_PRIVATE_KEY")

#: Character limits per localized field, from the INT-613 brief and Apple's
#: app-information page as INT-495 read it (PR #860, 2026-10-16).
CHAR_LIMITS: Final[Mapping[str, int]] = {
    "name": 30,
    "subtitle": 30,
    "description": 4000,
    "promotional_text": 170,
    "release_notes": 4000,
}
#: Keywords are limited in bytes, not characters (INT-495 §1). Turkish letters
#: take two bytes in UTF-8.
KEYWORD_BYTES: Final[int] = 100
TEXT_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "subtitle",
    "keywords",
    "description",
    "promotional_text",
    "release_notes",
)
URL_FIELDS: Final[tuple[str, ...]] = ("privacy_url", "support_url", "marketing_url")
#: The listing strings, each of which needs a recorded approval:human-legal.
LISTING_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "subtitle",
    "keywords",
    "description",
    "promotional_text",
)
#: metadata key -> (ASC resource, attribute)
ASC_ATTRIBUTE: Final[Mapping[str, tuple[str, str]]] = {
    "name": ("appInfoLocalizations", "name"),
    "subtitle": ("appInfoLocalizations", "subtitle"),
    "privacy_url": ("appInfoLocalizations", "privacyPolicyUrl"),
    "description": ("appStoreVersionLocalizations", "description"),
    "keywords": ("appStoreVersionLocalizations", "keywords"),
    "promotional_text": ("appStoreVersionLocalizations", "promotionalText"),
    "support_url": ("appStoreVersionLocalizations", "supportUrl"),
    "marketing_url": ("appStoreVersionLocalizations", "marketingUrl"),
    "release_notes": ("appStoreVersionLocalizations", "whatsNew"),
}
EDITABLE_STATES: Final[frozenset[str]] = frozenset(
    {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED"}
)


# --- errors ---------------------------------------------------------------------------


class MetadataError(ValueError):
    """The metadata file breaks its own contract."""


class CredentialsError(RuntimeError):
    """A credential is missing or unusable. The message names the variable only."""


class ForbiddenRequest(RuntimeError):
    """The guard refused a request before it left the machine."""


class ApiError(RuntimeError):
    """App Store Connect answered with an error status."""


# --- metadata -------------------------------------------------------------------------


@dataclass(frozen=True)
class Approval:
    approval: str
    legal_lane: str
    granted_by: str | None
    granted_on: str | None

    @property
    def granted(self) -> bool:
        return bool(self.granted_by) and bool(self.granted_on)


@dataclass(frozen=True)
class ScreenshotSlot:
    slot_id: str
    placement_type: str
    placement_group: str | None
    size: tuple[int, int]
    required: bool
    directory: str
    files: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class Metadata:
    app_identifier: str
    asc_app_id: str
    platform: str
    primary_locale: str
    locales: tuple[str, ...]
    primary_category: str
    copyright: str | None
    localized: Mapping[str, Mapping[str, str | None]]
    approvals: Mapping[str, Mapping[str, Approval]]
    screenshots: tuple[ScreenshotSlot, ...]
    legal_source: Mapping[str, Any]


def _str_or_none(value: Any, where: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise MetadataError(f"{where}: expected text or null")


def load_metadata(path: Path = METADATA) -> Metadata:
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(body, Mapping) or body.get("schema") != "intake/app-store-metadata@1":
        raise MetadataError(f"{path}: not an intake/app-store-metadata@1 document")
    locales = tuple(str(loc) for loc in body["locales"])
    localized: dict[str, dict[str, str | None]] = {}
    for key in (*TEXT_FIELDS, *URL_FIELDS):
        raw = body.get(key)
        if not isinstance(raw, Mapping):
            raise MetadataError(f"{key}: missing per-locale mapping")
        if set(raw) != set(locales):
            raise MetadataError(f"{key}: locales {sorted(raw)} differ from {sorted(locales)}")
        localized[key] = {str(loc): _str_or_none(raw[loc], f"{key}[{loc}]") for loc in locales}
    approvals: dict[str, dict[str, Approval]] = {}
    for key, per_locale in (body.get("approvals") or {}).items():
        approvals[str(key)] = {
            str(loc): Approval(
                approval=str(entry["approval"]),
                legal_lane=str(entry.get("legal_lane", "")),
                granted_by=entry.get("granted_by"),
                granted_on=None if entry.get("granted_on") is None else str(entry["granted_on"]),
            )
            for loc, entry in per_locale.items()
        }
    slots = tuple(
        ScreenshotSlot(
            slot_id=str(raw["id"]),
            placement_type=str(raw["placement_type"]),
            placement_group=raw["placement_group"],
            size=(int(raw["size"][0]), int(raw["size"][1])),
            required=bool(raw["required"]),
            directory=str(raw["dir"]),
            files={str(k): tuple(str(f) for f in v) for k, v in raw["files"].items()},
        )
        for raw in body.get("screenshots") or ()
    )
    return Metadata(
        app_identifier=str(body["app_identifier"]),
        asc_app_id=str(body["asc_app_id"]),
        platform=str(body["platform"]),
        primary_locale=str(body["primary_locale"]),
        locales=locales,
        primary_category=str(body["primary_category"]),
        copyright=_str_or_none(body.get("copyright"), "copyright"),
        localized=localized,
        approvals=approvals,
        screenshots=slots,
        legal_source=body.get("legal_source") or {},
    )


@dataclass(frozen=True)
class Finding:
    """``kind`` is ``invalid`` (fix the file) or ``blocked`` (a human or credential)."""

    kind: str
    where: str
    message: str

    def render(self) -> str:
        return f"{self.kind.upper():8} {self.where}: {self.message}"


def _claim_hits(text: str, where: str) -> list[str]:
    from intake_platform.legal import claims
    from intake_platform.store import listing

    hits = [
        f"performance claim [{hit.pattern}]"
        for hit in claims.scan_text(text, groups=listing.LISTING_GATE_GROUPS, path=where)
    ]
    hits.extend(
        f"device-function claim [{hit.pattern}]"
        for hit in listing.device_claim_hits(text, field=where)
    )
    return hits


def check_text(metadata: Metadata) -> list[Finding]:
    findings: list[Finding] = []
    for key in TEXT_FIELDS:
        for loc, text in metadata.localized[key].items():
            where = f"{key}[{loc}]"
            if text is None:
                continue
            if key == "keywords":
                size = len(text.encode("utf-8"))
                if size > KEYWORD_BYTES:
                    findings.append(
                        Finding("invalid", where, f"{size} bytes, limit {KEYWORD_BYTES}")
                    )
            elif len(text) > CHAR_LIMITS[key]:
                findings.append(
                    Finding("invalid", where, f"{len(text)} characters, limit {CHAR_LIMITS[key]}")
                )
            findings.extend(Finding("invalid", where, hit) for hit in _claim_hits(text, where))
    for key in LISTING_FIELDS:
        for loc in metadata.locales:
            where = f"{key}[{loc}]"
            if metadata.localized[key][loc] is None:
                findings.append(Finding("blocked", where, "no text; the legal lane supplies it"))
                continue
            entry = metadata.approvals.get(key, {}).get(loc)
            if entry is None or entry.approval != "human-legal":
                findings.append(Finding("invalid", where, "no approval:human-legal entry"))
            elif not entry.granted:
                findings.append(
                    Finding("blocked", where, "approval:human-legal not yet recorded by a human")
                )
    for key in ("privacy_url", "support_url"):
        for loc in metadata.locales:
            if metadata.localized[key][loc] is None:
                owner = "HB-L27" if key == "privacy_url" else "HB-L21 (e)"
                findings.append(Finding("blocked", f"{key}[{loc}]", f"no URL yet ({owner})"))
    if metadata.copyright is None:
        findings.append(Finding("blocked", "copyright", "no seller legal entity yet (HB-L21 (a))"))
    return findings


def check_identity(metadata: Metadata, app_json: Path, eas_json: Path) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    expo = json.loads(app_json.read_text(encoding="utf-8"))["expo"]
    eas = json.loads(eas_json.read_text(encoding="utf-8"))
    bundle = expo.get("ios", {}).get("bundleIdentifier")
    if bundle != metadata.app_identifier:
        findings.append(
            Finding("invalid", "app_identifier", f"app.json bundleIdentifier is {bundle!r}")
        )
    asc_app_id = eas.get("submit", {}).get("production", {}).get("ios", {}).get("ascAppId")
    if str(asc_app_id) != metadata.asc_app_id:
        findings.append(Finding("invalid", "asc_app_id", f"eas.json ascAppId is {asc_app_id!r}"))
    version = str(expo.get("version", ""))
    if not re.fullmatch(r"\d+(\.\d+){0,2}", version):
        findings.append(Finding("invalid", "version", f"app.json version {version!r}"))
    if eas.get("cli", {}).get("appVersionSource") != "remote":
        findings.append(
            Finding("invalid", "build_number", "eas.json appVersionSource is not 'remote'")
        )
    if not eas.get("build", {}).get("production", {}).get("autoIncrement"):
        findings.append(Finding("invalid", "build_number", "production autoIncrement is off"))
    return version, findings


# --- screenshots ----------------------------------------------------------------------

_PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
_ALPHA_COLOUR_TYPES: Final[frozenset[int]] = frozenset({4, 6})


def png_facts(data: bytes) -> tuple[int, int, bool] | None:
    """(width, height, has alpha) from the PNG header and chunk types, or None."""
    if not data.startswith(_PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height, _depth, colour = struct.unpack(">IIBB", data[16:26])
    alpha = colour in _ALPHA_COLOUR_TYPES
    offset = 8
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        if kind == b"tRNS":
            alpha = True
        if kind == b"IEND":
            break
        offset += 12 + length
    return width, height, alpha


def check_screenshots(metadata: Metadata, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for slot in metadata.screenshots:
        for loc, names in slot.files.items():
            where = f"screenshots.{slot.slot_id}[{loc}]"
            if not names:
                if slot.required:
                    findings.append(
                        Finding("blocked", where, "no files; INT-502's framed export (PR #1009)")
                    )
                continue
            if len(names) > 10:
                findings.append(Finding("invalid", where, f"{len(names)} files, limit 10"))
            for name in names:
                path = repo / slot.directory / loc / name
                if not path.is_file():
                    findings.append(Finding("invalid", where, f"{name}: no such file"))
                    continue
                facts = png_facts(path.read_bytes())
                if facts is None:
                    findings.append(Finding("invalid", where, f"{name}: not a PNG"))
                    continue
                width, height, alpha = facts
                if (width, height) != slot.size:
                    findings.append(
                        Finding(
                            "invalid",
                            where,
                            f"{name}: {width}x{height}, slot takes {slot.size[0]}x{slot.size[1]}",
                        )
                    )
                if alpha:
                    findings.append(Finding("invalid", where, f"{name}: has an alpha channel"))
    return findings


def validate(
    repo: Path = REPO, metadata_path: Path | None = None
) -> tuple[Metadata, str, list[Finding]]:
    metadata = load_metadata(metadata_path or repo / "docs" / "release" / "app-store-metadata.yaml")
    version, identity = check_identity(
        metadata, repo / "apps" / "mobile" / "app.json", repo / "apps" / "mobile" / "eas.json"
    )
    findings = [*check_text(metadata), *identity, *check_screenshots(metadata, repo)]
    return metadata, version, findings


# --- credentials and token ------------------------------------------------------------


@dataclass(frozen=True)
class Credentials:
    key_id: str = field(repr=False)
    issuer_id: str = field(repr=False)
    private_key: ec.EllipticCurvePrivateKey = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Credentials:
        missing = [name for name in ENV_KEYS if not environ.get(name)]
        if missing:
            raise CredentialsError("missing environment variable(s): " + ", ".join(missing))
        pem = environ["ASC_PRIVATE_KEY"].replace("\\n", "\n").encode("ascii")
        try:
            key = serialization.load_pem_private_key(pem, password=None)
        except (ValueError, TypeError) as exc:
            raise CredentialsError("ASC_PRIVATE_KEY is not a PEM private key") from exc
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
            raise CredentialsError("ASC_PRIVATE_KEY is not a P-256 key")
        return cls(environ["ASC_KEY_ID"], environ["ASC_ISSUER_ID"], key)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_token(credentials: Credentials, *, now: float) -> str:
    """An ES256 JWT for the App Store Connect API (raw r||s signature)."""
    header = {"alg": "ES256", "kid": credentials.key_id, "typ": "JWT"}
    payload = {
        "iss": credentials.issuer_id,
        "iat": int(now),
        "exp": int(now) + TOKEN_SECONDS,
        "aud": AUDIENCE,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    der = credentials.private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return signing_input + "." + _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


# --- the guard ------------------------------------------------------------------------

_ID = r"[^/?]+"
_ALLOWED: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("GET", re.compile(r"/v1/apps\?filter\[bundleId\]=[A-Za-z0-9.\-]+")),
    ("GET", re.compile(rf"/v1/apps/{_ID}/appStoreVersions(\?.*)?")),
    ("POST", re.compile(r"/v1/appStoreVersions")),
    ("PATCH", re.compile(rf"/v1/appStoreVersions/{_ID}")),
    ("GET", re.compile(rf"/v1/appStoreVersions/{_ID}/appStoreVersionLocalizations")),
    ("POST", re.compile(r"/v1/appStoreVersionLocalizations")),
    ("PATCH", re.compile(rf"/v1/appStoreVersionLocalizations/{_ID}")),
    ("GET", re.compile(rf"/v1/apps/{_ID}/appInfos")),
    ("GET", re.compile(rf"/v1/appInfos/{_ID}/appInfoLocalizations")),
    ("POST", re.compile(r"/v1/appInfoLocalizations")),
    ("PATCH", re.compile(rf"/v1/appInfoLocalizations/{_ID}")),
    ("GET", re.compile(rf"/v1/apps/{_ID}/assetLibrary")),
    ("GET", re.compile(r"/v1/appAssetLibraryRefData")),
    ("POST", re.compile(r"/v1/appAssetLibraryImages")),
    ("PATCH", re.compile(rf"/v1/appAssetLibraryImages/{_ID}")),
    ("POST", re.compile(r"/v1/appAssetLibraryPlacements")),
)
#: Never sent, whatever the allow-list says: D39 keeps the reviewer sign-in in
#: the owner's hands, and release decisions stay with the owner in the console.
_FORBIDDEN_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {
        "demoAccountName",
        "demoAccountPassword",
        "demoAccountRequired",
        "contactEmail",
        "contactFirstName",
        "contactLastName",
        "contactPhone",
        "notes",
        "releaseType",
        "earliestReleaseDate",
        "usesIdfa",
    }
)
_VERSION_ATTRIBUTES: Final[frozenset[str]] = frozenset({"platform", "versionString", "copyright"})


def guard(method: str, path: str, body: Mapping[str, Any] | None) -> None:
    """Refuse anything this script has no business sending."""
    if not any(m == method and pattern.fullmatch(path) for m, pattern in _ALLOWED):
        raise ForbiddenRequest(f"{method} {path.split('?')[0]} is not on the allow-list")
    attributes = set(((body or {}).get("data") or {}).get("attributes") or {})
    forbidden = attributes & _FORBIDDEN_ATTRIBUTES
    if forbidden:
        raise ForbiddenRequest(f"{method} {path}: refused attribute(s) {sorted(forbidden)}")
    if "appStoreVersions" in path and method in {"POST", "PATCH"}:
        extra = attributes - _VERSION_ATTRIBUTES
        if extra:
            raise ForbiddenRequest(f"{method} {path}: version attribute(s) {sorted(extra)}")


# --- transport ------------------------------------------------------------------------


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]: ...


class HttpTransport:
    """urllib over HTTPS. Used only by --live."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        if not url.startswith("https://"):
            raise ForbiddenRequest("only https is allowed")
        req = urllib.request.Request(  # noqa: S310 - https checked above
            url, data=body, method=method, headers=dict(headers)
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310 - https only
                return int(response.status), bytes(response.read())
        except urllib.error.HTTPError as exc:
            return int(exc.code), bytes(exc.read())


@dataclass
class Client:
    transport: Transport
    credentials: Credentials
    clock: Callable[[], float] = time.time
    log: Callable[[str], None] = print
    _token: str | None = None
    _token_at: float = 0.0

    def _bearer(self) -> str:
        now = self.clock()
        if self._token is None or now - self._token_at > TOKEN_SECONDS - 60:
            self._token = make_token(self.credentials, now=now)
            self._token_at = now
        return self._token

    def call(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        guard(method, path, body)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._bearer()}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        status, raw = self.transport.request(method, API + path, headers=headers, body=payload)
        fields = sorted(((body or {}).get("data") or {}).get("attributes") or {})
        self.log(f"{method} {path.split('?')[0]} -> {status} fields={','.join(fields) or '-'}")
        if status >= 400:
            raise ApiError(f"{method} {path.split('?')[0]} answered {status}")
        return json.loads(raw) if raw else {}

    def upload(self, operation: Mapping[str, Any], chunk: bytes) -> None:
        """One upload operation from a reserve response (Apple's own URL and headers)."""
        url = str(operation["url"])
        if not url.startswith("https://"):
            raise ForbiddenRequest("an upload operation must be https")
        headers = {str(h["name"]): str(h["value"]) for h in operation.get("requestHeaders", [])}
        status, _ = self.transport.request(
            str(operation["method"]), url, headers=headers, body=chunk
        )
        self.log(f"UPLOAD part offset={operation.get('offset', 0)} -> {status}")
        if status >= 400:
            raise ApiError(f"upload part answered {status}")


# --- the plan and its execution -------------------------------------------------------


def plan(metadata: Metadata, version: str) -> list[str]:
    """What a live run would do, in order, in words. Offline."""
    steps = [
        f"GET /v1/apps?filter[bundleId]={metadata.app_identifier}"
        f" -> expect id {metadata.asc_app_id}",
        "GET /v1/apps/{app}/appStoreVersions"
        f"?filter[platform]=IOS&filter[versionString]={version}",
        f"POST /v1/appStoreVersions (platform IOS, versionString {version}) when none exists",
    ]
    for loc in metadata.locales:
        version_fields = [
            ASC_ATTRIBUTE[k][1]
            for k in ASC_ATTRIBUTE
            if ASC_ATTRIBUTE[k][0] == "appStoreVersionLocalizations"
            and metadata.localized[k][loc] is not None
        ]
        info_fields = [
            ASC_ATTRIBUTE[k][1]
            for k in ASC_ATTRIBUTE
            if ASC_ATTRIBUTE[k][0] == "appInfoLocalizations"
            and metadata.localized[k][loc] is not None
        ]
        steps.append(f"PATCH|POST appStoreVersionLocalizations[{loc}]: {', '.join(version_fields)}")
        steps.append(f"PATCH|POST appInfoLocalizations[{loc}]: {', '.join(info_fields)}")
    for slot in metadata.screenshots:
        for loc, names in slot.files.items():
            group = slot.placement_group or "<from appAssetLibraryRefData>"
            steps.append(
                f"asset library: {len(names)} x {slot.placement_type} {group} [{loc}] "
                f"{slot.size[0]}x{slot.size[1]}"
            )
    steps.append("never: review submission, release, demo account, review notes (D39)")
    return steps


def _one(data: Any, what: str) -> Mapping[str, Any]:
    items = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(items, list) or len(items) != 1:
        raise ApiError(f"expected exactly one {what}")
    item: Mapping[str, Any] = items[0]
    return item


def _locale_ids(data: Any) -> dict[str, str]:
    return {str(item["attributes"]["locale"]): str(item["id"]) for item in (data.get("data") or [])}


def _upsert_localizations(
    client: Client,
    *,
    resource: str,
    parent_type: str,
    parent_rel: str,
    parent_id: str,
    existing: Mapping[str, str],
    metadata: Metadata,
) -> None:
    for loc in metadata.locales:
        attributes = {
            ASC_ATTRIBUTE[key][1]: text
            for key in ASC_ATTRIBUTE
            if ASC_ATTRIBUTE[key][0] == resource
            and (text := metadata.localized[key][loc]) is not None
        }
        if loc in existing:
            client.call(
                "PATCH",
                f"/v1/{resource}/{existing[loc]}",
                {"data": {"type": resource, "id": existing[loc], "attributes": attributes}},
            )
        else:
            client.call(
                "POST",
                f"/v1/{resource}",
                {
                    "data": {
                        "type": resource,
                        "attributes": {"locale": loc, **attributes},
                        "relationships": {
                            parent_rel: {"data": {"type": parent_type, "id": parent_id}}
                        },
                    }
                },
            )


def _placement_group(client: Client, slot: ScreenshotSlot) -> str:
    if slot.placement_group:
        return slot.placement_group
    data = client.call("GET", "/v1/appAssetLibraryRefData")
    width, height = slot.size
    for item in data.get("data") or []:
        attrs = item.get("attributes") or {}
        sizes = {(int(w), int(h)) for w, h in attrs.get("imageSizes") or []}
        if attrs.get("placementType") == slot.placement_type and (width, height) in sizes:
            return str(attrs["placementGroup"])
    raise ApiError(f"no placement group for {slot.slot_id} in appAssetLibraryRefData")


def _upload_slot(
    client: Client,
    slot: ScreenshotSlot,
    *,
    library_id: str,
    localization_ids: Mapping[str, str],
    repo: Path,
) -> None:
    group = _placement_group(client, slot)
    for loc, names in slot.files.items():
        for name in names:
            data = (repo / slot.directory / loc / name).read_bytes()
            reserved = client.call(
                "POST",
                "/v1/appAssetLibraryImages",
                {
                    "data": {
                        "type": "appAssetLibraryImages",
                        "attributes": {"fileName": name, "fileSize": len(data)},
                        "relationships": {
                            "assetLibrary": {
                                "data": {"type": "appAssetLibraries", "id": library_id}
                            }
                        },
                    }
                },
            )
            image = reserved["data"]
            for operation in image["attributes"].get("uploadOperations") or []:
                offset = int(operation.get("offset", 0))
                length = int(operation.get("length", len(data)))
                client.upload(operation, data[offset : offset + length])
            client.call(
                "PATCH",
                f"/v1/appAssetLibraryImages/{image['id']}",
                {
                    "data": {
                        "type": "appAssetLibraryImages",
                        "id": image["id"],
                        "attributes": {
                            "uploaded": True,
                            "sourceFileChecksum": hashlib.md5(  # noqa: S324 - Apple's checksum
                                data, usedforsecurity=False
                            ).hexdigest(),
                        },
                    }
                },
            )
            client.call(
                "POST",
                "/v1/appAssetLibraryPlacements",
                {
                    "data": {
                        "type": "appAssetLibraryPlacements",
                        "attributes": {
                            "placementType": slot.placement_type,
                            "placementGroup": group,
                        },
                        "relationships": {
                            "image": {"data": {"type": "appAssetLibraryImages", "id": image["id"]}},
                            "appStoreVersionLocalization": {
                                "data": {
                                    "type": "appStoreVersionLocalizations",
                                    "id": localization_ids[loc],
                                }
                            },
                        },
                    }
                },
            )


def apply(client: Client, metadata: Metadata, version: str, repo: Path = REPO) -> str:
    """The live run. Returns the App Store version's id. Never submits."""
    app = _one(client.call("GET", f"/v1/apps?filter[bundleId]={metadata.app_identifier}"), "app")
    if str(app["id"]) != metadata.asc_app_id:
        raise ApiError("the bundle id resolves to a different app than eas.json names")
    app_id = str(app["id"])
    versions = (
        client.call(
            "GET",
            f"/v1/apps/{app_id}/appStoreVersions?filter[platform]=IOS&filter[versionString]={version}",
        ).get("data")
        or []
    )
    if versions:
        current = versions[0]
        state = str(current["attributes"].get("appStoreState", ""))
        if state not in EDITABLE_STATES:
            raise ApiError(f"version {version} is in state {state}, which is not editable")
        version_id = str(current["id"])
    else:
        attributes: dict[str, Any] = {"platform": metadata.platform, "versionString": version}
        if metadata.copyright is not None:
            attributes["copyright"] = metadata.copyright
        created = client.call(
            "POST",
            "/v1/appStoreVersions",
            {
                "data": {
                    "type": "appStoreVersions",
                    "attributes": attributes,
                    "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
                }
            },
        )
        version_id = str(created["data"]["id"])
    _upsert_localizations(
        client,
        resource="appStoreVersionLocalizations",
        parent_type="appStoreVersions",
        parent_rel="appStoreVersion",
        parent_id=version_id,
        existing=_locale_ids(
            client.call("GET", f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")
        ),
        metadata=metadata,
    )
    infos = client.call("GET", f"/v1/apps/{app_id}/appInfos").get("data") or []
    editable = [i for i in infos if str(i["attributes"].get("state", "")) in EDITABLE_STATES]
    if len(editable) != 1:
        raise ApiError("expected exactly one editable appInfo")
    info_id = str(editable[0]["id"])
    _upsert_localizations(
        client,
        resource="appInfoLocalizations",
        parent_type="appInfos",
        parent_rel="appInfo",
        parent_id=info_id,
        existing=_locale_ids(client.call("GET", f"/v1/appInfos/{info_id}/appInfoLocalizations")),
        metadata=metadata,
    )
    if any(names for slot in metadata.screenshots for names in slot.files.values()):
        library = client.call("GET", f"/v1/apps/{app_id}/assetLibrary")["data"]
        localization_ids = _locale_ids(
            client.call("GET", f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")
        )
        for slot in metadata.screenshots:
            if any(slot.files.values()):
                _upload_slot(
                    client,
                    slot,
                    library_id=str(library["id"]),
                    localization_ids=localization_ids,
                    repo=repo,
                )
    return version_id


# --- command line ---------------------------------------------------------------------


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    repo: Path = REPO,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate offline (the default)")
    mode.add_argument(
        "--live", action="store_true", help="the owner's run against App Store Connect"
    )
    parser.add_argument("--metadata", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        metadata, version, findings = validate(repo, args.metadata)
    except (MetadataError, KeyError, TypeError) as exc:
        print(f"INVALID  metadata: {exc}")
        return 1
    invalid = [f for f in findings if f.kind == "invalid"]
    blocked = [f for f in findings if f.kind == "blocked"]
    print(f"app {metadata.app_identifier} ({metadata.asc_app_id}), version {version}")
    print("plan:")
    for step in plan(metadata, version):
        print(f"  {step}")
    for finding in findings:
        print(finding.render())
    print(f"summary: {len(invalid)} invalid, {len(blocked)} blocked")
    if not args.live:
        return 1 if invalid else 0
    if invalid or blocked:
        print("refused: --live needs zero invalid and zero blocked findings")
        return 3
    try:
        credentials = Credentials.from_env(os.environ if environ is None else environ)
    except CredentialsError as exc:
        print(f"refused: {exc}")
        return 3
    client = Client(transport or HttpTransport(), credentials)
    try:
        version_id = apply(client, metadata, version, repo)
    except (ApiError, ForbiddenRequest) as exc:
        print(f"stopped: {exc}")
        return 2
    print(f"done: version {version} ({version_id}) holds the metadata; nothing was submitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
