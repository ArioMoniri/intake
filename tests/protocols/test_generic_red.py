"""INT-465 / CD-24: the generic RED escalation document is active and holds its own provenance.

The committed ``packages/protocols/generic/generic_red.yaml`` carries CD-24's verified
copy. CD-24 is the INT-432 register row: agent author plus independent verifier, D18
scope, so simulated patients only, and a licensed physician's review is required before
any real patient.

The document is ``active``. Every location entry states:
- its location;
- its script id;
- CD-24's register policy (``carry_engine_register``, never a fixed register);
- its own source blocks.

Every guideline quote is verbatim in a committed snapshot under
``packages/protocols/sources/``. Every spec sentence is verbatim in the committed file it
cites. No source appears here that CD-24 does not cite, and the copy is CD-24's value
byte for byte, so the document cannot drift from the decision.

ON_SITE never offers 112 in any carrier: the flag, the numbers, the action codes, and
(CD-24's near-miss test) the text itself, as digits or as the spoken "yüz on iki". The
UNKNOWN question asks before any 112. Every refusal has a near miss.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.triage import RedLocation
from protocols.clinical_decisions import (
    REGISTER_DIR,
    load_decision,
    quote_in_snapshot,
    snapshot_body,
)
from protocols.generic_red import (
    GENERIC_RED_DECISION,
    GENERIC_RED_SCRIPT_IDS,
    GenericRedCopy,
    GenericRedError,
    generic_red_clip_rows,
    generic_red_refusals,
    generic_red_strings,
    load_generic_red,
)

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
CD24 = load_decision(REGISTER_DIR / "CD-24.yaml")
CD24_SCRIPTS = CD24.value["scripts"]["base"]["generic_red"]
LOCATION_KEY = {RedLocation.REMOTE: "remote", RedLocation.ON_SITE: "on_site"}


def _doc() -> dict[str, Any]:
    loaded = yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write(tmp_path: Path, edit: Any) -> Path:
    doc = copy.deepcopy(_doc())
    edit(doc)
    path = tmp_path / "generic_red.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def committed() -> GenericRedCopy:
    return load_generic_red(COMMITTED)


# --- active, servable, and CD-24's own -------------------------------------------------------


def test_the_committed_document_is_active_and_servable(committed: GenericRedCopy) -> None:
    assert committed.decision == GENERIC_RED_DECISION == "CD-24"
    assert committed.status.value == "active"
    assert committed.scope == "simulated_patient_stress_testing"
    assert committed.register_policy == "carry_engine_register"
    assert generic_red_refusals(committed) == ()


def test_cd24_itself_is_active_for_what_the_document_carries() -> None:
    assert CD24.status.value == "active"
    assert CD24.verifier.verdict.value == "agree"
    for key in ("scripts", "unknown_location_verdict", "numeral_form", "register_policy.verdict"):
        assert CD24.value_status[key].value == "active", key


def test_the_copy_is_cd24s_value_byte_for_byte(committed: GenericRedCopy) -> None:
    action = committed.action
    assert action is not None
    for location, key in LOCATION_KEY.items():
        script = action.remote if location is RedLocation.REMOTE else action.on_site
        decided = CD24_SCRIPTS[key]
        assert script.primary == decided["primary"]
        assert script.show_112 is decided["show112"]
        assert script.action_tr == {"tr": decided["action_tr"]}
        assert script.do_nots_tr == {"tr": tuple(decided["do_nots_tr"])}
        assert script.why_tr == {"tr": decided["why_tr"]}
    assert (
        action.on_site.notify_staff_immediate is CD24_SCRIPTS["on_site"]["notify_staff_immediate"]
    )
    decided_unknown = CD24_SCRIPTS["unknown"]
    assert action.unknown.ask_one_tr == {"tr": decided_unknown["ask_one_tr"]}
    assert (action.unknown.on_yes, action.unknown.on_no, action.unknown.on_no_answer) == (
        decided_unknown["on_yes"],
        decided_unknown["on_no"],
        decided_unknown["on_no_answer"],
    )


def _identity(source: Any) -> tuple[Any, ...]:
    return (
        source.guideline_id,
        source.title,
        source.version_or_date,
        source.url,
        source.retrieved_on,
        source.quote,
        source.snapshot,
    )


def test_every_source_is_cd24s_and_quoted_verbatim_in_its_snapshot(
    committed: GenericRedCopy,
) -> None:
    decided = {_identity(source) for source in CD24.sources}
    decided_spec = {(basis.file, basis.quote) for basis in CD24.spec_basis}
    assert committed.scripts is not None
    for location, entry in committed.scripts.items():
        for source in entry.sources:
            assert _identity(source) in decided, (location, source.quote[:60])
            body = snapshot_body((REPO / source.snapshot).read_text(encoding="utf-8"))
            assert quote_in_snapshot(source.quote, body)
        for basis in entry.spec_basis:
            assert (basis.file, basis.quote) in decided_spec, (location, basis.quote[:60])
            assert quote_in_snapshot(basis.quote, (REPO / basis.file).read_text(encoding="utf-8"))


# What each block supports, read off CD-24's own `supports` line for that source
# (packages/protocols/decisions/CD-24.yaml line numbers). A block may name only
# the fields CD-24 gives it, for this location: the clinical review of INT-465
# found three ON_SITE blocks claiming action_tr where CD-24 says otherwise.
CD24_SUPPORTS: dict[tuple[str, str], frozenset[str]] = {
    ("REMOTE", "İllerde 112 acil çağrı"): frozenset({"action_tr"}),  # :75
    ("REMOTE", "Kategori 1:"): frozenset({"do_nots_tr"}),  # :21
    ("REMOTE", "Kategori 2:"): frozenset({"do_nots_tr", "why_tr"}),  # :30
    ("REMOTE", "(5) 112 acil"): frozenset({"why_tr"}),  # :39
    ("REMOTE", "tıbbi önceliklerinin"): frozenset({"why_tr"}),  # :48
    ("REMOTE", "single national emergency"): frozenset({"action_tr", "primary", "show_112"}),  # :80
    ("REMOTE", "Both are statements"): frozenset({"why_tr"}),  # :160
    ("REMOTE", "Action scripts carry"): frozenset({"do_nots_tr"}),  # :176
    ("REMOTE", "Invert inside RED"): frozenset({"action_tr", "do_nots_tr"}),  # :180
    ("ON_SITE", "Kategori 1:"): frozenset({"why_tr"}),  # :21
    ("ON_SITE", "Kategori 2:"): frozenset({"do_nots_tr", "why_tr"}),  # :30
    ("ON_SITE", "tıbbi önceliklerinin"): frozenset({"why_tr"}),  # :48
    ("ON_SITE", "ayaktan hasta girişlerinde"): frozenset({"why_tr"}),  # :57
    ("ON_SITE", "Ayaktan başvurduğu"): frozenset({"do_nots_tr"}),  # :66
    ("ON_SITE", "Direct them to the hospital"): frozenset(
        {"primary", "notify_staff_immediate"}
    ),  # :140
    ("ON_SITE", "is therefore promoted"): frozenset({"action_tr"}),  # :144
    ("ON_SITE", "is the sentence that changes"): frozenset({"action_tr"}),  # :148
    ("ON_SITE", "Not de-emphasised"): frozenset(
        {"show_112", "action_tr", "do_nots_tr", "why_tr"}
    ),  # :152
    ("ON_SITE", "Under ON_SITE the 112"): frozenset({"show_112"}),  # :156
    ("ON_SITE", "Both are statements"): frozenset({"why_tr"}),  # :160
    ("ON_SITE", "Acil Servis'e gidin["): frozenset({"action_tr"}),  # :164
    ("ON_SITE", "Action scripts carry"): frozenset({"do_nots_tr"}),  # :176
    ("ON_SITE", "Invert inside RED"): frozenset({"action_tr", "do_nots_tr"}),  # :180
    ("UNKNOWN", "Under ON_SITE the 112"): frozenset({"ask_one_tr"}),  # :156 verdict
    ("UNKNOWN", "Never guess"): frozenset({"ask_one_tr"}),  # :168
    ("UNKNOWN", "It is never resolved"): frozenset({"ask_one_tr"}),  # :172
}


def test_every_block_supports_only_what_cd24_gives_it(committed: GenericRedCopy) -> None:
    assert committed.scripts is not None
    seen: set[tuple[str, str]] = set()
    for location, entry in committed.scripts.items():
        for block in (*entry.sources, *entry.spec_basis):
            [key] = [
                key
                for key in CD24_SUPPORTS
                if key[0] == location.value and block.quote.startswith(key[1])
            ]
            fields = frozenset(t.strip() for t in (block.supports or "").split(","))
            assert fields == CD24_SUPPORTS[key], (key, sorted(fields))
            seen.add(key)
    assert seen == set(CD24_SUPPORTS)  # no CD-24 reading left unused, none added


def test_every_location_states_its_location_register_and_basis(committed: GenericRedCopy) -> None:
    assert committed.scripts is not None
    assert set(committed.scripts) == set(RedLocation)
    for location, entry in committed.scripts.items():
        assert entry.location is location
        assert entry.script_id == GENERIC_RED_SCRIPT_IDS[location]
        assert entry.register == "carry_engine_register"
        if location is RedLocation.UNKNOWN:
            assert entry.spec_basis  # the question is fixed by files/04 §8.1 rule 7
        else:
            assert entry.sources  # action content needs a guideline, not only a spec


# --- refusals, each the near miss of the committed document above -----------------------------


def _on_site_action(text: str) -> Any:
    return lambda d: d["action"]["ON_SITE"]["action_tr"].update(tr=text)


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.pop("scripts"),
        lambda d: d["scripts"].pop("UNKNOWN"),
        lambda d: d["scripts"]["REMOTE"].update(location="ON_SITE"),
        lambda d: d["scripts"]["REMOTE"].update(script_id="base.generic_red.other"),
        lambda d: d["scripts"]["ON_SITE"].update(register="ALERT"),
        lambda d: d["scripts"]["REMOTE"].update(sources=[]),
        lambda d: d["scripts"]["UNKNOWN"].update(spec_basis=[]),
        lambda d: (
            [s.update(supports="action_tr") for s in d["scripts"]["REMOTE"]["sources"]]
            and [b.update(supports="action_tr") for b in d["scripts"]["REMOTE"]["spec_basis"]]
        ),
        lambda d: d["scripts"]["REMOTE"]["sources"][0].update(supports="action_tr, ask_one_tr"),
        lambda d: d["scripts"]["REMOTE"]["sources"][0].update(quote="uydurma bir alıntı"),
        lambda d: d["scripts"]["REMOTE"]["sources"][0].update(
            snapshot="packages/protocols/sources/ABSENT-2026.txt"
        ),
        lambda d: d["scripts"]["REMOTE"]["sources"][0].update(
            snapshot="packages/protocols/sources/TR-EK4-2022.txt"
        ),
        lambda d: d["scripts"]["REMOTE"]["sources"][0].update(snapshot="files/04.md"),
        lambda d: d["action"]["ON_SITE"].update(show_112=True),
        _on_site_action("Acil Servis'e gidin. Gerekirse 112 arayın."),
        lambda d: d["action"]["ON_SITE"]["do_nots_tr"]["tr"].append("112 aramayın."),
        lambda d: d["action"]["ON_SITE"]["why_tr"].update(tr="Yüz on iki ile gelenler beklemez."),
        lambda d: d["action"]["UNKNOWN"]["ask_one_tr"].update(tr="Hastanede misiniz? 112"),
        lambda d: d.update(status="draft_needs_source"),
        lambda d: d.update(decision="CD-99"),
        lambda d: d.update(register_policy="always_alert"),
        lambda d: d.update(scope="production"),
    ],
    ids=[
        "no-location-entries",
        "a-location-missing",
        "location-mismatch",
        "script-id-mismatch",
        "fixed-register",
        "remote-without-guideline",
        "unknown-without-basis",
        "a-field-unsupported",
        "supports-a-field-it-lacks",
        "quote-not-in-snapshot",
        "snapshot-not-committed",
        "snapshot-of-another-guideline",
        "snapshot-outside-sources",
        "on-site-show-112",
        "on-site-action-text-112",
        "on-site-do-not-112",
        "on-site-why-spoken-112",
        "unknown-question-112",
        "draft-without-gap",
        "wrong-decision",
        "always-alert",
        "wrong-scope",
    ],
)
def test_a_document_claiming_more_than_it_carries_is_refused(tmp_path: Path, edit: Any) -> None:
    with pytest.raises(GenericRedError):
        load_generic_red(_write(tmp_path, edit))


def test_112_in_remote_text_is_the_near_miss_that_loads(committed: GenericRedCopy) -> None:
    assert committed.action is not None
    assert "112" in committed.action.remote.action_tr["tr"]  # type: ignore[index]


def test_a_draft_with_its_gap_loads_and_refuses_to_serve(tmp_path: Path) -> None:
    def draft(doc: dict[str, Any]) -> None:
        doc["status"] = "draft_needs_source"
        doc["source_gap"] = "sentetik: waiting for a register row"

    loaded = load_generic_red(_write(tmp_path, draft))
    assert generic_red_refusals(loaded) == ("generic_red_draft_needs_source",)


def test_a_draft_without_copy_has_no_strings_and_no_clips(tmp_path: Path) -> None:
    def draft(doc: dict[str, Any]) -> None:
        doc.pop("action")
        doc["status"] = "draft_needs_source"
        doc["source_gap"] = "sentetik: no copy yet"

    loaded = load_generic_red(_write(tmp_path, draft))
    assert generic_red_strings(loaded) == ()
    assert generic_red_clip_rows(loaded, voice="ses", acil_location_tr=None) == ()


def test_clip_rows_refuse_text_that_cannot_be_rendered_or_spoken(
    committed: GenericRedCopy,
) -> None:
    """A RED string that cannot be spoken correctly never reaches a TTS model."""
    assert committed.action is not None
    unrenderable = committed.model_copy(
        update={
            "action": committed.action.model_copy(
                update={
                    "remote": committed.action.remote.model_copy(
                        update={"action_tr": {"tr": "Hemen {{tenant.floor}} arayın."}}
                    )
                }
            )
        }
    )
    with pytest.raises(GenericRedError, match="rendered"):
        generic_red_clip_rows(unrenderable, voice="ses", acil_location_tr=None)
    unspeakable = committed.model_copy(
        update={
            "action": committed.action.model_copy(
                update={
                    "remote": committed.action.remote.model_copy(
                        update={"action_tr": {"tr": "Hemen 112'yi arayın."}}
                    )
                }
            )
        }
    )
    with pytest.raises(GenericRedError, match="spoken"):
        generic_red_clip_rows(unspeakable, voice="ses", acil_location_tr=None)
    # Near miss: the committed copy renders and speaks.
    assert generic_red_clip_rows(committed, voice="ses", acil_location_tr=None)


def test_absent_refuses_and_unreadable_raises(tmp_path: Path) -> None:
    assert generic_red_refusals(None) == ("generic_red_absent",)
    with pytest.raises(GenericRedError):
        load_generic_red(tmp_path / "absent.yaml")


# --- CD-24's content near-miss tests ---------------------------------------------------------

CONDITION_STEMS = ("kalp", "kalb", "inme", "kanama")  # CD-24's own named examples


def test_the_copy_names_no_condition(committed: GenericRedCopy) -> None:
    strings = generic_red_strings(committed)
    assert strings
    for text in strings:
        folded = text.casefold()
        assert not any(stem in folded for stem in CONDITION_STEMS), text
    # Near miss: CD-24's own example of the wording it rejects fails the same
    # check. A literal, so a fix to HB-C12b can never turn this test red.
    assert any(stem in "kalple ilgili olabilir" for stem in CONDITION_STEMS)


def test_on_site_asks_for_an_escort_and_remote_carries_no_pending_do_not(
    committed: GenericRedCopy,
) -> None:
    assert committed.action is not None
    on_site = committed.action.on_site.do_nots_tr["tr"]
    assert "Tek başınıza gitmeyin; bir görevliden yardım isteyin." in on_site
    # Near miss: driving, accompaniment and nil-by-mouth stay draft in CD-24 for REMOTE.
    remote = " ".join(committed.action.remote.do_nots_tr["tr"]).casefold()
    for pending in ("aracınızla", "tek başınıza", "yiyip içmeyin"):
        assert pending not in remote


def test_on_site_carries_no_112_in_any_carrier(committed: GenericRedCopy) -> None:
    assert committed.action is not None
    on_site = committed.action.on_site
    texts = [on_site.action_tr["tr"], on_site.why_tr["tr"], *on_site.do_nots_tr["tr"]]  # type: ignore[index]
    for text in (*texts, on_site.primary, on_site.secondary or ""):
        assert not re.search(r"112|yüz on iki", text.casefold())
    assert on_site.show_112 is False and on_site.numbers == ()


def test_one_generic_id_per_location() -> None:
    assert set(GENERIC_RED_SCRIPT_IDS) == set(RedLocation)
    assert len(set(GENERIC_RED_SCRIPT_IDS.values())) == len(RedLocation)
