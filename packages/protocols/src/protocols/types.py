"""Core enums of the Protocol DSL v2 (INT-040).

Every member set below is copied from the blueprint, never invented:
files/12 §2.1 (EK-4 acuity), files/12 §2.4 (tense), files/12 §1 + files/03 §6
(pack layers / resolution order), files/09 §1-2 (visit types, maturity),
files/13 §13 (delivery), files/04 §1 (voice hints), files/02 §5.3 via the
rule schema in files/protocols/base.life_threat.yaml (route, notify_clinic),
files/04 §8.1 rule 3 (rule status). The RED axes (register, location) are
re-exported from the INT-031 clinical schemas so the DSL and TriageResult
share one definition (CLAUDE.md invariant 21).
"""

from __future__ import annotations

import enum
from datetime import timedelta

from clinical_schemas.triage import RedLocation, RedRegister

__all__ = [
    "AckStyle",
    "Delivery",
    "EK4Level",
    "Maturity",
    "NotifyClinic",
    "Pace",
    "PackLayer",
    "RedFlagRoute",
    "RedLocation",
    "RedRegister",
    "RuleStatus",
    "SlotType",
    "Tense",
    "VisitType",
]


class PackLayer(enum.StrEnum):
    """Where a pack sits in the resolution chain ``base → cluster →
    specialty → visit_type → overlay → hospital`` (files/03 §6; files/12 §1
    directory layout; files/09 §1)."""

    BASE = "base"
    CLUSTER = "cluster"
    SPECIALTY = "specialty"
    VISIT_TYPE = "visit_type"
    OVERLAY = "overlay"
    HOSPITAL = "hospital"


class Maturity(enum.StrEnum):
    """Pack maturity ladder (files/09 §2): L0 generated (never served) →
    L1 reviewed → L2 validated → L3 published."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class VisitType(enum.StrEnum):
    """Visit types, orthogonal to branch (files/09 §1)."""

    FIRST = "first"
    FOLLOWUP = "followup"
    PREOP = "preop"
    REPORT = "report"
    PREGNANCY_FOLLOWUP = "pregnancy_followup"
    CHRONIC_REVIEW = "chronic_review"
    POST_DISCHARGE = "post_discharge"
    SCREENING = "screening"
    SECOND_OPINION = "second_opinion"
    TELECONSULT = "teleconsult"


_EK4_SEVERITY_ORDER = ("YESIL", "SARI_K2", "SARI_K1", "KIRMIZI_K2", "KIRMIZI_K1")


class EK4Level(enum.StrEnum):
    """EK-4 acuity, five-valued (files/12 §2.1; files/04 §3: RG 13/9/2022
    s. 31952 EK-4 — three colours, five levels).

    files/12 §2.1 orders the levels with ``functools.total_ordering``; here
    the order lives in :attr:`severity` because a ``StrEnum`` inherits
    ``str`` comparison, under which ``KIRMIZI_K1 < YESIL`` alphabetically —
    exactly the silent bug an acuity lattice cannot afford.
    """

    YESIL = "YESIL"
    SARI_K2 = "SARI_K2"
    SARI_K1 = "SARI_K1"
    KIRMIZI_K2 = "KIRMIZI_K2"
    KIRMIZI_K1 = "KIRMIZI_K1"

    @property
    def severity(self) -> int:
        """Position in the EK-4 lattice; higher is more acute."""
        return _EK4_SEVERITY_ORDER.index(self.value)

    @property
    def is_red(self) -> bool:
        """KIRMIZI levels are the RED of CLAUDE.md invariant 21 — the rules
        that must carry register and location-resolved actions."""
        return self in (EK4Level.KIRMIZI_K2, EK4Level.KIRMIZI_K1)

    @property
    def time_target(self) -> timedelta | None:
        """Only KIRMIZI_K2 carries the 10-minute regulatory target; K1 is
        *immediate*, which is not a numeric target (files/12 §2.1)."""
        return timedelta(minutes=10) if self is EK4Level.KIRMIZI_K2 else None


class Tense(enum.StrEnum):
    """When the triggering event happened (files/12 §2.4; files/04 §8.1
    rule 4). Every rule declares one, plus a ``tense_anchor`` slot."""

    NOW = "now"
    TODAY = "today"
    WITHIN_7D = "within_7d"
    WITHIN_30D = "within_30d"
    EVER = "ever"


class RedFlagRoute(enum.StrEnum):
    """Patient route axis (files/02 §5.3 Axis 1, as carried by the rule
    schema in files/protocols/base.life_threat.yaml)."""

    EMERGENCY_NOW = "EMERGENCY_NOW"
    SAME_DAY_ACIL = "SAME_DAY_ACIL"
    EXPEDITE = "EXPEDITE"


class NotifyClinic(enum.StrEnum):
    """Clinic notification policy per rule; for every RED it is ``always``,
    unconditional and time-bound (files/protocols/base.life_threat.yaml;
    files/04 §4.2 defect 1)."""

    ALWAYS = "always"
    NEVER = "never"


class RuleStatus(enum.StrEnum):
    """Rule provenance status (files/04 §8.1 rule 3): ``active`` rules carry
    a source block; ``draft_needs_source`` rules carry a source_gap and are
    never compiled into a served pack (CLAUDE.md invariant 17)."""

    ACTIVE = "active"
    DRAFT_NEEDS_SOURCE = "draft_needs_source"


class Delivery(enum.StrEnum):
    """Per-section / per-slot delivery channel (files/13 §13): safeguarding
    and screening content is ``text_only`` — no clip, no speech, ever."""

    VOICE = "voice"
    TEXT_FIRST = "text_first"
    TEXT_ONLY = "text_only"


class AckStyle(enum.StrEnum):
    """Voice hint ``ack_style`` (files/04 §1: brief|warm|none)."""

    BRIEF = "brief"
    WARM = "warm"
    NONE = "none"


class Pace(enum.StrEnum):
    """Voice hint ``pace`` (files/04 §1: normal|slow)."""

    NORMAL = "normal"
    SLOW = "slow"


class SlotType(enum.StrEnum):
    """Typed slot answers. Members come from files/03 §6 slot examples
    (code, quantity, integer) and the GuardExpr scalar types of files/13
    §9.5 (bool, int, decimal, string, code, date, duration) — no floats
    anywhere, per the same section."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    CODE = "code"
    DATE = "date"
    DURATION = "duration"
    QUANTITY = "quantity"
