"""INT-613: docs/release/app-store-metadata.yaml stays inside its limits, claims nothing,
and is the served listing's text, byte for byte.

* limits: name and subtitle 30 characters, keywords 100 bytes, description
  4000, promotional text 170, release notes 4000;
* invariant 20: scripts/ci/claims_scan.sh at its strict tier finds nothing in
  the file, and neither do the same patterns through intake_platform.legal.claims;
* invariant 18: each listing string equals docs/legal/store/listing/
  app-store.<locale>.yaml whenever that file is on the tree, and the file's
  sha256 is the one `legal_source` pins. Until #860 lands, the binding must
  still name #860, and no approval may be recorded against text that is not
  on main;
* every listing string carries approval:human-legal.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
METADATA = REPO / "docs" / "release" / "app-store-metadata.yaml"
LISTING_KEY = {
    "name": "title",
    "subtitle": "subtitle",
    "keywords": "keywords",
    "description": "description",
    "promotional_text": "promoText",
}


def _load() -> ModuleType:
    path = REPO / "scripts" / "release" / "asc_submit.py"
    spec = importlib.util.spec_from_file_location("asc_submit_meta", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


A = _load()
BODY = yaml.safe_load(METADATA.read_text(encoding="utf-8"))
LOCALES = tuple(BODY["locales"])


def test_the_locales_are_turkish_first() -> None:
    assert BODY["primary_locale"] == "tr" and LOCALES[0] == "tr"
    assert set(LOCALES) == {"tr", "en-US"}


@pytest.mark.parametrize("locale", ["tr", "en-US"])
def test_every_field_is_within_its_limit(locale: str) -> None:
    for key, limit in A.CHAR_LIMITS.items():
        text = BODY[key][locale]
        assert text is None or len(text) <= limit, f"{key}[{locale}]"
    keywords = BODY["keywords"][locale]
    assert len(keywords.encode("utf-8")) <= 100
    assert BODY["name"][locale] and BODY["description"][locale]


def test_the_limits_are_the_ones_the_brief_names() -> None:
    assert dict(A.CHAR_LIMITS) == {
        "name": 30,
        "subtitle": 30,
        "description": 4000,
        "promotional_text": 170,
        "release_notes": 4000,
    }
    assert A.KEYWORD_BYTES == 100


def test_the_claims_scan_finds_nothing_at_the_strict_tier() -> None:
    result = subprocess.run(
        ["bash", str(REPO / "scripts/ci/claims_scan.sh"), "--strict", str(METADATA)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout


def test_near_miss_the_claims_scan_catches_a_claim_in_this_shape(tmp_path: Path) -> None:
    body = yaml.safe_load(METADATA.read_text(encoding="utf-8"))
    body["promotional_text"]["tr"] = "Şikâyetlerinizi %95 doğrulukla not eder."
    probe = tmp_path / "app-store-metadata.yaml"
    probe.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    result = subprocess.run(
        ["bash", str(REPO / "scripts/ci/claims_scan.sh"), "--strict", str(probe)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert result.returncode == 1


def test_no_invalid_finding_in_the_committed_text() -> None:
    metadata = A.load_metadata(METADATA)
    assert [f.render() for f in A.check_text(metadata) if f.kind == "invalid"] == []


def test_every_listing_string_is_marked_approval_human_legal() -> None:
    for key in LISTING_KEY:
        for locale in LOCALES:
            entry = BODY["approvals"][key][locale]
            assert entry["approval"] == "human-legal", f"{key}[{locale}]"
            assert entry["legal_lane"], f"{key}[{locale}]"


def test_no_url_or_seller_value_is_invented() -> None:
    for key in ("privacy_url", "support_url", "marketing_url"):
        assert all(BODY[key][loc] is None for loc in LOCALES), key
    assert BODY["copyright"] is None
    # What's New is not offered for the first version (INT-495 §1)
    assert all(BODY["release_notes"][loc] is None for loc in LOCALES)


@pytest.mark.parametrize("locale", ["tr", "en-US"])
def test_the_text_is_the_served_listing_where_it_exists(locale: str) -> None:
    source = BODY["legal_source"]["listings"][locale]
    listing = REPO / source["path"]
    assert source["path"] == f"docs/legal/store/listing/app-store.{locale}.yaml"
    if listing.is_file():
        raw = listing.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["sha256"], (
            "the served listing changed: re-copy its text here and re-pin the sha256"
        )
        fields = yaml.safe_load(raw)["fields"]
        for key, listing_key in LISTING_KEY.items():
            assert BODY[key][locale] == fields[listing_key], f"{key}[{locale}]"
    else:
        # The listing is on PR #860 only. No human approval may stand against
        # text that main does not hold yet.
        assert BODY["legal_source"]["pr"] == 860
        for key in LISTING_KEY:
            assert BODY["approvals"][key][locale]["granted_by"] is None


def test_the_identity_matches_the_app_and_eas_config() -> None:
    _, version, findings = A.validate(REPO)
    assert not [f.render() for f in findings if f.where in {"app_identifier", "asc_app_id"}]
    assert version
