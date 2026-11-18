"""INT-613: scripts/release/asc_submit.py, offline only.

No test here reaches App Store Connect. The live path runs against a fixture
transport that replays tests/fixtures/release/asc/first_version.json and
asserts each request in order. The fixture is synthetic: it is written to
Apple's JSON:API response shape, and no request was sent to make it.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import struct
import sys
import zlib
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "release" / "asc" / "first_version.json"


def _load() -> ModuleType:
    path = REPO / "scripts" / "release" / "asc_submit.py"
    spec = importlib.util.spec_from_file_location("asc_submit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


A = _load()


# --- helpers ----------------------------------------------------------------------------


def _png(width: int, height: int, *, alpha: bool = False) -> bytes:
    colour = 6 if alpha else 2
    row = b"\x00" + (b"\xfa\xf8\xf4\xff" if alpha else b"\xfa\xf8\xf4") * width

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(row * height, 9))
        + chunk(b"IEND", b"")
    )


def _repo_copy(tmp_path: Path, edit: Any = None) -> Path:
    """A tree holding the real metadata, app.json and eas.json, editable."""
    (tmp_path / "docs" / "release").mkdir(parents=True)
    (tmp_path / "apps" / "mobile").mkdir(parents=True)
    body = yaml.safe_load((REPO / "docs/release/app-store-metadata.yaml").read_text("utf-8"))
    if edit is not None:
        edit(body)
    (tmp_path / "docs/release/app-store-metadata.yaml").write_text(
        yaml.safe_dump(body, allow_unicode=True, sort_keys=False), "utf-8"
    )
    for name in ("app.json", "eas.json"):
        (tmp_path / "apps/mobile" / name).write_text(
            (REPO / "apps/mobile" / name).read_text("utf-8"), "utf-8"
        )
    return tmp_path


def _findings(repo: Path) -> list[Any]:
    _, _, findings = A.validate(repo)
    return findings


def _invalid(repo: Path) -> list[str]:
    return [f.render() for f in _findings(repo) if f.kind == "invalid"]


def _grant_all(body: dict[str, Any]) -> None:
    for per_locale in body["approvals"].values():
        for entry in per_locale.values():
            entry["granted_by"] = "Named Counsel (fixture)"
            entry["granted_on"] = "2026-11-17"


def _key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _creds(key: ec.EllipticCurvePrivateKey | None = None) -> Any:
    return A.Credentials("KEYID12345", "issuer-fixture", key or _key())


# --- the committed metadata -------------------------------------------------------------


def test_the_committed_metadata_dry_runs_clean(capsys: pytest.CaptureFixture[str]) -> None:
    assert A.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "0 invalid" in out
    assert "never: review submission" in out


def test_the_committed_metadata_is_blocked_only_on_humans_and_open_prs() -> None:
    _, version, findings = A.validate(REPO)
    assert version == json.loads((REPO / "apps/mobile/app.json").read_text())["expo"]["version"]
    blocked = {f.where for f in findings if f.kind == "blocked"}
    assert {"copyright", "privacy_url[tr]", "support_url[tr]"} <= blocked
    assert {f"{k}[{loc}]" for k in A.LISTING_FIELDS for loc in ("tr", "en-US")} <= blocked
    assert "screenshots.iphone-medium[tr]" in blocked


# --- near misses on the limits and gates ------------------------------------------------


def test_near_miss_name_over_30_characters(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["name"]["tr"] = "Ö" * 31

    assert any("name[tr]: 31 characters" in f for f in _invalid(_repo_copy(tmp_path, edit)))


def test_thirty_characters_is_within_the_name_limit(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["name"]["tr"] = "Ö" * 30

    assert not _invalid(_repo_copy(tmp_path, edit))


def test_near_miss_keywords_are_counted_in_bytes(tmp_path: Path) -> None:
    def over(body: dict[str, Any]) -> None:
        body["keywords"]["tr"] = "ş" * 50 + "a"  # 50 characters of 2 bytes, plus one: 101 bytes

    def at(body: dict[str, Any]) -> None:
        body["keywords"]["tr"] = "ş" * 50  # 100 bytes

    assert any("101 bytes" in f for f in _invalid(_repo_copy(tmp_path / "o", over)))
    assert not _invalid(_repo_copy(tmp_path / "a", at))


def test_near_miss_promotional_text_over_170(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["promotional_text"]["en-US"] = "a" * 171

    assert any("171 characters" in f for f in _invalid(_repo_copy(tmp_path, edit)))


@pytest.mark.parametrize(
    "text",
    [
        "Şikâyetlerinizi %95 doğrulukla anlar.",
        "Clinically proven accuracy for your visit.",
        "High sensitivity for urgent symptoms.",
    ],
)
def test_near_miss_a_performance_claim_is_invalid(tmp_path: Path, text: str) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["promotional_text"]["tr"] = text

    assert any("performance claim" in f for f in _invalid(_repo_copy(tmp_path, edit)))


def test_near_miss_a_device_function_claim_is_invalid(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["subtitle"]["tr"] = "Akıllı triyaj"

    assert any("device-function claim" in f for f in _invalid(_repo_copy(tmp_path, edit)))


def test_the_disclaimer_is_not_a_device_claim() -> None:
    """The served description denies diagnosis; the gate must leave a denial alone."""
    metadata = A.load_metadata()
    assert "tanı koymaz" in (metadata.localized["description"]["tr"] or "")
    assert not [f for f in A.check_text(metadata) if f.kind == "invalid"]


def test_near_miss_a_listing_string_without_an_approval_entry(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        del body["approvals"]["subtitle"]["en-US"]

    assert any("subtitle[en-US]: no approval" in f for f in _invalid(_repo_copy(tmp_path, edit)))


def test_near_miss_the_identity_must_match_app_and_eas_json(tmp_path: Path) -> None:
    def edit(body: dict[str, Any]) -> None:
        body["app_identifier"] = "com.example.other"
        body["asc_app_id"] = "1"

    invalid = _invalid(_repo_copy(tmp_path, edit))
    assert any(f.startswith("INVALID  app_identifier") for f in invalid)
    assert any(f.startswith("INVALID  asc_app_id") for f in invalid)


# --- screenshots ------------------------------------------------------------------------


def _with_shot(tmp_path: Path, name: str, data: bytes, slot: str = "iphone-6.5") -> Path:
    def edit(body: dict[str, Any]) -> None:
        for entry in body["screenshots"]:
            if entry["id"] == slot:
                entry["files"]["tr"] = [name]

    repo = _repo_copy(tmp_path, edit)
    folder = repo / f"docs/release/screenshots/{slot}/tr"
    folder.mkdir(parents=True)
    (folder / name).write_bytes(data)
    return repo


def test_a_screenshot_of_the_exact_size_without_alpha_passes(tmp_path: Path) -> None:
    repo = _with_shot(tmp_path, "01-giris.png", _png(1284, 2778))
    assert not _invalid(repo)
    assert "screenshots.iphone-6.5[tr]" not in {f.where for f in _findings(repo)}


def test_near_miss_a_screenshot_one_pixel_off(tmp_path: Path) -> None:
    repo = _with_shot(tmp_path, "01-giris.png", _png(1284, 2777))
    assert any("1284x2777" in f for f in _invalid(repo))


def test_near_miss_a_screenshot_with_alpha(tmp_path: Path) -> None:
    """INT-502's raw captures carry the simulator's alpha mask: not uploadable as they are."""
    repo = _with_shot(tmp_path, "01-giris.png", _png(1320, 2868, alpha=True), slot="iphone-6.9")
    assert any("alpha" in f for f in _invalid(repo))


# --- token and credentials --------------------------------------------------------------


def _b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_the_token_is_an_es256_jwt_apple_accepts_in_shape() -> None:
    key = _key()
    token = A.make_token(_creds(key), now=1_800_000_000)
    head, body, sig = token.split(".")
    assert json.loads(_b64d(head)) == {"alg": "ES256", "kid": "KEYID12345", "typ": "JWT"}
    claims = json.loads(_b64d(body))
    assert claims["aud"] == "appstoreconnect-v1" and claims["iss"] == "issuer-fixture"
    assert 0 < claims["exp"] - claims["iat"] <= 20 * 60
    raw = _b64d(sig)
    assert len(raw) == 64
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))


def test_credentials_name_missing_variables_and_never_show_values() -> None:
    with pytest.raises(A.CredentialsError, match="ASC_ISSUER_ID, ASC_PRIVATE_KEY"):
        A.Credentials.from_env({"ASC_KEY_ID": "KEYID12345"})
    pem = (
        _key()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    creds = A.Credentials.from_env(
        {"ASC_KEY_ID": "KEYID12345", "ASC_ISSUER_ID": "issuer-fixture", "ASC_PRIVATE_KEY": pem}
    )
    assert "KEYID12345" not in repr(creds) and "issuer-fixture" not in repr(creds)


def test_near_miss_a_non_p256_key_is_refused() -> None:
    pem = (
        ec.generate_private_key(ec.SECP384R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    with pytest.raises(A.CredentialsError, match="P-256"):
        A.Credentials.from_env({"ASC_KEY_ID": "k", "ASC_ISSUER_ID": "i", "ASC_PRIVATE_KEY": pem})


# --- the guard --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/v1/reviewSubmissions", {"data": {"attributes": {"platform": "IOS"}}}),
        ("POST", "/v1/appStoreVersionSubmissions", None),
        ("DELETE", "/v1/appStoreVersions/ver-0001", None),
        ("POST", "/v1/appStoreReviewDetails", {"data": {"attributes": {"notes": "x"}}}),
        (
            "PATCH",
            "/v1/appStoreVersionLocalizations/vloc-tr",
            {"data": {"attributes": {"demoAccountPassword": "x"}}},
        ),
        ("PATCH", "/v1/appStoreVersions/ver-0001", {"data": {"attributes": {"releaseType": "x"}}}),
        ("PATCH", "/v1/apps/6814005465", {"data": {"attributes": {"contentRightsDeclaration": 1}}}),
    ],
)
def test_the_guard_refuses_what_this_script_never_sends(
    method: str, path: str, body: Mapping[str, Any] | None
) -> None:
    with pytest.raises(A.ForbiddenRequest):
        A.guard(method, path, body)


def test_the_guard_admits_creating_the_version() -> None:
    A.guard(
        "POST",
        "/v1/appStoreVersions",
        {"data": {"attributes": {"platform": "IOS", "versionString": "0.1.0"}}},
    )


# --- the live path, on recorded fixtures ------------------------------------------------


class FixtureTransport:
    def __init__(self, exchanges: list[dict[str, Any]]) -> None:
        self._exchanges = list(exchanges)
        self.sent: list[tuple[str, str, Any]] = []

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str], body: bytes | None
    ) -> tuple[int, bytes]:
        assert self._exchanges, f"unexpected request {method} {url}"
        expected = self._exchanges.pop(0)
        want = expected.get("url") or A.API + expected["path"]
        assert (method, url) == (expected["method"], want)
        if url.startswith(A.API):
            assert headers["Authorization"].startswith("Bearer ")
        parsed = json.loads(body) if body and url.startswith(A.API) else body
        self.sent.append((method, url, parsed))
        raw = b"" if expected["body"] is None else json.dumps(expected["body"]).encode()
        return int(expected["status"]), raw

    @property
    def done(self) -> bool:
        return not self._exchanges


def _fixture() -> list[dict[str, Any]]:
    return copy.deepcopy(json.loads(FIXTURE.read_text("utf-8"))["exchanges"])


def test_apply_creates_the_version_and_writes_every_locale(tmp_path: Path) -> None:
    repo = _with_shot(tmp_path, "01-giris.png", _png(1284, 2778))
    metadata, version, _ = A.validate(repo)
    transport = FixtureTransport(_fixture())
    lines: list[str] = []
    client = A.Client(transport, _creds(), clock=lambda: 1_800_000_000.0, log=lines.append)

    assert A.apply(client, metadata, version, repo) == "ver-0001"
    assert transport.done

    by_call = {(m, u.removeprefix(A.API)): b for m, u, b in transport.sent}
    created = by_call[("POST", "/v1/appStoreVersions")]["data"]["attributes"]
    assert created == {"platform": "IOS", "versionString": version}
    tr = by_call[("PATCH", "/v1/appStoreVersionLocalizations/vloc-tr")]["data"]["attributes"]
    assert tr["keywords"] == metadata.localized["keywords"]["tr"]
    assert set(tr) == {"description", "keywords", "promotionalText"}
    en = by_call[("POST", "/v1/appStoreVersionLocalizations")]["data"]
    assert en["attributes"]["locale"] == "en-US"
    assert en["relationships"]["appStoreVersion"]["data"]["id"] == "ver-0001"
    info = by_call[("PATCH", "/v1/appInfoLocalizations/iloc-tr")]["data"]["attributes"]
    assert info == {"name": "Önvizit", "subtitle": metadata.localized["subtitle"]["tr"]}
    placement = by_call[("POST", "/v1/appAssetLibraryPlacements")]["data"]
    assert placement["attributes"]["placementGroup"] == "SYNTHETIC_FACE_ID_LARGE_GROUP"
    parts = [b for m, u, b in transport.sent if m == "PUT"]
    assert (
        b"".join(parts)
        == (repo / "docs/release/screenshots/iphone-6.5/tr/01-giris.png").read_bytes()
    )

    log = "\n".join(lines)
    assert "Önvizit" not in log and "Bearer" not in log and "KEYID12345" not in log
    assert "fields=description,keywords,promotionalText" in log


def test_near_miss_apply_stops_on_a_version_that_is_not_editable(tmp_path: Path) -> None:
    exchanges = _fixture()[:2]
    exchanges[1]["body"] = {
        "data": [
            {
                "type": "appStoreVersions",
                "id": "ver-0001",
                "attributes": {"versionString": "0.1.0", "appStoreState": "WAITING_FOR_REVIEW"},
            }
        ]
    }
    metadata, version, _ = A.validate(REPO)
    client = A.Client(FixtureTransport(exchanges), _creds(), log=lambda _: None)
    with pytest.raises(A.ApiError, match="WAITING_FOR_REVIEW"):
        A.apply(client, metadata, version, REPO)


def test_near_miss_apply_stops_when_the_bundle_resolves_to_another_app() -> None:
    exchanges = _fixture()[:1]
    exchanges[0]["body"]["data"][0]["id"] = "999"
    metadata, version, _ = A.validate(REPO)
    client = A.Client(FixtureTransport(exchanges), _creds(), log=lambda _: None)
    with pytest.raises(A.ApiError, match="different app"):
        A.apply(client, metadata, version, REPO)


def test_live_refuses_while_any_blocker_stands(capsys: pytest.CaptureFixture[str]) -> None:
    transport = FixtureTransport([])
    assert A.main(["--live"], environ={}, transport=transport) == 3
    assert "refused" in capsys.readouterr().out
    assert transport.sent == []


def test_live_with_every_blocker_cleared_still_needs_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def edit(body: dict[str, Any]) -> None:
        _grant_all(body)
        body["copyright"] = "2026 Fixture Seller"
        for key in ("privacy_url", "support_url"):
            body[key] = {"tr": "https://fixture.invalid/p", "en-US": "https://fixture.invalid/p"}

    repo = _with_shot(tmp_path, "01-giris.png", _png(1206, 2622), slot="iphone-medium")
    body = yaml.safe_load((repo / "docs/release/app-store-metadata.yaml").read_text("utf-8"))
    edit(body)
    sizes = {"iphone-6.9": (1320, 2868), "iphone-6.5": (1284, 2778)}
    for entry in body["screenshots"]:
        if entry["id"] in sizes:
            entry["files"]["tr"] = ["01-giris.png"]
            folder = repo / entry["dir"] / "tr"
            folder.mkdir(parents=True)
            (folder / "01-giris.png").write_bytes(_png(*sizes[entry["id"]]))
    (repo / "docs/release/app-store-metadata.yaml").write_text(
        yaml.safe_dump(body, allow_unicode=True, sort_keys=False), "utf-8"
    )
    _, _, findings = A.validate(repo)
    assert not findings, [f.render() for f in findings]

    transport = FixtureTransport([])
    assert A.main(["--live"], environ={}, transport=transport, repo=repo) == 3
    assert "ASC_KEY_ID, ASC_ISSUER_ID, ASC_PRIVATE_KEY" in capsys.readouterr().out
    assert transport.sent == []
