"""Refusals at the extraction boundary (INT-083).

One base class so a caller can catch the whole boundary, and a named subclass
per reason so a caller that cares can tell "the operator has not configured a
model" from "the model tried to set a triage level".

**No message in this hierarchy ever echoes a value.** Every one of these
exceptions is raised while holding either a transcript or a model completion,
and an exception message reaches a log (CLAUDE.md invariant 6; the same rule
:mod:`intake_platform.audit` and :mod:`intake_platform.observability.spans`
state for their own boundaries). Messages name the field, the key or the
digest — never the content.
"""

from __future__ import annotations

__all__ = [
    "DeidentificationRequired",
    "DelimiterCollisionError",
    "IdentifierInTraceError",
    "LlmError",
    "LlmNotConfiguredError",
    "LlmRefusedError",
    "LlmUnavailableError",
    "RecordedCompletionMismatch",
    "RecordedCompletionMissing",
    "SchemaError",
    "SchemaViolation",
    "TriageAssertionRefused",
    "UnpinnedModelError",
]


class LlmError(Exception):
    """Base for every refusal at the extraction boundary."""


class LlmNotConfiguredError(LlmError):
    """No unambiguous source of completions. The caller stops rather than guessing."""


class LlmUnavailableError(LlmError):
    """The configured endpoint could not be reached."""


class LlmRefusedError(LlmError):
    """The endpoint answered, and the answer was a refusal."""


class RecordedCompletionMissing(LlmError):
    """No recorded completion exists for this input under the recording root."""


class RecordedCompletionMismatch(LlmError):
    """A recording exists but was made for another schema or another model."""


class UnpinnedModelError(LlmError):
    """A model id that is not a row of the canonical pin table (files/03 §4.9.1).

    ADR-021: *"a model not in that table is not pinned, and no other file
    restates a pin"*. The gateway refuses rather than serving from whatever
    the operator typed.
    """


class DelimiterCollisionError(LlmError):
    """Text handed to the data boundary already contains the fence token.

    Refused, never escaped: escaping is a rewriting of what the patient said,
    and the whole point of the fence is that its contents are untouched
    (CLAUDE.md invariant 14 — speech is data, never instructions).
    """


class SchemaError(LlmError):
    """A slot schema could not be built from the specs given."""


class SchemaViolation(LlmError):
    """A model completion did not validate against the slot schema."""


class TriageAssertionRefused(SchemaViolation):
    """The completion carried a key that names a triage level or a priority.

    CLAUDE.md invariant 1 / ADR-004: RED and YELLOW come from
    ``packages/protocols/triage`` alone. The completion is refused outright —
    it is not stripped of the offending key and used for the rest, because a
    model that answered outside the schema answered a different question.
    """


class DeidentificationRequired(LlmError):
    """A dev/mock-tier gateway was reached without INT-015's egress de-identification."""


class IdentifierInTraceError(LlmError):
    """A trace field value matched an identifier pattern (TCKN, TR mobile, IBAN)."""
