"""INT-483 / ADR-040 — the runtime selects proxy text or skips, by subject role.

The compiler half (tests/protocols/test_proxy_addressing.py) proves a proxy
document exists only when every self-addressed item is handled. This half
proves what the engine does with it:

* a proxy session speaks the pack's proxy text verbatim, and a self session
  the self text, from documents resolved for each (invariant 10);
* a session whose subject role disagrees with the document's addressing is
  refused before any question is asked — a proxy is never put the patient's
  own second-person questions, and the self document never runs a proxy
  session (D24 1Y: the paths stay closed until the content exists);
* a skipped item is recorded ``NOT_ASKED_PROXY``: never offered, never bound,
  never confirmed from the patient's overlay, never ``ASKED_ABSENT``, counted
  against must-ask coverage, and shown to the clinician as not asked (proxy).
  That it reads Unknown to every rule is asserted in the safety suite
  (tests/safety/test_triage_when.py).

Synthetic ids and strings throughout (files/04 §7), on the INT-041 compiler
fixture. No proxy copy for a real pack is written here.
"""

from __future__ import annotations

import ast
import datetime
import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.note import NoteMeta, ScreeningBlock, ScreeningProvenance
from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RulesTriageResult, TriageLevel
from intake_platform.legal import LegalStringsCatalog
from intake_voice_runtime.clinical_agent import EngineError, IntakeEngine
from intake_voice_runtime.composition import build_residency_tr_session, build_typed_session
from intake_voice_runtime.note import (
    NOTE_COPY_KEYS,
    NoteGap,
    NoteGapReason,
    compose,
    note_copy_from_legal_strings,
    render_soap,
)
from protocols.addressing import Addressing
from protocols.bindings import OperationalTemplate, load_opt
from protocols.compile import LifeThreatSet, load_life_threat_set, resolve_protocol
from protocols.compile.resolve import ResolvedProtocol
from protocols.loader import PackRegistry
from protocols.pack import ProtocolPack

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "protocols" / "compile"
OPT = REPO / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"
SYNTHETIC_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.synthetic.yaml"
NOW = datetime.datetime(2026, 10, 4, 9, 0, tzinfo=datetime.UTC)

VEKIL_NEDEN = "Sentetik vekil sorusu: yakınınızı bugün buraya getiren nedir?"
SELF_NEDEN = "Bugün sizi buraya getiren nedir?"
SKIPPED = "tarama.sessiz_soru"


def _text(value: str) -> dict[str, str]:
    return {"tr": value}


def _raw() -> dict[str, Any]:
    """The compiler fixture, every askable slot handled. ``tarama.sessiz_soru``
    is made must_ask and skipped in a proxy session, so the must-ask coverage
    consequence of a skip is observable."""
    raw = yaml.safe_load((FIXTURES / "tree" / "base" / "intake.yaml").read_text("utf-8"))
    slots = raw["sections"]["ziyaret"]["slots"]
    slots["basvuru_nedeni"]["proxy"] = {
        "ask_tr": _text(VEKIL_NEDEN),
        "follow_up_tr": _text("Sentetik vekil sorusu: yakınınızın en önemli şikâyeti nedir?"),
    }
    slots["sure_dakika"]["proxy"] = {
        "ask_tr": _text("Sentetik vekil sorusu: yakınınızın şikâyeti ne kadar sürüyor?"),
        "confirm_tr": _text("Sentetik vekil onayı: mg cinsinden mi?"),
        "follow_up_tr": _text("Sentetik vekil sorusu: yaklaşık olarak söyleyebilir misiniz?"),
    }
    slots["renk_secimi"]["proxy"] = {"ask_tr": _text("Sentetik vekil renk sorusu?")}
    sessiz = raw["sections"]["tarama"]["slots"]["sessiz_soru"]
    sessiz["must_ask"] = True
    sessiz["proxy"] = {"skip": True}
    assert isinstance(raw, dict)
    return raw


@pytest.fixture(scope="module")
def life_threat() -> LifeThreatSet:
    return load_life_threat_set(FIXTURES / "life_threat_signed.yaml")


@pytest.fixture(scope="module")
def template() -> OperationalTemplate:
    return load_opt(OPT)


def _document(
    addressing: Addressing, life_threat: LifeThreatSet, template: OperationalTemplate
) -> ResolvedProtocol:
    registry = PackRegistry()
    registry.add(ProtocolPack.model_validate(_raw()))
    return resolve_protocol(
        pack_id="base.derlenebilir",
        registry=registry,
        life_threat=life_threat,
        template=template,
        addressing=addressing,
    )


@pytest.fixture(scope="module")
def proxy_document(life_threat: LifeThreatSet, template: OperationalTemplate) -> ResolvedProtocol:
    return _document(Addressing.PROXY, life_threat, template)


@pytest.fixture(scope="module")
def self_document(life_threat: LifeThreatSet, template: OperationalTemplate) -> ResolvedProtocol:
    return _document(Addressing.SELF, life_threat, template)


# --- selection by subject role ----------------------------------------------------


def test_a_proxy_session_speaks_the_packs_proxy_text(proxy_document: ResolvedProtocol) -> None:
    engine = IntakeEngine(protocol=proxy_document, reference_time=NOW, addressing=Addressing.PROXY)
    step = engine.next_step()
    assert step is not None
    assert step.step_id == "ziyaret.basvuru_nedeni"
    assert step.text_tr == VEKIL_NEDEN
    assert engine.addressing is Addressing.PROXY


def test_a_self_session_speaks_the_self_text(self_document: ResolvedProtocol) -> None:
    """The near miss: same pack, same slot, the patient answering."""
    engine = IntakeEngine(protocol=self_document, reference_time=NOW, addressing=Addressing.SELF)
    step = engine.next_step()
    assert step is not None
    assert step.text_tr == SELF_NEDEN
    assert engine.state_of(SKIPPED) is AnswerState.NOT_ASKED
    assert engine.proxy_skipped == ()


def test_a_session_cannot_be_composed_without_its_subject_role() -> None:
    """The production boundary: both session builders require the role, with
    no default, so whoever wires session start has to state it — a
    ``proxy_report`` session cannot fall through to the self document."""
    for builder in (build_residency_tr_session, build_typed_session):
        parameter = inspect.signature(builder).parameters["addressing"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_every_engine_built_in_services_is_handed_the_sessions_role() -> None:
    """The engine's own ``addressing`` may be omitted by a unit test, which
    then runs the document's addressing; a service may not omit it."""
    unstated: list[str] = []
    for path in sorted((REPO / "services").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "IntakeEngine"
                and "addressing" not in {keyword.arg for keyword in node.keywords}
            ):
                unstated.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert unstated == []


def test_an_engine_built_without_a_role_runs_the_documents_addressing(
    proxy_document: ResolvedProtocol, self_document: ResolvedProtocol
) -> None:
    assert IntakeEngine(protocol=proxy_document, reference_time=NOW).addressing is Addressing.PROXY
    assert IntakeEngine(protocol=self_document, reference_time=NOW).addressing is Addressing.SELF


def test_a_proxy_session_on_a_self_document_is_refused(self_document: ResolvedProtocol) -> None:
    """D24 1Y: the proxy path is closed until a proxy document exists. The self
    document's second-person questions are never put to a proxy."""
    with pytest.raises(EngineError, match="proxy"):
        IntakeEngine(protocol=self_document, reference_time=NOW, addressing=Addressing.PROXY)


def test_a_self_session_on_a_proxy_document_is_refused(proxy_document: ResolvedProtocol) -> None:
    with pytest.raises(EngineError, match="self"):
        IntakeEngine(protocol=proxy_document, reference_time=NOW, addressing=Addressing.SELF)


# --- the skipped item -------------------------------------------------------------


def _proxy_engine(document: ResolvedProtocol) -> IntakeEngine:
    return IntakeEngine(protocol=document, reference_time=NOW, addressing=Addressing.PROXY)


def test_a_skipped_item_records_not_asked_proxy_and_is_never_offered(
    proxy_document: ResolvedProtocol,
) -> None:
    engine = _proxy_engine(proxy_document)
    assert engine.state_of(SKIPPED) is AnswerState.NOT_ASKED_PROXY
    assert engine.proxy_skipped == (SKIPPED,)
    offered: list[str] = []
    while (step := engine.next_step()) is not None:
        offered.append(step.step_id)
        engine.mark_asked(step.step_id)
        engine.apply_extraction(step.step_id, {step.step_id: "sentetik"})
    assert SKIPPED not in offered
    with pytest.raises(EngineError, match="frontier"):
        engine.mark_asked(SKIPPED)


def test_a_skipped_item_never_binds_and_never_becomes_asked_absent(
    proxy_document: ResolvedProtocol,
) -> None:
    """An extraction that names the skipped slot — the speaker volunteering
    their OWN answer, the hazard the skip exists for — binds nothing."""
    engine = _proxy_engine(proxy_document)
    engine.mark_asked("ziyaret.basvuru_nedeni")
    engine.apply_extraction(
        "ziyaret.basvuru_nedeni", {"ziyaret.basvuru_nedeni": "sentetik", SKIPPED: False}
    )
    assert engine.state_of(SKIPPED) is AnswerState.NOT_ASKED_PROXY
    assert engine.value_of(SKIPPED) is None


def test_a_skipped_must_ask_counts_against_coverage(proxy_document: ResolvedProtocol) -> None:
    """Not asked is a gap, never a covered item and never a negative."""
    coverage = _proxy_engine(proxy_document).must_ask_coverage()
    assert SKIPPED in coverage.obliged
    assert SKIPPED in coverage.outstanding
    assert SKIPPED not in coverage.covered


def _overlay(key: str, value: object) -> PatientOverlay:
    return PatientOverlay(
        patient_ref="sentetik-hasta",
        version=1,
        facts=(
            LearnedFact(
                key=key,
                value=value,
                source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
                source_ref="sentetik-kaynak",
                confidence=1.0,
                confirmed_at=NOW,
            ),
        ),
    )


def test_a_skipped_item_is_never_confirmed_from_the_overlay(
    proxy_document: ResolvedProtocol,
) -> None:
    """A confirm is a question too: a step the proxy session never asks is
    not offered as a confirm either."""
    engine = IntakeEngine(
        protocol=proxy_document,
        reference_time=NOW,
        overlay_facts=_overlay(SKIPPED, True),
        addressing=Addressing.PROXY,
    )
    assert engine.delta.prefills == ()
    assert engine.state_of(SKIPPED) is AnswerState.NOT_ASKED_PROXY


def test_a_reworded_item_is_confirmed_in_its_proxy_wording(
    proxy_document: ResolvedProtocol,
) -> None:
    """The near miss: the reworded slot does prefill, and the confirm the
    proxy hears is the pack's proxy confirm_tr, verbatim."""
    engine = IntakeEngine(
        protocol=proxy_document,
        reference_time=NOW,
        overlay_facts=_overlay("ziyaret.sure_dakika", 5),
        addressing=Addressing.PROXY,
    )
    (prefill,) = engine.delta.prefills
    assert prefill.slot_ref == "ziyaret.sure_dakika"
    assert prefill.confirm_tr == "Sentetik vekil onayı: mg cinsinden mi?"


def test_the_clinician_note_shows_a_skipped_item_as_not_asked_proxy(
    proxy_document: ResolvedProtocol,
) -> None:
    engine = _proxy_engine(proxy_document)
    gaps = tuple(NoteGap.not_asked_proxy(step_id) for step_id in engine.proxy_skipped)
    assert gaps == (
        NoteGap(section="tarama", reason=NoteGapReason.NOT_ASKED_PROXY, unit="sessiz_soru"),
    )
    composed = compose(
        meta=NoteMeta(
            visit_id="visit-0483",
            protocol_hash=proxy_document.resolved_protocol_hash,
            mode="detailed",
            generated_at=NOW,
            model="synthetic-note-model@rev0",
            prompt_version="note-v0",
        ),
        triage=RulesTriageResult(level=TriageLevel.GREEN),
        screening=ScreeningBlock(
            provenance=ScreeningProvenance(
                administration_mode="voice", proxy_reported=True, third_party_present=False
            )
        ),
        gaps=gaps,
    )
    assert composed.note.data_gaps == ("tarama:not_asked_proxy:sessiz_soru",)
    copy = note_copy_from_legal_strings(
        LegalStringsCatalog(SYNTHETIC_STRINGS).entry(required=NOTE_COPY_KEYS)
    )
    marker = copy.gap(NoteGapReason.NOT_ASKED_PROXY)
    assert f"tarama · sessiz_soru — {marker}" in render_soap(composed, copy)
    # near miss: a declined item is a different fact with a different marker
    assert marker != copy.gap(NoteGapReason.DECLINED)
