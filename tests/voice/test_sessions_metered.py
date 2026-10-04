"""INT-190 — the per-session denominator: one count per metered session.

The cost module's per-session figure is usage in a window divided by the
sessions metered in that window. The numerator series (``voice_tts_chars`` and
the other group B quantities) are emitted by the INT-101 ``SessionMeter``; the
denominator has to come from the same object, or the ratio would divide one
population by another. So the meter counts its session exactly once, when the
composition root builds a session around it, with the meter's own label set
minus ``vendor`` (a session has no vendor) — and never with the session key,
which would make the series' cardinality the number of patients seen
(CLAUDE.md invariant 6).
"""

from __future__ import annotations

import test_typed_parity as parity
from intake_platform.slo import PHI_RISK_LABEL_NAMES
from intake_voice_runtime.composition import build_residency_tr_session, build_typed_session
from intake_voice_runtime.metering import SessionLedger, SessionMeter, TurnLabels
from intake_voice_runtime.metrics import VOICE_SESSIONS_METERED
from intake_voice_runtime.profiles import VoiceProfile
from prometheus_client import REGISTRY
from protocols.addressing import Addressing
from red_harness import RecordingClinicNotifier
from talker_harness import VOICE_ID, FakeClock, RecordedClipStore, RecordingSynthesizer

TENANT = "t-sessions"
BRANCH = "genel"


def _count(profile: VoiceProfile) -> float:
    value = REGISTRY.get_sample_value(
        "voice_sessions_metered_total",
        {"tenant": TENANT, "profile": profile.value, "branch": BRANCH},
    )
    return value if value is not None else 0.0


def _meter(profile: VoiceProfile) -> SessionMeter:
    return SessionMeter(
        ledger=SessionLedger(parity.SESSION),
        labels=TurnLabels(tenant=TENANT, profile=profile, branch=BRANCH),
    )


def _typed(meter: SessionMeter | None) -> None:
    build_typed_session(
        protocol=parity._protocol(),
        addressing=Addressing.SELF,
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        protocol_hash=parity.HASH,
        clock=FakeClock(),
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        clinic=RecordingClinicNotifier(),
        screen=parity.RecordingScreen(),
        meter=meter,
    )


def test_composing_a_metered_session_counts_it_once() -> None:
    before = _count(VoiceProfile.TYPED)
    _typed(_meter(VoiceProfile.TYPED))
    assert _count(VoiceProfile.TYPED) == before + 1.0


def test_a_voice_session_is_counted_under_its_own_profile() -> None:
    before_voice = _count(VoiceProfile.RESIDENCY_TR)
    before_typed = _count(VoiceProfile.TYPED)
    clock = FakeClock()
    build_residency_tr_session(
        protocol=parity._protocol(),
        addressing=Addressing.SELF,
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        voice_id=VOICE_ID,
        protocol_hash=parity.HASH,
        clock=clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=parity.RecordingSink(clock=clock),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        clinic=RecordingClinicNotifier(),
        screen=parity.RecordingScreen(),
        meter=_meter(VoiceProfile.RESIDENCY_TR),
    )
    assert _count(VoiceProfile.RESIDENCY_TR) == before_voice + 1.0
    assert _count(VoiceProfile.TYPED) == before_typed


def test_near_miss_an_unmetered_session_is_not_counted() -> None:
    # the denominator counts the sessions whose usage the numerator carries;
    # a session with no meter spends into no series and must not dilute it
    before = _count(VoiceProfile.TYPED)
    _typed(None)
    assert _count(VoiceProfile.TYPED) == before


def test_a_meter_counts_its_session_at_most_once() -> None:
    meter = _meter(VoiceProfile.TYPED)
    before = _count(VoiceProfile.TYPED)
    meter.count_session()
    meter.count_session()
    assert _count(VoiceProfile.TYPED) == before + 1.0


def test_the_session_labels_carry_no_identifier() -> None:
    meter = _meter(VoiceProfile.TYPED)
    labels = meter.labels.session_labels()
    assert set(labels) == {"tenant", "profile", "branch"}
    assert not set(labels) & PHI_RISK_LABEL_NAMES
    assert meter.ledger.session_key not in labels.values()
    assert parity.SESSION not in labels.values()
    assert VOICE_SESSIONS_METERED._labelnames == ("tenant", "profile", "branch")
