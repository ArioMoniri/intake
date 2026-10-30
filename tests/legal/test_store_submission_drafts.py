"""INT-482 — ``store.config.json``, legal links, review notes, age rating, checklist.

The companion of ``test_store_listing_drafts.py`` (the copy itself). Four rules
are held here:

- **``store.config.json`` is rendered, never written.** It is a function of the
  served listing and submission files under ``docs/legal/store`` and nothing
  else, so on today's tree — where nothing is served — the render refuses and
  the file must not exist. After promotion the committed file must equal the
  render.
- **A legal link binds to signed bytes** (invariant 18): the document must
  render from docs/legal with its counsel sign-off and hash, and the URL must
  name that sha256.
- **The review notes explain 112 and the synthetic scope and claim nothing,**
  and no store draft carries a reviewer sign-in or contact.
- **The checklist links every artefact** and lists the owner's asks.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from intake_platform.legal import claims
from intake_platform.legal.document_index import LegalDocumentSet
from intake_platform.legal.documents import LegalDocumentError, required_document
from intake_platform.store import eas_metadata as eas
from intake_platform.store import listing as listing_mod
from store_drafts_harness import (
    APP_NAME,
    DRAFTS,
    LOCALES,
    REPO,
    STRICT,
    body,
    cited_path,
    promote,
    store_texts,
    submission_source,
)

CHECKLIST = REPO / "docs" / "release" / "production-checklist.md"
SCREENSHOTS = REPO / "docs" / "store" / "screenshots" / "app-store-screenshots.json"
SCRIPT = REPO / "scripts" / "release" / "render_store_config.py"


def _checklist_section_5() -> str:
    return CHECKLIST.read_text(encoding="utf-8").split("## 5.", 1)[1].split("\n## ", 1)[0]


# --- 1. legal links: only to a signed, hash-bound docs/legal document ----------------------


def _signed_gizlilik(root: Path) -> tuple[LegalDocumentSet, str]:
    text = "Sentetik test metni (INT-482). Hukuki bir metin değildir.\n"
    summary = "Sentetik sade dil özeti (INT-482).\n"
    required = required_document("gizlilik")
    assert required.summary_path is not None
    for relative, content in ((required.relative_path, text), (required.summary_path, summary)):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(content, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    (root / "documents.yaml").write_text(
        'legal_index_version: "test-fixture.1"\ndocuments:\n'
        '  - id: "gizlilik"\n    version: "test-fixture.1"\n'
        f'    sha256: "{digest}"\n'
        f'    summary_sha256: "{hashlib.sha256(summary.encode()).hexdigest()}"\n'
        '    counsel:\n      signed_by: "Sentetik Test Danismani"\n'
        "      signed_on: 2026-10-04\n"
        '      evidence: "docs/evidence/INT-210.md#counsel-sign-off"\n',
        encoding="utf-8",
    )
    return LegalDocumentSet(root), digest


def test_a_legal_link_binds_only_the_signed_bytes(tmp_path: Path) -> None:
    documents, digest = _signed_gizlilik(tmp_path)
    url = f"https://legal.example.invalid/gizlilik?sha256={digest}"
    link = eas.bind_legal_link(documents, field="privacyPolicyUrl", document_id="gizlilik", url=url)
    assert (link.url, link.text_hash) == (url, digest)
    unbound = "https://legal.example.invalid/gizlilik"
    with pytest.raises(eas.StoreConfigError, match="sha256"):
        eas.bind_legal_link(
            documents, field="privacyPolicyUrl", document_id="gizlilik", url=unbound
        )
    with pytest.raises(eas.StoreConfigError, match="https"):
        eas.bind_legal_link(
            documents, field="privacyPolicyUrl", document_id="gizlilik", url=url.replace("s:", ":")
        )
    with pytest.raises(eas.StoreConfigError, match="gizlilik"):
        eas.bind_legal_link(documents, field="privacyPolicyUrl", document_id="cerez", url=url)


def test_today_no_legal_link_can_bind_because_nothing_is_signed() -> None:
    with pytest.raises(LegalDocumentError):
        eas.bind_legal_link(
            LegalDocumentSet(REPO / "docs" / "legal"),
            field="privacyPolicyUrl",
            document_id="gizlilik",
            url="https://legal.example.invalid/gizlilik?sha256=" + "0" * 64,
        )


def test_a_bound_link_and_the_seller_fields_reach_every_locale(tmp_path: Path) -> None:
    root = promote(tmp_path)
    _, digest = _signed_gizlilik(root / "docs" / "legal")
    path = eas.submission_path(root)
    loaded = body(path)
    url = f"https://legal.example.invalid/gizlilik?sha256={digest}"
    loaded["legal_links"] = {"privacyPolicyUrl": {"document": "gizlilik", "url": url}}
    loaded["support_url"] = "https://support.example.invalid/onvizit"
    loaded["copyright"] = "2026 Sentetik Test"
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    result = eas.render_for_repo(root)
    for info in result.config["apple"]["info"].values():
        assert info["privacyPolicyUrl"] == url
        assert info["supportUrl"].startswith("https://")
    assert result.config["apple"]["copyright"] == "2026 Sentetik Test"
    # INT-502 legal review B5/R1: only the held review notes stay blocked.
    assert [r for r in result.blocked if not r.startswith("review.notes")] == []


# --- 2. the render: store.config.json from served copy only ----------------------------------


def test_the_render_assembles_store_config_from_the_promoted_drafts(tmp_path: Path) -> None:
    result = eas.render_for_repo(promote(tmp_path))
    config = result.config
    apple = config["apple"]
    assert config["configVersion"] == 0
    assert set(apple["info"]) == set(LOCALES)
    assert {apple["info"][x]["title"] for x in LOCALES} == {APP_NAME}
    assert isinstance(apple["info"]["tr"]["keywords"], list)
    assert apple["release"] == {"automaticRelease": False}
    assert apple["categories"] and apple["advisory"]
    # INT-502 legal review B5/R1: the held notes, and so any review block, are absent;
    # no reviewer contact or sign-in is ever in the repo either.
    assert "review" not in apple
    assert any(reason.startswith("review.notes") for reason in result.blocked)
    assert all("privacyPolicyUrl" not in info for info in apple["info"].values())
    assert any("HB-L27" in reason for reason in result.blocked)
    assert any("HB-L21(e)" in reason for reason in result.blocked)
    text = eas.serialise(config)
    assert claims.scan_text(text, groups=STRICT) == ()
    notes = eas.load_submission(eas.submission_path(promote(tmp_path / "again"))).review_notes
    assert listing_mod.device_claim_hits(notes) == ()
    assert json.loads(text) == config
    assert set(result.sources) >= {
        "docs/legal/store/listing/app-store.tr.yaml",
        "docs/legal/store/listing/app-store.en-US.yaml",
        "docs/legal/store/submission/app-store.yaml",
    }
    # The CI gate's own patterns too (Turkish kesinlik/isabet among them), at
    # the strict tier invariant 20 gives a store listing.
    rendered = tmp_path / "store.config.json"
    rendered.write_text(text, encoding="utf-8")
    scan = REPO / "scripts" / "ci" / "claims_scan.sh"
    gate = subprocess.run(["bash", str(scan), "--strict", str(rendered)], capture_output=True)
    assert gate.returncode == 0, gate.stdout


def test_the_real_tree_fails_closed_until_the_listing_is_promoted() -> None:
    served = sorted(listing_mod.listing_dir(REPO).glob("app-store.*.yaml"))
    assert eas.store_config_path(REPO).exists() == bool(served)
    if not served:
        with pytest.raises(listing_mod.StoreListingMissingError, match="HB-L21"):
            eas.render_for_repo(REPO)
        return
    rendered = eas.serialise(eas.render_for_repo(REPO).config)
    assert eas.store_config_path(REPO).read_text(encoding="utf-8") == rendered


def _script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_the_render_script_refuses_without_served_copy(tmp_path: Path) -> None:
    empty = _script("--repo", str(tmp_path), "--check")
    assert empty.returncode == 3, empty.stdout + empty.stderr
    assert "HB-L21" in empty.stdout
    root = promote(tmp_path / "promoted")
    (root / "apps" / "mobile").mkdir(parents=True)
    wrote = _script("--repo", str(root))
    assert wrote.returncode == 0, wrote.stdout + wrote.stderr
    assert "blocked:" in wrote.stdout
    assert _script("--repo", str(root), "--check").returncode == 0
    eas.store_config_path(root).write_text("{}\n", encoding="utf-8")
    assert _script("--repo", str(root), "--check").returncode == 1


def test_a_stale_store_config_with_no_served_copy_fails(tmp_path: Path) -> None:
    (tmp_path / "apps" / "mobile").mkdir(parents=True)
    eas.store_config_path(tmp_path).write_text("{}\n", encoding="utf-8")
    assert _script("--repo", str(tmp_path), "--check").returncode == 1


def test_a_refused_served_artefact_exits_2(tmp_path: Path) -> None:
    root = promote(tmp_path)
    path = eas.submission_path(root)
    path.write_text(path.read_text(encoding="utf-8").replace("MEDICAL", "PODCASTS"), "utf-8")
    refused = _script("--repo", str(root), "--check")
    assert refused.returncode == 2, refused.stdout


def _rewrite_listing(root: Path, name: str, edit: object) -> None:
    path = root / "docs" / "legal" / "store" / "listing" / name
    loaded = body(path)
    assert callable(edit)
    edit(loaded["fields"])
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda f: f.update(marketingUrl="tanıtım"), "outside apple.info"),
        (lambda f: f.update(subtitle="Akıllı triyaj asistanı"), "listing gate"),
        (lambda f: f.update(title="Önvizit " + "ön not " * 5), "limit"),
        (lambda f: f.update(keywords="muayene,,hekim"), "empty keyword"),
        (lambda f: f.update(promoText="Notes ready 20% sooner."), "performance-claim"),
    ],
)
def test_a_broken_served_listing_is_refused(tmp_path: Path, edit: object, match: str) -> None:
    root = promote(tmp_path, stores=("app-store",))
    _rewrite_listing(root, "app-store.tr.yaml", edit)
    with pytest.raises(eas.StoreConfigError, match=match):
        eas.render_for_repo(root)


def test_a_listing_in_a_locale_eas_does_not_know_is_refused(tmp_path: Path) -> None:
    root = promote(tmp_path, stores=("app-store",))
    listing = root / "docs" / "legal" / "store" / "listing"
    (listing / "app-store.tr.yaml").rename(listing / "app-store.tr-XX.yaml")
    with pytest.raises(eas.StoreConfigError, match="not an EAS locale"):
        eas.render_for_repo(root)


def test_play_copy_alone_renders_no_app_store_file(tmp_path: Path) -> None:
    root = promote(tmp_path, stores=("google-play",))
    with pytest.raises(listing_mod.StoreListingMissingError, match="App Store"):
        eas.render_for_repo(root)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("advisory: [\n", "YAML"),
        ("- a list\n", "mapping"),
        ("categories: [MEDICAL]\nadvisory: none\n", "advisory must be a mapping"),
    ],
)
def test_an_unreadable_submission_is_refused(tmp_path: Path, text: str, match: str) -> None:
    path = tmp_path / "app-store.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(eas.StoreConfigError, match=match):
        eas.load_submission(path)


# --- 3. submission answers: categories, age rating, review notes ---------------------------


def test_the_age_rating_answers_cover_the_eas_schema_and_cite_their_source() -> None:
    submission = eas.load_submission(submission_source())
    assert set(submission.advisory) == set(eas.ADVISORY_LEVEL_KEYS) | set(eas.ADVISORY_FLAG_KEYS)
    for key in eas.ADVISORY_LEVEL_KEYS:
        assert submission.advisory[key] in eas.ADVISORY_LEVELS
    for key in eas.ADVISORY_FLAG_KEYS:
        assert isinstance(submission.advisory[key], bool)
    for key, source in submission.advisory_sources.items():
        assert cited_path(source).exists(), (key, source)
    assert set(submission.categories) <= eas.CATEGORIES


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda b: b["advisory"].pop("gambling"), "gambling"),
        (lambda b: b["advisory"]["contests"].update(answer="SOMETIMES"), "contests"),
        (lambda b: b["advisory"]["gambling"].update(answer="no"), "gambling"),
        (lambda b: b["advisory"]["contests"].update(source=""), "contests"),
        (lambda b: b.update(review_notes="The app has high accuracy."), "claim"),
        (lambda b: b.update(support_url="http://support.example.invalid"), "https"),
        (lambda b: b.update(categories=[]), "categories"),
        (lambda b: b.update(review_notes="The app runs triage on it."), "device-function"),
        (lambda b: b.update(review_notes=" "), "review_notes"),
        (lambda b: b.update(legal_links={"privacyPolicyUrl": "gizlilik"}), "legal_links"),
        (lambda b: b.update(copyright=2026), "copyright"),
        (lambda b: b["advisory_asc"].pop("lootBox"), "lootBox"),
        (lambda b: b["advisory_asc"]["advertising"].update(answer="NONE"), "advertising"),
        (lambda b: b.update(content_rights={"answer": "MAYBE", "source": "x"}), "content_rights"),
        (
            lambda b: b.update(content_rights={"answer": "USES_THIRD_PARTY_CONTENT"}),
            "content_rights",
        ),
    ],
)
def test_a_broken_submission_is_refused(tmp_path: Path, edit: object, match: str) -> None:
    loaded = body(submission_source())
    assert callable(edit)
    edit(loaded)
    path = tmp_path / "app-store.yaml"
    path.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    with pytest.raises(eas.StoreConfigError, match=match):
        eas.load_submission(path)


def _review_texts() -> dict[str, str]:
    apple = eas.load_submission(submission_source()).review_notes
    play = body(DRAFTS / "google-play.submission.draft.yaml")["app_access_instructions"]
    return {"apple": apple, "play": play}


def test_the_review_notes_explain_112_and_the_synthetic_scope_and_claim_nothing() -> None:
    for where, text in _review_texts().items():
        assert "112" in text, where
        assert "simulated" in text, where
        assert "does not diagnose" in text, where
        assert claims.scan_text(text, groups=STRICT) == (), where
        assert listing_mod.device_claim_hits(text) == (), where


def test_no_credential_is_committed_in_any_store_draft() -> None:
    #: A secret word, an e-mail address, an international or a Turkish mobile
    #: number. Dates and hashes are not credentials and must not match.
    credential = re.compile(
        r"(?i)password|parola|şifre|demoUsername|demoPassword|\b[\w.+-]+@[\w-]+\.\w"
        r"|\+\d{1,3}[\d ()-]{7,}|\b05\d{2}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}\b"
    )
    # Assembled at run time, so no phone-shaped literal sits in the tree.
    assert credential.search("hasta" + "@example.invalid")
    assert credential.search("0" + "5" + "32 123 45 67")
    assert not credential.search("prepared_on: 2026-10-04")
    found = [
        (path.name, match.group(0))
        for path in store_texts()
        for match in credential.finditer(path.read_text(encoding="utf-8"))
    ]
    assert found == []


def test_the_play_content_rating_facts_cite_sources_and_await_counsel() -> None:
    loaded = body(DRAFTS / "google-play.submission.draft.yaml")
    assert "HB-L21(c)" in loaded["content_rating_owner"]
    assert "HB-L21(b)" in loaded["health_apps_owner"]
    for row in loaded["content_rating_facts"] + loaded["health_apps_facts"]:
        assert row["fact"].strip()
        assert cited_path(row["source"]).exists(), row


# --- 4. screenshots and the release checklist ----------------------------------------------


def test_the_screenshot_captions_pass_the_gates_or_the_checklist_waits_for_738() -> None:
    if not SCREENSHOTS.exists():
        assert "#738" in _checklist_section_5() and "INT-425" in _checklist_section_5()
        return
    strings = re.findall(r'"([^"]{8,})"', SCREENSHOTS.read_text(encoding="utf-8"))
    for text in strings:
        assert claims.scan_text(text, groups=STRICT) == (), text
        assert listing_mod.device_claim_hits(text) == (), text


def test_the_checklist_links_every_artefact_and_names_the_owner_asks() -> None:
    section = _checklist_section_5()
    for path in store_texts():
        assert path.name in section, path.name
    for needle in (
        "eas login",
        "EXPO_TOKEN",
        "App Store Connect",
        "Google Play Console",
        APP_NAME,
        "render_store_config.py",
        "automaticRelease",
        "HB-L21",
        "HB-L27",
        "INT-117",
        # The legal lane's round on #828: the reviewer sign-in path, and voice
        # gated behind __DEV__ in a release build while the copy promises it.
        "INT-488",
        "INT-440",
        "voiceEligible",
    ):
        assert needle in section, needle


def test_the_review_guide_gates_submission_on_release_voice_and_reviewer_sign_in() -> None:
    """The listing and the notes describe voice intake, and a release build
    has none today; App Review needs a way in. Both are §1 conditions, owned."""
    guide = (DRAFTS / "app-review-notes.draft.md").read_text(encoding="utf-8")
    first = guide.split("## 1", 1)[1].split("\n## ", 1)[0]
    assert "voiceEligible" in first and "INT-440 (#768)" in first and "INT-454 (#769)" in first
    assert "INT-488 (#829)" in first
    intake = REPO / "apps/mobile/src/app/(tabs)/visits/[visitId]/intake.tsx"
    gated = re.search(r"voiceEligible =\s*__DEV__", intake.read_text(encoding="utf-8"))
    # Both ways: the guide says voice is dev-only exactly while the code says so.
    assert bool(gated) == ("Today `voiceEligible` requires" in first)


def test_the_review_guide_gates_submission_on_a_turkish_only_binary() -> None:
    """INT-595 and the legal re-check of 31 Oct 2026: the App Store's Languages row is
    read from the uploaded build's .lproj folders, so the build sent for review must
    carry tr.lproj only. Build 7 predates INT-595 and is not that build."""
    guide = (DRAFTS / "app-review-notes.draft.md").read_text(encoding="utf-8")
    first = guide.split("## 1", 1)[1].split("\n## ", 1)[0]
    row = next(line for line in first.splitlines() if "INT-595 (#1008)" in line)
    assert row.startswith("| 13 |")
    assert "`tr.lproj`" in row and "uploaded build" in row and "Build 7" in row
