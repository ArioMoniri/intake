"""What the blueprint publishes as a per-turn budget, and nothing else.

files/02 §8.1 is the source, and its first sentence is the reason this module
exists rather than a constant somewhere: *"A latency NFR without a measurement
point and a named network profile is unfalsifiable and does not belong in a
tender."* So every row here carries the network profile it was published for
and the sentence it came from, and a row the blueprint does **not** publish is
a :class:`BudgetNotPublished` rather than a number.

Three rows are refusals, and each is a different kind:

* **``typed``** — files/02 §8.1 publishes no per-turn NFR for it at all. The
  temptation is to reuse ``residency_tr``'s; that would be inventing an NFR.
* **``residency_tr`` p95** — published as *"OPEN — to be measured … We will
  publish a p95 when we have measured one."* Deliberately unset, not missing.
* **hospital guest wifi** — *"publish no NFR — force cellular"*. An
  instruction, not a gap.

⚠ The two files disagree about the fourth case and this module does not
resolve it. files/03 §4.4 gives ``residency_tr`` *"p95 ≈ 1684–2364 ms"*, which
``apps/mobile/src/lib/dialogue/tts.ts`` has already committed as
``TURN_ROUND_TRIP_BUDGET_MS``; files/02 §8.1 says the same figure is OPEN.
:data:`RESIDENCY_TR_P95_BAND_MS` records the band so the disagreement is
visible, and :func:`published_budget` returns the §8.1 answer, because §8.1 is
the product NFR section and the one a tender would quote.

**Measurement point, stated once**, because a number without it is not a
budget: *"last patient speech sample → first agent audio sample, on device,
client clock."* The simulator measures the Talker's own turn, which is a
**part** of that interval and never the whole of it — see
:mod:`intake_voice_runtime.simulator.report`.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "DISPLACED_FLOOR",
    "IN_COUNTRY_FLOOR",
    "MID_LTE_DYNAMIC_P95_ITEMISED_MS",
    "RESIDENCY_TR_P95_BAND_MS",
    "VENDOR_HOP_SAVING_P50_MS",
    "VENDOR_HOP_SAVING_P95_MS",
    "BudgetNotPublished",
    "NetworkProfile",
    "PublishedBudget",
    "StructuralFloor",
    "TurnClass",
    "displaced_baseline_dynamic",
    "published_budget",
]


class BudgetNotPublished(LookupError):
    """No per-turn budget is published for this row, and none is invented."""


class TurnClass(enum.StrEnum):
    """files/02 §8.1 publishes two turn classes and prices them differently."""

    #: Served from the pre-synthesised clip cache — *"~70 % of fast-mode turns"*.
    SCRIPTED = "scripted"
    #: The remainder, where the model and the streaming TTS are on the path.
    DYNAMIC = "dynamic"


class NetworkProfile(enum.StrEnum):
    """The named network profiles of files/02 §8.1, with their TR shares."""

    HOME_WIFI = "home_wifi"
    TR_MOBILE_5G = "tr_mobile_5g"
    TR_MOBILE_MID_LTE = "tr_mobile_mid_lte"
    TR_MOBILE_WEAK_LTE = "tr_mobile_weak_lte"
    HOSPITAL_GUEST_WIFI = "hospital_guest_wifi"


class PublishedBudget(FrozenModel):
    """One published row. A ``None`` bound must say why it is ``None``."""

    profile: VoiceProfile
    turn_class: TurnClass
    network: NetworkProfile | None = Field(
        default=None, description="None where the row is published per voice profile only."
    )
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    p99_ms: float | None = Field(default=None, ge=0.0)
    open_reason: str | None = Field(
        default=None, description="Why an unset bound is unset — the blueprint's own words."
    )
    source: str = Field(min_length=1, description="The file and section the row comes from.")

    @model_validator(mode="after")
    def _an_unset_bound_states_its_reason(self) -> PublishedBudget:
        if (self.p50_ms is None or self.p95_ms is None) and not self.open_reason:
            raise ValueError(
                "a budget row with an unset bound must carry open_reason: an NFR that "
                "is silently absent is indistinguishable from one nobody wrote down "
                "(files/02 §8.1)"
            )
        return self


class StructuralFloor(FrozenModel):
    """The arithmetic floor a turn cannot beat, whatever the models do."""

    p50_ms: float = Field(gt=0.0)
    p95_ms: float = Field(gt=0.0)
    source: str = Field(min_length=1)


_S81: Final = "files/02 §8.1"

#: files/02 §8.1: *"a structural floor that is 376 ms p50 / 481 ms p95 with a
#: Frankfurt SFU and 338 / 434 ms in-country"*.
DISPLACED_FLOOR: Final = StructuralFloor(
    p50_ms=376.0, p95_ms=481.0, source=f"{_S81} (Frankfurt SFU)"
)
IN_COUNTRY_FLOOR: Final = StructuralFloor(p50_ms=338.0, p95_ms=434.0, source=f"{_S81} (in-country)")

#: files/02 §8.1 / files/03 §4.4: *"`residency_tr` removes 117 ms p50 / 141 ms
#: p95 of vendor-hop RTT"*. The lever the whole profile argument rests on.
VENDOR_HOP_SAVING_P50_MS: Final = 117.0
VENDOR_HOP_SAVING_P95_MS: Final = 141.0

#: files/02 §8.1's itemised mid-LTE p95: *"transport 114 + jitter 190 + EOU 320
#: + STT flush & hop 297 + LLM TTFT & hop 647 + PolicyGuard 40 + TTS first-byte
#: & hop 447 = 2055 ms"*. Note this is the **itemisation**, not the published
#: target of 2100 ms in the same section — the section states both.
MID_LTE_DYNAMIC_P95_ITEMISED_MS: Final = 2_055.0

#: files/03 §4.4's competing p95 for the same profile files/02 §8.1 leaves
#: OPEN. Recorded so the disagreement is visible; not returned as a budget.
RESIDENCY_TR_P95_BAND_MS: Final[tuple[float, float]] = (1_684.0, 2_364.0)

_RESIDENCY_OPEN: Final = (
    "files/02 §8.1: 'OPEN - to be measured. Deliberately unset. … We will publish a p95 "
    "when we have measured one.'"
)

_TYPED_ABSENT: Final = (
    "files/02 §8.1 publishes no per-turn latency NFR for 'typed'. It is the degrade "
    "target and the kill switch (ADR-010); reusing residency_tr's row would be "
    "inventing an NFR for a modality whose whole point is that it does not stream."
)

_HOSPITAL_ABSENT: Final = (
    "files/02 §8.1: 'hospital guest wifi - publish no NFR - force cellular (03 §4.4b)'. "
    "Hospital wifi measurements are UNVERIFIED (files/03 §4.4b)."
)

#: Dynamic turn, per voice profile. Exactly one row is published.
_DYNAMIC_BY_PROFILE: Final[Mapping[VoiceProfile, PublishedBudget]] = {
    VoiceProfile.RESIDENCY_TR: PublishedBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_class=TurnClass.DYNAMIC,
        p50_ms=1_300.0,
        p95_ms=None,
        open_reason=_RESIDENCY_OPEN,
        source=f"{_S81} 'Other profiles' table",
    ),
}

#: Scripted turn, per network profile: *"home or wifi ≤ 400 / 620 / 850 ms ·
#: 5G-class ≤ 430 / 620 / 850 · mid LTE ≤ 450 / 680 / 950 · weak LTE ≤ 520 /
#: 820 / 1200"*.
_SCRIPTED_BY_NETWORK: Final[Mapping[NetworkProfile, tuple[float, float, float]]] = {
    NetworkProfile.HOME_WIFI: (400.0, 620.0, 850.0),
    NetworkProfile.TR_MOBILE_5G: (430.0, 620.0, 850.0),
    NetworkProfile.TR_MOBILE_MID_LTE: (450.0, 680.0, 950.0),
    NetworkProfile.TR_MOBILE_WEAK_LTE: (520.0, 820.0, 1_200.0),
}

#: Dynamic turn, per network profile — the **displaced baseline** with three EU
#: vendor hops. files/02 §8.1 keeps this table *"only for the arithmetic it
#: contains"*, so it is exposed for the lever calculation and never as a
#: per-voice-profile budget.
_DYNAMIC_BY_NETWORK: Final[Mapping[NetworkProfile, tuple[float, float, float]]] = {
    NetworkProfile.HOME_WIFI: (850.0, 1_700.0, 2_400.0),
    NetworkProfile.TR_MOBILE_5G: (950.0, 1_900.0, 2_700.0),
    NetworkProfile.TR_MOBILE_MID_LTE: (1_000.0, 2_100.0, 3_000.0),
    NetworkProfile.TR_MOBILE_WEAK_LTE: (1_150.0, 2_400.0, 3_600.0),
}


def published_budget(
    profile: VoiceProfile,
    turn_class: TurnClass,
    *,
    network: NetworkProfile | None = None,
) -> PublishedBudget:
    """The published row, or a refusal naming the sentence that refuses.

    ``network`` is required for a scripted turn, because files/02 §8.1
    publishes the scripted row per network profile and there is no
    profile-wide scripted figure to fall back on.
    """
    if profile is not VoiceProfile.RESIDENCY_TR:
        raise BudgetNotPublished(f"{profile.value!r}: {_TYPED_ABSENT}")
    if network is NetworkProfile.HOSPITAL_GUEST_WIFI:
        raise BudgetNotPublished(_HOSPITAL_ABSENT)
    if turn_class is TurnClass.DYNAMIC:
        # Deliberately network-independent. The per-network dynamic table is
        # the *displaced baseline* — the stack with three EU vendor hops that
        # files/02 §8.1 keeps "only for the arithmetic it contains" — and
        # returning one of its rows here would report a budget for a stack we
        # do not run. See :func:`displaced_baseline_dynamic`.
        return _DYNAMIC_BY_PROFILE[profile]
    if network is None:
        raise BudgetNotPublished(
            f"{_S81} publishes the scripted row per network profile; there is no "
            "profile-wide figure to fall back on, and a budget without a named "
            "network profile is unfalsifiable"
        )
    p50, p95, p99 = _SCRIPTED_BY_NETWORK[network]
    return PublishedBudget(
        profile=profile,
        turn_class=turn_class,
        network=network,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        open_reason=None,
        source=f"{_S81} scripted-turn row",
    )


def displaced_baseline_dynamic(network: NetworkProfile) -> PublishedBudget:
    """The pre-lever dynamic arithmetic, labelled as what it is.

    files/02 §8.1: the cloud tables are *"kept only for the arithmetic they
    contain, relabelled — not as live profiles."* This is that arithmetic, and
    it is a separate function rather than a branch of
    :func:`published_budget` so that no caller can print it as the budget of a
    profile we run.
    """
    if network is NetworkProfile.HOSPITAL_GUEST_WIFI:
        raise BudgetNotPublished(_HOSPITAL_ABSENT)
    p50, p95, p99 = _DYNAMIC_BY_NETWORK[network]
    return PublishedBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_class=TurnClass.DYNAMIC,
        network=network,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        open_reason=None,
        source=f"{_S81} displaced-baseline dynamic table (three EU vendor hops)",
    )
