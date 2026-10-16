"""INT-224 — store compliance: Apple health guidelines, Google Play Health
policy, Data safety / App Privacy labels and IARC (CLAUDE.md invariants 18 and
20; files/06 §1 row ``STORE``; sec_row ``mobile``).

Acceptance lines under test, verbatim from docs/backlog/issues.yaml:

  "checklists as tests where automatable; labels generated from the data
   inventory (single source)"

Five groups, in the order the harm arrives:

1. **The single source is the data inventory, and the inventory is bigger than
   the schema.** files/06 §1 says the labels are "generated from the single
   data inventory so they can never drift from reality". The schema
   annotations (invariant 18, ``Column.info["inventory"]``) are the persisted
   half. The other half is real and has no column: the microphone audio that
   invariant 3 forbids anyone to write, the health-platform reads that stay on
   the device, the uploaded document bytes in object storage, and crash
   diagnostics. A declaration derived from columns alone would tell both
   stores that this product does not process voice — which is false, and
   false in the one direction a reviewer notices. So the derivation runs over
   both halves and the app's own permission manifest is cross-checked against
   it, which is what makes "single source" a property rather than a promise.

2. **No vendor taxonomy is invented.** Apple's App Privacy data types, Google
   Play's Data safety categories, its Health apps policy and the IARC
   questionnaire are published artefacts that move. Nothing here paraphrases
   one from memory: the loader demands a committed, dated, hash-bound verbatim
   snapshot, and refuses without it (HB-A12). The derivation is fully built and
   fully exercised against fixture taxonomies; only the vendors' own words are
   missing, and they are missing loudly.

3. **A store listing is a regulatory document.** Two gates run on it. App
   Review 1.4.1 — quoted verbatim in ADR-022 and files/00 §3 D16 — rejects
   health-accuracy claims that cannot be validated, so the listing tree sits
   inside the invariant-20 claims gate rather than beside it. And a listing
   that describes automated triage or automated instrument interpretation is
   claiming a `device_functions` capability that stays off without a CE
   certificate or a clinical-investigation approval id (invariant 18,
   files/06 §0.3), so it fails closed instead of relying on App Review to
   notice. The near-miss control is the *permitted* copy: the fixed
   disclaimers of files/06 §7 contain the word "tanı" and must survive.

4. **Every checklist row is automatable or blocked — never quietly green.** A
   row with a check names the committed file its obligation comes from; a row
   without one names a HUMAN_BLOCKERS id that exists.

5. **The claims gate has one pattern set in one place.** docs/security
   (INT-020), docs/legal including the new store subtree, and docs/regulatory
   when it exists, all scan through ``intake_platform.legal.claims``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml
from intake_platform.db import models
from intake_platform.db.inventory import INVENTORY_FIELDS, INVENTORY_KEY
from intake_platform.legal import claims
from intake_platform.store import checklist as checklist_mod
from intake_platform.store import declaration as declaration_mod
from intake_platform.store import facts as facts_mod
from intake_platform.store import listing as listing_mod
from intake_platform.store import taxonomy as taxonomy_mod

REPO = Path(__file__).resolve().parents[2]
APP_JSON = REPO / "apps" / "mobile" / "app.json"
LOCALES = (
    REPO / "apps" / "mobile" / "src" / "locales" / "app-tr.json",
    REPO / "apps" / "mobile" / "src" / "locales" / "app-en.json",
)

# files/06 §7 — the fixed legal copy. Quoted here as the near-miss control for
# the device-claim lexicon: every one of these strings is copy we are REQUIRED
# to show, and two of them contain the word the lexicon hunts for.
FIXED_DISCLAIMERS = (
    "Bu belge hastanın beyanına dayanır; hekim değerlendirmesinin yerine geçmez. "
    "İçerik yapay zekâ desteğiyle yapılandırılmıştır ve tanı niteliği taşımaz.",
    "Acil bir durum yaşıyorsanız 112'yi arayın veya en yakın acil servise başvurun.",
    "Yapay zekâ tarafından üretilmiş sinyal — tanı değildir.",
    "Bu ölçümler kayıt koşullarından etkilenir ve bir değerlendirme değildir.",
)


# --------------------------------------------------------------------------------------
# 1. the single source: the data inventory, both halves
# --------------------------------------------------------------------------------------


def _schema_annotations() -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    for name, table in sorted(models.Base.metadata.tables.items()):
        for column in table.columns:
            out.append((f"{name}.{column.name}", dict(column.info[INVENTORY_KEY])))
    return out


def test_schema_facts_are_exactly_the_distinct_category_sharing_pairs() -> None:
    """No fact is authored: the persisted half of the declaration is a fold of
    the annotations already on the columns, and nothing else."""
    expected = {
        (a["category"], facts_mod.RECIPIENT_SHARING[a["recipients"]])
        for _, a in _schema_annotations()
    }
    got = {(f.category, f.sharing) for f in facts_mod.data_facts() if f.origin == "schema"}
    assert got == expected


def test_every_schema_fact_names_the_columns_it_folds() -> None:
    columns = {where for where, _ in _schema_annotations()}
    folded: set[str] = set()
    for fact in facts_mod.data_facts():
        if fact.origin == "schema":
            assert fact.columns, f"{fact.fact_id} folds no column"
            folded.update(fact.columns)
    assert folded == columns


def test_an_unclassified_recipient_is_refused_rather_than_defaulted() -> None:
    """A new recipient string is a new disclosure. It must stop the build, not
    fall through to 'not shared'."""
    with pytest.raises(facts_mod.UnclassifiedRecipientError, match="recipient"):
        facts_mod.sharing_for("a recipient nobody has classified")


def test_the_recipient_table_covers_every_recipient_the_schema_uses() -> None:
    used = {a["recipients"] for _, a in _schema_annotations()}
    assert used <= set(facts_mod.RECIPIENT_SHARING)


def test_off_schema_flows_carry_the_same_complete_annotation() -> None:
    """Invariant 18's five fields are the shape of an inventory row whether or
    not a column holds the data."""
    assert facts_mod.OFF_SCHEMA_FLOWS, "the off-schema half of the inventory is empty"
    for flow in facts_mod.OFF_SCHEMA_FLOWS.values():
        assert set(flow.annotation) == set(INVENTORY_FIELDS), flow.flow_id
        for field_name in INVENTORY_FIELDS:
            assert flow.annotation[field_name].strip(), f"{flow.flow_id}.{field_name} is empty"
        assert flow.source.strip(), f"{flow.flow_id} cites no file for its facts"


def test_every_off_schema_flow_cites_a_file_that_exists() -> None:
    for flow in facts_mod.OFF_SCHEMA_FLOWS.values():
        assert (REPO / flow.source_path).exists(), f"{flow.flow_id} cites {flow.source_path}"


def test_microphone_audio_is_a_fact_although_no_column_holds_it() -> None:
    """The finding this issue exists to prevent. Invariant 3 forbids writing
    raw audio, so the schema has no audio row — and a label derived from the
    schema alone would declare that the app does not process voice."""
    schema_categories = {a["category"] for _, a in _schema_annotations()}
    assert "voice_audio" not in schema_categories
    audio = [f for f in facts_mod.data_facts() if f.fact_id == "flow:voice_audio"]
    assert len(audio) == 1
    assert audio[0].persisted is False
    assert audio[0].origin == "flow"


def test_declared_app_permissions_are_read_from_the_shipped_manifest() -> None:
    declared = facts_mod.declared_app_permissions(APP_JSON, LOCALES)
    android = json.loads(APP_JSON.read_text(encoding="utf-8"))["expo"]["android"]["permissions"]
    assert set(android) <= set(declared)
    assert "NSMicrophoneUsageDescription" in declared
    assert "NSHealthShareUsageDescription" in declared


def test_every_declared_permission_is_classified_against_the_inventory() -> None:
    """The drift gate, in the direction a store reviewer walks: the app asks
    for a capability, so something in the inventory must account for it — or
    the classification must say, in writing, that it carries no personal
    data."""
    unclassified = facts_mod.unclassified_permissions(APP_JSON, LOCALES)
    assert unclassified == (), f"app permissions with no inventory row: {unclassified}"


def test_every_permission_classification_resolves_to_a_real_flow_or_states_why_not() -> None:
    flows = set(facts_mod.OFF_SCHEMA_FLOWS)
    for entry in facts_mod.PERMISSION_CLASSIFICATION.values():
        assert entry.reason.strip(), f"{entry.permission} carries no reason"
        if entry.flow_id is not None:
            assert entry.flow_id in flows, f"{entry.permission} names unknown flow {entry.flow_id}"


def test_no_classification_exists_for_a_permission_the_app_does_not_declare() -> None:
    """A classification the manifest no longer needs is a claim about a
    capability we do not have; it drifts silently in the other direction."""
    declared = set(facts_mod.declared_app_permissions(APP_JSON, LOCALES))
    stale = sorted(set(facts_mod.PERMISSION_CLASSIFICATION) - declared)
    assert stale == [], f"classified but not declared: {stale}"


def test_data_facts_are_deterministic_and_sorted() -> None:
    first = facts_mod.data_facts()
    assert first == facts_mod.data_facts()
    assert list(first) == sorted(first)


# --------------------------------------------------------------------------------------
# 2. the vendor taxonomy: fail closed on a snapshot nobody has committed
# --------------------------------------------------------------------------------------

FIXTURE_SNAPSHOT = (
    "Fixture text standing in for a published store form. It is not a quotation\n"
    "of any vendor document; the test only needs bytes to hash.\n"
)


def _write_taxonomy(
    tmp_path: Path,
    *,
    mappings: Iterable[dict[str, object]] | None = None,
    snapshot: str | None = FIXTURE_SNAPSHOT,
    snapshot_sha: str | None = None,
    provenance_overrides: dict[str, object] | None = None,
    data_types: list[dict[str, str]] | None = None,
) -> Path:
    directory = tmp_path / "taxonomy"
    directory.mkdir(parents=True, exist_ok=True)
    if snapshot is not None:
        (directory / "fixture_form.txt").write_text(snapshot, encoding="utf-8")
    digest = snapshot_sha or hashlib.sha256((snapshot or "").encode("utf-8")).hexdigest()
    provenance: dict[str, object] = {
        "store": "fixture_store",
        "form": "fixture_form",
        "source_url": "https://example.invalid/fixture-form",
        "retrieved_on": "2026-08-29",
        "snapshot": "fixture_form.txt",
        "snapshot_sha256": digest,
    }
    provenance.update(provenance_overrides or {})
    body: dict[str, object] = {
        "provenance": provenance,
        "data_types": data_types
        if data_types is not None
        else [
            {"id": "health_info", "label": "Fixture health type"},
            {"id": "app_info", "label": "Fixture app type"},
            {"id": "audio", "label": "Fixture audio type"},
        ],
        "mapping": list(mappings) if mappings is not None else _full_mapping(),
    }
    path = directory / "fixture_store.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path


def _full_mapping() -> list[dict[str, object]]:
    """A mapping row for every fact the inventory currently produces, so the
    fixture exercises the derivation rather than the refusal."""
    rows: list[dict[str, object]] = []
    for fact in facts_mod.data_facts():
        rows.append(
            {
                "category": fact.category,
                "sharing": str(fact.sharing),
                "data_type": "health_info" if "health" in fact.category else "app_info",
                "collected": True,
                "shared": fact.sharing is not facts_mod.Sharing.NONE,
            }
        )
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, object]] = []
    for row in rows:
        key = (str(row["category"]), str(row["sharing"]))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def test_no_committed_store_taxonomy_exists_yet_and_the_loader_says_so() -> None:
    directory = taxonomy_mod.taxonomy_dir(REPO)
    assert not directory.exists() or not list(directory.glob("*.yaml")), (
        "a taxonomy snapshot landed — HB-A12 is closed and this test must change with it"
    )
    with pytest.raises(taxonomy_mod.StoreTaxonomyMissingError, match="HB-A12"):
        taxonomy_mod.load_taxonomy(directory / "google_play.yaml")


def test_a_valid_fixture_taxonomy_loads_and_binds_its_own_bytes(tmp_path: Path) -> None:
    path = _write_taxonomy(tmp_path)
    loaded = taxonomy_mod.load_taxonomy(path)
    assert loaded.text_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.provenance.retrieved_on.isoformat() == "2026-08-29"
    assert set(loaded.data_types) == {"health_info", "app_info", "audio"}


def test_a_taxonomy_without_its_verbatim_snapshot_is_invalid(tmp_path: Path) -> None:
    path = _write_taxonomy(tmp_path, snapshot=None)
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match="snapshot"):
        taxonomy_mod.load_taxonomy(path)


def test_a_taxonomy_whose_snapshot_hash_does_not_match_is_invalid(tmp_path: Path) -> None:
    path = _write_taxonomy(tmp_path, snapshot_sha="0" * 64)
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match="sha256"):
        taxonomy_mod.load_taxonomy(path)


@pytest.mark.parametrize(
    "field", ["store", "form", "source_url", "retrieved_on", "snapshot", "snapshot_sha256"]
)
def test_a_taxonomy_missing_any_provenance_field_is_invalid(tmp_path: Path, field: str) -> None:
    path = _write_taxonomy(tmp_path, provenance_overrides={field: ""})
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match=field):
        taxonomy_mod.load_taxonomy(path)


def test_a_taxonomy_with_an_undated_snapshot_is_invalid(tmp_path: Path) -> None:
    path = _write_taxonomy(tmp_path, provenance_overrides={"retrieved_on": "last Tuesday"})
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match="retrieved_on"):
        taxonomy_mod.load_taxonomy(path)


def test_a_mapping_naming_an_unknown_data_type_is_invalid(tmp_path: Path) -> None:
    rows = _full_mapping()
    rows[0]["data_type"] = "a_type_the_snapshot_does_not_list"
    path = _write_taxonomy(tmp_path, mappings=rows)
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match="data_type"):
        taxonomy_mod.load_taxonomy(path)


def test_a_mapping_with_an_unknown_sharing_value_is_invalid(tmp_path: Path) -> None:
    rows = _full_mapping()
    rows[0]["sharing"] = "sometimes"
    path = _write_taxonomy(tmp_path, mappings=rows)
    with pytest.raises(taxonomy_mod.StoreTaxonomyInvalidError, match="sharing"):
        taxonomy_mod.load_taxonomy(path)


# --------------------------------------------------------------------------------------
# 3. the declaration: derived, never hand-maintained
# --------------------------------------------------------------------------------------


def test_declaration_rows_trace_back_to_inventory_facts(tmp_path: Path) -> None:
    taxonomy = taxonomy_mod.load_taxonomy(_write_taxonomy(tmp_path))
    rows = declaration_mod.build_declaration(taxonomy, facts_mod.data_facts())
    assert rows
    known = {f.fact_id for f in facts_mod.data_facts()}
    covered: set[str] = set()
    for row in rows:
        assert row.fact_ids, f"{row.data_type} declares nothing"
        covered.update(row.fact_ids)
        assert set(row.fact_ids) <= known
    assert covered == known, "a fact vanished between the inventory and the declaration"


def test_a_fact_the_taxonomy_does_not_map_is_refused_not_defaulted(tmp_path: Path) -> None:
    rows = _full_mapping()[1:]
    taxonomy = taxonomy_mod.load_taxonomy(_write_taxonomy(tmp_path, mappings=rows))
    with pytest.raises(declaration_mod.UnmappedFactError, match="not mapped"):
        declaration_mod.build_declaration(taxonomy, facts_mod.data_facts())


def test_declaration_is_deterministic_and_sorted(tmp_path: Path) -> None:
    taxonomy = taxonomy_mod.load_taxonomy(_write_taxonomy(tmp_path))
    first = declaration_mod.build_declaration(taxonomy, facts_mod.data_facts())
    assert first == declaration_mod.build_declaration(taxonomy, facts_mod.data_facts())
    assert list(first) == sorted(first)


def test_a_shared_fact_makes_its_row_shared(tmp_path: Path) -> None:
    taxonomy = taxonomy_mod.load_taxonomy(_write_taxonomy(tmp_path))
    rows = {
        r.data_type: r for r in declaration_mod.build_declaration(taxonomy, facts_mod.data_facts())
    }
    assert rows["health_info"].shared is True


def test_no_declaration_can_be_produced_for_a_real_store_today() -> None:
    """The fail-closed end state: the mechanism is complete and the vendors'
    own words are not committed, so nothing renders (HB-A12)."""
    with pytest.raises(taxonomy_mod.StoreTaxonomyMissingError):
        declaration_mod.declaration_for_store(REPO, "google_play")


# --------------------------------------------------------------------------------------
# 4. the listing: a regulatory document with two gates
# --------------------------------------------------------------------------------------


def _write_listing(tmp_path: Path, fields: dict[str, str]) -> Path:
    directory = tmp_path / "listing"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fixture_store.tr.yaml"
    body = {
        "provenance": {"store": "fixture_store", "locale": "tr"},
        "fields": fields,
    }
    path.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path


def test_no_store_listing_is_committed_yet_and_the_loader_says_so() -> None:
    directory = listing_mod.listing_dir(REPO)
    with pytest.raises(listing_mod.StoreListingMissingError, match="HB-L21"):
        listing_mod.load_all_listings(directory)


def test_a_listing_binds_its_own_bytes(tmp_path: Path) -> None:
    path = _write_listing(tmp_path, {"description": "Vizite, ziyaret öncesi notunuzu hazırlar."})
    loaded = listing_mod.load_listing(path)
    assert loaded.text_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.locale == "tr"


def test_the_loader_imposes_no_invented_field_list(tmp_path: Path) -> None:
    """Which fields a store's form requires is the store's published fact, not
    ours. The loader takes whatever the human authored against the real form
    and checks only that every value is a non-empty string."""
    path = _write_listing(tmp_path, {"a_field_name_we_did_not_choose": "değer"})
    assert listing_mod.load_listing(path).fields == {"a_field_name_we_did_not_choose": "değer"}


def test_a_listing_with_a_non_string_value_is_invalid(tmp_path: Path) -> None:
    directory = tmp_path / "listing"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fixture_store.tr.yaml"
    path.write_text(
        yaml.safe_dump(
            {"provenance": {"store": "fixture_store", "locale": "tr"}, "fields": {"n": 3}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(listing_mod.StoreListingInvalidError, match="string"):
        listing_mod.load_listing(path)


@pytest.mark.parametrize(
    "copy_line",
    [
        "Konuşmayı %98 doğrulukla yazıya döker.",
        "Our transcription accuracy is measured at 94 percent.",
        "Triyaj hassasiyeti (sensitivity) yüksektir.",
        "WER 8.0 on Turkish speech.",
    ],
)
def test_a_listing_quoting_a_performance_figure_is_caught(copy_line: str) -> None:
    """App Review 1.4.1, quoted verbatim in ADR-022: an unvalidatable health
    accuracy claim is a rejection. Invariant 20 forbids it independently."""
    assert claims.scan_text(copy_line, groups=("performance",))


def test_the_permitted_product_copy_survives_the_claims_gate() -> None:
    for line in FIXED_DISCLAIMERS:
        assert claims.scan_text(line, groups=("performance", "satisfaction")) == ()


@pytest.mark.parametrize(
    "copy_line",
    [
        "Belirtilerinizi değerlendirip aciliyet düzeyi belirler.",
        "Otomatik triyaj ile kırmızı alan ataması yapar.",
        "It scores your depression from your answers.",
        "Yapay zekâ PHQ-9 puanınızı yorumlar.",
        "Sesinizden depresyon riskinizi ölçer.",
        "Size tanı koyar.",
        "This app is a medical device for urgency assessment.",
    ],
)
def test_a_listing_claiming_a_device_function_is_caught(copy_line: str) -> None:
    """A store listing that describes automated urgency direction or automated
    instrument interpretation claims a `device_functions` capability that is
    off without a CE certificate or an approval id (invariant 18)."""
    assert listing_mod.device_claim_hits(copy_line)


@pytest.mark.parametrize(
    "copy_line",
    [
        "Vizite, hekiminize iletmek üzere anlattıklarınızı düzenler.",
        "Acil bir durum yaşıyorsanız 112'yi arayın veya en yakın acil servise başvurun.",
        "Bu belge hastanın beyanına dayanır; hekim değerlendirmesinin yerine geçmez.",
        "Yapay zekâ tarafından üretilmiş sinyal — tanı değildir.",
        "İçerik yapay zekâ desteğiyle yapılandırılmıştır ve tanı niteliği taşımaz.",
        "Ziyaret öncesi hazırlığınızı kolaylaştırır.",
        "Vizite bir tıbbi cihaz değildir.",
        "Vizite is not a medical device.",
        "Uygulama triyaj yapmaz.",
        "Bu uygulama depresyon puanı hesaplamaz.",
    ],
)
def test_the_near_miss_copy_that_describes_the_non_device_product_passes(copy_line: str) -> None:
    """The control that gives the lexicon its meaning. Two of these lines are
    fixed copy we are required to show and both contain 'tanı'; the static
    112 line is permitted in device-off mode by files/06 §7. A token-level
    lexicon would reject all three."""
    assert listing_mod.device_claim_hits(copy_line) == ()


@pytest.mark.parametrize(
    ("copy_line", "expected"),
    [
        # files/01 §4's own promise to clinicians. "not" is Turkish for "note",
        # and a bare English \bnot\b in the denial set silently exempted the
        # triage claim standing beside it.
        ("Yapılandırılmış vizit öncesi not ve triyaj bayrağı.", {"triage_tr"}),
        ("A structured pre-visit note plus a triage flag.", {"triage_en"}),
        # -sız/-siz negates the noun, not the predicate: this claims triage.
        ("Kesintisiz triyaj sunar.", {"triage_tr"}),
    ],
)
def test_a_turkish_word_that_looks_like_an_english_negation_does_not_excuse_a_claim(
    copy_line: str, expected: set[str]
) -> None:
    assert {hit.pattern for hit in listing_mod.device_claim_hits(copy_line)} == expected


def test_a_denial_earlier_in_the_sentence_does_not_excuse_a_later_claim() -> None:
    """The negation window is bounded on purpose: denying one capability may
    not launder a claim about another in the same breath."""
    hits = listing_mod.device_claim_hits("Triyaj yapmaz ama aciliyet düzeyi belirler.")
    assert {hit.pattern for hit in hits} == {"urgency_tr"}


def test_every_device_claim_pattern_names_the_function_it_guards() -> None:
    assert listing_mod.DEVICE_CLAIM_PATTERNS
    for pattern in listing_mod.DEVICE_CLAIM_PATTERNS:
        assert pattern.function.strip()
        assert pattern.source.strip()


def test_the_listing_gate_runs_both_scans_over_every_committed_listing(tmp_path: Path) -> None:
    good = _write_listing(tmp_path, {"description": "Ziyaret öncesi notunuzu hazırlar."})
    assert listing_mod.gate_listing(listing_mod.load_listing(good)) == ()
    bad = _write_listing(
        tmp_path / "second", {"description": "Otomatik triyaj ile %99 doğruluk sağlar."}
    )
    findings = listing_mod.gate_listing(listing_mod.load_listing(bad))
    kinds = {f.kind for f in findings}
    assert kinds == {"performance_claim", "device_claim"}


# --------------------------------------------------------------------------------------
# 5. the checklist
# --------------------------------------------------------------------------------------


def test_the_checklist_covers_all_four_artefacts_the_issue_names() -> None:
    stores = {item.store for item in checklist_mod.CHECKLIST}
    assert {"apple", "google", "iarc"} <= stores


def test_every_checklist_row_is_automatable_or_names_a_blocker() -> None:
    for item in checklist_mod.CHECKLIST:
        if item.check is None:
            assert item.blocker, f"{item.item_id} has neither a check nor a blocker"
        assert item.obligation.strip(), item.item_id
        assert item.source or item.blocker, f"{item.item_id} cites nothing"


def test_every_cited_source_is_a_file_in_this_repo() -> None:
    for item in checklist_mod.CHECKLIST:
        if item.source:
            assert (REPO / item.source).exists(), f"{item.item_id} cites missing {item.source}"


def test_every_named_blocker_exists_in_human_blockers() -> None:
    text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    for item in checklist_mod.CHECKLIST:
        if item.blocker:
            assert f"**{item.blocker}**" in text, f"{item.item_id} names unknown {item.blocker}"


def test_no_row_asserts_a_vendor_requirement_we_have_not_committed() -> None:
    """The rule that keeps a paraphrased policy out of the checklist: a row
    whose obligation is a vendor's published requirement may only cite a file
    under docs/legal/store/taxonomy — and none exists yet, so every such row
    is blocked rather than asserted."""
    for item in checklist_mod.CHECKLIST:
        if item.vendor_published:
            assert not item.source, f"{item.item_id} claims to source a vendor requirement"
            assert item.blocker, f"{item.item_id} asserts a vendor requirement with no blocker"


def test_running_the_checklist_produces_a_verdict_for_every_row() -> None:
    results = checklist_mod.run_checklist(checklist_mod.CheckContext(repo=REPO))
    assert len(results) == len(checklist_mod.CHECKLIST)
    for item, result in results:
        assert result.verdict in set(checklist_mod.Verdict)
        assert result.detail.strip(), item.item_id
        if item.check is None:
            assert result.verdict is checklist_mod.Verdict.BLOCKED


def test_no_automatable_row_fails_on_the_tree_as_it_stands() -> None:
    failures = [
        f"{item.item_id}: {result.detail}"
        for item, result in checklist_mod.run_checklist(checklist_mod.CheckContext(repo=REPO))
        if result.verdict is checklist_mod.Verdict.FAILED
    ]
    assert failures == [], "\n".join(failures)


def test_every_declared_sensor_names_the_module_that_uses_it() -> None:
    """INT-138 turned `apple/no-sensor-the-product-cannot-use` from *no camera*
    into *no sensor without a path*, because the product gained a camera — one
    still capture of the patient's own report — and the obligation a store
    reviewer actually applies was never "no camera"."""
    result = checklist_mod._check_no_sensor_without_a_code_path(
        checklist_mod.CheckContext(repo=REPO)
    )
    assert result.verdict is checklist_mod.Verdict.SATISFIED, result.detail
    assert "android.permission.CAMERA" in result.detail


def test_a_declared_sensor_with_no_code_path_fails_the_rule(tmp_path: Path) -> None:
    """The near miss the old form could not catch: a permission that outlives
    the feature it was added for. The manifest still asks; nothing uses it."""
    (tmp_path / "apps" / "mobile").mkdir(parents=True)
    (tmp_path / "apps" / "mobile" / "app.json").write_text(
        json.dumps({"expo": {"android": {"permissions": ["android.permission.CAMERA"]}}}),
        encoding="utf-8",
    )
    result = checklist_mod._check_no_sensor_without_a_code_path(
        checklist_mod.CheckContext(repo=tmp_path)
    )
    assert result.verdict is checklist_mod.Verdict.FAILED
    assert "android.permission.CAMERA" in result.detail


def _sensor_repo(tmp_path: Path, permissions: list[str], blocked: list[str] | None = None) -> Path:
    """A minimal tree the sensor rule can read: an app.json and the plugin."""
    mobile = tmp_path / "apps" / "mobile"
    (mobile / "plugins").mkdir(parents=True)
    (mobile / "app.json").write_text(
        json.dumps({"expo": {"android": {"permissions": permissions}}}), encoding="utf-8"
    )
    names = ",\n".join(f'  "{name}"' for name in (blocked or []))
    (mobile / "plugins" / "withVoiceAudio.js").write_text(
        f"const FORBIDDEN_PERMISSIONS = [\n{names}\n];\n", encoding="utf-8"
    )
    return tmp_path


#: Every sensor family the rule guards, so a family added to `_SENSOR_MARKERS`
#: cannot be added without a case proving it is actually enforced.
_ALL_BLOCKED = [
    "android.permission.CAMERA",
    "android.permission.MICROPHONE",
    "android.permission.RECORD_AUDIO",
    "android.permission.ACCESS_FINE_LOCATION",
]


def test_a_sensor_permission_with_no_recorded_row_fails_rather_than_passes(
    tmp_path: Path,
) -> None:
    """A new sensor cannot arrive unnoticed: an unknown CAMERA/MICROPHONE/
    LOCATION permission is refused rather than ignored for lack of a row."""
    result = checklist_mod._check_no_sensor_without_a_code_path(
        checklist_mod.CheckContext(
            repo=_sensor_repo(tmp_path, ["android.permission.ACCESS_FINE_LOCATION"], _ALL_BLOCKED)
        )
    )
    assert result.verdict is checklist_mod.Verdict.FAILED
    assert "no recorded path" in result.detail


def test_a_non_sensor_permission_needs_no_path(tmp_path: Path) -> None:
    """The control that keeps the rule from flagging everything: network state
    is not a sensor and has no module to name."""
    result = checklist_mod._check_no_sensor_without_a_code_path(
        checklist_mod.CheckContext(
            repo=_sensor_repo(tmp_path, ["android.permission.ACCESS_NETWORK_STATE"], _ALL_BLOCKED)
        )
    )
    assert result.verdict is checklist_mod.Verdict.SATISFIED


@pytest.mark.parametrize("family", sorted(checklist_mod._SENSOR_FAMILIES))
def test_a_sensor_family_neither_declared_nor_blocked_fails(tmp_path: Path, family: str) -> None:
    """The blind spot the rule was rewritten to close (INT-138 review).

    `expo.android.permissions` is what this app WRITES; the manifest a device
    installs is that merged with every dependency's AAR, and the merged file
    does not exist until a prebuild — which is exactly how `expo-image-picker`
    brings CAMERA in. A family with no code path must therefore be REMOVED from
    the merge with tools:node="remove", not merely left unwritten.
    """
    fragments = checklist_mod._SENSOR_FAMILIES[family]
    kept = [name for name in _ALL_BLOCKED if not any(f in name for f in fragments)]
    result = checklist_mod._check_no_sensor_without_a_code_path(
        checklist_mod.CheckContext(repo=_sensor_repo(tmp_path, [], kept))
    )
    assert result.verdict is checklist_mod.Verdict.FAILED
    assert family in result.detail


def test_the_shipped_plugin_blocks_every_sensor_family_it_has_no_path_for() -> None:
    """The rule above, against the real tree rather than a fixture."""
    blocked = checklist_mod._blocked_permissions(REPO)
    assert "android.permission.ACCESS_FINE_LOCATION" in blocked
    assert "android.permission.READ_EXTERNAL_STORAGE" in blocked
    declared = set(
        json.loads(APP_JSON.read_text(encoding="utf-8"))["expo"]["android"]["permissions"]
    )
    for family, fragments in checklist_mod._SENSOR_FAMILIES.items():
        covered = any(f in p for f in fragments for p in (*declared, *blocked))
        assert covered, f"{family} is neither declared with a path nor blocked"


def test_clinical_health_records_is_not_declared_anywhere_in_the_mobile_app() -> None:
    """files/00 §2: CA/UK/US only, non-functional in Türkiye, and an App
    Review rejection risk if declared but unused."""
    mobile = REPO / "apps" / "mobile"
    offenders = [
        str(path.relative_to(REPO))
        for path in sorted(mobile.rglob("*"))
        if path.is_file()
        and path.suffix in {".json", ".js", ".ts", ".tsx"}
        and "healthkit.access" in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    assert offenders == [], f"clinical health records capability declared in {offenders}"


def test_device_functions_stays_off_by_default() -> None:
    from intake_platform.flags import SAFETY_FLAG_DEFAULTS

    assert SAFETY_FLAG_DEFAULTS["device_functions"] is False


# --------------------------------------------------------------------------------------
# 6. the claims gate: one pattern set, one place, and the store tree inside it
# --------------------------------------------------------------------------------------


def test_the_declared_trees_include_the_legal_tree_that_holds_the_store_artefacts() -> None:
    scanned = {tree.path for tree in claims.SCANNED_TREES}
    assert "docs/legal" in scanned
    assert "docs/security" in scanned
    assert "docs/regulatory" in scanned
    store_root = listing_mod.listing_dir(REPO)
    assert any(store_root.is_relative_to(REPO / tree.path) for tree in claims.SCANNED_TREES), (
        "the store listing tree sits outside every scanned tree"
    )


def test_the_claims_gate_is_green_on_the_declared_trees() -> None:
    hits = claims.scan_declared_trees(REPO)
    assert hits == (), "\n".join(f"{h.path}:{h.line_no} [{h.pattern}] {h.line}" for h in hits)


def test_a_missing_declared_tree_is_not_an_error(tmp_path: Path) -> None:
    assert claims.scan_tree(tmp_path / "nothing-here", ("performance",)) == ()


def test_the_gate_catches_a_figure_planted_in_a_store_artefact(tmp_path: Path) -> None:
    tree = tmp_path / "docs" / "legal" / "store"
    tree.mkdir(parents=True)
    (tree / "listing.tr.yaml").write_text(
        'fields:\n  description: "%97 doğrulukla yazıya döker (WER 3.0)."\n', encoding="utf-8"
    )
    hits = claims.scan_tree(tmp_path / "docs" / "legal", ("performance",))
    # INT-536: the CI gate's strict-tier arms fire on the same line too
    assert {h.pattern for h in hits} == {"wer", "accuracy_tr", "ci_term_en", "ci_claim_tr"}


def test_only_text_shaped_files_are_scanned(tmp_path: Path) -> None:
    tree = tmp_path / "docs" / "legal"
    tree.mkdir(parents=True)
    (tree / "logo.png").write_bytes(b"\x89PNG accuracy 99%")
    assert claims.scan_tree(tree, ("performance",)) == ()


@pytest.mark.parametrize(
    "suite",
    ["tests/security/test_threat_model.py", "tests/experience/test_metrics_service.py"],
)
def test_no_other_suite_keeps_a_private_copy_of_the_vocabulary(suite: str) -> None:
    """One pattern set in one place. The two suites that predate this module
    read their groups from it; a re-grown local tuple of regexes is the drift
    this test exists to catch."""
    source = (REPO / suite).read_text(encoding="utf-8")
    assert "from intake_platform.legal import claims" in source
    assert (
        "CLAIM_PATTERNS = (" not in source and "CLAIM_PATTERNS: tuple[str, ...] = (" not in source
    ), f"{suite} defines its own claim patterns again"
