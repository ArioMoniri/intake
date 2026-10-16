"""CD-08's chest-pain clinic-inbox items, raised from the live session (INT-547, INT-525).

Verified decisions decide two clinician-only items, and before INT-547 and
INT-525 nothing raised either (GitHub #927, split from #917 finding F3; #891):

- **CD-04** ``unresolved_after_follow_up``: a CD-01 chest-pain slot still
  UNCLEAR after its ``follow_up_tr`` has been asked once raises
  ``chest_pain_arms_unresolved``. Under three-valued logic such a slot can
  leave both chest-pain arms Unknown, so the session can end GREEN on a pain
  nobody could characterise.
- **CD-01** ``proxy_unasked_inbox_item``: a proxy session leaves the seven
  chest-pain slots unasked (CD-01's stop-gap ``skip_if`` on the screen, until
  the DSL can select proxy copy) and raises ``proxy_chest_pain_screen_unasked``
  for a subject in the rules' adult band or of unknown age.

:class:`ClinicItemWatch` raises them, and holds to this:

- **It is not a RED, and it cannot become one** (invariants 1 and 9). The
  watch wraps a state handler and hands back the handler's own effect
  object, so it cannot add a determination; the queue still derives
  ``priority`` from a rules-engine RED and nothing else, and evaluates triage
  after the Work exactly as before. A :class:`ClinicItem` has no level,
  register, location or priority field to carry.
- **Exactly when the decision says, once per session.** The arms item is
  raised when :meth:`protocols.clinic_items.ArmsUnresolvedRule.unresolved` says so:
  the slot UNCLEAR, and its scripted follow-up (a ``follow_up`` re-entry)
  observed asked at least CD-04's "once". The watch observes the engine
  before and after every state Work it wraps — a re-entry the engine still
  holds and no longer offers has been spoken — so the close Work counts a
  follow-up spoken and never answered. The proxy item is raised when the
  screen's ``skip_if`` reads TRUE, the seven slots are unasked and the subject
  is not known to be outside the adult band; the voice runtime holds no age
  fact, so the age is unknown, which CD-01 raises for. Each kind is raised
  once: the item id is derived from the session and the kind, and the watch
  records each kind the route took.
- **Never dropped** (CD-08). A route that raises costs the Work nothing: the
  failure is counted (``clinic_inbox_item_route_failures_total``, which pages:
  CD-08 counts a delivery failure as an SLA breach) and logged by ids, and the
  item is raised again on the session's next state Work.
- **Ids only** (invariant 6). The item carries its own id, the kind, the
  session id, the protocol's slot ids, the rule ids and the decision ids.
  No answer, value or transcript has a field, so none can reach the inbox,
  the audit chain or a log line.

The production route is
:class:`~intake_voice_runtime.safety_inbox.ClinicItemNotifier`: the clinic
Safety inbox the RED already writes (INT-406, INT-475), with an audit row per
item (invariant 4).

**What ADR-040 (#833) changes.** Today a proxy session is read from the
subject-role answer, through the screen's stop-gap ``skip_if``. #833 starts a
proxy-skipped step in ``NOT_ASKED_PROXY``; the one line it needs here is that
state joining :data:`_UNASKED`. Its proxy path refuses the stop-gap until
CD-01's proxy copy is spoken, and a spoken screen closes the gap this item
reports.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from clinical_schemas.session import AnswerState
from intake_platform.safety_inbox.metrics import (
    CLINIC_INBOX_ITEM_ROUTE_FAILURES_TOTAL,
    CLINIC_INBOX_ITEMS_RAISED_TOTAL,
)
from intake_platform.safety_inbox.model import ID_SHAPE, RULE_ID_SHAPE
from protocols.clinic_items import (
    ClinicItemKind,
    ClinicItemRules,
    SubjectAge,
    load_clinic_item_rules,
)
from protocols.compile.resolve import ResolvedProtocol
from protocols.compile.rule_reads import rule_reads
from protocols.gates import SlotNamespace, qualify_gate
from protocols.triage.context import canonical_scalar
from protocols.triage.expr import Lookup, Truth, WhenNode, evaluate_node, parse_when
from protocols.triage.expr import referenced_slots as _referenced
from pydantic import ConfigDict, Field, StringConstraints

from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.live_triage import served_rules, step_spellings
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect, StateHandler
from intake_voice_runtime.steps import StepKind

__all__ = [
    "ClinicItem",
    "ClinicItemRoute",
    "ClinicItemRouteMissing",
    "ClinicItemWatch",
    "ClinicItemWiringError",
    "clinic_item_id",
]

logger = logging.getLogger("intake_voice_runtime.clinical_agent.clinic_items")

#: The states that leave a slot unasked. ADR-040 (#833) adds NOT_ASKED_PROXY.
_UNASKED: Final = frozenset({AnswerState.NOT_ASKED})

type _Id = Annotated[str, StringConstraints(pattern=ID_SHAPE)]
type _ItemId = Annotated[str, StringConstraints(pattern=r"^ci_[0-9a-f]{32}$")]
type _StepId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")]
type _RuleId = Annotated[str, StringConstraints(pattern=RULE_ID_SHAPE)]
type _DecisionId = Annotated[str, StringConstraints(pattern=r"^CD-\d{2,3}$")]


def clinic_item_id(session_id: str, kind: ClinicItemKind) -> str:
    """``ci_`` + the first 32 hex of sha256(session, kind): one item per session and kind."""
    digest = hashlib.sha256(
        "\x00".join(("clinic_item", session_id, kind.value)).encode("utf-8")
    ).hexdigest()
    return f"ci_{digest[:32]}"


class ClinicItem(FrozenModel):
    """One CD-08 clinician-only clinic-inbox item: ids and a closed kind, nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    item_id: _ItemId
    kind: ClinicItemKind
    session_id: _Id
    #: The protocol's slot ids the item is about (``<section>.<slot>``).
    slot_refs: tuple[_StepId, ...] = Field(min_length=1)
    #: The served chest-pain rules the item concerns; never a fired RED.
    rule_ids: tuple[_RuleId, ...] = Field(min_length=1)
    #: The decision that raises it, then CD-08, which routes it.
    decision_ids: tuple[_DecisionId, ...] = Field(min_length=1)


@runtime_checkable
class ClinicItemRoute(Protocol):
    """The clinic route for a CD-08 item. **No member is awaitable** (invariant 9)."""

    def raise_item(self, item: ClinicItem) -> None: ...


class ClinicItemRouteMissing(ValueError):
    """A session that can raise a CD-08 item, composed with no route to raise it on."""


class ClinicItemWiringError(ValueError):
    """The protocol skips the chest-pain screen on a reading CD-01 does not name."""


@dataclass
class ClinicItemWatch:
    """One session's CD-08 items: when to raise each, and the route."""

    session_id: str
    route: ClinicItemRoute
    rules: ClinicItemRules
    #: ``{CD-04 slot this plan holds: the served rules that read it}``.
    arms: Mapping[str, tuple[str, ...]]
    #: CD-01's seven slots this plan holds.
    proxy_slots: tuple[str, ...] = ()
    #: The served rules reading any of the seven.
    proxy_rule_ids: tuple[str, ...] = ()
    #: The screen's ``skip_if``, qualified; ``None`` where nothing skips it.
    screen_skip: WhenNode | None = None
    #: The runtime holds no age fact for the subject (CD-01: unknown raises).
    subject_age: SubjectAge = SubjectAge.UNKNOWN
    #: The items the route took, by kind: at most one each.
    raised: dict[ClinicItemKind, ClinicItem] = field(default_factory=dict, init=False)
    _follow_ups: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _asked: dict[str, set[str]] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def for_protocol(
        cls,
        protocol: ResolvedProtocol,
        *,
        route: ClinicItemRoute | None,
        session_id: str,
        rules: ClinicItemRules | None = None,
    ) -> ClinicItemWatch | None:
        """The watch for a session pinned to ``protocol``, or ``None``.

        ``None`` where no served rule reads a CD-01 slot: the session has no
        chest-pain arms to leave unresolved or unasked. Otherwise the route is required
        (:class:`ClinicItemRouteMissing`), as the RED's is.
        """
        served = served_rules(protocol)
        if not served:
            return None
        decided = load_clinic_item_rules() if rules is None else rules
        pairs = [
            (section.id, resolved.key)
            for section in protocol.sections
            for resolved in section.slots
        ]
        step_ids = frozenset(f"{section_id}.{key}" for section_id, key in pairs)
        reads: dict[str, frozenset[str]] = {}
        for rule in served:
            spelled = rule_reads(rule)
            names = spelled.all if spelled is not None else frozenset()
            reads[rule.id] = frozenset(step_spellings(names, step_ids).values())
        arms = {
            slot: tuple(sorted(rule_id for rule_id, read in reads.items() if slot in read))
            for slot in sorted(decided.arms.slots & step_ids)
        }
        arms = {slot: rule_ids for slot, rule_ids in arms.items() if rule_ids}
        seven = decided.proxy.slots & step_ids
        proxy_rule_ids = tuple(sorted(rule_id for rule_id, read in reads.items() if read & seven))
        if not arms and not proxy_rule_ids:
            return None
        if route is None:
            kinds = ", ".join(kind.value for kind in ClinicItemKind)
            raise ClinicItemRouteMissing(
                f"the pinned protocol serves the chest-pain rules and no clinic-item route was "
                f"handed in: a session that can raise a CD-08 item ({kinds}) needs the "
                "clinic route to raise it on (CD-08: never dropped; INT-547)"
            )
        return cls(
            session_id=session_id,
            route=route,
            rules=decided,
            arms=arms,
            proxy_slots=tuple(sorted(seven)),
            proxy_rule_ids=proxy_rule_ids,
            screen_skip=_screen_skip(protocol, decided, SlotNamespace(pairs)),
        )

    def wrap(self, handler: StateHandler) -> StateHandler:
        """``handler``, watched: its own effect is returned, untouched."""

        def watched(context: StateContext) -> StateEffect:
            self._observe(context.engine)
            effect = handler(context)
            self._observe(context.engine)
            self._raise_due(context.engine)
            return effect

        return watched

    # --- internals -------------------------------------------------------------------

    def _observe(self, engine: IntakeEngine) -> None:
        """Note each follow-up of an arms slot offered, and each one since spoken."""
        offered = engine.frontier()
        offered_ids = {step.step_id for step in offered}
        pending = engine.follow_ups
        for step in offered:
            if step.kind is StepKind.FOLLOW_UP and step.step_id in pending:
                origin = engine.origin_of(step.step_id)
                if origin in self.arms:
                    self._follow_ups.setdefault(step.step_id, origin)
        for reentry in pending:
            spoken_for = self._follow_ups.get(reentry)
            if spoken_for is not None and reentry not in offered_ids:
                self._asked.setdefault(spoken_for, set()).add(reentry)

    def _raise_due(self, engine: IntakeEngine) -> None:
        arms = self.rules.arms
        if arms.kind not in self.raised and self.arms:
            unresolved = arms.unresolved(
                {slot: engine.state_of(slot) for slot in self.arms},
                {slot: len(self._asked.get(slot, ())) for slot in self.arms},
            )
            if unresolved:
                rule_ids = sorted({rule_id for slot in unresolved for rule_id in self.arms[slot]})
                self._raise(arms.kind, unresolved, tuple(rule_ids), arms.decision_ids)
        proxy = self.rules.proxy
        if proxy.kind not in self.raised and self.screen_skip is not None and self.proxy_rule_ids:
            skipped = evaluate_node(self.screen_skip, _lookup(engine)) is Truth.TRUE
            unasked = all(engine.state_of(slot) in _UNASKED for slot in self.proxy_slots)
            if proxy.raised(
                screen_skipped=skipped, slots_unasked=unasked, subject_age=self.subject_age
            ):
                self._raise(proxy.kind, self.proxy_slots, self.proxy_rule_ids, proxy.decision_ids)

    def _raise(
        self,
        kind: ClinicItemKind,
        slot_refs: tuple[str, ...],
        rule_ids: tuple[str, ...],
        decision_ids: tuple[str, ...],
    ) -> None:
        item = ClinicItem(
            item_id=clinic_item_id(self.session_id, kind),
            kind=kind,
            session_id=self.session_id,
            slot_refs=slot_refs,
            rule_ids=rule_ids,
            decision_ids=decision_ids,
        )
        try:
            self.route.raise_item(item)
        except Exception as err:  # the route must never cost the Work; the failure pages
            CLINIC_INBOX_ITEM_ROUTE_FAILURES_TOTAL.labels(kind=kind.value).inc()
            logger.error(
                "clinic item route failed",
                extra={
                    "session_id": self.session_id,
                    "kind": kind.value,
                    "error": type(err).__name__,
                },
            )
            return
        self.raised[kind] = item
        CLINIC_INBOX_ITEMS_RAISED_TOTAL.labels(kind=kind.value).inc()
        logger.info(
            "clinic item raised",
            extra={"session_id": self.session_id, "kind": kind.value, "item_id": item.item_id},
        )


def _lookup(engine: IntakeEngine) -> Lookup:
    """The engine's own gate reading: only an answered slot carries a value."""
    answered = engine.answered()

    def lookup(ref: str) -> bool | Decimal | str | None:
        entry = answered.get(ref)
        return None if entry is None else canonical_scalar(entry[1])

    return lookup


def _screen_skip(
    protocol: ResolvedProtocol, rules: ClinicItemRules, namespace: SlotNamespace
) -> WhenNode | None:
    """The screen's ``skip_if``, qualified, when it is CD-01's proxy stop-gap.

    A screen with no ``skip_if`` is asked of every session, so nothing can be
    raised for it. One whose ``skip_if`` reads a slot CD-01 does not name as
    the proxy reading is refused: retiring the screen on anything else would
    raise a proxy item for a session that is not a proxy one.
    """
    screen = rules.proxy.screen
    for section in protocol.sections:
        for resolved in section.slots:
            if f"{section.id}.{resolved.key}" != screen or resolved.slot.skip_if is None:
                continue
            node, issues = qualify_gate(parse_when(resolved.slot.skip_if), namespace)
            unnamed = sorted(
                ref for ref in _referenced(node) if issues or not rules.proxy.names_reading(ref)
            )
            if unnamed:
                raise ClinicItemWiringError(
                    f"{screen}: its skip_if reads {', '.join(unnamed)}, which "
                    f"{rules.proxy.decision_ids[0]} does not name as the proxy reading"
                )
            return node
    return None
