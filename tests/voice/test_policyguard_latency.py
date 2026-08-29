"""INT-091 — streaming PolicyGuard (CLAUDE.md invariant 2; files/03 §4.2).

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-091):
  "... PolicyGuard <=20ms per sentence"

files/03 §4.2: *"Streaming PolicyGuard: regex + tiny classifier per sentence
before TTS (≤ 20 ms); violation → sentence dropped and a cached safe bridge is
spoken"*, and the Talker's own system prompt constrains it to *"speak ≤ 2
sentences; no diagnosis/treatment/prognosis language; one question per turn;
B1 Turkish"*.

The one place invariant 2 and invariant 10 could collide is scripted text:
files/03 §4.6 invariant 7 resolves it — *"Talker output for kind=scripted
equals text_tr (PolicyGuard still runs)"*. So on scripted text the guard
**reports** and never mutates; on dynamic text it drops the offending
sentence. Both directions are asserted.

The budget is measured as a hard maximum over a warm corpus, not a mean: a
p50 under budget with a p99 over it is exactly the failure the ≤ 20 ms line
exists to prevent.
"""

from __future__ import annotations

import time

import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import (
    B1_MAX_WORDS_PER_SENTENCE,
    MAX_SENTENCES_PER_TURN,
    POLICY_GUARD_BUDGET_MS,
    FormOfAddress,
    PolicyGuard,
    ViolationClass,
)

CLEAN = "Ağrınız ne zaman başladı?"


@pytest.fixture()
def guard() -> PolicyGuard:
    return PolicyGuard(profile=VoiceProfile.RESIDENCY_TR)


def _classes(guard: PolicyGuard, text: str) -> set[ViolationClass]:
    return {violation.violation_class for violation in guard.inspect_sentence(text)}


# --- the budget --------------------------------------------------------------------


def test_the_budget_constant_is_the_blueprint_number() -> None:
    assert POLICY_GUARD_BUDGET_MS == 20.0


def test_every_sentence_is_inspected_inside_the_budget(guard: PolicyGuard) -> None:
    corpus = [
        CLEAN,
        "Bu şikâyetiniz ne zamandır var?",
        "Size teşhis koyabilirim.",
        "İlacınızı hemen kullanın.",
        "Merak etmeyin, kısa sürede geçer.",
        "Şu anda hastanede misiniz, yanınızda biri var mı?",
        "Anamnezinizde bir etiyoloji saptanmadı ve semptomatoloji atipik seyrediyor.",
        "Nasılsın, iyi misin?",
    ]
    guard.inspect_sentence(CLEAN)  # warm the compiled patterns

    worst_ms = 0.0
    for _ in range(40):
        for sentence in corpus:
            started = time.perf_counter()
            guard.inspect_sentence(sentence)
            worst_ms = max(worst_ms, (time.perf_counter() - started) * 1000.0)

    assert worst_ms <= POLICY_GUARD_BUDGET_MS, (
        f"worst per-sentence inspection {worst_ms:.3f} ms exceeds the "
        f"{POLICY_GUARD_BUDGET_MS} ms budget (files/03 §4.2, §4.5)"
    )


def test_the_filter_reports_the_time_it_spent(guard: PolicyGuard) -> None:
    verdict = guard.filter(CLEAN, scripted=False)
    assert verdict.elapsed_ms >= 0.0
    assert verdict.elapsed_ms <= POLICY_GUARD_BUDGET_MS * MAX_SENTENCES_PER_TURN


# --- clean text passes --------------------------------------------------------------


def test_a_clean_question_passes_untouched(guard: PolicyGuard) -> None:
    verdict = guard.filter(CLEAN, scripted=False)
    assert verdict.text_tr == CLEAN
    assert verdict.violations == ()
    assert verdict.dropped == ()
    assert verdict.bridge_required is False


def test_an_empathic_acknowledgement_plus_one_question_passes(guard: PolicyGuard) -> None:
    text = "Anlıyorum. Ağrınız ne zaman başladı?"
    assert guard.filter(text, scripted=False).text_tr == text


# --- invariant 2: no diagnosis, treatment or prognosis ------------------------------


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Size teşhis koyabilirim.", ViolationClass.DIAGNOSIS),
        ("Bu bir migren atağı.", ViolationClass.DIAGNOSIS),
        ("Kalp krizi geçiriyorsunuz.", ViolationClass.DIAGNOSIS),
        ("Günde iki kez ağrı kesici alın.", ViolationClass.TREATMENT),
        ("Bu ilacı kullanmayı bırakın.", ViolationClass.TREATMENT),
        ("Size bir tedavi öneriyorum.", ViolationClass.TREATMENT),
        ("Merak etmeyin, kısa sürede geçer.", ViolationClass.PROGNOSIS),
        ("Ciddi bir şey değil.", ViolationClass.PROGNOSIS),
        ("Endişelenmenize gerek yok.", ViolationClass.PROGNOSIS),
    ],
)
def test_clinical_language_is_caught(
    guard: PolicyGuard, sentence: str, expected: ViolationClass
) -> None:
    assert expected in _classes(guard, sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Düzenli kullandığınız bir ilaç var mı?",
        "Daha önce bu şikâyet için tedavi gördünüz mü?",
        "Doktorunuz size bir tanı söyledi mi?",
        "Ağrınız geçti mi?",
    ],
)
def test_asking_about_diagnosis_or_treatment_is_not_giving_one(
    guard: PolicyGuard, sentence: str
) -> None:
    """Near-miss negative controls: the protocol's own questions must pass, or
    the guard would silence the intake it exists to protect."""
    clinical = {ViolationClass.DIAGNOSIS, ViolationClass.TREATMENT, ViolationClass.PROGNOSIS}
    assert _classes(guard, sentence) & clinical == set()


# --- one question per turn, two sentences, B1, register -----------------------------


def test_two_questions_in_one_turn_are_caught(guard: PolicyGuard) -> None:
    sentence = "Şu anda hastanede misiniz, yanınızda biri var mı?"
    assert ViolationClass.MULTI_QUESTION in _classes(guard, sentence)


def test_two_question_marks_in_one_turn_are_caught(guard: PolicyGuard) -> None:
    verdict = guard.filter("Nereniz ağrıyor? Ne zaman başladı?", scripted=False)
    assert ViolationClass.MULTI_QUESTION in {v.violation_class for v in verdict.violations}


def test_more_than_two_sentences_is_caught(guard: PolicyGuard) -> None:
    verdict = guard.filter("Anlıyorum. Peki. Devam edelim. Nereniz ağrıyor?", scripted=False)
    assert ViolationClass.TOO_LONG in {v.violation_class for v in verdict.violations}
    assert MAX_SENTENCES_PER_TURN == 2


def test_a_long_sentence_fails_the_b1_bound(guard: PolicyGuard) -> None:
    long_sentence = " ".join(["kelime"] * (B1_MAX_WORDS_PER_SENTENCE + 3)) + "."
    assert ViolationClass.JARGON in _classes(guard, long_sentence)


def test_unexplained_jargon_fails_b1(guard: PolicyGuard) -> None:
    assert ViolationClass.JARGON in _classes(guard, "Anamnezinizde bir etiyoloji saptanmadı.")


def test_the_sen_register_is_caught_when_the_patient_has_not_mirrored_it(
    guard: PolicyGuard,
) -> None:
    """CLAUDE.md: `siz` universally — `sen` is reachable only by mirroring."""
    assert ViolationClass.REGISTER in _classes(guard, "Nasılsın, iyi misin?")


def test_the_sen_register_passes_once_the_patient_has_mirrored_it() -> None:
    mirrored = PolicyGuard(profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SEN)
    assert ViolationClass.REGISTER not in _classes(mirrored, "Nasılsın?")


def test_siz_forms_never_trip_the_register_rule(guard: PolicyGuard) -> None:
    for sentence in ("Nasılsınız?", "Şikâyetinizi anlatır mısınız?", "Devam edelim."):
        assert ViolationClass.REGISTER not in _classes(guard, sentence)


# --- what happens to a violating turn ------------------------------------------------


def test_a_violating_sentence_is_dropped_from_dynamic_text(guard: PolicyGuard) -> None:
    verdict = guard.filter("Bu bir migren atağı. Ağrınız ne zaman başladı?", scripted=False)
    assert "migren" not in verdict.text_tr
    assert verdict.text_tr == "Ağrınız ne zaman başladı?"
    assert verdict.dropped == ("Bu bir migren atağı.",)
    assert verdict.bridge_required is False


def test_a_wholly_violating_turn_asks_for_the_safe_bridge(guard: PolicyGuard) -> None:
    verdict = guard.filter("Bu bir migren atağı.", scripted=False)
    assert verdict.text_tr == ""
    assert verdict.bridge_required is True


def test_scripted_text_is_reported_but_never_mutated(guard: PolicyGuard) -> None:
    """Invariant 10 beats invariant 2's drop action on authored, reviewed text
    — files/03 §4.6 invariant 7 says the output still equals text_tr."""
    scripted = "Şu anda hastanede misiniz, yanınızda biri var mı?"
    verdict = guard.filter(scripted, scripted=True)
    assert verdict.text_tr == scripted
    assert verdict.dropped == ()
    assert verdict.bridge_required is False
    assert ViolationClass.MULTI_QUESTION in {v.violation_class for v in verdict.violations}


def test_blocks_are_counted_by_class_and_profile(guard: PolicyGuard) -> None:
    from intake_voice_runtime.metrics import POLICYGUARD_BLOCKS_TOTAL

    label = POLICYGUARD_BLOCKS_TOTAL.labels(
        **{"class": ViolationClass.DIAGNOSIS.value, "profile": VoiceProfile.RESIDENCY_TR.value}
    )
    before = label._value.get()
    guard.filter("Bu bir migren atağı.", scripted=False)
    assert label._value.get() == before + 1


def test_scripted_violations_are_not_counted_as_blocks(guard: PolicyGuard) -> None:
    """A report is not a block: nothing was withheld from the patient."""
    from intake_voice_runtime.metrics import POLICYGUARD_BLOCKS_TOTAL

    label = POLICYGUARD_BLOCKS_TOTAL.labels(
        **{
            "class": ViolationClass.MULTI_QUESTION.value,
            "profile": VoiceProfile.RESIDENCY_TR.value,
        }
    )
    before = label._value.get()
    guard.filter("Şu anda hastanede misiniz, yanınızda biri var mı?", scripted=True)
    assert label._value.get() == before


# --- sentence splitting is its own hazard --------------------------------------------


def test_the_splitter_keeps_turkish_abbreviations_whole(guard: PolicyGuard) -> None:
    assert guard.sentences("Dr. Ayşe sizi bekliyor.") == ("Dr. Ayşe sizi bekliyor.",)


def test_the_splitter_handles_every_terminator(guard: PolicyGuard) -> None:
    assert guard.sentences("Anlıyorum! Nereniz ağrıyor?") == (
        "Anlıyorum!",
        "Nereniz ağrıyor?",
    )


def test_empty_text_is_clean_and_needs_no_bridge(guard: PolicyGuard) -> None:
    verdict = guard.filter("   ", scripted=False)
    assert verdict.text_tr == ""
    assert verdict.violations == ()
    assert verdict.bridge_required is False
