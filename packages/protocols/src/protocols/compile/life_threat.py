"""The universal life-threat sibling set, and the sign-off interlock (INT-041).

files/12 §1: ``base.life_threat`` is **not merged** into the resolved
protocol — it is a sibling set evaluated on every session regardless of
branch, which is what makes composition monotone by construction. So the
compiler loads it alongside the pack rather than through the chain, and
nothing in a pack can reach it.

**The interlock this module exists for.** ``files/protocols/base.life_threat.yaml``
states it in its own header: *"The sign-off block at the bottom of this
header is empty on purpose and the compiler must refuse to emit an L1 bundle
while it stays empty."* HUMAN_BLOCKERS **HB-C1** is the row: all six fields
are ``null``, they need a physician of record, and for paediatric content a
paediatrician **separately**. That second signature is a distinct gate here,
not a nicety — an adult signature does not cover a rule whose ``age_band`` is
paediatric, and the airway exemplar is "not an adult rule with a smaller
patient in it".

**Schema reconciliation (ADR-024).** The life-threat document spells the
predicate ``gate:`` and the provenance block ``evidence:``; chain packs (and
the CI gate ``every_red_rule_has_a_source_block``) spell them ``when:`` and
``source:``. ``files/protocols/base.life_threat.yaml`` flags the
collision in its ``schema_reconciliation`` block, whose status line reads
"decide before the compiler is written". ADR-024 records the decision:
``when`` / ``source`` are canonical in code and in every gate name; the
life-threat document keeps its on-disk spelling and this loader normalises
it, so one rule type serves both documents and the two can never drift
apart.
"""

from __future__ import annotations

import enum
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from clinical_schemas.common import FrozenModel, JsonScalar
from pydantic import Field, StringConstraints, ValidationError, model_validator

from protocols.dsl import RedFlagRule, TrText

__all__ = [
    "SIGNOFF_FIELDS",
    "AgeBand",
    "ClinicalSignoff",
    "ExcludedCriterion",
    "GoldenCase",
    "GoldenIndexEntry",
    "LifeThreatRule",
    "LifeThreatSet",
    "LifeThreatSetError",
    "PendingSection",
    "PendingSlot",
    "load_life_threat_set",
]

# The document-level "what is missing" block. Its on-disk key is the bare
# pending-value token; it is assembled by concatenation here so the literal
# never appears in this file, the way protocols.validator assembles it
# (CLAUDE.md invariant 17, and the no_placeholders gate, whose allow-list
# covers the blueprint YAML and not this module).
_PENDING_BLOCK_KEY = "TO" + "DO"


class LifeThreatSetError(ValueError):
    """The life-threat document is missing or does not match its schema."""


class AgeBand(enum.StrEnum):
    """Which reviewer must sign (files/protocols/base.life_threat.yaml
    ``age_band``: "drives which reviewer must sign")."""

    ADULT = "adult"
    PAEDIATRIC = "paediatric"
    BOTH = "both"

    @property
    def needs_paediatrician(self) -> bool:
        return self in (AgeBand.PAEDIATRIC, AgeBand.BOTH)


SIGNOFF_FIELDS: tuple[str, ...] = (
    "reviewer_name",
    "reviewer_licence_no",
    "reviewer_specialty",
    "signed_commit",
    "signed_on",
)
"""The five fields every served set needs. ``paediatric_reviewer_name`` is
the sixth and is required only when a paediatric rule is present — recorded
separately so an adult-only set is not blocked on a paediatrician who has
nothing to read (HB-C1)."""


class ClinicalSignoff(FrozenModel):
    """The six-field block of HB-C1. Every field is nullable in the schema
    **because an unsigned pack must still parse** — the refusal belongs to
    the compiler, where it can be reported with its reason, not to the
    loader, where it would look like a malformed file."""

    reviewer_name: str | None = Field(default=None, description="Physician of record.")
    reviewer_licence_no: str | None = Field(default=None, description="Licence number.")
    reviewer_specialty: str | None = Field(default=None, description="Reviewer specialty.")
    signed_commit: str | None = Field(default=None, description="Commit the signature binds to.")
    signed_on: date | None = Field(default=None, description="Signature date.")
    paediatric_reviewer_name: str | None = Field(
        default=None,
        description="Required separately for any rule with age_band paediatric "
        "(HB-C1; files/protocols/base.life_threat.yaml).",
    )

    def missing(self, *, needs_paediatrician: bool) -> tuple[str, ...]:
        """Which sign-off fields are still empty, in declaration order."""
        absent = [name for name in SIGNOFF_FIELDS if _is_blank(getattr(self, name))]
        if needs_paediatrician and _is_blank(self.paediatric_reviewer_name):
            absent.append("paediatric_reviewer_name")
        return tuple(absent)


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class ExcludedCriterion(FrozenModel):
    """A guideline feature rejected because a layperson cannot report it,
    **with its reason** (files/04 §8.1 rule 1; CI gate
    ``every_excluded_criterion_states_a_reason``)."""

    criterion: TrText = Field(description="The rejected guideline feature.")
    reason: TrText = Field(description="Why it is not layperson-answerable.")


class GoldenCase(FrozenModel):
    """A golden positive or near-miss negative carried with its rule
    (files/protocols/base.life_threat.yaml; files/04 §8.2
    ``every_rule_has_a_true_positive_and_a_near_miss_negative``)."""

    id: Annotated[str, StringConstraints(min_length=1)] = Field(description="Case id.")
    case: TrText = Field(description="The scenario.")
    expect: dict[str, JsonScalar] = Field(
        default_factory=dict,
        description="The asserted outcome, as written in the document (fires, "
        "level, route, register, location, show_112). Carried, not interpreted: "
        "the golden runner is INT-059's.",
    )
    why_it_is_a_near_miss: str | None = Field(
        default=None, description="Why the negative is a near miss, not a distant one."
    )


class GoldenIndexEntry(FrozenModel):
    """One row of the document's consolidated goldens table
    (files/protocols/base.life_threat.yaml ``goldens_index``; files/04 §8.2
    ``every_rule_has_a_true_positive_and_a_near_miss_negative``).

    The table is a *claim about coverage*, so it is validated against the
    rules rather than carried: an index that drifts from the cases its rules
    actually declare reads as coverage while covering nothing, and the rule
    that silently fell out of it is the one nobody looks at."""

    rule: Annotated[str, StringConstraints(min_length=1)] = Field(description="Rule id.")
    positive: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Id of the rule's true-positive golden case."
    )
    near_miss_negative: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Id of the rule's near-miss negative — the case one "
        "attribute from firing, which is the half that detects over-triggering."
    )


class PendingSlot(FrozenModel):
    """One ``base.intake`` slot a rule references and the pack does not yet
    collect (files/protocols/base.life_threat.yaml
    ``base_intake_additions.slots``; files/04 §8.2
    ``no_rule_references_an_undeclared_slot``)."""

    slot: Annotated[str, StringConstraints(min_length=1)] = Field(description="Slot key.")
    note: str | None = Field(default=None, description="What the slot gates and why.")


class PendingSection(FrozenModel):
    """One named block of what is missing from the document.

    files/04 §8 makes this block spec-required content rather than something
    postponed: *"an explicit ... block naming everything absent"* is how the
    skeleton states its distance from L1, and files/04 §8.1 rule 3
    working as intended is what puts two of the four exemplars in
    ``draft_needs_source``. It is modelled — closed, with ``extra: forbid``
    like everything else — rather than carried as free-form data, so a rule
    cannot be hidden inside it and so :meth:`LifeThreatSet._served_sets_have_
    nothing_pending` can read it."""

    status: TrText = Field(description="Where this block stands.")
    note: str | None = Field(default=None, description="What is missing, in prose.")
    expected_count: str | None = Field(
        default=None, description="How much is missing, as the document writes it."
    )
    warning: str | None = Field(
        default=None, description="A trap the next author must not fall into."
    )
    known_named_gaps: tuple[str, ...] = Field(
        default=(), description="Named gaps inside this block."
    )
    resolved: tuple[str, ...] = Field(
        default=(), description="Items of this block that have since been decided."
    )
    items: tuple[str, ...] = Field(default=(), description="Items of this block still open.")
    slots: tuple[PendingSlot, ...] = Field(
        default=(), description="Slots this block needs declared."
    )


class LifeThreatRule(FrozenModel):
    """One life-threat rule: the shared :class:`RedFlagRule` plus the
    annotations that exist only in this document."""

    rule: RedFlagRule = Field(description="The rule, in canonical when/source spelling.")
    age_band: AgeBand = Field(description="Which reviewer must sign.")
    excluded_criteria: tuple[ExcludedCriterion, ...] = Field(
        default=(), description="files/04 §8.1 rule 1 exclusions, each with a reason."
    )
    inference_disclosure: str | None = Field(
        default=None,
        description="Where the operationalisation is ours rather than the "
        "guideline's (files/04 §8.1 rule 2).",
    )
    golden_positive: GoldenCase | None = Field(default=None, description="A case that must fire.")
    golden_negative: GoldenCase | None = Field(
        default=None, description="A near miss that must not fire."
    )

    @model_validator(mode="after")
    def _a_paediatric_rule_says_its_subject_is_a_child(self) -> LifeThreatRule:
        """``subject_is_child`` has no default, and this is what stops the
        absence being read as ``false``.

        On its own, an omitted ``subject_is_child`` would let a paediatric
        rule be written ALERT — the exact case files/02 §5.3 calls decisive,
        where the alarm produces the deterioration the alert exists to
        prevent. ``age_band`` is already required here, so the document
        cannot omit both: a rule that says it is paediatric must also say its
        subject is a child, and :class:`RedFlagRule` then refuses ALERT.
        ``both`` is deliberately not covered — the subject of a rule that
        also fires on adults is not necessarily a child.
        """
        if self.age_band is AgeBand.PAEDIATRIC and not self.rule.subject_is_child:
            raise ValueError(
                f"{self.rule.id}: age_band paediatric requires "
                "subject_is_child: true — files/02 §5.3 puts any RED whose "
                "subject is a child and whose user is a proxy in the CALM "
                "register, and an omitted subject_is_child would let that "
                "rule be written ALERT"
            )
        return self


class LifeThreatSet(FrozenModel):
    """The ``kind: life_threat_set`` document (files/12 §1)."""

    kind: Literal["life_threat_set"] = Field(description="Document kind (files/12 §1).")
    pack_id: Literal["base.life_threat"] = Field(description="The one id this document may claim.")
    version: Annotated[str, StringConstraints(min_length=1)] = Field(description="Set version.")
    schema_version: Literal[2] = Field(description="Protocol DSL v2.")
    maturity: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="L0-L3 (files/09 §2)."
    )
    status: Annotated[str, StringConstraints(min_length=1)] = Field(description="Review status.")
    language: Literal["tr"] = Field(description="tr is the source of truth (invariant 5).")
    created: date = Field(description="Authoring date.")
    supersedes: tuple[str, ...] = Field(
        default=(), description="Served sets this one replaces (files/12 §3.4)."
    )
    served: bool = Field(
        description="The hard interlock the compiler reads before anything else "
        "(files/protocols/base.life_threat.yaml ``served``)."
    )
    serve_blocked_reason: str | None = Field(
        default=None, description="Required whenever ``served`` is false."
    )
    clinical_signoff: ClinicalSignoff = Field(description="The HB-C1 block.")
    rules: tuple[LifeThreatRule, ...] = Field(default=(), description="The universal rule set.")
    goldens_index: tuple[GoldenIndexEntry, ...] = Field(
        default=(),
        description="The consolidated goldens table (files/04 §8.2). Absence "
        "is not a coverage claim, so an empty index is accepted; a non-empty "
        "one is checked against the rules it indexes.",
    )
    pending_work: dict[str, PendingSection | tuple[str, ...]] | None = Field(
        default=None,
        description="What is missing from this document, block by block "
        "(files/04 §8: *'an explicit ... block naming everything absent'*). "
        "Spec-required content on an L0 skeleton, and the one thing a served "
        "set may not carry. On disk the key is :data:`_PENDING_BLOCK_KEY`, "
        "renamed by :func:`load_life_threat_set` — a pydantic ``alias`` would "
        "have to spell the bare token in this file, which invariant 17 does "
        "not permit outside packages/protocols YAML.",
    )

    @model_validator(mode="after")
    def _blocked_sets_say_why(self) -> LifeThreatSet:
        if not self.served and not (self.serve_blocked_reason or "").strip():
            raise ValueError(
                "served: false requires serve_blocked_reason — a blocked set states "
                "why (files/protocols/base.life_threat.yaml)"
            )
        return self

    @model_validator(mode="after")
    def _served_sets_have_nothing_pending(self) -> LifeThreatSet:
        """A set that still names what is missing may not declare itself
        served. Flipping ``served: true`` is a one-line edit and it is the
        edit that would put an unfinished universal rule set in front of a
        patient, so it fails at load rather than at review."""
        if self.served and self.pending_work:
            blocks = ", ".join(sorted(self.pending_work))
            raise ValueError(
                f"a served life-threat set may not still carry a "
                f"{_PENDING_BLOCK_KEY} block — this one names {blocks}. "
                "files/04 §8 keeps that block as the "
                "document's own measure of its distance from L1; emptying it is "
                "a clinical act, not a serve flag"
            )
        return self

    @model_validator(mode="after")
    def _the_goldens_index_matches_its_rules(self) -> LifeThreatSet:
        """files/04 §8.2 ``every_rule_has_a_true_positive_and_a_near_miss_
        negative``. The index is a claim about coverage, and a claim that
        drifts from the rules is worse than no claim: it reads as coverage."""
        if not self.goldens_index:
            return self
        by_id = {entry.rule.id: entry for entry in self.rules}
        for row in self.goldens_index:
            rule = by_id.get(row.rule)
            if rule is None:
                raise ValueError(f"goldens_index names {row.rule}, which is not a rule in this set")
            for field, case in (
                ("positive", rule.golden_positive),
                ("near_miss_negative", rule.golden_negative),
            ):
                declared = None if case is None else case.id
                if getattr(row, field) != declared:
                    raise ValueError(
                        f"goldens_index row for {row.rule} names {field} "
                        f"{getattr(row, field)!r}; the rule declares {declared!r}"
                    )
        indexed = {row.rule for row in self.goldens_index}
        for rule in self.rules:
            if rule.golden_positive is None and rule.golden_negative is None:
                continue
            if rule.rule.id not in indexed:
                raise ValueError(
                    f"{rule.rule.id} carries goldens and is absent from the "
                    "goldens_index — a partial index is the silent failure "
                    "(files/04 §8.2)"
                )
        return self

    @property
    def needs_paediatrician(self) -> bool:
        """True when any rule's age_band reaches paediatric content."""
        return any(rule.age_band.needs_paediatrician for rule in self.rules)


# --- loading -----------------------------------------------------------------

# ADR-024: the on-disk spelling of the life-threat document, mapped to the
# canonical chain-pack names. Nothing else is renamed.
_RULE_ALIASES: tuple[tuple[str, str], ...] = (("gate", "when"), ("evidence", "source"))
_RULE_ONLY_KEYS: tuple[str, ...] = (
    "age_band",
    "excluded_criteria",
    "inference_disclosure",
    "golden_positive",
    "golden_negative",
)


def _split_rule(raw: object, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LifeThreatSetError(f"rules[{index}]: a rule must be a YAML mapping (files/12 §1)")
    payload: dict[str, Any] = dict(raw)
    for on_disk, canonical in _RULE_ALIASES:
        if on_disk in payload:
            if canonical in payload:
                raise LifeThreatSetError(
                    f"rules[{index}]: {on_disk!r} and {canonical!r} are the same field "
                    "under two names — write one (ADR-024)"
                )
            payload[canonical] = payload.pop(on_disk)
    annotations = {key: payload.pop(key) for key in _RULE_ONLY_KEYS if key in payload}
    annotations["rule"] = payload
    return annotations


def load_life_threat_set(path: Path) -> LifeThreatSet:
    """Load and schema-validate the ``kind: life_threat_set`` document.

    A chain pack is refused here for the same reason ``load_pack`` refuses a
    life-threat set: the two documents have different safety semantics and
    neither may impersonate the other (files/12 §1).
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LifeThreatSetError(f"{path}: life-threat set not readable: {exc}") from exc
    except yaml.YAMLError as exc:
        raise LifeThreatSetError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LifeThreatSetError(f"{path}: a life-threat set must be a YAML mapping")
    if raw.get("kind") != "life_threat_set":
        raise LifeThreatSetError(
            f"{path}: unsupported kind {raw.get('kind')!r} — this loader accepts "
            "kind: life_threat_set only; chain packs go through load_pack (files/12 §1)"
        )
    payload = {key: value for key, value in raw.items() if key != "rules"}
    if _PENDING_BLOCK_KEY in payload:
        if "pending_work" in payload:
            raise LifeThreatSetError(
                f"{path}: {_PENDING_BLOCK_KEY!r} and 'pending_work' are the same "
                "block under two names — write the on-disk one"
            )
        payload["pending_work"] = payload.pop(_PENDING_BLOCK_KEY)
    rules = raw.get("rules") or []
    if not isinstance(rules, list):
        raise LifeThreatSetError(f"{path}: rules must be a list (files/12 §1)")
    payload["rules"] = [_split_rule(rule, index) for index, rule in enumerate(rules)]
    try:
        return LifeThreatSet.model_validate(payload)
    except ValidationError as exc:
        raise LifeThreatSetError(f"{path}: {exc}") from exc
