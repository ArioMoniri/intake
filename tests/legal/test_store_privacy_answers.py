"""INT-482 — the App Privacy / Data safety answers, derived from the inventory.

Acceptance (GitHub #825): *"App Privacy (nutrition label) and Google Play Data
safety answers derived from the data inventory annotations (invariant 18),
synthetic-scope caveat stated"*, and the test *"every privacy answer maps to an
inventory annotation"*.

What is derived, and what deliberately is not:

- **Every row is an inventory fact.** ``intake_platform.store.facts`` already
  folds both halves of the inventory — invariant 18's column annotations and
  the off-schema flows (microphone audio, health-platform reads, document
  bytes) — into store-neutral facts. The answer sheet is one row per fact and
  nothing else, so a row with no fact behind it, or a fact with no row, fails
  here (both directions, with a near-miss each).
- **No vendor vocabulary.** Which of Apple's data types or Google Play's
  categories a row becomes is the vendors' published form, and HB-A12 forbids
  recalling it. ``intake_platform.store.declaration`` does that mapping from a
  committed snapshot; this sheet stops one step before it.
- **The open determinations stay open.** Whether audio that is transmitted for
  transcription and never written counts as *collected* is HB-L21(a), and the
  voice row says so instead of answering it.
- **The draft is the derivation.** The committed draft under
  docs/legal/drafts/store must equal what the module derives today, so it can
  never be edited by hand into disagreement with the schema.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.db import models
from intake_platform.db.inventory import (
    BASIS_CONTRACT,
    CAT_DIRECT_IDENTIFIER,
    CAT_PSEUDONYM,
    INVENTORY_KEY,
)
from intake_platform.legal import claims
from intake_platform.store import answers
from intake_platform.store import facts as facts_mod

REPO = Path(__file__).resolve().parents[2]
DRAFT = REPO / "docs" / "legal" / "drafts" / "store" / "privacy-answers.draft.yaml"


def _draft() -> dict[str, Any]:
    loaded = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_committed_draft_is_exactly_the_derivation() -> None:
    assert _draft() == answers.answer_sheet()


def test_every_answer_maps_to_an_inventory_fact_and_every_fact_has_an_answer() -> None:
    sheet = answers.answer_sheet()
    rows = {row["inventory"]: row for row in sheet["answers"]}
    facts = {fact.fact_id: fact for fact in facts_mod.data_facts()}
    assert set(rows) == set(facts)
    for fact_id, fact in facts.items():
        row = rows[fact_id]
        assert row["category"] == fact.category
        assert row["purposes"] == list(fact.purposes)
        assert row["bases"] == list(fact.bases)
        assert row["retentions"] == list(fact.retentions)
        assert row["recipients"] == list(fact.recipients)
        assert row["stored"] is fact.persisted
        assert row["shared"] == fact.sharing.value
    assert answers.check_sheet(sheet) == ()


def test_an_answer_with_no_inventory_fact_is_refused() -> None:
    """The near miss in the direction a hand edit takes: a plausible row that
    the inventory does not hold."""
    sheet = answers.answer_sheet()
    invented = dict(sheet["answers"][0], inventory="flow:location_history")
    errors = answers.check_sheet({**sheet, "answers": [*sheet["answers"], invented]})
    assert any("flow:location_history" in error for error in errors)


def test_a_fact_with_no_answer_is_refused() -> None:
    sheet = answers.answer_sheet()
    errors = answers.check_sheet({**sheet, "answers": sheet["answers"][1:]})
    assert any(sheet["answers"][0]["inventory"] in error for error in errors)


def test_an_answer_that_drifted_from_its_annotation_is_refused() -> None:
    sheet = answers.answer_sheet()
    first = dict(sheet["answers"][0], purposes=["reklam ve pazarlama"])
    errors = answers.check_sheet({**sheet, "answers": [first, *sheet["answers"][1:]]})
    assert any("purposes" in error for error in errors)


def test_the_voice_row_leaves_the_audio_determination_open() -> None:
    rows = {row["inventory"]: row for row in answers.answer_sheet()["answers"]}
    voice = rows["flow:voice_audio"]
    assert voice["stored"] is False
    assert voice["leaves_device"] is True
    assert any(item.startswith("HB-L21(a)") for item in voice["open_determinations"])


def test_the_sign_in_phone_number_is_a_fact_although_no_column_holds_it() -> None:
    """The legal lane's finding on #828. Release builds sign in by phone and an
    SMS code; the raw number goes to the SMS vendor and only a keyed pseudonym
    is stored (invariant 14). A label derived from the schema alone would omit
    the one direct identifier that leaves the PHI boundary."""
    schema_categories = {
        column.info[INVENTORY_KEY]["category"]
        for table in models.Base.metadata.tables.values()
        for column in table.columns
    }
    assert CAT_DIRECT_IDENTIFIER not in schema_categories
    phone = [f for f in facts_mod.data_facts() if f.fact_id == "flow:phone_sign_in"]
    assert len(phone) == 1
    fact = phone[0]
    assert (fact.persisted, fact.origin) == (False, "flow")
    assert fact.category == CAT_DIRECT_IDENTIFIER
    assert fact.category != CAT_PSEUDONYM, "the raw number is not a pseudonym"
    assert fact.sharing is facts_mod.Sharing.TO_PROCESSOR
    assert fact.bases == (BASIS_CONTRACT,)
    otp = (REPO / "services/api/src/intake_api/otp.py").read_text(encoding="utf-8")
    assert "delivery.send(phone_e164=phone" in otp, "the raw number reaches the adapter"
    row = {r["inventory"]: r for r in answers.answer_sheet()["answers"]}["flow:phone_sign_in"]
    assert row["leaves_device"] is True and row["stored"] is False
    assert any(item.startswith("INT-358") for item in row["open_determinations"])
    assert any("retention is awaiting-human" in item for item in row["open_determinations"])


def test_on_device_health_reads_never_leave_the_device_until_added() -> None:
    rows = {row["inventory"]: row for row in answers.answer_sheet()["answers"]}
    health = rows["flow:health_platform_reads"]
    assert health["leaves_device"] is False
    assert health["stored"] is False


def test_an_awaiting_human_annotation_surfaces_as_an_open_determination() -> None:
    rows = answers.answer_sheet()["answers"]
    awaiting = [
        row
        for row in rows
        if any("awaiting-human" in v for v in row["bases"] + row["retentions"] + row["recipients"])
    ]
    assert awaiting, "the inventory holds awaiting-human rows today (guardianship_link)"
    for row in awaiting:
        assert row["open_determinations"], row["inventory"]


def test_switched_off_flows_are_listed_and_not_declared() -> None:
    sheet = answers.answer_sheet()
    off = {row["flow"] for row in sheet["not_declared"]}
    assert off == {f.flow_id for f in facts_mod.OFF_SCHEMA_FLOWS.values() if not f.active}
    assert "crash_diagnostics" in off


# --- the product-wide answers, each checked against the file it cites ------------------


def _product() -> dict[str, dict[str, str]]:
    return {row["id"]: row for row in answers.answer_sheet()["product"]}


def test_every_product_answer_cites_files_that_exist() -> None:
    for row in _product().values():
        for path in row["sources"]:
            assert (REPO / path).exists(), (row["id"], path)


def test_no_tracking_and_no_advertising() -> None:
    assert {"tracking", "advertising"} <= set(_product())
    app = (REPO / "apps" / "mobile" / "app.json").read_text(encoding="utf-8")
    locales = "".join(
        p.read_text(encoding="utf-8") for p in (REPO / "apps/mobile/src/locales").glob("*.json")
    )
    package = json.loads((REPO / "apps" / "mobile" / "package.json").read_text(encoding="utf-8"))
    tracking_key = "NSUser" + "TrackingUsageDescription"
    assert tracking_key not in app + locales
    assert not [d for d in package.get("dependencies", {}) if "tracking" in d]
    advertising = re.compile(r"(?i)reklam|pazarlama|advertis|marketing")
    assert not [p for f in facts_mod.data_facts() for p in f.purposes if advertising.search(p)]


def test_data_travels_over_https_and_the_patient_can_request_deletion() -> None:
    assert {"encryption_in_transit", "deletion"} <= set(_product())
    eas_json = json.loads((REPO / "apps" / "mobile" / "eas.json").read_text(encoding="utf-8"))
    assert eas_json["build"]["production"]["env"]["EXPO_PUBLIC_API_BASE_URL"].startswith("https://")
    requests_ts = (REPO / "apps/mobile/src/lib/dsar/requests.ts").read_text(encoding="utf-8")
    assert re.search(r'DSAR_KINDS = \[[^\]]*"delete"', requests_ts)
    router = (REPO / "services/api/src/intake_api/dsar/router.py").read_text(encoding="utf-8")
    assert '@router.post("/delete"' in router


def test_the_synthetic_scope_caveat_and_the_review_status_are_stated() -> None:
    sheet = answers.answer_sheet()
    assert sheet["provenance"]["status"] == "pending legal-lane review"
    caveats = {row["id"]: row["text"] for row in sheet["caveats"]}
    assert "simulated patients only" in caveats["synthetic_scope"]
    assert "HB-I5" in caveats["synthetic_scope"] and "HB-L11" in caveats["synthetic_scope"]
    assert "HB-A12" in caveats["vendor_vocabulary"]
    assert "HB-L21(e)" in caveats["seller_identity"]


def test_the_sheet_carries_no_performance_claim() -> None:
    text = DRAFT.read_text(encoding="utf-8")
    assert claims.scan_text(text, groups=("performance", "satisfaction")) == ()


def test_the_module_prints_the_sheet_for_regeneration(capsys: pytest.CaptureFixture[str]) -> None:
    assert answers.main() == 0
    assert yaml.safe_load(capsys.readouterr().out) == answers.answer_sheet()
    out = subprocess.run(
        [sys.executable, "-m", "intake_platform.store.answers"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert yaml.safe_load(out) == answers.answer_sheet()


@pytest.mark.parametrize("key", ["inventory", "stored", "leaves_device", "shared"])
def test_a_row_missing_a_field_is_refused(key: str) -> None:
    sheet = answers.answer_sheet()
    broken = {k: v for k, v in sheet["answers"][0].items() if k != key}
    errors = answers.check_sheet({**sheet, "answers": [broken, *sheet["answers"][1:]]})
    assert errors
