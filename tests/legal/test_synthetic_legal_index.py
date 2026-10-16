"""INT-529 — the synthetic-scope legal index (owner, 16 Oct 2026; D25 legal lane).

The real-tenant index ``docs/legal/documents.yaml`` stays empty until a licensed
Turkish lawyer countersigns (HB-L27, G3). The owner said yes to a SEPARATE index
for synthetic tenants only, so the synthetic host can exercise the consent flow.
This suite pins what that index may and may not be:

- it lives at ``docs/legal/synthetic/``, apart from the real index, and the
  real index still declares nothing;
- it loads only for the ``synthetic`` deployment data class; any other class is
  refused before a byte is read;
- every text it serves is hash-bound (the index's sha256 equals the bytes, and
  the front-matter version equals the index version) and carries the visible
  "sentetik test metni" marker on its first body line;
- near misses: an unmarked text, a marker hidden in the front matter, in an HTML
  comment or below the first line, a moved byte, a version drift, a performance
  claim, an id outside the sixteen, a duplicate row and a non-synthetic index
  are all refused;
- a real-tenant catalog refuses a text that carries the marker, so a synthetic
  text copied into the real tree cannot bind a real grant;
- every built text rests only on inventory values the repo already declares,
  and every one of the sixteen ids is either built or listed as awaiting-human
  with what is missing;
- the claims scan (invariant 20) and the PHI scan pass on the tree.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from intake_platform.consent import ConsentTextCatalog, ConsentTextInvalidError
from intake_platform.consent.registry import CHANNELS, purpose_ids
from intake_platform.consent.texts import (
    SYNTHETIC_MARKER,
    carries_synthetic_marker,
    synthetic_marker_is_visible,
    text_filename,
)
from intake_platform.db import inventory
from intake_platform.legal import LegalDocumentSet
from intake_platform.legal.documents import (
    LegalDocumentHashMismatchError,
    LegalDocumentInvalidError,
    LegalDocumentMissingError,
)
from intake_platform.legal.synthetic import (
    DATA_CLASS_ENV,
    SYNTHETIC_LEGAL_ROOT,
    DeploymentDataClass,
    SyntheticLegalIndex,
    SyntheticLegalTreeRefusedError,
    SyntheticMarkerMissingError,
    deployment_data_class,
    synthetic_document_ids,
    within_synthetic_legal_tree,
)

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / SYNTHETIC_LEGAL_ROOT
INDEX = ROOT / "documents.yaml"
RETENTION_POLICY = (
    REPO
    / "packages"
    / "intake_platform"
    / "src"
    / "intake_platform"
    / "retention"
    / "retention_policy.yaml"
)
SYN = DeploymentDataClass.SYNTHETIC

#: What INT-529 built, and what it left for the owner. The split is the
#: evidence file's §4 table: a text is built only when every value it states is
#: already declared in the repository.
BUILT = frozenset(
    {
        "acik_riza.core",
        "acik_riza.voice",
        "acik_riza.wellbeing",
        "acik_riza.lane.affect",
        "acik_riza.documents",
        "acik_riza.satisfaction",
        "acik_riza.share",
    }
)
AWAITING = frozenset(
    {
        "aydinlatma.app",
        "aydinlatma.kiosk",
        "aydinlatma.clinician",
        "aydinlatma.admin",
        "aydinlatma.web",
        "acik_riza.lane.linguistic",
        "acik_riza.learning.personal",
        "acik_riza.learning.service_improvement",
        "acik_riza.research",
    }
)


def _index() -> SyntheticLegalIndex:
    return SyntheticLegalIndex(ROOT, data_class=SYN)


def _copy_tree(tmp_path: Path) -> Path:
    target = tmp_path / "legal" / "synthetic"
    shutil.copytree(ROOT, target)
    return target


def _rehash(root: Path, document_id: str, path: Path) -> None:
    """Re-sign one row after a test edit, so the refusal under test is the one
    the edit is about and not the hash check."""
    raw = yaml.safe_load((root / "documents.yaml").read_text(encoding="utf-8"))
    for row in raw["documents"]:
        if row["id"] == document_id:
            row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "documents.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")


def _core_path(root: Path) -> Path:
    return root / "consents" / text_filename("core")


def _replace_body(path: Path, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    head, _, _ = text.partition("\n---\n")
    path.write_text(head + "\n---\n" + body, encoding="utf-8")


# --- the set ----------------------------------------------------------------------------


def test_the_synthetic_set_is_the_five_aydinlatma_and_the_eleven_acik_riza_ids() -> None:
    ids = synthetic_document_ids()
    assert len(ids) == 16
    assert {i for i in ids if i.startswith("aydinlatma.")} == {f"aydinlatma.{c}" for c in CHANNELS}
    assert {i for i in ids if i.startswith("acik_riza.")} == {
        "acik_riza." + p.replace(":", ".") for p in purpose_ids()
    }
    assert "acik_riza.lane.acoustic" not in ids  # files/06 §2.4: an ICF, not a toggle


def test_every_id_is_built_or_awaiting_human_and_never_both() -> None:
    index = _index().index()
    assert set(index.rows) == BUILT
    assert set(index.awaiting) == AWAITING
    assert BUILT | AWAITING == set(synthetic_document_ids())
    for row in index.awaiting.values():
        assert row.missing, row.id
        assert all(item.strip() for item in row.missing), row.id
        assert row.ask.strip(), row.id


def test_the_real_index_is_untouched_and_still_serves_nothing() -> None:
    real = LegalDocumentSet(REPO / "docs" / "legal")
    assert real.index() == {}
    assert real.available() == ()
    assert not (REPO / "docs" / "legal" / "consents").exists()
    assert INDEX != real.index_path


def test_no_fixed_strings_file_is_created_or_bound_here() -> None:
    """Invariant 18's fixed strings stay verbatim by staying untouched: the
    synthetic set has no row for them and the tree holds no strings file."""
    assert "strings" not in synthetic_document_ids()
    assert not (ROOT / "strings.yaml").exists()
    assert not (REPO / "docs" / "legal" / "strings.yaml").exists()


# --- loading the committed texts --------------------------------------------------------


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_every_built_text_is_hash_bound_versioned_and_visibly_marked(document_id: str) -> None:
    index = _index()
    row = index.index().rows[document_id]
    text = index.entry(document_id)
    raw = text.path.read_bytes()
    assert text.text_hash == hashlib.sha256(raw).hexdigest() == row.sha256
    assert text.version == row.version
    assert synthetic_marker_is_visible(text.body)
    first = next(line for line in text.body.splitlines() if line.strip())
    assert first.startswith("Sentetik test metni")


@pytest.mark.parametrize("document_id", sorted(AWAITING))
def test_every_unbuilt_id_refuses_as_missing_and_names_the_gap(document_id: str) -> None:
    with pytest.raises(LegalDocumentMissingError) as caught:
        _index().entry(document_id)
    assert "awaiting-human" in str(caught.value)


def test_available_is_exactly_the_built_set() -> None:
    assert set(_index().available()) == BUILT


# --- the data class gate ----------------------------------------------------------------


@pytest.mark.parametrize(
    "value", [None, "", "real_phi", "Synthetic", "synthetic ", "SYNTHETIC", "test"]
)
def test_anything_but_the_exact_literal_is_real_phi(value: str | None) -> None:
    environ = {} if value is None else {DATA_CLASS_ENV: value}
    assert deployment_data_class(environ) is DeploymentDataClass.REAL_PHI


def test_the_exact_literal_is_synthetic() -> None:
    assert deployment_data_class({DATA_CLASS_ENV: "synthetic"}) is SYN


def test_a_non_synthetic_data_class_refuses_the_synthetic_index() -> None:
    with pytest.raises(SyntheticLegalTreeRefusedError):
        SyntheticLegalIndex(ROOT, data_class=DeploymentDataClass.REAL_PHI)


def test_the_synthetic_tree_is_recognised_wherever_it_is_mounted(tmp_path: Path) -> None:
    assert within_synthetic_legal_tree(ROOT / "consents")
    assert within_synthetic_legal_tree(Path("docs/legal/synthetic/consents"))
    assert within_synthetic_legal_tree(tmp_path / "legal" / "synthetic" / "consents")
    # near misses: the real tree, and a directory merely named "synthetic"
    assert not within_synthetic_legal_tree(REPO / "docs" / "legal" / "consents")
    assert not within_synthetic_legal_tree(tmp_path / "synthetic" / "consents")


def test_a_symlink_into_the_synthetic_tree_is_still_the_synthetic_tree(tmp_path: Path) -> None:
    link = tmp_path / "consents"
    link.symlink_to(ROOT / "consents")
    assert within_synthetic_legal_tree(link)


# --- near misses: each one refused --------------------------------------------------------


def test_an_unmarked_text_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    _replace_body(path, "Açık rıza metni: Temel hizmet\n\nBeyanım: açık rıza veriyorum.\n")
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(SyntheticMarkerMissingError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_marker_only_in_the_front_matter_is_not_visible(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    version = SyntheticLegalIndex(root, data_class=SYN).index().rows["acik_riza.core"].version
    path.write_text(
        f"---\nconsent_text_version: {version}\n# {SYNTHETIC_MARKER}\n---\n"
        "Açık rıza metni: Temel hizmet\n",
        encoding="utf-8",
    )
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(SyntheticMarkerMissingError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_marker_below_the_first_line_is_not_visible(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    _replace_body(path, "Açık rıza metni: Temel hizmet\n\nSentetik test metni.\n")
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(SyntheticMarkerMissingError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_marker_inside_an_html_comment_is_not_visible(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    _replace_body(path, "<!-- Sentetik test metni -->\nAçık rıza metni: Temel hizmet\n")
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(SyntheticMarkerMissingError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_moved_byte_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(LegalDocumentHashMismatchError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_front_matter_version_that_drifted_from_the_index_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        re.sub(r"consent_text_version: \S+", "consent_text_version: 1999-01-01.x", text, count=1),
        encoding="utf-8",
    )
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(LegalDocumentInvalidError):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_a_performance_claim_is_refused_at_render(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    path = _core_path(root)
    path.write_text(
        # The render-time scanner is intake_platform.legal.claims, shared with
        # INT-210; its Turkish arm matches "doğruluk" (the softened "doğruluğu"
        # is caught by scripts/ci/claims_scan.sh, not by that module).
        path.read_text(encoding="utf-8") + "\nBu sistemin doğruluk oranı yüzde 99'dur.\n",
        encoding="utf-8",
    )
    _rehash(root, "acik_riza.core", path)
    with pytest.raises(LegalDocumentInvalidError, match="performance claim"):
        SyntheticLegalIndex(root, data_class=SYN).entry("acik_riza.core")


def test_an_index_that_does_not_declare_the_synthetic_class_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    raw = yaml.safe_load((root / "documents.yaml").read_text(encoding="utf-8"))
    raw["data_class"] = "real_phi"
    (root / "documents.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SyntheticLegalTreeRefusedError):
        SyntheticLegalIndex(root, data_class=SYN).index()


def test_the_real_index_cannot_be_loaded_as_a_synthetic_one() -> None:
    with pytest.raises(SyntheticLegalTreeRefusedError):
        SyntheticLegalIndex(REPO / "docs" / "legal", data_class=SYN).index()


@pytest.mark.parametrize("document_id", ["gizlilik", "strings", "acik_riza.lane.acoustic"])
def test_a_row_outside_the_sixteen_is_a_defect(tmp_path: Path, document_id: str) -> None:
    root = _copy_tree(tmp_path)
    raw = yaml.safe_load((root / "documents.yaml").read_text(encoding="utf-8"))
    raw["documents"].append({"id": document_id, "version": "v1", "sha256": "0" * 64})
    (root / "documents.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        SyntheticLegalIndex(root, data_class=SYN).index()


def test_a_duplicate_row_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    raw = yaml.safe_load((root / "documents.yaml").read_text(encoding="utf-8"))
    raw["documents"].append(dict(raw["documents"][0]))
    (root / "documents.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        SyntheticLegalIndex(root, data_class=SYN).index()


def test_an_id_both_built_and_awaiting_is_refused(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    raw = yaml.safe_load((root / "documents.yaml").read_text(encoding="utf-8"))
    raw["awaiting_human"].append({"id": "acik_riza.core", "missing": ["x"], "ask": "y"})
    (root / "documents.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        SyntheticLegalIndex(root, data_class=SYN).index()


def test_a_missing_index_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LegalDocumentMissingError):
        SyntheticLegalIndex(tmp_path / "legal" / "synthetic", data_class=SYN).index()


# --- the real-tenant catalog refuses a marked text -------------------------------------


def test_the_marker_is_recognised_in_either_turkish_case() -> None:
    assert carries_synthetic_marker("Sentetik test metni: yalnızca test.")
    assert carries_synthetic_marker("SENTETİK TEST METNİ")
    assert not carries_synthetic_marker("Sentetik test fikstürü metni (INT-038).")


def test_a_real_tenant_catalog_refuses_a_marked_text(tmp_path: Path) -> None:
    real_root = tmp_path / "legal" / "consents"
    real_root.mkdir(parents=True)
    shutil.copy(_core_path(ROOT), real_root / text_filename("core"))
    catalog = ConsentTextCatalog(real_root)
    with pytest.raises(ConsentTextInvalidError, match="synthetic"):
        catalog.entry("core")
    with pytest.raises(ConsentTextInvalidError):
        catalog.try_entry("core")


# --- what the texts may rest on -----------------------------------------------------------


def _sourced_retention_names() -> set[str]:
    policy = yaml.safe_load(RETENTION_POLICY.read_text(encoding="utf-8"))
    sourced = {row["data_class"] for row in policy["classes"] if row["status"] == "sourced"}
    return sourced | {row["data_class"] for row in policy["non_persisted"]}


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_every_built_text_rests_only_on_declared_inventory(document_id: str) -> None:
    grounds = _index().index().rows[document_id].grounds
    assert set(grounds) == {"retention", "recipients", "categories", "bases"}
    assert grounds["retention"], "a text with no declared retention is not built"
    assert set(grounds["retention"]) <= _sourced_retention_names()
    assert grounds["recipients"] and grounds["bases"]
    for name in (*grounds["recipients"], *grounds["categories"], *grounds["bases"]):
        value = getattr(inventory, name)
        assert isinstance(value, str)
        assert not value.startswith("awaiting-human"), name


def test_an_unsourced_retention_class_would_not_qualify() -> None:
    """Near miss for the test above: the two draft_needs_source classes are
    exactly the gaps that keep research and the consumer consent record unbuilt."""
    names = _sourced_retention_names()
    assert "research_extracts" not in names
    assert "consent_records_consumer_tenant" not in names


# --- what the texts say -------------------------------------------------------------------

_SEN_TOKENS = re.compile(r"(?i)\b(sen|senin|sana|seni|sende|senden|seninle)\b")


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_patient_copy_uses_the_siz_register(document_id: str) -> None:
    body = _index().entry(document_id).body
    assert not _SEN_TOKENS.search(body)


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_policyguard_finds_nothing_in_any_sentence(document_id: str) -> None:
    """Invariant 2's arms, sentence by sentence: no diagnosis, treatment or
    prognosis language, no singular second person, and every sentence within
    the signed lexicon's B1 word limit. Labels sit on their own lines, so a
    label is its own sentence and does not lengthen the one after it."""
    from intake_voice_runtime.profiles import VoiceProfile
    from intake_voice_runtime.talker.policy_guard import policy_guard_for

    guard = policy_guard_for(locale="tr", profile=VoiceProfile.TYPED)
    body = _index().entry(document_id).body
    findings = [
        (violation.violation_class.value, sentence)
        for line in body.splitlines()
        for sentence in guard.sentences(line)
        for violation in guard.inspect_sentence(sentence)
    ]
    assert findings == []


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_every_acik_riza_text_ends_with_the_subjects_own_declaration(document_id: str) -> None:
    """Board principle decision 2026/347: the person declares consent to the
    purposes and legal grounds the text states."""
    body = _index().entry(document_id).body
    last = [line for line in body.splitlines() if line.strip()][-1]
    assert last.startswith("Beyanım:")
    assert last.rstrip().endswith("açık rıza veriyorum.")


@pytest.mark.parametrize("document_id", sorted(BUILT))
def test_every_text_states_its_legal_ground_and_where_it_runs(document_id: str) -> None:
    body = _index().entry(document_id).body
    assert "Hukuki sebep:" in body
    assert "ABD" in body  # the synthetic host is in us-east-1; never "Türkiye'de kalır"
    assert "Türkiye'deki sunucularda kalır" not in body


_LANE_ORDER = ("Ne için:", "Ses kimlere gider:", "Nerede:", "Ne kadar saklanır:", "Geri çekme:")


@pytest.mark.parametrize("document_id", ["acik_riza.voice", "acik_riza.lane.affect"])
def test_lane_texts_state_the_five_files06_items_in_order(document_id: str) -> None:
    """files/06 §2.1: purpose; vendor; whether audio or only text leaves
    Türkiye; retention; how to withdraw — in that order."""
    body = _index().entry(document_id).body
    positions = [body.index(label) for label in _LANE_ORDER]
    assert positions == sorted(positions)


#: The sentences that are true only while no outside party can receive the data.
#: Two routes could make them false, and both are tripwires here:
#: - ADR-035 (INT-428) lets the synthetic deployment switch speech recognition,
#:   extraction and speech output to a hosted provider; it fails closed until that
#:   provider's egress row is listed;
#: - any PHI-path egress row. The one admitted purpose is ``sms_otp_delivery``
#:   (INT-528's Netgsm row): it carries the sign-in number and code, never audio
#:   or answers, so none of these sentences speaks about it.
#: When either trips, the texts below must name the recipient (legal name and
#: country) in the same change — files/06 §2.1's consent/vendor parity — which
#: re-binds their hashes.
_NO_VENDOR_SENTENCES = {
    "acik_riza.voice": "Sesiniz hiçbir dış şirkete gönderilmez.",
    "acik_riza.core": "yalnızca hizmeti çalıştıran sistemlerimizde işlenir.",
    "acik_riza.documents": "yalnızca hizmeti çalıştıran sistemlerimizde işlenir.",
}
#: The PHI-path purpose these sentences do not cover, and why: see above.
_PHI_PATH_PURPOSES_OUTSIDE_THE_TEXTS = frozenset({"sms_otp_delivery"})


def _allowlist() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(
        (REPO / "infra" / "security" / "egress-allowlist.yaml").read_text(encoding="utf-8")
    )
    return loaded


def _vendor_rows_the_texts_deny(allowlist: dict[str, object]) -> list[str]:
    providers = yaml.safe_load(
        (REPO / "infra" / "model-lanes" / "providers.yaml").read_text(encoding="utf-8")
    )
    hosted_rows = {provider["egress_row"] for provider in providers["providers"]}
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    hosted = [
        str(row["name"])
        for rows in tiers.values()
        for row in rows or []
        if row.get("name") in hosted_rows or row.get("purpose_id") == "hosted_model_inference"
    ]
    phi = [
        str(row.get("name"))
        for row in tiers.get("phi_path") or []
        if row.get("purpose_id") not in _PHI_PATH_PURPOSES_OUTSIDE_THE_TEXTS
    ]
    return hosted + phi


def test_no_vendor_sentences_hold_only_while_no_such_row_is_listed() -> None:
    for document_id, sentence in _NO_VENDOR_SENTENCES.items():
        assert sentence in _index().entry(document_id).body, document_id
    listed = _vendor_rows_the_texts_deny(_allowlist())
    assert listed == [], (
        f"egress rows {listed} reach an outside party: name it in "
        f"{sorted(_NO_VENDOR_SENTENCES)} (files/06 §2.1) and re-sign the synthetic index"
    )


@pytest.mark.parametrize(
    ("tier", "row"),
    [
        ("phi_path", {"name": "sms-otp", "purpose_id": "sms_otp_delivery"}),
        ("phi_path", {"name": "asr-vendor", "purpose_id": "clinical_transcription"}),
        ("dev", {"name": "openai-api", "purpose_id": "hosted_model_inference"}),
    ],
)
def test_the_tripwire_admits_only_the_sign_in_sms_row(tier: str, row: dict[str, str]) -> None:
    """Near miss for the test above, on a copy of the allow-list: the Netgsm
    sign-in row passes; any other PHI-path row, or a hosted lane row, trips."""
    allowlist = _allowlist()
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    tiers[tier] = [*(tiers.get(tier) or []), row]
    expected = [] if row["purpose_id"] == "sms_otp_delivery" else [row["name"]]
    assert _vendor_rows_the_texts_deny(allowlist) == expected


def test_the_affect_text_says_what_files06_2_1_requires() -> None:
    body = _index().entry("acik_riza.lane.affect").body
    assert "sesinizin tonundan" in body
    assert "duygu tanıma sistemi" in body
    assert "Bu ipuçları tanı koymaz." in body
    assert "hekiminize bir değerlendirme olarak gönderilmez" in body


# --- the gates ----------------------------------------------------------------------------


def _tree_files() -> list[str]:
    return sorted(str(p.relative_to(REPO)) for p in ROOT.rglob("*") if p.is_file())


def test_the_claims_scan_passes_on_the_synthetic_tree() -> None:
    result = subprocess.run(
        ["bash", "scripts/ci/claims_scan.sh", *_tree_files()],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_phi_scan_passes_on_the_synthetic_tree() -> None:
    result = subprocess.run(
        ["bash", "scripts/ci/phi_scan.sh", *_tree_files()],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
