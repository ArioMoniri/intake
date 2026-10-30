"""INT-495 — the App Store Connect draft writer, dry-run by default.

GitHub #846. Fill the Önvizit App Store listing in App Store Connect as an
**editable draft only**, from repo sources, through the ASC API, with the
owner's existing credentials read at run time and never copied anywhere.

What this suite pins, in the order the harm would arrive:

1. **The plan comes from served copy only.** ``scripts/store/asc_plan.py``
   reads ``eas_metadata.render_for_repo`` — the same hash-bound, gated render
   that writes ``store.config.json`` — plus the submission answers the EAS
   schema cannot carry (the live age-rating keys, the content-rights answer).
   Every field the plan cannot fill is listed as blocked, with its owner.
2. **The dry run prints field names, never values,** and needs no network and
   no credentials.
3. **Nothing outside the draft is ever touched.** Every request passes an
   allow-list; submission, release, pricing, availability, agreements and the
   reviewer's sign-in fields are refused before a byte leaves (near misses).
4. **The token is ES256 and short-lived,** built from the key file named in
   the owner's eas.json at run time; a test key is generated at run time, so no
   key-shaped literal sits in the tree.
5. **Assets are validated against the specs read on 2026-10-16** and their
   upload waits for the capture step; the plan says so instead of skipping.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from intake_platform.store import eas_metadata as eas
from store_drafts_harness import REPO, promote

STORE_SCRIPTS = REPO / "scripts" / "store"
sys.path.insert(0, str(STORE_SCRIPTS))

import asc_assets  # noqa: E402
import asc_client  # noqa: E402
import asc_plan  # noqa: E402

CLI = STORE_SCRIPTS / "asc_listing.py"


@pytest.fixture()
def served(tmp_path: Path) -> Path:
    """The promotion PR in a temporary tree, with the manifest the export
    compliance answer is read from."""
    root = promote(tmp_path / "repo")
    (root / "apps" / "mobile").mkdir(parents=True)
    shutil.copy(REPO / "apps" / "mobile" / "app.json", root / "apps" / "mobile" / "app.json")
    return root


def _steps(plan: asc_plan.Plan) -> dict[tuple[str, str | None], tuple[str, ...]]:
    return {(step.resource, step.locale): step.fields for step in plan.steps}


# --- 1. the plan, from served copy only ------------------------------------------------


def test_the_plan_fills_every_text_field_the_served_copy_holds(served: Path) -> None:
    plan = asc_plan.build_plan(served)
    steps = _steps(plan)
    for locale in ("tr", "en-US"):
        assert steps[("appInfoLocalizations", locale)] == ("name", "subtitle")
        assert steps[("appStoreVersionLocalizations", locale)] == (
            "description",
            "keywords",
            "promotionalText",
        )
    assert steps[("appInfos", None)] == ("primaryCategory",)
    assert steps[("apps", None)] == ("contentRightsDeclaration",)
    assert ("appStoreReviewDetails", None) not in steps, "the notes are held (legal review B5)"
    assert set(steps[("ageRatingDeclarations", None)]) == set(asc_plan.AGE_RATING_KEYS)


def test_every_field_the_plan_cannot_fill_is_blocked_with_its_owner(served: Path) -> None:
    blocked = "\n".join(asc_plan.build_plan(served).blocked)
    for needle in (
        "privacyPolicyUrl",
        "HB-L27",
        "supportUrl",
        "copyright",
        "HB-L21(e)",
        "App Privacy",
        "privacy-answers",
        "whatsNew",
        "PRODUCT_PAGE_HEADER_ASSET",
        "APP_SCREENSHOT",
    ):
        assert needle in blocked, needle


def test_the_hold_is_the_one_switch_for_both_routes(served: Path) -> None:
    """Lifting the hold (a legal-lane edit) puts the notes back on both routes, and an
    empty hold is refused rather than read as lifted."""
    path = eas.submission_path(served)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    loaded["review_notes_hold"] = " "
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    with pytest.raises(eas.StoreConfigError, match="review_notes_hold"):
        eas.load_submission(path)
    del loaded["review_notes_hold"]
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    assert eas.render_for_repo(served).config["apple"]["review"] == {
        "notes": loaded["review_notes"]
    }
    steps = _steps(asc_plan.build_plan(served))
    assert steps[("appStoreReviewDetails", None)] == ("notes",)


def test_the_review_notes_are_held_until_they_are_true(served: Path) -> None:
    """Legal review B5 (INT-502): the notes promise a 112 notice, a reviewer sign-in,
    voice and delivery. None of these holds for a store build today, so the notes are
    blocked with their owners rather than written."""
    blocked = "\n".join(asc_plan.build_plan(served).blocked)
    for needle in (
        "appStoreReviewDetails.notes",
        "INT-117 Stage A (static 112 notice; no patient-facing RED on the review host)",
        "INT-488",
        "INT-587",
        "INT-440",
        "scanner",
    ):
        assert needle in blocked, needle
    # R1: the EAS route is held by the same submission field, so neither the
    # render nor the committed store.config.json carries a review block.
    render = eas.render_for_repo(served)
    assert "review" not in render.config["apple"]
    assert any(r.startswith("review.notes") and "INT-587" in r for r in render.blocked)
    committed = json.loads((REPO / "apps/mobile/store.config.json").read_text(encoding="utf-8"))
    assert "review" not in committed["apple"]


def _store_build_has_voice() -> bool:
    """The store build reaches voice intake only when ``voiceEligible`` stops
    requiring ``__DEV__`` (INT-440, INT-454)."""
    intake = REPO / "apps/mobile/src/app/(tabs)/visits/[visitId]/intake.tsx"
    text = intake.read_text(encoding="utf-8")
    start = text.index("const voiceEligible")
    return "__DEV__" not in text[start : text.index(";", start)]


def _host_scans_uploads() -> bool:
    """A store build talks to the synthetic host, and an upload succeeds only
    where a malware scanner runs (docs/runbooks/staging.md: no ClamAV, so the
    upload fails closed)."""
    compose = (REPO / "infra/staging/compose.yaml").read_text(encoding="utf-8")
    return "clamav" in compose.lower()


VOICE_TERMS = re.compile(
    r"(?i)\bses(?:li|iniz|ini)?\b|konuş|mikrofon|\bvoice\b|\bspeak|\baudio\b|microphone"
)
UPLOAD_TERMS = re.compile(r"(?i)yükle|\bupload")


def test_the_served_listing_promises_no_voice_or_upload_this_build_lacks() -> None:
    """Legal review B1 and B2 (INT-502): while the store build has no voice and the
    host cannot scan an upload, no listing field may offer either."""
    for locale in ("tr", "en-US"):
        fields = _served_fields(locale)
        text = "\n".join(str(v) for v in fields.values())
        if not _store_build_has_voice():
            assert not VOICE_TERMS.search(text), (locale, VOICE_TERMS.search(text))
        if not _host_scans_uploads():
            assert not UPLOAD_TERMS.search(text), (locale, UPLOAD_TERMS.search(text))
    assert VOICE_TERMS.search("Şikâyetinizi sesli anlatabilirsiniz."), "near miss: tr voice"
    assert VOICE_TERMS.search("You can speak your answers."), "near miss: en voice"
    assert UPLOAD_TERMS.search("Raporlarınızı yükleyebilirsiniz."), "near miss: tr upload"


def test_unheld_review_notes_promise_no_voice_or_upload_this_build_lacks(
    served: Path,
) -> None:
    """Legal re-check R4: once the hold is lifted the notes go out, so they must pass
    the same voice and upload checks as the listing, under the same conditions."""
    submission = eas.load_submission(eas.submission_path(served))
    assert _unheld_note_findings(submission) == []
    # Near miss: notes that still promise voice and upload, with the hold lifted.
    lifted = dataclasses.replace(
        submission,
        review_notes_hold=None,
        review_notes="The user describes their complaints by voice. "
        "A photographed report can be uploaded.",
    )
    expected = [
        name
        for name, present in (
            ("voice", not _store_build_has_voice()),
            ("upload", not _host_scans_uploads()),
        )
        if present
    ]
    assert _unheld_note_findings(lifted) == expected


def _unheld_note_findings(submission: eas.AppStoreSubmission) -> list[str]:
    """What unheld notes promise that this build lacks; nothing while the hold stands."""
    if submission.review_notes_hold is not None:
        return []
    found: list[str] = []
    if not _store_build_has_voice() and VOICE_TERMS.search(submission.review_notes):
        found.append("voice")
    if not _host_scans_uploads() and UPLOAD_TERMS.search(submission.review_notes):
        found.append("upload")
    return found


def _served_fields(locale: str) -> dict[str, object]:
    path = REPO / f"docs/legal/store/listing/app-store.{locale}.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(loaded["fields"])


def _guardian_flow_exists() -> bool:
    """A minor may use the app only through a guardian account with guardian consent
    (apps/mobile/e2e/guardian.spec.ts). That flow needs a guardian consent text."""
    from intake_platform.legal.documents import REQUIRED_DOCUMENTS

    return any("guardian" in row.id or "veli" in row.id for row in REQUIRED_DOCUMENTS)


def test_the_top_age_band_holds_while_no_guardian_flow_exists(served: Path) -> None:
    """Legal review B8 (INT-502): with no guardian flow, the EAS answer is 17+ and the
    live override is 18+ (ageRatingOverrideV2, Apple's attributes read 2026-10-29)."""
    submission = eas.load_submission(eas.submission_path(served))
    if not _guardian_flow_exists():
        assert submission.advisory["seventeenPlus"] is True
        assert submission.advisory_asc["ageRatingOverrideV2"] == "EIGHTEEN_PLUS"
    values = asc_plan.build_plan(served).values[("ageRatingDeclarations", None)]
    assert values["ageRatingOverrideV2"] == submission.advisory_asc["ageRatingOverrideV2"]


def test_an_override_outside_apples_values_is_refused(tmp_path: Path) -> None:
    root = promote(tmp_path / "repo")
    path = eas.submission_path(root)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    loaded["advisory_asc"]["ageRatingOverrideV2"]["answer"] = "SEVENTEEN_PLUS"
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    with pytest.raises(eas.StoreConfigError, match="ageRatingOverrideV2"):
        eas.load_submission(path)


def test_the_age_rating_speaks_the_live_api_not_the_eas_schema(served: Path) -> None:
    values = asc_plan.build_plan(served).values[("ageRatingDeclarations", None)]
    assert "seventeenPlus" not in values, "no such attribute in the live API"
    assert set(values) == set(asc_plan.AGE_RATING_KEYS)
    assert values["healthOrWellnessTopics"] is True
    assert values["alcoholTobaccoOrDrugUseOrReferences"] == "INFREQUENT_OR_MILD"


def test_the_plan_refuses_unserved_copy(tmp_path: Path) -> None:
    from intake_platform.store.listing import StoreListingMissingError

    with pytest.raises(StoreListingMissingError):
        asc_plan.build_plan(tmp_path)


def test_keywords_are_counted_in_bytes(served: Path) -> None:
    """App Store Connect counts keywords in bytes (platform version
    information, retrieved 2026-10-16), and Turkish letters are two bytes."""
    assert asc_plan.keyword_bytes(["şikâyet", "sağlık"]) == len("şikâyet,sağlık".encode())
    long = ["ğüşıöç" * 3] * 5
    assert len(",".join(long)) <= 100 < asc_plan.keyword_bytes(long)
    with pytest.raises(asc_plan.PlanError, match="bytes"):
        asc_plan.check_keywords(long, where="tr")


# --- 2. the dry run ---------------------------------------------------------------------


def test_the_dry_run_prints_field_names_and_never_a_value(served: Path) -> None:
    plan = asc_plan.build_plan(served)
    text = asc_plan.render_plan(plan)
    assert "PLAN appInfoLocalizations[tr] name,subtitle" in text
    for (_, _), values in plan.values.items():
        for value in values.values():
            if isinstance(value, str) and len(value) > 12:
                assert value not in text


def test_the_cli_dry_run_needs_no_credentials(served: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(CLI), "--repo", str(served)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "DRY RUN" in done.stdout and "PLAN " in done.stdout


def test_the_cli_refuses_apply_without_the_owners_eas_json(served: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(CLI), "--repo", str(served), "--apply"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2
    assert "--eas-json" in done.stdout + done.stderr


def test_the_cli_fails_closed_without_served_copy(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(CLI), "--repo", str(tmp_path)], capture_output=True, text=True
    )
    assert done.returncode == 3
    assert "HB-L21" in done.stdout


# --- 3. nothing outside the draft --------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/reviewSubmissions"),
        ("POST", "/v1/reviewSubmissionItems"),
        ("POST", "/v1/appStoreVersionSubmissions"),
        ("POST", "/v1/appStoreVersionReleaseRequests"),
        ("POST", "/v1/appStoreVersionPhasedReleases"),
        ("PATCH", "/v1/appPriceSchedules/1"),
        ("POST", "/v1/appAvailabilities"),
        ("DELETE", "/v1/appStoreVersionLocalizations/1"),
        ("PATCH", "/v1/apps/1/relationships/prices"),
        ("POST", "/v1/appStoreVersions"),
    ],
)
def test_the_guard_refuses_everything_that_is_not_a_draft_edit(method: str, path: str) -> None:
    with pytest.raises(asc_client.ForbiddenRequest):
        asc_client.guard(method, path, None)


def test_the_guard_refuses_the_reviewer_sign_in_fields() -> None:
    body = {"data": {"type": "appStoreReviewDetails", "attributes": {"demoAccountName": "x"}}}
    with pytest.raises(asc_client.ForbiddenRequest, match="demoAccountName"):
        asc_client.guard("PATCH", "/v1/appStoreReviewDetails/1", body)
    body = {"data": {"type": "appStoreReviewDetails", "attributes": {"contactEmail": "x"}}}
    with pytest.raises(asc_client.ForbiddenRequest, match="contactEmail"):
        asc_client.guard("PATCH", "/v1/appStoreReviewDetails/1", body)


class FakeAsc:
    """A recorded App Store Connect: canned reads, every write recorded."""

    def __init__(self, *, version_state: str = "PREPARE_FOR_SUBMISSION") -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.version_state = version_state

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        asc_client.guard(method, path, body)
        self.calls.append((method, path, body))
        if method != "GET":
            return (201 if method == "POST" else 200), {"data": {"id": "new"}}
        base = path.split("?", 1)[0]
        canned: dict[str, Any] = {
            "/v1/apps/APP/appInfos": [
                {"id": "info-live", "attributes": {"state": "READY_FOR_DISTRIBUTION"}},
                {"id": "info-1", "attributes": {"state": "PREPARE_FOR_SUBMISSION"}},
            ],
            "/v1/appInfos/info-1/appInfoLocalizations": [
                {"id": "ail-tr", "attributes": {"locale": "tr"}}
            ],
            "/v1/apps/APP/appStoreVersions": [
                {"id": "v-1", "attributes": {"appVersionState": self.version_state}}
            ],
            "/v1/appStoreVersions/v-1/appStoreVersionLocalizations": [
                {"id": "avl-en", "attributes": {"locale": "en-US"}}
            ],
            "/v1/appInfos/info-1/ageRatingDeclaration": {"id": "age-1"},
            "/v1/appStoreVersions/v-1/appStoreReviewDetail": None,
        }
        return 200, {"data": canned[base]}


def test_apply_writes_only_draft_metadata(served: Path) -> None:
    fake = FakeAsc()
    log: list[str] = []
    asc_client.apply_plan(asc_plan.build_plan(served), fake, app_id="APP", log=log.append)
    writes = [(m, p) for m, p, _ in fake.calls if m != "GET"]
    assert ("PATCH", "/v1/appInfoLocalizations/ail-tr") in writes
    assert ("POST", "/v1/appInfoLocalizations") in writes
    assert ("PATCH", "/v1/appStoreVersionLocalizations/avl-en") in writes
    assert ("POST", "/v1/appStoreVersionLocalizations") in writes
    assert ("PATCH", "/v1/ageRatingDeclarations/age-1") in writes
    assert ("PATCH", "/v1/apps/APP") in writes
    assert ("PATCH", "/v1/appInfos/info-1") in writes
    assert not [p for _, p in writes if "appStoreReviewDetails" in p], "notes held (B5)"
    assert not [p for _, p, _ in fake.calls if "info-live" in p], "the live appInfo is untouched"
    # The log holds field names and statuses; no value of any field.
    plan = asc_plan.build_plan(served)
    joined = "\n".join(log)
    for values in plan.values.values():
        for value in values.values():
            if isinstance(value, str) and len(value) > 12:
                assert value not in joined


def test_apply_refuses_when_no_version_is_editable(served: Path) -> None:
    fake = FakeAsc(version_state="READY_FOR_DISTRIBUTION")
    with pytest.raises(asc_client.ApplyError, match="editable"):
        asc_client.apply_plan(asc_plan.build_plan(served), fake, app_id="APP", log=print)
    assert [m for m, _, _ in fake.calls if m != "GET"] == []


def test_apply_stops_at_the_first_refused_write(served: Path) -> None:
    class Refusing(FakeAsc):
        def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
            if method == "PATCH":
                self.calls.append((method, path, body))
                return 409, {"errors": [{"code": "STATE_ERROR"}]}
            return super().request(method, path, body)

    fake = Refusing()
    log: list[str] = []
    with pytest.raises(asc_client.ApplyError, match="409"):
        asc_client.apply_plan(asc_plan.build_plan(served), fake, app_id="APP", log=log.append)
    assert len([m for m, _, _ in fake.calls if m == "PATCH"]) == 1


# --- 4. the token ---------------------------------------------------------------------------


def _owner_files(tmp_path: Path) -> tuple[Path, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "AuthKey_TEST.p8").write_bytes(pem)
    eas_json = tmp_path / "eas.json"
    ios = {
        "ascApiKeyPath": "./keys/AuthKey_TEST.p8",
        "ascApiKeyId": "KEYID",
        "ascApiKeyIssuerId": "ISSUER",
        "ascAppId": "APP",
    }
    eas_json.write_text(json.dumps({"submit": {"production": {"ios": ios}}}), encoding="utf-8")
    return eas_json, key


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_the_token_is_es256_short_lived_and_verifiable(tmp_path: Path) -> None:
    eas_json, key = _owner_files(tmp_path)
    creds = asc_client.Credentials.from_eas_json(eas_json)
    assert "PRIVATE" not in repr(creds) and "KEYID" not in repr(creds)
    now = int(time.time())
    token = asc_client.make_token(creds, now=now)
    header_b64, payload_b64, signature_b64 = token.split(".")
    header = json.loads(_b64(header_b64))
    payload = json.loads(_b64(payload_b64))
    assert header == {"alg": "ES256", "kid": "KEYID", "typ": "JWT"}
    assert payload["iss"] == "ISSUER" and payload["aud"] == "appstoreconnect-v1"
    assert 0 < payload["exp"] - payload["iat"] <= 20 * 60
    raw = _b64(signature_b64)
    assert len(raw) == 64
    signature = encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:]))
    key.public_key().verify(
        signature, f"{header_b64}.{payload_b64}".encode(), ec.ECDSA(hashes.SHA256())
    )


def test_a_missing_credential_field_is_named_and_no_value_is_echoed(tmp_path: Path) -> None:
    eas_json, _ = _owner_files(tmp_path)
    data = json.loads(eas_json.read_text(encoding="utf-8"))
    del data["submit"]["production"]["ios"]["ascApiKeyIssuerId"]
    eas_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(asc_client.CredentialsError, match="ascApiKeyIssuerId") as caught:
        asc_client.Credentials.from_eas_json(eas_json)
    assert "KEYID" not in str(caught.value)


# --- 5. assets ------------------------------------------------------------------------------


def _png(path: Path, width: int, height: int, color_type: int = 2) -> Path:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0"))
    path.write_bytes(body + chunk(b"IEND", b""))
    return path


def test_the_manifest_carries_the_specs_read_on_2026_10_16() -> None:
    manifest = asc_assets.load_manifest(asc_assets.MANIFEST)
    groups = {entry.asset_id: entry for entry in manifest.entries}
    assert manifest.retrieved_on == "2026-10-16"
    assert groups["product-page-header"].sizes == ((3840, 1646),)
    assert groups["product-page-header"].placement_type == "PRODUCT_PAGE_HEADER_ASSET"
    assert groups["iphone-large"].placement_group == "IPHONE_DYNAMIC_ISLAND_LARGE_PROFILE"
    assert (1320, 2868) in groups["iphone-large"].sizes
    assert (1206, 2622) in groups["iphone-medium"].sizes
    assert groups["iphone-medium"].required


def test_the_validator_accepts_a_right_png_and_refuses_the_near_misses(tmp_path: Path) -> None:
    manifest = asc_assets.load_manifest(asc_assets.MANIFEST)
    large = next(e for e in manifest.entries if e.asset_id == "iphone-large")
    good = _png(tmp_path / "01-bugun-light.png", 1320, 2868)
    assert asc_assets.check_file(good, large) == ()
    alpha = _png(tmp_path / "02-alpha.png", 1320, 2868, color_type=6)
    assert any("alpha" in p for p in asc_assets.check_file(alpha, large))
    small = _png(tmp_path / "03-small.png", 1206, 2622)
    assert any("size" in p for p in asc_assets.check_file(small, large))
    named = _png(tmp_path / "04-deneme-hastasi.png", 1320, 2868)
    assert any("name" in p for p in asc_assets.check_file(named, large))
    jpeg = tmp_path / "05.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0")
    assert any("PNG" in p for p in asc_assets.check_file(jpeg, large))


def test_assets_wait_for_the_capture_step(served: Path) -> None:
    plan = asc_plan.build_plan(served)
    assert any("capture" in reason for reason in plan.blocked)
    assert not [s for s in plan.steps if s.resource == "appAssetLibraryImages"]
