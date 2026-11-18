"""The wellbeing engine (INT-116): validated instruments, verbatim, scored, fail-closed.

Acceptance (docs/backlog/issues.yaml INT-116): *"validated Turkish items
verbatim; scoring deterministic; crisis path completion tested end-to-end;
outputs never in patient summary"*.

**Where the words come from.** Item text, the timeframe lead-in and the
response options are read from one committed file,
``packages/protocols/instruments/tr/registry.yaml``, and every one of those
strings must appear verbatim in the committed snapshot under
``packages/protocols/sources/`` the entry cites. :func:`load_instrument_registry`
checks that with :func:`protocols.source_snapshots.source_snapshot_problem`, the
same check the life-threat loader runs on a quote, and refuses the whole file
on any miss. Nothing here holds, builds or transforms an item string: a prompt
hands the registry's own record over by reference (CLAUDE.md invariant 10;
files/04 header, instrument fidelity).

**What ships is empty, and refuses.** PHQ-2, PHQ-9, GAD-2 and GAD-7 are licence
GO, but no snapshot of the rights holder's Turkish text is committed, so
:func:`open_instrument` refuses each with ``items_not_committed``
(HUMAN_BLOCKERS HB-C29). C-SSRS (HB-L2) and WHO-5 (HB-L3) are refused on
licence before anything else is looked at, and the loader refuses to load any
content or cut-off for a non-GO instrument, so their text cannot be committed.

**Scoring is a sum of explicit selections.** An answer is an option id and
nothing else; its score is the option's. files/04 header: *"an LLM may not
infer a score from narrative"*. A total exists only when every item was
answered; nothing is prorated, because prorating is a clinical rule nobody has
supplied.

**Every cut-off is sourced or refused.** Cascade, crisis-trigger and severity
cut-offs are :class:`Cutoff` rows. An active one carries an integer and a
source block whose quote is verbatim in a committed snapshot; a draft one
carries the one permitted pending form (CLAUDE.md invariant 17) and the engine
refuses to apply it. No shipped cut-off is active.

**The crisis path is the rules engine's.** An instrument with a crisis item
does not open unless its trigger cut-off is sourced and a :class:`CrisisPath`
exists, because files/04 §4 forbids ending on that item without the safety
script. A :class:`CrisisPath` is built only from the *served* rule set and only
around the consent-independent rule ``rf.crisis_disclosure_signposting``; a
triggering answer is handed to :func:`protocols.triage.evaluate_triage` as the
slot that rule reads, and the patient receives the rule's own frozen action
object for the location (invariants 1, 10, 21). No string is produced here and
no model is reachable from this module. Today that rule is draft and unserved
(HB-C8, HB-C17), so no :class:`CrisisPath` can be built, and an instrument with
a crisis item cannot open.

**Outputs are clinician-only.** :class:`ClinicianInstrumentRecord` carries the
totals, the per-item scores and any sourced severity band, and
:func:`to_screening_block` maps totals into the clinician note's
``PreVisitNote.screening`` — a section the patient summary excludes (INT-085).
The patient gets :class:`PatientWellbeingView`, whose single field says whether
the questions were answered and nothing about what the answers mean.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Final, Literal

import yaml
from clinical_schemas.common import FrozenModel
from clinical_schemas.note import ScreeningBlock, ScreeningProvenance
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from pydantic import Field, StringConstraints, ValidationError, model_validator

from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.licences import InstrumentLicence, LicenceTable, instrument_licence
from protocols.source_snapshots import REPO_ROOT, source_snapshot_problem
from protocols.triage import evaluate_triage
from protocols.triage.context import SlotAnswer, TriageContext
from protocols.triage.expr import parse_when, referenced_slots
from protocols.types import RuleStatus
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

__all__ = [
    "CRISIS_ANSWER_SLOT",
    "CRISIS_RULE_ID",
    "REGISTRY_PATH",
    "SCREENING_FIELDS",
    "THIRD_PARTY_QUALIFIER_TR",
    "AdministrationMode",
    "AdministrationStatus",
    "AnswerRefused",
    "AnsweredItem",
    "ClinicianInstrumentRecord",
    "CommittedInstrument",
    "CommittedItem",
    "CrisisDelivery",
    "CrisisPath",
    "CrisisPathAbsent",
    "Cutoff",
    "CutoffKind",
    "CutoffSource",
    "CutoffUnavailable",
    "InstrumentAdministration",
    "InstrumentRegistry",
    "InstrumentRegistryError",
    "InstrumentUnavailable",
    "ItemPrompt",
    "PatientWellbeingStatus",
    "PatientWellbeingView",
    "ResponseOption",
    "SnapshotRef",
    "WellbeingRefusal",
    "cascade_target",
    "load_instrument_registry",
    "open_instrument",
    "severity_band",
    "to_screening_block",
]

#: The one committed source of instrument content.
REGISTRY_PATH: Final[Path] = REPO_ROOT / "packages/protocols/instruments/tr/registry.yaml"

#: The consent-independent crisis rule (files/protocols/base.life_threat.yaml
#: exemplar 4). Signposting, not a screener (files/04 §4.2 defect 3).
CRISIS_RULE_ID: Final[str] = "rf.crisis_disclosure_signposting"

#: The slot that rule's gate reads when it is set from the patient's own answer
#: (base.life_threat.yaml exemplar 4 ``gate``; CD-02 rule_gate_slots).
CRISIS_ANSWER_SLOT: Final[str] = "safety.self_harm_statement"

#: files/04 §4.3, verbatim: the qualifier states that a second voice was heard
#: and never who it was.
THIRD_PARTY_QUALIFIER_TR: Final[str] = "başka bir konuşmacı duyuldu"

#: Instrument id → the clinician note's ``ScreeningBlock`` field (files/04 §5).
SCREENING_FIELDS: Final[Mapping[str, str]] = MappingProxyType(
    {"PHQ-2": "phq2", "GAD-2": "gad2", "PHQ-9": "phq9", "GAD-7": "gad7"}
)

InstrumentId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9-]*$")]
LocalId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
CutoffId = Annotated[str, StringConstraints(pattern=r"^cut\.[a-z0-9_]+$", max_length=96)]
VerbatimText = Annotated[str, StringConstraints(min_length=1)]


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class WellbeingRefusal(enum.StrEnum):
    """Why the engine would not do something. Each is a fail-closed state."""

    LICENCE_NOT_GO = "licence_not_go"
    ITEMS_NOT_COMMITTED = "items_not_committed"
    CRISIS_TRIGGER_UNSOURCED = "crisis_trigger_unsourced"
    CRISIS_PATH_ABSENT = "crisis_path_absent"
    CUTOFF_NOT_DECLARED = "cutoff_not_declared"
    CUTOFF_UNSOURCED = "cutoff_unsourced"


class InstrumentRegistryError(ValueError):
    """The registry file is malformed or quotes something its snapshot does not."""


class InstrumentUnavailable(RuntimeError):
    """An instrument cannot be administered. Carries ids and a code, never text."""

    def __init__(self, instrument_id: str, code: WellbeingRefusal, why: str) -> None:
        super().__init__(f"{instrument_id}: {code.value} — {why}")
        self.instrument_id = instrument_id
        self.code = code


class CutoffUnavailable(RuntimeError):
    """A cut-off is undeclared or unsourced, so the engine will not apply one."""

    def __init__(self, instrument_id: str, code: WellbeingRefusal, why: str) -> None:
        super().__init__(f"{instrument_id}: {code.value} — {why}")
        self.instrument_id = instrument_id
        self.code = code


class CrisisPathAbsent(RuntimeError):
    """There is no served, consent-independent crisis rule to hand a disclosure to."""


class AnswerRefused(ValueError):
    """An answer the administration may not record. Never quotes the answer."""


# ---------------------------------------------------------------------------
# Registry models
# ---------------------------------------------------------------------------


class SnapshotRef(FrozenModel):
    """The committed snapshot an instrument's strings are quoted from."""

    snapshot: str = Field(description="Repo-relative path under packages/protocols/sources/.")
    guideline_id: str = Field(description="The snapshot header's guideline_id.")
    url: str = Field(description="The snapshot header's url.")
    retrieved_on: date = Field(description="The snapshot header's retrieved_on.")
    version_or_date: str = Field(description="The snapshot header's version_or_date.")


class CutoffSource(SnapshotRef):
    """A cut-off's provenance: a verbatim quote that states it."""

    quote: VerbatimText = Field(description="Verbatim from the snapshot body.")


class ResponseOption(FrozenModel):
    """One verbatim response option and the score the instrument gives it."""

    id: LocalId
    score: int = Field(ge=0, description="The instrument's own score for this option.")
    text_tr: VerbatimText = Field(description="Verbatim from the cited snapshot.")


class CommittedItem(FrozenModel):
    """One verbatim item. ``crisis_item`` marks the item files/04 §4 forbids
    ending on without the safety script (PHQ-9 item nine is the only one named)."""

    id: LocalId
    text_tr: VerbatimText = Field(description="Verbatim from the cited snapshot.")
    crisis_item: bool = Field(default=False)


class CommittedInstrument(FrozenModel):
    """A GO-licensed instrument whose every string is quoted from a snapshot."""

    id: InstrumentId
    source: SnapshotRef
    timeframe_tr: VerbatimText = Field(description="The verbatim timeframe lead-in.")
    options: tuple[ResponseOption, ...] = Field(min_length=2)
    items: tuple[CommittedItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> CommittedInstrument:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError(f"{self.id}: item ids must be unique")
        if len({o.id for o in self.options}) != len(self.options) or len(
            {o.score for o in self.options}
        ) != len(self.options):
            raise ValueError(f"{self.id}: option ids and option scores must be unique")
        return self

    @property
    def max_total(self) -> int:
        """The largest total the instrument can produce."""
        return len(self.items) * max(option.score for option in self.options)

    @property
    def crisis_item_ids(self) -> tuple[str, ...]:
        """Ids of the items the crisis path guards."""
        return tuple(item.id for item in self.items if item.crisis_item)


class CutoffKind(enum.StrEnum):
    """What a cut-off decides."""

    CASCADE = "cascade"
    CRISIS_TRIGGER = "crisis_trigger"
    SEVERITY = "severity"


class Cutoff(FrozenModel):
    """One cut-off. ``threshold`` is the lowest score that meets it.

    Active: an integer, a :class:`CutoffSource`, no ``source_gap``. Draft
    (``draft_needs_source``): no source, a ``source_gap``, and as threshold
    only the pending form of CLAUDE.md invariant 17 —
    ``TODO: <what> requires clinical sign-off`` — never a number.
    """

    id: CutoffId
    instrument: InstrumentId
    kind: CutoffKind
    status: RuleStatus
    threshold: int | str
    target: InstrumentId | None = Field(default=None, description="cascade: what it schedules.")
    item: LocalId | None = Field(default=None, description="crisis_trigger: the item it reads.")
    band: LocalId | None = Field(default=None, description="severity: the band it names.")
    source: CutoffSource | None = None
    source_gap: str | None = None

    @model_validator(mode="after")
    def _status_shape(self) -> Cutoff:
        if self.status is RuleStatus.DRAFT_NEEDS_SOURCE:
            if not isinstance(self.threshold, str) or not PLACEHOLDER_SIGNOFF_RE.fullmatch(
                self.threshold
            ):
                raise ValueError(
                    f"{self.id}: a draft cut-off carries only the pending form "
                    "'TODO: <what> requires clinical sign-off', never a number "
                    "(CLAUDE.md invariant 17)"
                )
            if self.source is not None or not self.source_gap:
                raise ValueError(f"{self.id}: a draft cut-off has a source_gap and no source")
            return self
        if not isinstance(self.threshold, int) or isinstance(self.threshold, bool):
            raise ValueError(f"{self.id}: an active cut-off's threshold is an integer")
        if self.threshold < 0:
            raise ValueError(f"{self.id}: a negative threshold is not a score")
        if self.source is None:
            raise ValueError(f"{self.id}: an active cut-off needs a source block")
        if self.source_gap is not None:
            raise ValueError(f"{self.id}: an active cut-off carries no source_gap")
        needed = {
            CutoffKind.CASCADE: ("target", self.target),
            CutoffKind.CRISIS_TRIGGER: ("item", self.item),
            CutoffKind.SEVERITY: ("band", self.band),
        }[self.kind]
        if needed[1] is None:
            raise ValueError(
                f"{self.id}: an active {self.kind.value} cut-off names its {needed[0]}"
            )
        return self


class InstrumentRegistry(FrozenModel):
    """The committed instruments and cut-offs for one locale."""

    locale: Literal["tr"]
    instruments: tuple[CommittedInstrument, ...] = ()
    cutoffs: tuple[Cutoff, ...] = ()

    @model_validator(mode="after")
    def _references(self) -> InstrumentRegistry:
        ids = [instrument.id for instrument in self.instruments]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate instrument id in the registry")
        cutoff_ids = [cutoff.id for cutoff in self.cutoffs]
        if len(set(cutoff_ids)) != len(cutoff_ids):
            raise ValueError("duplicate cut-off id in the registry")
        by_id = {instrument.id: instrument for instrument in self.instruments}
        for cutoff in self.cutoffs:
            if cutoff.status is not RuleStatus.ACTIVE:
                continue
            instrument = by_id.get(cutoff.instrument)
            if instrument is None:
                raise ValueError(f"{cutoff.id}: {cutoff.instrument} is not committed")
            if cutoff.target is not None and cutoff.target not in by_id:
                raise ValueError(f"{cutoff.id}: cascade target {cutoff.target} is not committed")
            if cutoff.item is not None and cutoff.item not in {i.id for i in instrument.items}:
                raise ValueError(f"{cutoff.id}: {instrument.id} has no item {cutoff.item}")
        return self

    def instrument(self, instrument_id: str) -> CommittedInstrument | None:
        """The committed instrument, or ``None``."""
        return next((i for i in self.instruments if i.id == instrument_id), None)

    def cutoffs_for(self, instrument_id: str, kind: CutoffKind) -> tuple[Cutoff, ...]:
        """Every cut-off of one kind for one instrument, in file order."""
        return tuple(c for c in self.cutoffs if c.instrument == instrument_id and c.kind is kind)


def _verbatim_problems(
    instrument: CommittedInstrument, *, repo_root: Path | None, allow_fixture_snapshots: bool
) -> list[str]:
    strings: list[tuple[str, str]] = [(f"{instrument.id}.timeframe", instrument.timeframe_tr)]
    strings.extend((f"{instrument.id}.option.{o.id}", o.text_tr) for o in instrument.options)
    strings.extend((f"{instrument.id}.{i.id}", i.text_tr) for i in instrument.items)
    problems: list[str] = []
    source = instrument.source
    for where, text in strings:
        problem = source_snapshot_problem(
            quote_snapshot=source.snapshot,
            guideline_id=source.guideline_id,
            quote=text,
            url=source.url,
            retrieved_on=source.retrieved_on,
            version_or_date=source.version_or_date,
            repo_root=repo_root,
            allow_fixture_snapshots=allow_fixture_snapshots,
        )
        if problem is not None:
            problems.append(f"{where}: {problem}")
    return problems


def _cutoff_problem(
    cutoff: Cutoff, *, repo_root: Path | None, allow_fixture_snapshots: bool
) -> str | None:
    if cutoff.source is None:
        return None
    problem = source_snapshot_problem(
        quote_snapshot=cutoff.source.snapshot,
        guideline_id=cutoff.source.guideline_id,
        quote=cutoff.source.quote,
        url=cutoff.source.url,
        retrieved_on=cutoff.source.retrieved_on,
        version_or_date=cutoff.source.version_or_date,
        repo_root=repo_root,
        allow_fixture_snapshots=allow_fixture_snapshots,
    )
    return None if problem is None else f"{cutoff.id}: {problem}"


def load_instrument_registry(
    path: Path = REGISTRY_PATH,
    *,
    licences: LicenceTable | None = None,
    repo_root: Path | None = None,
    allow_fixture_snapshots: bool = False,
) -> InstrumentRegistry:
    """Load and verify the registry; any defect refuses the whole file.

    ``licences`` and ``allow_fixture_snapshots`` exist for SENTETİK test
    registries only; production callers pass neither.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InstrumentRegistryError(f"{path.name} cannot be read as YAML") from exc
    if not isinstance(raw, dict) or raw.get("kind") != "instrument_registry":
        raise InstrumentRegistryError(f"{path.name} is not an instrument_registry document")
    body = {key: value for key, value in raw.items() if key != "kind"}
    try:
        registry = InstrumentRegistry.model_validate(body)
    except ValidationError as exc:
        raise InstrumentRegistryError(f"{path.name} does not validate: {exc}") from exc
    problems: list[str] = []
    named = [i.id for i in registry.instruments] + [c.instrument for c in registry.cutoffs]
    for instrument_id in dict.fromkeys(named):
        status = instrument_licence(instrument_id, licences)
        if status is not InstrumentLicence.GO:
            problems.append(
                f"{instrument_id} licence is {status.value}: no content or cut-off for it may "
                "be committed (files/04 header table; HB-L2, HB-L3)"
            )
    for instrument in registry.instruments:
        problems.extend(
            _verbatim_problems(
                instrument, repo_root=repo_root, allow_fixture_snapshots=allow_fixture_snapshots
            )
        )
    for cutoff in registry.cutoffs:
        problem = _cutoff_problem(
            cutoff, repo_root=repo_root, allow_fixture_snapshots=allow_fixture_snapshots
        )
        if problem is not None:
            problems.append(problem)
    if problems:
        raise InstrumentRegistryError("; ".join(problems))
    return registry


# ---------------------------------------------------------------------------
# The crisis path
# ---------------------------------------------------------------------------


class CrisisDelivery(FrozenModel):
    """What the patient is shown on a crisis answer: the rule's own script.

    There is no text field. ``action`` is the served rule's frozen
    location-resolved action object, returned by :func:`evaluate_triage`.
    """

    rule_id: str
    red_register: RedRegister
    location: RedLocation
    action: LocationAction | UnknownAction


class CrisisPath:
    """The seam to the consent-independent crisis rule, built from the served set.

    It takes no consent argument: files/04 §4.2 defect 3.
    """

    def __init__(self, rule: RedFlagRule, answer_slot: str, register: RedRegister) -> None:
        self._rule = rule
        self._answer_slot = answer_slot
        self._register = register

    @classmethod
    def from_served(
        cls,
        served_rules: Iterable[RedFlagRule],
        *,
        rule_id: str = CRISIS_RULE_ID,
        answer_slot: str = CRISIS_ANSWER_SLOT,
    ) -> CrisisPath:
        """Find the crisis rule in what is actually served, or refuse."""
        rule = next((r for r in served_rules if r.id == rule_id), None)
        if rule is None:
            raise CrisisPathAbsent(
                f"{rule_id} is not served, so there is no crisis script to deliver "
                "(HUMAN_BLOCKERS HB-C8, HB-C17)"
            )
        if rule.status is not RuleStatus.ACTIVE:
            raise CrisisPathAbsent(f"{rule_id} is draft_needs_source and never evaluates")
        if not rule.consent_independent:
            raise CrisisPathAbsent(f"{rule_id} is not consent-independent (files/04 §4.2 defect 3)")
        if not rule.level.is_red or rule.register is None:
            raise CrisisPathAbsent(f"{rule_id} is not a KIRMIZI rule, so it carries no script")
        if answer_slot not in referenced_slots(parse_when(rule.when)):
            raise CrisisPathAbsent(f"{rule_id} does not read {answer_slot}")
        return cls(rule, answer_slot, rule.register)

    def deliver(self, *, reference_time: datetime, location: RedLocation) -> CrisisDelivery:
        """Hand the crisis answer to the rules engine and return its script."""
        context = TriageContext(
            reference_time=reference_time,
            answers={
                self._answer_slot: SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(True,)),
                self._rule.tense_anchor: SlotAnswer(
                    state=AnswerState.ASKED_PRESENT,
                    values=(reference_time.date().isoformat(),),
                ),
            },
        )
        evaluation = evaluate_triage((self._rule,), context, location)
        result = evaluation.result
        if result.level is not TriageLevel.RED or evaluation.action is None:
            raise CrisisPathAbsent(
                f"{self._rule.id} did not fire on the crisis answer, so no script is delivered"
            )
        return CrisisDelivery(
            rule_id=self._rule.id,
            red_register=self._register,
            location=location,
            action=evaluation.action,
        )


# ---------------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------------


class AdministrationMode(enum.StrEnum):
    """files/04 header: record ``administration_mode`` on every result."""

    VOICE = "voice"
    TYPED = "typed"
    KEYPAD = "keypad"


class AdministrationStatus(enum.StrEnum):
    """Where one administration is."""

    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    CRISIS_PATH = "crisis_path"


class ItemPrompt(FrozenModel):
    """One item to put in front of the patient, as the registry holds it."""

    instrument_id: str
    timeframe_tr: str
    item: CommittedItem
    options: tuple[ResponseOption, ...]


class AnsweredItem(FrozenModel):
    """One explicit selection, by id, with the instrument's score for it."""

    item_id: str
    option_id: str
    score: int


class ClinicianInstrumentRecord(FrozenModel):
    """Everything about one administration a clinician may read. Never patient-facing."""

    instrument_id: str
    answers: tuple[AnsweredItem, ...]
    complete: bool
    total: int | None
    max_total: int
    severity_band: str | None
    severity_refusal: WellbeingRefusal | None
    crisis_path_triggered: bool
    crisis_rule_id: str | None
    administration_mode: AdministrationMode
    third_party_present: bool
    proxy_reported: bool


class PatientWellbeingStatus(enum.StrEnum):
    """All a patient is told: whether the questions were answered."""

    ANSWERED = "answered"
    NOT_ANSWERED = "not_answered"


class PatientWellbeingView(FrozenModel):
    """The patient-facing result. No score, no band, no interpretation."""

    status: PatientWellbeingStatus


def _sourced_threshold(cutoff: Cutoff) -> int:
    if cutoff.status is not RuleStatus.ACTIVE:
        raise CutoffUnavailable(
            cutoff.instrument,
            WellbeingRefusal.CUTOFF_UNSOURCED,
            f"{cutoff.id} is draft_needs_source; it is never applied (CLAUDE.md invariant 17)",
        )
    return int(cutoff.threshold)


class InstrumentAdministration:
    """One scripted administration: one item at a time, in order."""

    def __init__(
        self,
        instrument: CommittedInstrument,
        *,
        crisis: tuple[int, CrisisPath] | None,
        mode: AdministrationMode,
        third_party_present: bool,
        proxy_reported: bool,
    ) -> None:
        if instrument.crisis_item_ids and crisis is None:
            raise InstrumentUnavailable(
                instrument.id,
                WellbeingRefusal.CRISIS_PATH_ABSENT,
                "an instrument with a crisis item is administered only with its sourced "
                "trigger and a served crisis path",
            )
        self._instrument = instrument
        self._crisis = crisis
        self._mode = mode
        self._third_party_present = third_party_present
        self._proxy_reported = proxy_reported
        self._answers: list[AnsweredItem] = []
        self._crisis_rule_id: str | None = None

    @property
    def status(self) -> AdministrationStatus:
        """In progress, complete, or stopped on the crisis path."""
        if self._crisis_rule_id is not None:
            return AdministrationStatus.CRISIS_PATH
        if len(self._answers) == len(self._instrument.items):
            return AdministrationStatus.COMPLETE
        return AdministrationStatus.IN_PROGRESS

    def next_item(self) -> ItemPrompt | None:
        """The next item, by reference; ``None`` once complete or on the crisis path."""
        if self.status is not AdministrationStatus.IN_PROGRESS:
            return None
        return ItemPrompt(
            instrument_id=self._instrument.id,
            timeframe_tr=self._instrument.timeframe_tr,
            item=self._instrument.items[len(self._answers)],
            options=self._instrument.options,
        )

    def answer(
        self,
        item_id: str,
        option_id: str,
        *,
        reference_time: datetime,
        location: RedLocation,
    ) -> CrisisDelivery | None:
        """Record one explicit option selection; return the crisis script if it fires."""
        status = self.status
        if status is AdministrationStatus.CRISIS_PATH:
            raise AnswerRefused("the administration stopped on the crisis path")
        if status is AdministrationStatus.COMPLETE:
            raise AnswerRefused("the administration is complete")
        item = self._instrument.items[len(self._answers)]
        if item_id != item.id:
            raise AnswerRefused("only the next item may be answered")
        option = next((o for o in self._instrument.options if o.id == option_id), None)
        if option is None:
            raise AnswerRefused("the answer is not an option this item offers")
        self._answers.append(AnsweredItem(item_id=item.id, option_id=option.id, score=option.score))
        if not item.crisis_item or self._crisis is None:
            return None
        threshold, path = self._crisis
        if option.score < threshold:
            return None
        delivery = path.deliver(reference_time=reference_time, location=location)
        self._crisis_rule_id = delivery.rule_id
        return delivery

    def clinician_record(self, registry: InstrumentRegistry) -> ClinicianInstrumentRecord:
        """The clinician-only record, with a sourced band or the reason there is none."""
        complete = len(self._answers) == len(self._instrument.items)
        total = sum(a.score for a in self._answers) if complete else None
        band: str | None = None
        refusal: WellbeingRefusal | None = None
        try:
            band = _band(self._instrument.id, total, registry)
        except CutoffUnavailable as exc:
            refusal = exc.code
        return ClinicianInstrumentRecord(
            instrument_id=self._instrument.id,
            answers=tuple(self._answers),
            complete=complete,
            total=total,
            max_total=self._instrument.max_total,
            severity_band=band,
            severity_refusal=refusal,
            crisis_path_triggered=self._crisis_rule_id is not None,
            crisis_rule_id=self._crisis_rule_id,
            administration_mode=self._mode,
            third_party_present=self._third_party_present,
            proxy_reported=self._proxy_reported,
        )

    def patient_view(self) -> PatientWellbeingView:
        """Whether the questions were answered — and nothing else."""
        answered = self.status is AdministrationStatus.COMPLETE
        return PatientWellbeingView(
            status=PatientWellbeingStatus.ANSWERED
            if answered
            else PatientWellbeingStatus.NOT_ANSWERED
        )


def open_instrument(
    instrument_id: str,
    registry: InstrumentRegistry,
    *,
    crisis_path: CrisisPath | None,
    licences: LicenceTable | None = None,
    mode: AdministrationMode = AdministrationMode.VOICE,
    third_party_present: bool = False,
    proxy_reported: bool = False,
) -> InstrumentAdministration:
    """Open an administration, or refuse in this order: licence, items, trigger, path.

    Licence first, so a BLOCKED instrument is never even looked up.
    """
    status = instrument_licence(instrument_id, licences)
    if status is not InstrumentLicence.GO:
        raise InstrumentUnavailable(
            instrument_id,
            WellbeingRefusal.LICENCE_NOT_GO,
            f"licence is {status.value} (files/04 header table; HB-L2, HB-L3)",
        )
    instrument = registry.instrument(instrument_id)
    if instrument is None:
        raise InstrumentUnavailable(
            instrument_id,
            WellbeingRefusal.ITEMS_NOT_COMMITTED,
            "no verbatim Turkish text is committed for it (HUMAN_BLOCKERS HB-C29)",
        )
    crisis: tuple[int, CrisisPath] | None = None
    if instrument.crisis_item_ids:
        triggers = [
            c
            for c in registry.cutoffs_for(instrument_id, CutoffKind.CRISIS_TRIGGER)
            if c.status is RuleStatus.ACTIVE and c.item in instrument.crisis_item_ids
        ]
        if len(triggers) != 1 or len(instrument.crisis_item_ids) != 1:
            raise InstrumentUnavailable(
                instrument_id,
                WellbeingRefusal.CRISIS_TRIGGER_UNSOURCED,
                "its crisis item has no sourced trigger, so the item is not asked",
            )
        if crisis_path is None:
            raise InstrumentUnavailable(
                instrument_id,
                WellbeingRefusal.CRISIS_PATH_ABSENT,
                "files/04 §4 forbids ending on the crisis item without the safety script, "
                "and no crisis script is served (HUMAN_BLOCKERS HB-C8, HB-C17)",
            )
        crisis = (_sourced_threshold(triggers[0]), crisis_path)
    return InstrumentAdministration(
        instrument,
        crisis=crisis,
        mode=mode,
        third_party_present=third_party_present,
        proxy_reported=proxy_reported,
    )


# ---------------------------------------------------------------------------
# Cut-offs applied
# ---------------------------------------------------------------------------


def _declared(registry: InstrumentRegistry, instrument_id: str, kind: CutoffKind) -> list[Cutoff]:
    cutoffs = list(registry.cutoffs_for(instrument_id, kind))
    if not cutoffs:
        raise CutoffUnavailable(
            instrument_id,
            WellbeingRefusal.CUTOFF_NOT_DECLARED,
            f"no {kind.value} cut-off is declared",
        )
    return cutoffs


def _band(instrument_id: str, total: int | None, registry: InstrumentRegistry) -> str | None:
    cutoffs = _declared(registry, instrument_id, CutoffKind.SEVERITY)
    thresholds = [(_sourced_threshold(c), c.band) for c in cutoffs]
    if total is None:
        return None
    met = [(threshold, band) for threshold, band in thresholds if total >= threshold]
    return max(met)[1] if met else None


def severity_band(record: ClinicianInstrumentRecord, registry: InstrumentRegistry) -> str | None:
    """The sourced band a complete total meets, for the clinician only."""
    return _band(record.instrument_id, record.total, registry)


def cascade_target(record: ClinicianInstrumentRecord, registry: InstrumentRegistry) -> str | None:
    """The instrument a sourced cascade cut-off schedules, or ``None``."""
    cutoffs = _declared(registry, record.instrument_id, CutoffKind.CASCADE)
    thresholds = [(_sourced_threshold(c), c.target) for c in cutoffs]
    if record.total is None:
        return None
    for threshold, target in thresholds:
        if record.total >= threshold:
            return target
    return None


# ---------------------------------------------------------------------------
# The clinician note
# ---------------------------------------------------------------------------


def to_screening_block(
    records: Sequence[ClinicianInstrumentRecord],
    *,
    fields: Mapping[str, str] = SCREENING_FIELDS,
) -> ScreeningBlock:
    """Map complete totals into ``PreVisitNote.screening`` (clinician-only)."""
    if not records:
        raise ValueError("no record to put in the screening block")
    provenance = {(r.administration_mode, r.third_party_present, r.proxy_reported) for r in records}
    if len(provenance) != 1:
        raise ValueError("one screening block carries one provenance; these records differ")
    mode, third_party, proxy = provenance.pop()
    totals: dict[str, int | None] = {}
    for record in records:
        field = fields.get(record.instrument_id)
        if field is None:
            raise ValueError(f"{record.instrument_id} has no screening field")
        totals[field] = record.total
    return ScreeningBlock.model_validate(
        {
            **totals,
            "provenance": ScreeningProvenance(
                administration_mode=mode.value,
                proxy_reported=proxy,
                third_party_present=third_party,
                qualifier_tr=THIRD_PARTY_QUALIFIER_TR if third_party else "",
            ),
        }
    )
