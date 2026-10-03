"""The generic RED escalation copy and its serve precondition (INT-453; CD-24; INT-465).

When a RED's own pre-positioned script cannot be addressed, the voice runtime still
triggers a RED on the device: the generic escalation, under the script ids below. Its
words come from one document, ``kind: generic_red``. They are decided by CD-24 in the
INT-432 clinical-decisions register: an agent author plus an independent verifier, in
D18 scope (simulated-patient testing only; a licensed physician's review is required
before any real patient). CD-24 is the source of truth
(``packages/protocols/decisions/CD-24.yaml``).

**Register.** CD-24 decides ``carry_engine_register``. The generic trigger carries the
register of the engine result that produced it and is never fixed at ALERT. An
always-ALERT generic would be a default register chosen once by an engineer, which
CLAUDE.md invariant 21 forbids. Every location entry states the policy as a literal, so
it cannot drift from the code that implements it. CD-24 leaves two things
``draft_needs_source``: the copy for a SILENT generic, and the register when fired rules
declare different registers. Meanwhile there is a delivery floor: intake stops, and the
clinic is told when a generic is delivered silently.

**Provenance (INT-465).** An active document carries, for every location entry:
- its location;
- its script id;
- the register policy;
- its own source blocks: CD-24's guideline sources, each quoted verbatim against a
  committed snapshot under ``packages/protocols/sources/``, and CD-24's spec sentences.

Every text field of the location's script is named by at least one block's
``supports``. REMOTE and ON_SITE are action content and need a guideline. UNKNOWN's one
question is fixed by files/04 §8.1 rule 7 and rests on the spec. The guideline quotes
are checked at load. The spec sentences live in files the API image does not ship, so
tests/protocols/test_generic_red.py checks them, together with the copy being CD-24's
value byte for byte.

**ON_SITE never offers 112, in any carrier.** The DSL closes the flag, the number list
and the action codes. CD-24's own near-miss test adds the text: no ON_SITE string may
carry "112" or its spoken form "yüz on iki", and neither may the UNKNOWN question,
which is asked before any 112 is shown.

**Serve precondition.** A blank generic must never reach a live tenant.
:func:`generic_red_refusals` is the precondition. While it refuses, nothing serves RED
scripts and ``device_functions`` is not enabled. It refuses while the document is
absent or ``draft_needs_source``. Nothing defaults to servable (HUMAN_BLOCKERS rule 2).
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation
from pydantic import Field, ValidationError, model_validator

from protocols.clinical_decisions import GuidelineSource, SpecBasis
from protocols.compile.emit_clips import ClipRow, SpeakableText, rows_from
from protocols.dsl import LocationAction, RedFlagAction
from protocols.red_render import RedRenderError, assert_speakable_red, render_red_text
from protocols.source_snapshots import source_snapshot_problem
from protocols.types import RuleStatus

__all__ = [
    "GENERIC_RED_DECISION",
    "GENERIC_RED_SCRIPT_IDS",
    "GenericRedCopy",
    "GenericRedError",
    "GenericRedScript",
    "generic_red_clip_rows",
    "generic_red_refusals",
    "generic_red_strings",
    "load_generic_red",
]

#: The clinical-decisions register row that owns the copy and the register policy.
GENERIC_RED_DECISION = "CD-24"

#: The ids the trigger names and the device catalog keys on, one per location.
#: The device mirrors them (apps/mobile/src/lib/livekit/red.ts).
GENERIC_RED_SCRIPT_IDS: Mapping[RedLocation, str] = {
    RedLocation.REMOTE: "base.generic_red.remote",
    RedLocation.ON_SITE: "base.generic_red.on_site",
    RedLocation.UNKNOWN: "base.generic_red.unknown",
}

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SNAPSHOT_PREFIX = "packages/protocols/sources/"
_ACTION_FIELDS = frozenset({"action_tr", "do_nots_tr", "why_tr"})
#: Non-text fields a block may also support (CD-24 cites sources for the
#: action code, the 112 flag and the staff notification too).
_ACTION_CODES = frozenset({"primary", "show_112", "notify_staff_immediate"})
_QUESTION_FIELDS = frozenset({"ask_one_tr"})
_TWELVE = re.compile(r"112|yüz\s+on\s+iki", re.IGNORECASE)


class GenericRedError(ValueError):
    """The generic RED document could not be read or is malformed."""


# The blueprint names the axis ``register`` (CLAUDE.md invariant 21); pydantic warns
# because a parent exposes a member of that name. The blueprint name wins, as in
# protocols.dsl and clinical_schemas.triage.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "GenericRedScript" shadows an attribute in parent',
    category=UserWarning,
)


def _supported(supports: str | None) -> frozenset[str]:
    return frozenset(token.strip() for token in (supports or "").split(",") if token.strip())


class GenericRedScript(FrozenModel):
    """One location entry: what it is, how it is told, and what it rests on."""

    location: RedLocation = Field(description="files/02 §5.3 Axis 3; must equal its key.")
    script_id: str = Field(description="The id the trigger names (GENERIC_RED_SCRIPT_IDS).")
    register: Literal["carry_engine_register"] = Field(
        description="CD-24 register_policy, stated per location: never a fixed register."
    )
    sources: tuple[GuidelineSource, ...] = Field(
        default=(), description="CD-24's guideline sources behind this location's text."
    )
    spec_basis: tuple[SpecBasis, ...] = Field(
        default=(), description="CD-24's spec sentences behind this location's text."
    )

    def supported_fields(self) -> frozenset[str]:
        named: set[str] = set()
        for source in self.sources:
            named |= _supported(source.supports)
        for basis in self.spec_basis:
            named |= _supported(basis.supports)
        return frozenset(named)


class GenericRedCopy(FrozenModel):
    """The ``kind: generic_red`` document."""

    kind: Literal["generic_red"] = Field(description="Document kind.")
    decision: Literal["CD-24"] = Field(
        description="The INT-432 clinical-decisions register row that owns this copy."
    )
    scope: Literal["simulated_patient_stress_testing"] = Field(
        description="D18's scope, CD-24's own: never a real patient without a physician."
    )
    status: RuleStatus = Field(description="``active`` only with its sources and the copy.")
    register_policy: Literal["carry_engine_register"] = Field(
        description="CD-24: the generic carries the engine result's own register, "
        "never a fixed one (CLAUDE.md invariant 21)."
    )
    scripts: dict[RedLocation, GenericRedScript] | None = Field(
        default=None, description="One entry per location, each with its own sources."
    )
    source_gap: str | None = Field(default=None, description="Required when draft.")
    action: RedFlagAction | None = Field(
        default=None,
        description="REMOTE and ON_SITE scripts and the UNKNOWN question, verbatim tr "
        "(CD-24 value.scripts.base.generic_red).",
    )

    @model_validator(mode="after")
    def _status_carries_what_it_claims(self) -> GenericRedCopy:
        if self.status is RuleStatus.ACTIVE:
            if self.scripts is None or self.action is None:
                raise ValueError("an active generic RED carries its location entries and copy")
            _check_entries(self.scripts, self.action)
        elif not self.source_gap:
            raise ValueError("a draft generic RED says what it is waiting for (source_gap)")
        if self.action is not None:
            _check_no_112_on_site(self.action)
        return self


def _texts(script: LocationAction) -> dict[str, tuple[str, ...]]:
    present: dict[str, tuple[str, ...]] = {}
    if script.action_tr is not None:
        present["action_tr"] = tuple(script.action_tr.values())
    if script.do_nots_tr:
        present["do_nots_tr"] = tuple(t for entries in script.do_nots_tr.values() for t in entries)
    if script.why_tr is not None:
        present["why_tr"] = tuple(script.why_tr.values())
    return present


def _check_entries(scripts: Mapping[RedLocation, GenericRedScript], action: RedFlagAction) -> None:
    """Every entry is its own location's; both registers are the one CD-24 literal,
    which the type already pins, so there is nothing to compare."""
    if set(scripts) != set(RedLocation):
        raise ValueError("an active generic RED has one entry for each of REMOTE, ON_SITE, UNKNOWN")
    for location, entry in scripts.items():
        if entry.location is not location:
            raise ValueError(f"the {location} entry states location {entry.location}")
        if entry.script_id != GENERIC_RED_SCRIPT_IDS[location]:
            raise ValueError(f"the {location} entry names script id {entry.script_id!r}")
        if location is RedLocation.UNKNOWN:
            needed, allowed = {"ask_one_tr"}, _QUESTION_FIELDS
            if not (entry.sources or entry.spec_basis):
                raise ValueError("the UNKNOWN question rests on a source or a spec sentence")
        else:
            script = action.remote if location is RedLocation.REMOTE else action.on_site
            needed, allowed = set(_texts(script)), _ACTION_FIELDS | _ACTION_CODES
            if not entry.sources:
                raise ValueError(f"the {location} script is action content and cites a guideline")
        named = entry.supported_fields()
        if not named <= allowed:
            raise ValueError(f"the {location} entry supports fields it does not have")
        missing = needed - named
        if missing:
            raise ValueError(f"no source supports the {location} field(s) {sorted(missing)}")


def _check_no_112_on_site(action: RedFlagAction) -> None:
    """CD-24 ``generic_red_on_site_has_no_112_anywhere``: the text is a carrier too."""
    for field, texts in _texts(action.on_site).items():
        if any(_TWELVE.search(text) for text in texts):
            raise ValueError(f"the ON_SITE {field} names 112 (CLAUDE.md invariant 21; CD-24)")
    if any(_TWELVE.search(text) for text in action.unknown.ask_one_tr.values()):
        raise ValueError("the UNKNOWN question names 112: it is asked before any 112 (CD-24)")


def _check_snapshots(copy: GenericRedCopy, repo_root: Path) -> None:
    """Each guideline source agrees with its committed snapshot: header id, the
    quote verbatim, the url (``url`` or ``url_annex``) and ``retrieved_on``."""
    for entry in (copy.scripts or {}).values():
        for source in entry.sources:
            if not source.snapshot.startswith(_SNAPSHOT_PREFIX):
                raise GenericRedError(
                    f"snapshot {source.snapshot!r} must live under {_SNAPSHOT_PREFIX}"
                )
            problem = source_snapshot_problem(
                quote_snapshot=source.snapshot,
                guideline_id=source.guideline_id,
                quote=source.quote,
                url=source.url,
                retrieved_on=source.retrieved_on,
                repo_root=repo_root,
            )
            if problem is not None:
                raise GenericRedError(problem)


def load_generic_red(
    path: Path, *, repo_root: Path | None = None, data: bytes | None = None
) -> GenericRedCopy:
    """Load the document, validate its shape and check every guideline quote.

    ``data`` parses bytes the caller already holds (INT-465: the bytes a
    signature was checked over), instead of reading ``path`` again.
    """
    try:
        text = path.read_text(encoding="utf-8") if data is None else data.decode("utf-8")
        raw = yaml.safe_load(text)
        copy = GenericRedCopy.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise GenericRedError(f"{path.name}: generic RED document unusable") from exc
    _check_snapshots(copy, repo_root if repo_root is not None else _REPO_ROOT)
    return copy


def generic_red_refusals(copy: GenericRedCopy | None) -> tuple[str, ...]:
    """Why the generic RED is not servable; empty means servable."""
    if copy is None:
        return ("generic_red_absent",)
    if copy.status is not RuleStatus.ACTIVE:
        return ("generic_red_draft_needs_source",)
    return ()


def generic_red_strings(copy: GenericRedCopy) -> tuple[str, ...]:
    """Every authored Turkish string the generic can show or speak, in a fixed order."""
    if copy.action is None:
        return ()
    strings: list[str] = []
    for script in (copy.action.remote, copy.action.on_site):
        for texts in _texts(script).values():
            strings.extend(texts)
    strings.extend(copy.action.unknown.ask_one_tr.values())
    return tuple(strings)


def generic_red_clip_rows(
    copy: GenericRedCopy, *, voice: str, acil_location_tr: str | None
) -> tuple[ClipRow, ...]:
    """The generic's spoken rows: rendered, expanded, scripted (invariants 10 and 22).

    Raises :class:`GenericRedError` when a string cannot be rendered or expanded. A
    RED string that cannot be spoken correctly is never handed to a TTS model.
    """
    try:
        sources = [
            SpeakableText(
                subject=GENERIC_RED_DECISION,
                text=render_red_text(text, acil_location_tr=acil_location_tr),
                scripted=True,
                clipped=True,
            )
            for text in generic_red_strings(copy)
        ]
    except RedRenderError as exc:
        raise GenericRedError(f"generic RED text cannot be rendered: {exc}") from exc
    rows, _prompts, refusals = rows_from(sources, voice=voice)
    if refusals:
        raise GenericRedError(f"generic RED text cannot be spoken: {refusals[0].message}")
    try:
        for row in rows:
            # The last check before a RED row is handed to a TTS model (invariant 22).
            assert_speakable_red(row.text_tr)
    except RedRenderError as exc:
        raise GenericRedError(f"generic RED text cannot be spoken: {exc}") from exc
    return rows
