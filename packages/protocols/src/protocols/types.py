"""Core enums of the Protocol DSL v2 (INT-040).

Every member set below is copied from the blueprint, never invented:
files/12 §2.1 (EK-4 acuity), files/12 §2.4 (tense), files/12 §1 + files/03 §6
(pack layers / resolution order), files/09 §1-2 (visit types, maturity),
files/13 §13 (delivery), files/04 §1 (voice hints), files/02 §5.3 via the
rule schema in files/protocols/base.life_threat.yaml (route, notify_clinic),
files/04 §8.1 rule 3 (rule status), and the owner's D3 decision of
2026-09-26 for the data categories (INT-349). The RED axes (register, location) are
re-exported from the INT-031 clinical schemas so the DSL and TriageResult
share one definition (CLAUDE.md invariant 21).
"""

from __future__ import annotations

import enum
from datetime import timedelta

from clinical_schemas.triage import RedLocation, RedRegister

__all__ = [
    "SLOT_KEY_PATTERN",
    "SLOT_REF_PATTERN",
    "AbandonmentHandler",
    "AckStyle",
    "CrisisNumber",
    "DataCategory",
    "Delivery",
    "EK4Level",
    "Maturity",
    "NotifyClinic",
    "OfflineDraftPath",
    "Pace",
    "PackLayer",
    "Prosody",
    "RedFlagRoute",
    "RedLocation",
    "RedRegister",
    "RuleStatus",
    "SlotType",
    "Tense",
    "VisitType",
]

# The two key shapes, unanchored so both the pydantic constraints in
# :mod:`protocols.dsl` and the ``when`` tokenizer in
# :mod:`protocols.triage.expr` can be built from them. They live here, in the
# leaf module both sides already import, because a slot REFERENCE is what a
# red-flag predicate reads (files/03 §6 atoms, e.g. ``hpi.single_hot_swollen_
# joint``, ``vitals.temp_c``) and ``tense_anchor`` is unioned into exactly
# that reference set by :func:`protocols.triage.engine` — files/12 §2.4. Two
# patterns would let the anchor and the predicate drift into two namespaces,
# which is how an anchor silently stops resolving and its rule silently stops
# firing.
SLOT_KEY_PATTERN = r"[a-z][a-z0-9_]*"
"""A bare slot or section key, snake_case (files/03 §6 examples)."""

SLOT_REF_PATTERN = rf"{SLOT_KEY_PATTERN}(?:\.{SLOT_KEY_PATTERN})*"
"""A slot reference: one or more dot-joined keys. Section-qualified
(``chest_pain.onset_at``) or bare (``sikayet_suresi``) — files/03 §6 atoms;
files/protocols/base.life_threat.yaml writes the qualified form throughout."""


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


class Prosody(enum.StrEnum):
    """How a spoken RED is voiced (files/02 §5.3 Axis 2, Audio column):
    ``ALERT`` is *"Spoken with urgent prosody, alert sound"* and ``CALM`` is
    *"Spoken softly, no alert sound"*. Two members because the table names
    two; a rule that speaks nothing carries no prosody at all rather than a
    third "none" member, so the absence is visible in the type."""

    URGENT = "urgent"
    SOFT = "soft"


class OfflineDraftPath(enum.StrEnum):
    """Whether an item may enter the encrypted offline-resume cache
    (files/02 §8). One member, because files/04 §8.2 names one value:
    ``crisis_items_have_no_offline_draft_path``. files/04 §4.2 defect 2 gives
    the reason — a disclosure cached for offline resume *"may never reach the
    server at all"*. A second member is a clinician's decision to add, not an
    engineer's; until then anything but ``forbidden`` fails to parse."""

    FORBIDDEN = "forbidden"


class AbandonmentHandler(enum.StrEnum):
    """What happens when a patient force-quits after a disclosure — *"the
    highest-risk state the product can enter"* (files/04 §4.2 defect 2). One
    member, because that defect names one required mechanism: server-side
    evaluation **on the answer**. Same reasoning as
    :class:`OfflineDraftPath`: the set is closed until a human widens it."""

    SERVER_SIDE_ON_ANSWER = "server_side_on_answer"


class CrisisNumber(enum.IntEnum):
    """The Turkish crisis numbers, as the files/04 §4.1 table states them —
    a closed set, so no model, search tool or learning-loop proposal can ever
    widen it (files/04 §4.1, binding).

    182 is **not** a member and never will be: ALO 182 is the MHRS *hospital
    appointment* line, and putting it in a crisis script routes a suicidal
    patient to a booking queue. The claim that it is a 24/7 suicide line is
    still in wide circulation, which is exactly why the set is enumerated
    here rather than left as an integer. Türkiye has no 988 equivalent.

    The numerals never reach a TTS model: these are screen affordances, and
    the protocol compiler expands every spoken numeral to Turkish orthography
    separately (CLAUDE.md invariant 22). The Turkish text that accompanies
    them lives in docs/legal/strings.yaml under PolicyGuard, never here.
    """

    EMERGENCY = 112
    """Single national emergency number since 1 Feb 2018; psychiatric
    emergencies including suicide risk are in remit (files/04 §4.1)."""

    SOCIAL_SERVICES = 183
    """ALO 183 — violence, child abuse, neglect (files/04 §4.1)."""

    SUBSTANCE_MISUSE = 191
    """ALO 191 — substance misuse (files/04 §4.1)."""


class Delivery(enum.StrEnum):
    """Per-section / per-slot delivery channel (files/13 §13): safeguarding
    and screening content is ``text_only`` — no clip, no speech, ever."""

    VOICE = "voice"
    TEXT_FIRST = "text_first"
    TEXT_ONLY = "text_only"


class DataCategory(enum.StrEnum):
    """What kind of personal data a slot's answer is (INT-349; owner decision
    D3 of 2026-09-26).

    A closed set. ``general_health`` is the default, and its answers ride the
    ``slots.value`` column inventory as they always have. Each other member is
    a category the owner approved for the specialty review queue on
    2026-09-26 and that counsel has not yet placed. Its answers are
    envelope-encrypted at rest, and a slot carrying it is not servable until
    its row in docs/legal/data-categories.yaml is complete. A new member is a
    new category of personal data, which CLAUDE.md makes a stop-and-ask
    rather than an engineer's addition.
    """

    GENERAL_HEALTH = "general_health"
    """The patient's own symptoms, history and medicines: the pre-visit intake
    as it stood before D3."""

    PERSONAL_SAFETY = "personal_safety"
    """Forensic and personal-safety questions (adli tıp)."""

    SEXUAL_HEALTH = "sexual_health"
    """Genital and sexual-health symptoms (deri)."""

    SUBSTANCE_USE = "substance_use"
    """Use of substances other than alcohol (ruh sağlığı, klinik psikoloji)."""

    HOUSEHOLD = "household"
    """Household basic needs and household contacts (sosyal pediatri, halk
    sağlığı, nükleer tıp). The other members of the household are data
    subjects too."""

    RELATIVES_HEALTH = "relatives_health"
    """Relatives' family health history and consanguinity (tıbbi genetik,
    onkoloji, pediatri, immünoloji, nefroloji, hematoloji, metabolizma,
    gastroenteroloji). The relatives are data subjects too."""

    PARTNER_FERTILITY = "partner_fertility"
    """The partner's fertility data (üreme endokrinolojisi, tıbbi genetik). The
    partner is a data subject too."""

    OCCUPATIONAL = "occupational"
    """Employer, occupational exposure and the purpose of a report (iş ve
    meslek hastalıkları, sağlık kurulu)."""

    LITERACY = "literacy"
    """Reading and learning difficulty (hemşirelik eğitim, sosyal pediatri)."""


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
