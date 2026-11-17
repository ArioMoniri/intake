"""INT-465: the generic RED goldens (CD-24's near-miss tests), checked on the served artefact.

These cases do not use a hand-built fixture. They read what the synthetic AWS host would
serve:
- ``files/protocols/base.life_threat.yaml``;
- the active CD-24 generic RED;
- the committed test-key signature;
- a synthetic tenant config.

Those go through ``intake_api.triage_rules.load_served_red_rules``, so the catalog checked
here is the one the device would pre-position. Every golden has a near-miss negative
control: the closest thing that must NOT behave the same way.

CD-24 is D18 scope: simulated patients only, and a licensed physician's review is
required before any real patient. The delivery goldens (the register carried from the
engine, mixed registers, SILENT, DEFERRED_CLINICIAN, and intake stopping) live with the
voice runtime in tests/voice/test_red_winner.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from clinical_schemas.triage import RedLocation, RedRegister
from intake_api.triage_rules import CatalogOut, ServedRedRules, load_served_red_rules
from intake_platform.red_signature import COMMITTED_SIGNATURE
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from protocols.generic_red import (
    GENERIC_RED_SCRIPT_IDS,
    generic_red_clip_rows,
    load_generic_red,
)
from protocols.red_render import RedRenderError, assert_markup_free

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
SYNTHETIC = TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment="i-0e489e48739f5de98")
REMOTE_ID = GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]
ON_SITE_ID = GENERIC_RED_SCRIPT_IDS[RedLocation.ON_SITE]
UNKNOWN_ID = GENERIC_RED_SCRIPT_IDS[RedLocation.UNKNOWN]
CARDIAC = "rf.chest_pain_cardiac_features"
TWELVE = re.compile(r"112|yüz on iki", re.IGNORECASE)
MARKUP = re.compile(r"[*{}\[\]]")


@pytest.fixture(scope="module")
def served() -> ServedRedRules:
    loaded = load_served_red_rules(
        LIFE_THREAT, GENERIC, signature_path=COMMITTED_SIGNATURE, tenant=SYNTHETIC
    )
    assert loaded is not None, "the synthetic host's signed rule set must serve"
    return loaded


@pytest.fixture(scope="module")
def catalog(served: ServedRedRules) -> CatalogOut:
    return served.catalog


def _texts(catalog: CatalogOut, script_id: str) -> list[str]:
    script = catalog.scripts[script_id]
    return [script.actionTr, *script.doNotsTr, *([script.whyTr] if script.whyTr else [])]


def test_g01_on_site_generic_has_no_112_anywhere(catalog: CatalogOut) -> None:
    on_site = catalog.scripts[ON_SITE_ID]
    assert on_site.show112 is False
    assert on_site.primary == "GO_TO_IN_HOUSE_ACIL"
    assert not any(TWELVE.search(text) for text in _texts(catalog, ON_SITE_ID))
    # Near miss: the REMOTE generic carries the affordance and the number.
    assert catalog.scripts[REMOTE_ID].show112 is True
    assert TWELVE.search(catalog.scripts[REMOTE_ID].actionTr)


def test_g02_unknown_generic_asks_before_any_112(catalog: CatalogOut) -> None:
    question = catalog.questions[UNKNOWN_ID]
    assert question.askTr == "Şu anda hastanede misiniz?"
    assert not TWELVE.search(question.askTr)
    assert UNKNOWN_ID not in catalog.scripts  # a question, never a script with an affordance
    # Near miss: "hayır" leads to the REMOTE script, which does show 112.
    assert question.onNo == "REMOTE" and catalog.scripts[REMOTE_ID].show112 is True


def test_g03_no_answer_goes_remote_and_is_never_left_without_an_action(
    catalog: CatalogOut,
) -> None:
    """The catalog half. The device half drives the RED store from the question to
    REMOTE with the 112 control (apps/mobile/src/lib/red/store.test.ts, listed in
    CD24_GOLDENS below)."""
    question = catalog.questions[UNKNOWN_ID]
    no_answer = catalog.scripts[REMOTE_ID] if question.onNoAnswer == "REMOTE" else None
    assert no_answer is not None and no_answer.actionTr and no_answer.show112 is True
    # Near miss: "evet" leads ON_SITE, a script with words and no 112.
    yes = catalog.scripts[ON_SITE_ID] if question.onYes == "ON_SITE" else None
    assert yes is not None and yes.actionTr and yes.show112 is False


def test_g04_the_generic_names_no_condition(catalog: CatalogOut) -> None:
    stems = ("kalp", "kalb", "inme", "kanama")  # CD-24's own named examples
    generic = _texts(catalog, REMOTE_ID) + _texts(catalog, ON_SITE_ID)
    assert not any(stem in text.casefold() for text in generic for stem in stems)
    # Near miss: CD-24's own quoted example of the rejected wording fails the same
    # check. A literal rather than a served rule, so fixing HB-C12b keeps this green.
    assert any(stem in "kalple ilgili olabilir" for stem in stems)


def test_g05_every_spoken_generic_string_is_expanded_and_markup_free() -> None:
    rows = generic_red_clip_rows(load_generic_red(GENERIC), voice="ses", acil_location_tr=None)
    assert rows and all(row.scripted for row in rows)
    for row in rows:
        assert not re.search(r"\d", row.text_tr), row.text_tr
        assert_markup_free(row.text_tr)
    assert any("yüz on iki" in row.text_tr for row in rows)
    # Near miss: the authored ON_SITE line, sent as written, carries markup.
    authored = yaml.safe_load(GENERIC.read_text(encoding="utf-8"))
    with pytest.raises(RedRenderError):
        assert_markup_free(authored["action"]["ON_SITE"]["action_tr"]["tr"])


def test_g06_on_site_asks_for_an_escort_and_remote_carries_none(catalog: CatalogOut) -> None:
    assert "Tek başınıza gitmeyin; bir görevliden yardım isteyin." in (
        catalog.scripts[ON_SITE_ID].doNotsTr
    )
    # Near miss: REMOTE accompaniment and driving do-nots stay draft in CD-24.
    remote = " ".join(catalog.scripts[REMOTE_ID].doNotsTr).casefold()
    assert "tek başınıza" not in remote and "aracınızla" not in remote


def test_g07_no_served_script_carries_authoring_markup(catalog: CatalogOut) -> None:
    for script_id in catalog.scripts:
        for text in _texts(catalog, script_id):
            assert not MARKUP.search(text), (script_id, text)
    for question in catalog.questions.values():
        assert not MARKUP.search(question.askTr)
    # Near miss: the authored cardiac ON_SITE line is bold and carries the tenant segment.
    doc = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    authored = doc["rules"][0]["action"]["ON_SITE"]["action_tr"]["tr"]
    assert MARKUP.search(authored)
    assert catalog.scripts[f"{CARDIAC}.on_site"].actionTr.startswith("Acil Servis'e gidin. ")


def test_g08_draft_rules_are_never_served(served: ServedRedRules, catalog: CatalogOut) -> None:
    ids = {rule.id for rule in served.rules}
    assert "rf.crisis_disclosure_signposting" not in ids
    assert "rf.paediatric_airway_obstruction" not in ids
    assert not any(key.startswith("rf.paediatric_airway_obstruction") for key in catalog.scripts)
    # Near miss: the active, sourced cardiac rule is served with all three locations.
    assert CARDIAC in ids
    assert {f"{CARDIAC}.remote", f"{CARDIAC}.on_site"} <= set(catalog.scripts)
    assert f"{CARDIAC}.unknown" in catalog.questions


def test_g10_the_served_set_cannot_mix_registers_across_acuities(
    served: ServedRedRules,
) -> None:
    """CD-24 fail_closed_while_draft: never ALERT when any fired rule is CALM or
    SILENT. ``RuleFire`` carries no register, so a voice-lane generic over REDs of
    different acuity takes the winner's register (docs/evidence/INT-465.md, finding
    3). That cannot happen while every served RED shares one device register. A set
    that breaks this turns this golden red before it can be served unexamined."""
    device = {RedRegister.ALERT, RedRegister.CALM, RedRegister.SILENT}
    registers = {rule.register for rule in served.rules if rule.level.is_red}
    assert len(registers & device) <= 1, registers
    # Near miss: the check really sees registers (one RED is served, as ALERT).
    assert registers == {RedRegister.ALERT}


def test_g09_the_same_set_is_never_served_to_a_non_synthetic_tenant() -> None:
    for kind in (kind for kind in TenantKind if kind is not TenantKind.SYNTHETIC):
        assert (
            load_served_red_rules(
                LIFE_THREAT,
                GENERIC,
                signature_path=COMMITTED_SIGNATURE,
                tenant=TenantRedConfig(kind=kind),
            )
            is None
        )


# --- CD-24's near-miss tests, and where each one is pinned ---------------------------------

#: CD-24 (docs/clinical/decisions/CD-24.md, "Near-miss tests that pin it") names twelve
#: tests. Some live in the device or the voice runtime, where the behaviour is, so this
#: registry lists each one by file and by the name it is pinned under. A file that loses
#: one fails here.
CD24_GOLDENS: dict[str, tuple[tuple[str, str], ...]] = {
    "generic_red_on_site_has_no_112_anywhere": (
        (
            "tests/safety/test_generic_red_goldens.py",
            "test_g01_on_site_generic_has_no_112_anywhere",
        ),
        ("tests/protocols/test_generic_red.py", "test_on_site_carries_no_112_in_any_carrier"),
    ),
    "generic_red_unknown_asks_before_112": (
        (
            "tests/safety/test_generic_red_goldens.py",
            "test_g02_unknown_generic_asks_before_any_112",
        ),
        ("apps/mobile/src/lib/red/store.test.ts", "CD-24 generic_red_unknown_asks_before_112"),
    ),
    "generic_red_unknown_no_answer_goes_remote": (
        ("tests/safety/test_generic_red_goldens.py", "test_g03_no_answer_goes_remote"),
        (
            "apps/mobile/src/lib/red/store.test.ts",
            "CD-24 generic_red_unknown_no_answer_goes_remote",
        ),
    ),
    "generic_red_copy_names_no_condition": (
        ("tests/safety/test_generic_red_goldens.py", "test_g04_the_generic_names_no_condition"),
    ),
    "generic_red_strings_expand_for_tts": (
        ("tests/safety/test_generic_red_goldens.py", "test_g05_every_spoken_generic_string"),
    ),
    "generic_red_carries_the_engine_register": (
        (
            "tests/voice/test_red_winner.py",
            "test_an_unaddressable_red_shows_the_generic_red_in_the_results_own_register",
        ),
    ),
    "generic_red_mixed_registers_take_the_most_restrictive": (
        (
            "tests/voice/test_red_winner.py",
            "test_a_generic_over_mixed_registers_takes_the_most_restrictive",
        ),
    ),
    "generic_red_silent_is_never_wordless": (
        ("apps/mobile/src/lib/red/hop.test.ts", "CD-24 generic_red_silent_is_never_wordless"),
        (
            "apps/mobile/src/lib/livekit/session.test.ts",
            "CD-24 generic_red_silent_is_never_wordless",
        ),
    ),
    "generic_red_stops_intake": (
        (
            "tests/voice/test_red_preemption.py",
            "test_protocol_next_after_a_red_offers_and_speaks_no_question",
        ),
        ("apps/mobile/src/lib/red/store.test.ts", "CD-24 generic_red_stops_intake"),
    ),
    "silent_over_alert_is_stated_to_the_clinic": (
        (
            "tests/voice/test_red_winner.py",
            "test_a_generic_over_mixed_registers_takes_the_most_restrictive",
        ),
        (
            "tests/voice/test_red_winner.py",
            "test_a_silent_red_with_its_own_script_is_not_marked_generic",
        ),
    ),
    "generic_red_on_site_asks_for_an_escort": (
        ("tests/safety/test_generic_red_goldens.py", "test_g06_on_site_asks_for_an_escort"),
    ),
    "generic_red_deferred_never_reaches_device": (
        (
            "tests/voice/test_red_winner.py",
            "test_a_deferred_clinician_red_never_reaches_the_device_even_unaddressable",
        ),
    ),
}


def test_every_cd24_golden_is_pinned_where_the_registry_says() -> None:
    named = (REPO / "docs" / "clinical" / "decisions" / "CD-24.md").read_text(encoding="utf-8")
    assert set(re.findall(r"^- `([a-z0-9_]+)`", named, re.M)) == set(CD24_GOLDENS)
    for golden, places in CD24_GOLDENS.items():
        for path, name in places:
            assert name in (REPO / path).read_text(encoding="utf-8"), (golden, path, name)
