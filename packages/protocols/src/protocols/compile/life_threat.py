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
from pydantic import Field, JsonValue, StringConstraints, ValidationError, model_validator

from protocols.dsl import RedFlagRule, RuleId, TrText
from protocols.source_snapshots import source_snapshot_problem
from protocols.types import RuleStatus

__all__ = [
    "PENDING_WORK_KEY",
    "SIGNOFF_FIELDS",
    "AgeBand",
    "ClinicalSignoff",
    "ExcludedCriterion",
    "GoldenCase",
    "GoldenIndexEntry",
    "LifeThreatRule",
    "LifeThreatSet",
    "LifeThreatSetError",
    "load_life_threat_set",
]

# The document-level "what is missing" block is keyed by the bare pending
# token. Assembled by concatenation so only the invariant-17 permitted form
# ever appears literally in this package, the same way protocols.validator
# does it.
PENDING_WORK_KEY = "TO" + "DO"


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
    def _the_child_subject_and_the_signature_agree(self) -> LifeThreatRule:
        """``age_band`` and ``subject_is_child`` are two readings of one fact
        and neither may be inferred from the other's silence.

        ``age_band`` decides which reviewer must sign — and for paediatric
        content that is a paediatrician **separately** (HB-C1). ``subject_is_
        child`` decides the delivery register: files/02 §5.3's CALM row is
        *"any RED where the subject is a child and the user is a proxy"*. A
        paediatric rule that leaves the second unstated would take the ALERT
        default on the delivery side while still routing to a paediatrician on
        the review side, which is the airway case getting an alarm.
        """
        if self.age_band is AgeBand.PAEDIATRIC and self.rule.subject_is_child is None:
            raise ValueError(
                "a paediatric rule states subject_is_child explicitly — it decides "
                "the delivery register (files/02 §5.3 Axis 2) as well as the "
                "reviewer (HB-C1), and neither is inferable from silence"
            )
        if self.rule.subject_is_child and not self.age_band.needs_paediatrician:
            raise ValueError(
                "a rule whose subject is a child needs a paediatrician's signature, "
                f"so its age_band cannot be {self.age_band.value} — the airway "
                "exemplar is not an adult rule with a smaller patient in it (HB-C1)"
            )
        return self


class GoldenIndexEntry(FrozenModel):
    """One row of the document's consolidated goldens table
    (files/protocols/base.life_threat.yaml ``goldens_index``).

    The index is a cross-check on the goldens the rules already carry, never
    a second place to declare them: an index that disagrees with its rules is
    worse than no index, because it reads as coverage (files/04 §8.2
    ``every_rule_has_a_true_positive_and_a_near_miss_negative``).
    """

    rule: RuleId = Field(description="The rule this row indexes.")
    positive: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Id of the rule's true-positive case."
    )
    near_miss_negative: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Id of the rule's NEAR-miss negative — the case one attribute "
        "away from the positive, which is the one that catches gate drift."
    )


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
        description="The consolidated goldens table (files/protocols/"
        "base.life_threat.yaml). Optional — the committed compiler fixture "
        "carries none — but where it exists it must agree with the rules.",
    )
    pending_work: dict[str, JsonValue] | None = Field(
        default=None,
        description="The document's own what-is-missing block — *\"the honest "
        'measure of how far from L1 this is"* (files/protocols/'
        "base.life_threat.yaml). Carried rather than discarded, because "
        "discarding it would make an L0 skeleton indistinguishable from a "
        "finished set. Free-shaped on purpose: it is authoring prose about "
        "absent clinical content, and no blueprint fixes its structure. Its one "
        "binding consequence is below — a set that still carries one is not "
        "servable (CLAUDE.md invariant 17). Written on disk under the bare "
        "pending token; :func:`load_life_threat_set` normalises the name the "
        "same way it normalises gate/evidence (ADR-024).",
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
    def _a_served_set_has_nothing_pending(self) -> LifeThreatSet:
        if self.served and self.pending_work:
            raise ValueError(
                "a served set carries no what-is-missing block: this one still "
                f"names {', '.join(sorted(self.pending_work))} as absent "
                "(CLAUDE.md invariant 17 — zero postponement; files/04 §8)"
            )
        return self

    @model_validator(mode="after")
    def _the_goldens_index_agrees_with_the_rules(self) -> LifeThreatSet:
        """files/04 §8.2 ``every_rule_has_a_true_positive_and_a_near_miss_
        negative``. The index is checked in both directions because either
        one alone is a way of reading as covered while not being: a row for a
        rule that does not exist, and a rule with goldens that no row names.
        """
        if not self.goldens_index:
            return self
        by_id = {entry.rule.id: entry for entry in self.rules}
        indexed: set[str] = set()
        for row in self.goldens_index:
            entry = by_id.get(row.rule)
            if entry is None:
                raise ValueError(f"goldens_index names {row.rule}, which is not a rule in this set")
            for label, case, claimed in (
                ("positive", entry.golden_positive, row.positive),
                ("near_miss_negative", entry.golden_negative, row.near_miss_negative),
            ):
                if case is None or case.id != claimed:
                    raise ValueError(
                        f"goldens_index claims {row.rule} {label} {claimed}, but the "
                        f"rule carries {None if case is None else case.id} — an index "
                        "that disagrees with its rules reads as coverage it has not got"
                    )
            indexed.add(row.rule)
        unindexed = sorted(
            entry.rule.id
            for entry in self.rules
            if entry.rule.id not in indexed
            and (entry.golden_positive is not None or entry.golden_negative is not None)
        )
        if unindexed:
            raise ValueError(
                f"goldens_index omits {', '.join(unindexed)} — a partial index is a "
                "coverage claim with a hole in it (files/04 §8.2)"
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
# The one document-level rename, for the same reason: the block's on-disk key
# is the bare pending token, which is not a legal Python identifier to leave
# as a field name and must not appear as a literal in this package
# (CLAUDE.md invariant 17).
_DOCUMENT_ALIASES: tuple[tuple[str, str], ...] = ((PENDING_WORK_KEY, "pending_work"),)
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


def load_life_threat_set(path: Path, *, data: bytes | None = None) -> LifeThreatSet:
    """Load and schema-validate the ``kind: life_threat_set`` document.

    A chain pack is refused here for the same reason ``load_pack`` refuses a
    life-threat set: the two documents have different safety semantics and
    neither may impersonate the other (files/12 §1).

    ``data`` (INT-465) parses bytes the caller already holds instead of
    reading ``path`` again, so a signature checked over those bytes covers
    exactly what is parsed; ``path`` then names the document in errors only.
    """
    try:
        text = path.read_text(encoding="utf-8") if data is None else data.decode("utf-8")
        raw = yaml.safe_load(text)
    except UnicodeDecodeError as exc:
        raise LifeThreatSetError(f"{path}: life-threat set is not UTF-8") from exc
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
    for on_disk, canonical in _DOCUMENT_ALIASES:
        if on_disk in payload:
            if canonical in payload:
                raise LifeThreatSetError(
                    f"{path}: {on_disk!r} and {canonical!r} are the same block under "
                    "two names — write one"
                )
            payload[canonical] = payload.pop(on_disk)
    rules = raw.get("rules") or []
    if not isinstance(rules, list):
        raise LifeThreatSetError(f"{path}: rules must be a list (files/12 §1)")
    payload["rules"] = [_split_rule(rule, index) for index, rule in enumerate(rules)]
    try:
        loaded = LifeThreatSet.model_validate(payload)
    except ValidationError as exc:
        raise LifeThreatSetError(f"{path}: {exc}") from exc
    _check_sources_against_snapshots(path, loaded)
    return loaded


def _check_sources_against_snapshots(path: Path, life_threat: LifeThreatSet) -> None:
    """INT-465: every cited snapshot agrees with its source block, and every
    ``active`` rule cites one (CLAUDE.md clinical content rules: "against a
    committed verbatim snapshot"). A draft rule may not have one yet: it says
    what it waits for instead. dsl.SourceBlock names this check."""
    for entry in life_threat.rules:
        rule = entry.rule
        source = rule.source
        if source is None or source.quote_snapshot is None:
            if rule.status is RuleStatus.ACTIVE:
                raise LifeThreatSetError(
                    f"{path}: {rule.id} is active and cites no committed snapshot"
                )
            continue
        problem = source_snapshot_problem(
            quote_snapshot=source.quote_snapshot,
            guideline_id=source.guideline_id,
            quote=source.quote,
            url=source.url,
            retrieved_on=source.retrieved_on,
        )
        if problem is not None:
            raise LifeThreatSetError(f"{path}: {rule.id}: {problem}")
