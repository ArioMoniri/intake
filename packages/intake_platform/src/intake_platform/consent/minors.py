"""INT-223 — the minor & guardian rules engine (files/06 §6; TMK-339; HHY-24).

Given a date of birth and its jurisdiction context, this module answers two
questions and nothing else:

1. **which age band** the subject is in — ``child`` / ``adolescent`` /
   ``adult`` / ``unknown``;
2. **which actor** must give a consent for a scope — ``self`` or
   ``guardian`` — plus whether the adolescent's own in-app acknowledgement
   is additionally required.

It decides nothing about whether the consent itself stands: that is
``intake_platform.consent.service`` and the api's one enforcement point
(``ensure_consent``). The two run in the same evaluation so a minor's own
grant can never unlock a scope the guardian has to hold.

**What is settled and what is not.** ``POLICY_TABLE`` is the whole rule set
as data. A row is either

- ``PolicyStatus.SET`` — files/06 (or a statute files/06 §1 names) states
  the value, and ``source`` cites where; or
- ``PolicyStatus.AWAITING_HUMAN`` — the question is legally contested and
  no document in the repo answers it. The row then carries the ``ask`` (a
  named human and one sentence) and the ``fail_closed`` behaviour the code
  actually implements meanwhile. Fail closed here always means the MOST
  restrictive reading: guardian required, service refused.

No age threshold, maturity rule or visibility default is invented in code.
Where the answer is unknown the row says so and the engine refuses; it never
picks a plausible number (HUMAN_BLOCKERS rule 1) and it never routes around
the gap (rule 2).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import date

from intake_platform.consent.registry import resolve_scope

__all__ = [
    "ADOLESCENT_MIN_AGE",
    "ADULT_AGE",
    "JURISDICTION_TR",
    "POLICY_TABLE",
    "ActorDecision",
    "AgeBand",
    "AgeContext",
    "ClinicPolicy",
    "DobAssurance",
    "PolicyEntry",
    "PolicyStatus",
    "RequiredActor",
    "SectionAudience",
    "VisibilityDecision",
    "adolescent_private_visibility",
    "classify",
    "policy_entry",
    "resolve_consent_actor",
]

#: files/06 §6, verbatim: "Under-18: guardian account holds the legal
#: consents (TMK velâyet; HHY-24)". Majority is the boundary, not a product
#: choice.
ADULT_AGE = 18

#: files/06 §6, verbatim: "the adolescent (12–17) additionally acknowledges
#: in-app". 12 is the lower edge of that band.
ADOLESCENT_MIN_AGE = 12

#: The one jurisdiction whose minor law this engine encodes (files/06 is a
#: Turkish compliance frame end to end). Anything else is refused, not
#: guessed — see the ``jurisdiction_tr_only`` policy row.
JURISDICTION_TR = "TR"

_JURISDICTION_SHAPE = re.compile(r"^[A-Z]{2}$")
#: Ids only — a clinic policy is referenced by its id, never by its text
#: (invariant 6, and the text itself is the clinic's document, not ours).
_ID_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class PolicyStatus(enum.StrEnum):
    SET = "set"
    AWAITING_HUMAN = "awaiting-human"


class AgeBand(enum.StrEnum):
    CHILD = "child"
    ADOLESCENT = "adolescent"
    ADULT = "adult"
    #: No usable date of birth: the minor regime cannot be asserted either
    #: way. It is NOT a band the engine ever treats as adult-by-default.
    UNKNOWN = "unknown"


class RequiredActor(enum.StrEnum):
    SELF = "self"
    GUARDIAN = "guardian"


class DobAssurance(enum.StrEnum):
    """How the date of birth was established. ``VERIFIED`` is the only value
    the adult path accepts (INT-223 acceptance: "age from verified DOB")."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    ABSENT = "absent"


class SectionAudience(enum.StrEnum):
    CLINICIAN = "clinician"
    GUARDIAN = "guardian"


@dataclass(frozen=True)
class PolicyEntry:
    """One row of the rule set. ``ask`` and ``fail_closed`` are required for
    an awaiting-human row and meaningless for a settled one — enforced in
    ``__post_init__`` so an under-specified row cannot be written."""

    id: str
    question: str
    status: PolicyStatus
    value: str
    source: str | None = None
    ask: str | None = None
    owner: str | None = None
    fail_closed: str | None = None

    def __post_init__(self) -> None:
        if self.status is PolicyStatus.SET:
            if not self.source:
                raise ValueError(f"policy row {self.id!r}: a settled row must cite its source")
            return
        if not self.ask or not self.owner or not self.fail_closed:
            raise ValueError(
                f"policy row {self.id!r}: an awaiting-human row must carry "
                "{ask, owner, fail_closed}"
            )


_FILES_06_6 = "files/06 §6 (Minors, companions, kiosk — firm rules)"
_COUNSEL = "Turkish counsel (health-law), instructed by the owner"

POLICY_TABLE: tuple[PolicyEntry, ...] = (
    # --- settled by files/06 §6 -----------------------------------------------------
    PolicyEntry(
        id="adult_age",
        question="At what age does the guardian-consent regime stop applying?",
        status=PolicyStatus.SET,
        value="18",
        source=f"{_FILES_06_6}: 'Under-18: guardian account holds the legal consents'; TMK-339",
    ),
    PolicyEntry(
        id="adolescent_min_age",
        question="Where does the adolescent band begin?",
        status=PolicyStatus.SET,
        value="12",
        source=f"{_FILES_06_6}: 'the adolescent (12–17) additionally acknowledges in-app'",
    ),
    PolicyEntry(
        id="adult_actor",
        question="Who consents for a verified adult?",
        status=PolicyStatus.SET,
        value="self",
        source=f"{_FILES_06_6}; KVKK m.6 açık rıza is the data subject's own",
    ),
    PolicyEntry(
        id="adolescent_actor",
        question="Who consents for a 12–17 year old?",
        status=PolicyStatus.SET,
        value="guardian, plus the adolescent's own in-app acknowledgement",
        source=f"{_FILES_06_6}; TMK-339 velâyet; HHY-24 (the child heard per maturity)",
    ),
    PolicyEntry(
        id="child_actor",
        question="Who consents for an under-12?",
        status=PolicyStatus.SET,
        value="guardian",
        source=f"{_FILES_06_6}; TMK-339 velâyet",
    ),
    PolicyEntry(
        id="no_dob_recorded",
        question="What applies when no date of birth is recorded at all?",
        status=PolicyStatus.SET,
        value="the minor regime is not asserted; ordinary consent state decides",
        source=(
            "INT-223 acceptance ('age from verified DOB') — under-18 status is established "
            "ONLY from a verified DOB, so with no DOB record the gate asserts nothing and "
            "the consent ledger alone answers. Whether a DOB must be collected before "
            "intake at all is the open dob_collection_mandatory row"
        ),
    ),
    PolicyEntry(
        id="adolescent_private_clinician_delivery",
        question="Is the adolescent-private section delivered to the clinician?",
        status=PolicyStatus.SET,
        value="yes, unconditionally",
        source=f"{_FILES_06_6}: 'the adolescent-private section is delivered to the clinician'",
    ),
    PolicyEntry(
        id="adolescent_private_guardian_clinic_policy",
        question="May the guardian see the adolescent-private section?",
        status=PolicyStatus.SET,
        value="only per the treating clinic's recorded written policy; the app records which",
        source=(
            f"{_FILES_06_6}: 'guardian visibility of that section follows the treating clinic's "
            "written policy within HHY information rights — the app records which policy applied'"
        ),
    ),
    # --- contested: fail closed, ask the human ---------------------------------------
    PolicyEntry(
        id="unverified_dob",
        question="Does a self-declared date of birth support the adult self-consent path?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="refuse until answered",
        ask=(
            "Does counsel accept a self-declared date of birth as the basis for the adult "
            "self-consent path, or must the DOB be verified against an authenticated identity "
            "source before any self-consent is recorded?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "an unverified DOB is refused outright — neither the adult path nor the guardian "
            "path is inferred from it"
        ),
    ),
    PolicyEntry(
        id="dob_collection_mandatory",
        question="Must a verified DOB be collected before any intake may run?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="not collected today; the gate asserts nothing without one",
        ask=(
            "Must counsel have us collect and verify a date of birth before any intake session, "
            "given that without one the under-18 regime of files/06 §6 cannot be asserted at all?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "no DOB is collected or persisted by this issue; the engine asserts no age band "
            "and the guardian regime therefore never engages silently"
        ),
    ),
    PolicyEntry(
        id="adolescent_self_consent",
        question="May a 12–17 year old self-consent for any scope (HHY-24 maturity)?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="no scope is self-consentable by a minor",
        ask=(
            "Does counsel read HHY m.24 as permitting a mature 12–17 year old to give açık rıza "
            "for any INTAKE purpose alone, and if so exactly which purposes?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "every purpose requires the guardian; the adolescent's acknowledgement is recorded "
            "alongside it and never in place of it"
        ),
    ),
    PolicyEntry(
        id="emancipation",
        question="Does emancipation (TMK ergin kılınma / marriage) end the guardian requirement?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="not recognised by the engine",
        ask=(
            "Does counsel require us to honour an emancipation claim (TMK ergin kılınma or "
            "majority by marriage) as ending the guardian requirement, and on what evidence?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "no emancipation input exists on the age context at all, so a claim cannot be "
            "expressed and the guardian requirement stands for every under-18"
        ),
    ),
    PolicyEntry(
        id="leap_day_maturity",
        question="On which day does a 29-February birth reach majority in a non-leap year?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="the later day (1 March)",
        ask=(
            "Does counsel confirm that a 29-February birth attains majority on 1 March in a "
            "non-leap year under Turkish reckoning, rather than on 28 February?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "the later day is used, so guardian coverage lasts one day longer rather than one "
            "day shorter"
        ),
    ),
    PolicyEntry(
        id="adolescent_private_guardian_default",
        question="What happens when the clinic has recorded no written visibility policy?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="the guardian sees nothing",
        ask=(
            "Where a clinic has recorded no written policy, does counsel accept withholding the "
            "adolescent-private section from the guardian, or do HHY information rights compel "
            "disclosure to the legal representative by default?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "no recorded policy means no guardian visibility, and the decision records that no "
            "policy applied"
        ),
    ),
    PolicyEntry(
        id="jurisdiction_tr_only",
        question="Which jurisdictions' minor rules does this engine encode?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="Türkiye only; anything else is refused",
        ask=(
            "Which jurisdictions beyond Türkiye must counsel have us serve, so their majority "
            "ages and guardian rules can be encoded rather than refused?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "a subject whose jurisdiction is anything other than TR is refused service rather "
            "than evaluated against Turkish thresholds"
        ),
    ),
    PolicyEntry(
        id="guardian_link_basis",
        question="What is the KVKK basis and retention for a persisted guardian↔minor link?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="unset; the linkage store stays behind a closed gate",
        ask=(
            "Which KVKK m.5/m.6 ground and which retention period does counsel assign to a "
            "persisted guardian↔minor relationship record, which is a new personal-data "
            "category we do not hold today?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "the guardian_links table exists with an awaiting-human basis annotation and its "
            "read AND write paths refuse while the guardian_link flag is off (default)"
        ),
    ),
    PolicyEntry(
        id="guardian_relationship_proof",
        question="What proves that a guardian account really is the child's legal representative?",
        status=PolicyStatus.AWAITING_HUMAN,
        value="no proof standard is implemented",
        ask=(
            "What evidence of velâyet does counsel require before a guardian account may consent "
            "for a minor — an in-app acknowledgement, a hospital-desk check, or an official "
            "record — and who bears the verification duty?"
        ),
        owner=_COUNSEL,
        fail_closed=(
            "the link row carries verified_at NULL and an id-shaped relationship_ref only; "
            "nothing in this issue treats a link as proof of representation"
        ),
    ),
)


def _index_policy_rows(rows: tuple[PolicyEntry, ...]) -> dict[str, PolicyEntry]:
    """Id → row, refusing a duplicate: two rows under one id would let a
    decision cite the settled one while the contested one is what applies."""
    index: dict[str, PolicyEntry] = {}
    for entry in rows:
        if entry.id in index:
            raise ValueError(f"duplicate policy row id {entry.id!r}")
        index[entry.id] = entry
    return index


_POLICY_BY_ID: dict[str, PolicyEntry] = _index_policy_rows(POLICY_TABLE)


def policy_entry(entry_id: str) -> PolicyEntry:
    """One row by id. Raises ``KeyError`` for an id the table does not hold —
    a caller inventing a policy name must fail, not silently proceed."""
    return _POLICY_BY_ID[entry_id]


@dataclass(frozen=True)
class AgeContext:
    """What the caller knows about the subject's age, and how well."""

    dob: date | None
    assurance: DobAssurance
    jurisdiction: str = JURISDICTION_TR

    def __post_init__(self) -> None:
        if self.assurance is DobAssurance.ABSENT:
            if self.dob is not None:
                raise ValueError("an absent assurance cannot carry a dob")
        elif self.dob is None:
            raise ValueError("a verified or unverified assurance requires a dob")
        if not _JURISDICTION_SHAPE.match(self.jurisdiction):
            raise ValueError("jurisdiction must be an ISO 3166-1 alpha-2 code")

    @classmethod
    def verified(cls, dob: date, *, jurisdiction: str = JURISDICTION_TR) -> AgeContext:
        return cls(dob=dob, assurance=DobAssurance.VERIFIED, jurisdiction=jurisdiction)

    @classmethod
    def unverified(cls, dob: date, *, jurisdiction: str = JURISDICTION_TR) -> AgeContext:
        return cls(dob=dob, assurance=DobAssurance.UNVERIFIED, jurisdiction=jurisdiction)

    @classmethod
    def absent(cls, *, jurisdiction: str = JURISDICTION_TR) -> AgeContext:
        return cls(dob=None, assurance=DobAssurance.ABSENT, jurisdiction=jurisdiction)


@dataclass(frozen=True)
class ActorDecision:
    """Which actor must consent, and what is missing if service is refused."""

    scope: str
    band: AgeBand
    required_actor: RequiredActor
    permitted: bool
    adolescent_ack_required: bool
    policy_entry: str
    missing: tuple[str, ...] = field(default=())
    refusal_code: str | None = None


@dataclass(frozen=True)
class ClinicPolicy:
    """The treating clinic's recorded written policy on guardian visibility
    of the adolescent-private section (files/06 §6). Referenced by id: the
    policy document belongs to the clinic, and the app records only which
    one applied."""

    policy_id: str
    guardian_may_view: bool

    def __post_init__(self) -> None:
        if not _ID_SHAPE.match(self.policy_id):
            raise ValueError("policy_id must be id-shaped (invariant 6)")


@dataclass(frozen=True)
class VisibilityDecision:
    audience: SectionAudience
    visible: bool
    policy_entry: str
    applied_policy: str | None = None


def _completed_years(dob: date, on: date) -> int:
    """Completed years, birthday-inclusive. A 29-February birth in a
    non-leap year rolls to 1 March, which is the fail-closed direction the
    ``leap_day_maturity`` row records (guardian coverage longer, not
    shorter)."""
    had_birthday = (on.month, on.day) >= (dob.month, dob.day)
    return on.year - dob.year - (0 if had_birthday else 1)


def classify(context: AgeContext, *, on: date) -> AgeBand:
    """The age band on the evaluation date. An absent or incoherent (future)
    date of birth is ``UNKNOWN`` — never quietly adult."""
    if context.dob is None:
        return AgeBand.UNKNOWN
    if context.dob > on:
        return AgeBand.UNKNOWN
    years = _completed_years(context.dob, on)
    if years >= ADULT_AGE:
        return AgeBand.ADULT
    if years >= ADOLESCENT_MIN_AGE:
        return AgeBand.ADOLESCENT
    return AgeBand.CHILD


#: Refusal codes the api maps 1:1 to a typed 403. Codes, never narrative,
#: and nothing derived from the DOB itself (invariant 6).
_REFUSAL_GUARDIAN = "guardian_consent_required"
_REFUSAL_DOB = "dob_unverified"
_REFUSAL_JURISDICTION = "jurisdiction_unsupported"


def resolve_consent_actor(context: AgeContext, *, scope: str, on: date) -> ActorDecision:
    """Which actor must hold the consent for ``scope``, and whether the
    subject may be served at all on the age axis.

    ``permitted`` answers only the age question. A ``True`` here still faces
    the consent ledger; a ``False`` is a refusal in its own right.
    """
    purpose = resolve_scope(scope)  # closed registry: an unknown scope raises

    def decided(
        band: AgeBand,
        actor: RequiredActor,
        *,
        permitted: bool,
        entry: str,
        ack: bool = False,
        missing: tuple[str, ...] = (),
        refusal: str | None = None,
    ) -> ActorDecision:
        policy_entry(entry)  # a decision may only cite a row that exists
        return ActorDecision(
            scope=purpose.id if purpose.parameterised else scope,
            band=band,
            required_actor=actor,
            permitted=permitted,
            adolescent_ack_required=ack,
            policy_entry=entry,
            missing=missing,
            refusal_code=refusal,
        )

    if context.jurisdiction != JURISDICTION_TR:
        return decided(
            AgeBand.UNKNOWN,
            RequiredActor.GUARDIAN,
            permitted=False,
            entry="jurisdiction_tr_only",
            missing=("recognised_jurisdiction",),
            refusal=_REFUSAL_JURISDICTION,
        )
    if context.assurance is DobAssurance.ABSENT:
        return decided(
            AgeBand.UNKNOWN,
            RequiredActor.SELF,
            permitted=True,
            entry="no_dob_recorded",
        )
    if context.assurance is DobAssurance.UNVERIFIED:
        return decided(
            AgeBand.UNKNOWN,
            RequiredActor.GUARDIAN,
            permitted=False,
            entry="unverified_dob",
            missing=("verified_dob",),
            refusal=_REFUSAL_DOB,
        )
    band = classify(context, on=on)
    if band is AgeBand.UNKNOWN:
        # verified assurance over a future date of birth: an incoherent
        # record is not a verified one
        return decided(
            AgeBand.UNKNOWN,
            RequiredActor.GUARDIAN,
            permitted=False,
            entry="unverified_dob",
            missing=("verified_dob",),
            refusal=_REFUSAL_DOB,
        )
    if band is AgeBand.ADULT:
        return decided(band, RequiredActor.SELF, permitted=True, entry="adult_actor")
    if band is AgeBand.ADOLESCENT:
        return decided(
            band,
            RequiredActor.GUARDIAN,
            permitted=False,
            entry="adolescent_actor",
            ack=True,
            missing=("guardian_consent", "adolescent_ack"),
            refusal=_REFUSAL_GUARDIAN,
        )
    return decided(
        band,
        RequiredActor.GUARDIAN,
        permitted=False,
        entry="child_actor",
        missing=("guardian_consent",),
        refusal=_REFUSAL_GUARDIAN,
    )


def adolescent_private_visibility(
    audience: SectionAudience, *, clinic_policy: ClinicPolicy | None
) -> VisibilityDecision:
    """Who may see the adolescent-private section (files/06 §6).

    The clinician always may. The guardian may only where the treating
    clinic has a recorded written policy saying so — and the decision names
    which policy applied, because "the app records which policy applied" is
    the obligation, not merely the outcome.
    """
    if audience is SectionAudience.CLINICIAN:
        return VisibilityDecision(
            audience=audience,
            visible=True,
            policy_entry="adolescent_private_clinician_delivery",
        )
    if clinic_policy is None:
        return VisibilityDecision(
            audience=audience,
            visible=False,
            policy_entry="adolescent_private_guardian_default",
        )
    return VisibilityDecision(
        audience=audience,
        visible=clinic_policy.guardian_may_view,
        policy_entry="adolescent_private_guardian_clinic_policy",
        applied_policy=clinic_policy.policy_id,
    )
