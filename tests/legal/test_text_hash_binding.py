"""INT-210 — the docs/legal document set, hash-bound and signed (invariant 18).

CLAUDE.md invariant 18: *"consent and legal texts render only from
``docs/legal/`` with hash binding; the fixed strings in
``docs/legal/strings.yaml`` are verbatim."* INT-038 bound the eleven açık rıza
texts one file at a time; this suite binds the **set** — the five per-channel
aydınlatma metinleri, those eleven, the gizlilik policy, the kullanım koşulları,
the KVKK başvuru formu, the çerez policy and the fixed strings — and adds the
two things a per-file loader cannot express: a **plain-language summary** beside
every patient-facing document, and a **counsel sign-off** without which the
document is unservable.

Nothing here authors legal copy. Every fixture is synthetic and says so; the
real texts are human legal work and the committed index is empty, which
``test_the_committed_index_declares_nothing_so_nothing_renders`` pins against
the real tree.

Four near-miss controls, each a different way to fake the gate: bytes that no
longer hash to the recorded value; a document nobody signed; a one-byte edit to
a fixed string, which invariant 18's second sentence makes verbatim; and — the
control that makes the other three mean anything — a well-formed, summarised,
signed document that **is** served.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.consent import CHANNELS, purpose_ids, text_filename
from intake_platform.legal import (
    LEGAL_INDEX_FILENAME,
    DocumentKind,
    LegalAcceptance,
    LegalDocumentHashMismatchError,
    LegalDocumentInvalidError,
    LegalDocumentMissingError,
    LegalDocumentSet,
    LegalDocumentUnsignedError,
    UnknownLegalDocumentError,
    document_ids,
    record_acceptance,
    required_document,
)

REPO = Path(__file__).resolve().parents[2]

BODY_TR = (
    "Sentetik test metni (INT-210). Bu satirlar hukuki bir metin degildir; "
    "yalnizca hash baglamayi ve imza kapisini sinar.\n"
)
SUMMARY_TR = "Sentetik sade dil ozeti (INT-210). Gercek ozet insan isidir.\n"
COUNSEL = (
    "    counsel:\n"
    '      signed_by: "Sentetik Test Danismani"\n'
    "      signed_on: 2026-09-03\n"
    '      evidence: "docs/evidence/INT-210.md#counsel-sign-off"\n'
)
ACTOR = "patient:11111111-1111-4111-8111-111111111111"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_document(
    root: Path, document_id: str, *, body: str = BODY_TR, summary: str | None = SUMMARY_TR
) -> None:
    """The one or two files a document is made of, at the registry's paths."""
    required = required_document(document_id)
    path = root / required.relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if required.summary_path is not None and summary is not None:
        summary_path = root / required.summary_path
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary, encoding="utf-8")


def _write_index(root: Path, documents_block: str, *, version: str = "test-fixture.1") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / LEGAL_INDEX_FILENAME
    tail = f"documents:\n{documents_block}" if documents_block.strip() else "documents: []\n"
    path.write_text(f'legal_index_version: "{version}"\n{tail}', encoding="utf-8")
    return path


def _index(
    root: Path,
    document_id: str,
    *,
    version: str = "test-fixture.1",
    sha256: str | None = None,
    summary_sha256: str | None = None,
    counsel: str = COUNSEL,
) -> Path:
    """One index row, in the committed file's shape."""
    required = required_document(document_id)
    rows = [
        f'  - id: "{document_id}"\n',
        f'    version: "{version}"\n',
        f'    sha256: "{sha256 if sha256 is not None else _sha256(BODY_TR)}"\n',
    ]
    if required.summary_path is not None:
        digest = summary_sha256 if summary_sha256 is not None else _sha256(SUMMARY_TR)
        rows.append(f'    summary_sha256: "{digest}"\n')
    rows.append(counsel)
    return _write_index(root, "".join(rows))


def _signed(root: Path, document_id: str = "gizlilik") -> LegalDocumentSet:
    """A tree holding exactly one well-formed, summarised, signed document."""
    _write_document(root, document_id)
    _index(root, document_id)
    return LegalDocumentSet(root)


# --- the required set ---------------------------------------------------------------------


def test_the_required_set_is_the_document_set_the_issue_names() -> None:
    """aydınlatma ×5, açık rıza per purpose, gizlilik, kullanım koşulları,
    KVKK başvuru formu, çerez — plus the files/06 §7 fixed strings, which are
    the second half of invariant 18's sentence."""
    by_kind: dict[DocumentKind, list[str]] = {}
    for required in map(required_document, document_ids()):
        by_kind.setdefault(required.kind, []).append(required.id)

    # Five, one per channel files/06 §1 names — not five of our own choosing.
    assert by_kind[DocumentKind.AYDINLATMA] == [f"aydinlatma.{c}" for c in CHANNELS]
    assert len(by_kind[DocumentKind.AYDINLATMA]) == 5
    assert by_kind[DocumentKind.ACIK_RIZA] == [
        "acik_riza." + p.replace(":", ".") for p in purpose_ids()
    ]
    assert by_kind[DocumentKind.GIZLILIK] == ["gizlilik"]
    assert by_kind[DocumentKind.KULLANIM_KOSULLARI] == ["kullanim_kosullari"]
    assert by_kind[DocumentKind.KVKK_BASVURU] == ["kvkk_basvuru_formu"]
    assert by_kind[DocumentKind.CEREZ] == ["cerez"]
    assert by_kind[DocumentKind.FIXED_STRINGS] == ["strings"]


def test_the_acoustic_icf_has_no_row_in_this_set() -> None:
    """files/06 §2.4 makes it an investigational-device ICF under TCKAY — a
    different artefact with a different process, not a {version, text_hash}
    row. The consent registry rejects it by name for the same reason."""
    assert not [doc_id for doc_id in document_ids() if "acoustic" in doc_id]


def test_the_acik_riza_rows_reuse_the_int_038_filenames() -> None:
    """One binding, not two: the açık rıza half of this set is the same eleven
    files ``intake_platform.consent.texts`` already loads, so a text cannot be
    signed here and absent there."""
    for purpose in purpose_ids():
        required = required_document("acik_riza." + purpose.replace(":", "."))
        assert required.relative_path == f"consents/{text_filename(purpose)}"


def test_an_unknown_document_id_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(UnknownLegalDocumentError):
        required_document("aydinlatma.billboard")


# --- the committed tree, today ------------------------------------------------------------


def test_the_committed_index_declares_nothing_so_nothing_renders() -> None:
    """The state INT-210 ships in: the mechanism is complete, the gate is
    wired, the content is empty because it is counsel's to author. If this
    ever fails a document was signed — update the evidence file, do not relax
    the assertion."""
    documents = LegalDocumentSet(REPO / "docs" / "legal")
    assert documents.available() == ()
    for document_id in document_ids():
        with pytest.raises(LegalDocumentMissingError):
            documents.entry(document_id)


def test_a_missing_index_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LegalDocumentMissingError):
        LegalDocumentSet(tmp_path / "legal").entry("gizlilik")


# --- the positive control -----------------------------------------------------------------


def test_a_signed_well_formed_summarised_document_is_served(tmp_path: Path) -> None:
    documents = _signed(tmp_path / "legal")
    entry = documents.entry("gizlilik")

    assert entry.id == "gizlilik"
    assert entry.kind is DocumentKind.GIZLILIK
    assert entry.version == "test-fixture.1"
    assert entry.text_hash == _sha256(BODY_TR)
    assert entry.summary_hash == _sha256(SUMMARY_TR)
    assert entry.body == BODY_TR
    assert entry.summary == SUMMARY_TR
    assert entry.counsel.signed_by == "Sentetik Test Danismani"
    assert entry.counsel.signed_on == date(2026, 9, 3)
    assert documents.available() == ("gizlilik",)


def test_the_hash_covers_the_exact_file_bytes(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    documents = _signed(root)
    on_disk = (root / required_document("gizlilik").relative_path).read_bytes()
    assert documents.entry("gizlilik").text_hash == hashlib.sha256(on_disk).hexdigest()


def test_render_reads_the_source_on_every_call(tmp_path: Path) -> None:
    """The "rendered in-app from source" clause is a property of the read,
    not of a cache: a document edited under a live process stops rendering
    rather than serving bytes nobody signed."""
    root = tmp_path / "legal"
    documents = _signed(root)
    assert documents.render("gizlilik").body == BODY_TR

    path = root / required_document("gizlilik").relative_path
    path.write_text(BODY_TR + "sonradan eklenen satir\n", encoding="utf-8")
    with pytest.raises(LegalDocumentHashMismatchError):
        documents.render("gizlilik")


# --- near-miss 1: the bytes moved ----------------------------------------------------------


def test_a_recorded_hash_that_does_not_match_the_bytes_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", sha256=_sha256(BODY_TR + " "))  # one trailing space
    with pytest.raises(LegalDocumentHashMismatchError):
        LegalDocumentSet(root).entry("gizlilik")


def test_a_summary_whose_hash_moved_is_refused(tmp_path: Path) -> None:
    """The summary is bound as tightly as the document it summarises — drift
    between the two is exactly what this clause exists to prevent."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", summary_sha256=_sha256(SUMMARY_TR + " "))
    with pytest.raises(LegalDocumentHashMismatchError):
        LegalDocumentSet(root).entry("gizlilik")


def test_a_document_with_no_plain_language_summary_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik", summary=None)
    _index(root, "gizlilik")
    with pytest.raises(LegalDocumentMissingError):
        LegalDocumentSet(root).entry("gizlilik")


# --- near-miss 2: nobody signed it ---------------------------------------------------------


def test_a_document_with_no_counsel_signoff_is_refused(tmp_path: Path) -> None:
    """Everything else is in order — the file is there, the hash matches, the
    summary is bound. It still does not serve."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", counsel="")
    with pytest.raises(LegalDocumentUnsignedError):
        LegalDocumentSet(root).entry("gizlilik")


@pytest.mark.parametrize(
    "partial",
    [
        '    counsel:\n      signed_on: 2026-09-03\n      evidence: "docs/evidence/INT-210.md"\n',
        '    counsel:\n      signed_by: "X"\n      evidence: "docs/evidence/INT-210.md"\n',
        '    counsel:\n      signed_by: "X"\n      signed_on: 2026-09-03\n',
        '    counsel:\n      signed_by: ""\n      signed_on: 2026-09-03\n'
        '      evidence: "docs/evidence/INT-210.md"\n',
    ],
    ids=["no-signer", "no-date", "no-evidence", "empty-signer"],
)
def test_a_signoff_missing_any_of_its_three_facts_is_not_a_signoff(
    tmp_path: Path, partial: str
) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", counsel=partial)
    with pytest.raises(LegalDocumentUnsignedError):
        LegalDocumentSet(root).entry("gizlilik")


def test_the_signoff_must_point_at_the_evidence_file_the_acceptance_names(
    tmp_path: Path,
) -> None:
    """The acceptance says "counsel sign-off recorded in evidence file before
    merge". A sign-off pointing anywhere else is unrecorded."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(
        root,
        "gizlilik",
        counsel=(
            "    counsel:\n"
            '      signed_by: "Sentetik Test Danismani"\n'
            "      signed_on: 2026-09-03\n"
            '      evidence: "docs/legal/somewhere-else.md"\n'
        ),
    )
    with pytest.raises(LegalDocumentUnsignedError):
        LegalDocumentSet(root).entry("gizlilik")


# --- near-miss 3: a fixed string moved by one byte -----------------------------------------


def test_a_one_byte_change_to_a_fixed_string_is_refused(tmp_path: Path) -> None:
    """Invariant 18: the fixed strings of files/06 §7 are VERBATIM. The index
    binds ``strings.yaml`` like every other document, so a single glyph is the
    whole difference between served and refused."""
    root = tmp_path / "legal"
    original = (
        "---\nlegal_strings_version: test-fixture.1\n---\n"
        'dsar_export.title: "Sentetik test basligi"\n'
    )
    _write_document(root, "strings", body=original, summary=None)
    _index(root, "strings", sha256=_sha256(original))
    assert LegalDocumentSet(root).entry("strings").text_hash == _sha256(original)

    moved = original.replace("basligi", "baslığı")
    (root / required_document("strings").relative_path).write_text(moved, encoding="utf-8")
    with pytest.raises(LegalDocumentHashMismatchError):
        LegalDocumentSet(root).entry("strings")


def test_the_fixed_strings_carry_no_plain_language_summary() -> None:
    """They are not a document a patient reads end to end; they are the
    verbatim sentences other documents embed. A summary of them would be a
    paraphrase of copy that may not be paraphrased."""
    assert required_document("strings").summary_path is None


# --- invariant 20 -------------------------------------------------------------------------


def test_a_performance_claim_in_a_legal_document_is_refused(tmp_path: Path) -> None:
    """Invariant 20 scans this tree in CI. The loader refuses at render too,
    so a claim cannot reach a patient between a merge and a scan."""
    root = tmp_path / "legal"
    claim = BODY_TR + "Sistemin sensitivity degeri yuksektir.\n"
    _write_document(root, "gizlilik", body=claim)
    _index(root, "gizlilik", sha256=_sha256(claim))
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).entry("gizlilik")


def test_a_performance_claim_in_a_summary_is_refused_too(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    claim = "Sentetik ozet. Olcum AUROC ile ifade edilir.\n"
    _write_document(root, "gizlilik", summary=claim)
    _index(root, "gizlilik", summary_sha256=_sha256(claim))
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).entry("gizlilik")


# --- the index's own contract --------------------------------------------------------------


def test_an_index_row_for_an_unknown_document_is_a_defect_not_an_extra(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_index(
        root,
        f'  - id: "aydinlatma.billboard"\n    version: "v1"\n    sha256: "{"0" * 64}"\n' + COUNSEL,
    )
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_duplicate_index_row_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    row = f'  - id: "gizlilik"\n    version: "v1"\n    sha256: "{_sha256(BODY_TR)}"\n'
    row += f'    summary_sha256: "{_sha256(SUMMARY_TR)}"\n' + COUNSEL
    _write_index(root, row + row)
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_an_index_with_no_version_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir(parents=True, exist_ok=True)
    (root / LEGAL_INDEX_FILENAME).write_text("documents: []\n", encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_hash_that_is_not_a_sha256_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", sha256="not-a-digest")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_an_empty_document_body_is_invalid_not_absent(tmp_path: Path) -> None:
    """The same rule the consent-text loader keeps: a scaffold is a defect in
    the legal tree, never a quiet absence."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik", body="   \n")
    _index(root, "gizlilik", sha256=_sha256("   \n"))
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).entry("gizlilik")


def test_a_declared_document_whose_file_is_absent_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir(parents=True)
    _index(root, "gizlilik")
    with pytest.raises(LegalDocumentMissingError):
        LegalDocumentSet(root).entry("gizlilik")


# --- acceptance evidence -------------------------------------------------------------------


def test_acceptance_evidence_binds_the_version_and_the_hash(tmp_path: Path) -> None:
    documents = _signed(tmp_path / "legal")
    acceptance = record_acceptance(
        AuditChain(InMemoryAuditStore()),
        documents.render("gizlilik"),
        actor=ACTOR,
        channel="app",
    )

    assert isinstance(acceptance, LegalAcceptance)
    assert acceptance.document_id == "gizlilik"
    assert acceptance.version == "test-fixture.1"
    assert acceptance.text_hash == _sha256(BODY_TR)
    assert acceptance.summary_hash == _sha256(SUMMARY_TR)
    assert acceptance.channel == "app"
    assert acceptance.audit_seq == 1


def test_acceptance_is_written_to_the_hash_chained_audit_log(tmp_path: Path) -> None:
    """Invariant 4's log is the store: a record of what was shown that a later
    edit of a row cannot silently change."""
    store = InMemoryAuditStore()
    documents = _signed(tmp_path / "legal")
    record_acceptance(AuditChain(store), documents.render("gizlilik"), actor=ACTOR, channel="app")

    (entry,) = store.entries()
    assert entry.action == "legal_document.accepted"
    assert entry.resource_ref == (
        f"legal_document:gizlilik@test-fixture.1/sha256:{_sha256(BODY_TR)}"
    )
    assert entry.consent_scope_ref == "basis:KVKK-10"
    assert AuditChain(store).verify().ok


def test_acceptance_carries_no_copy_only_ids(tmp_path: Path) -> None:
    """Invariant 6. The audit entry proves WHICH bytes were shown; it never
    carries them."""
    store = InMemoryAuditStore()
    documents = _signed(tmp_path / "legal")
    record_acceptance(AuditChain(store), documents.render("gizlilik"), actor=ACTOR, channel="app")

    (entry,) = store.entries()
    for field in (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref):
        assert "Sentetik" not in field


def test_an_unknown_channel_is_refused(tmp_path: Path) -> None:
    """The channels are files/06 §1's five. An acceptance recorded against a
    sixth would claim an aydınlatma surface that does not exist."""
    documents = _signed(tmp_path / "legal")
    with pytest.raises(LegalDocumentInvalidError):
        record_acceptance(
            AuditChain(InMemoryAuditStore()),
            documents.render("gizlilik"),
            actor=ACTOR,
            channel="billboard",
        )


def test_no_acceptance_can_be_recorded_for_an_unservable_document(tmp_path: Path) -> None:
    """The refusal is structural rather than a check at the call site: there
    is no way to obtain the rendered document an acceptance needs."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", counsel="")
    with pytest.raises(LegalDocumentUnsignedError):
        LegalDocumentSet(root).render("gizlilik")


# --- the remaining index refusals, each a branch a gate is made of -------------------------


def test_an_index_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir(parents=True)
    (root / LEGAL_INDEX_FILENAME).write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_an_index_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir(parents=True)
    (root / LEGAL_INDEX_FILENAME).write_text("legal_index_version: [\n", encoding="utf-8")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_documents_value_that_is_not_a_list_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir(parents=True)
    (root / LEGAL_INDEX_FILENAME).write_text(
        'legal_index_version: "v1"\ndocuments: "gizlilik"\n', encoding="utf-8"
    )
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_an_index_row_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_index(root, "  - gizlilik\n")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_malformed_version_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", version="sürüm 1")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_summary_hash_that_is_not_a_sha256_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", summary_sha256="not-a-digest")
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_a_document_that_is_not_utf8_is_invalid_not_absent(tmp_path: Path) -> None:
    """A legal text this repository cannot decode is a defect in the legal
    tree, and Turkish makes the encoding question a live one."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    path = root / required_document("gizlilik").relative_path
    path.write_bytes("Gizlilik".encode("iso-8859-9") + b"\xff\xfe")
    _index(root, "gizlilik", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).entry("gizlilik")


def test_an_empty_summary_is_invalid_not_absent(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_document(root, "gizlilik", summary="  \n")
    _index(root, "gizlilik", summary_sha256=_sha256("  \n"))
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).entry("gizlilik")


def test_available_skips_a_declared_document_that_does_not_resolve(tmp_path: Path) -> None:
    """``available()`` answers what renders, not what was declared — a signed
    row whose bytes moved is absent from it rather than listed and broken."""
    root = tmp_path / "legal"
    _write_document(root, "gizlilik")
    _index(root, "gizlilik", sha256="0" * 64)
    assert LegalDocumentSet(root).available() == ()


def test_the_acceptance_instant_is_the_callers_clock_not_a_guess(tmp_path: Path) -> None:
    documents = _signed(tmp_path / "legal")
    stamp = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    acceptance = record_acceptance(
        AuditChain(InMemoryAuditStore()),
        documents.render("gizlilik"),
        actor=ACTOR,
        channel="kiosk",
        now=stamp,
    )
    assert acceptance.accepted_at == stamp
    assert acceptance.channel == "kiosk"


def test_the_fixed_strings_accept_with_no_summary_hash(tmp_path: Path) -> None:
    """The one document without a summary still binds, and its acceptance
    records ``summary_hash`` as absent rather than as an empty digest."""
    root = tmp_path / "legal"
    body = '---\nlegal_strings_version: test-fixture.1\n---\ndsar_export.title: "X"\n'
    _write_document(root, "strings", body=body, summary=None)
    _index(root, "strings", sha256=_sha256(body))
    acceptance = record_acceptance(
        AuditChain(InMemoryAuditStore()),
        LegalDocumentSet(root).render("strings"),
        actor=ACTOR,
        channel="app",
    )
    assert acceptance.summary_hash is None


def test_a_row_missing_a_required_key_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    _write_index(root, '  - version: "v1"\n    sha256: "' + "0" * 64 + '"\n' + COUNSEL)
    with pytest.raises(LegalDocumentInvalidError):
        LegalDocumentSet(root).index()


def test_available_is_empty_when_there_is_no_index_at_all(tmp_path: Path) -> None:
    """The absent-index case answers "nothing renders" rather than raising:
    a surface asking what it may show gets an empty list, never a crash and
    never a default."""
    documents = LegalDocumentSet(tmp_path / "legal")
    assert documents.available() == ()
    assert documents.root == tmp_path / "legal"
    assert documents.index_path == tmp_path / "legal" / LEGAL_INDEX_FILENAME
