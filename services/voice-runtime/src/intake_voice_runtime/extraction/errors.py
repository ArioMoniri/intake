"""Every refusal on the extraction boundary, and the one rule they share.

**A message names the field, never the value.** An exception message reaches a
log, and the value on this boundary is a patient's own words — so a refusal
that quoted what it refused would be the leak it exists to prevent (CLAUDE.md
invariant 6; the rule :mod:`intake_platform.audit` and
:mod:`intake_platform.observability.spans` already state).

The hierarchy is flat on purpose: :class:`ExtractionRefused` is the one thing a
caller has to catch, and the subclasses exist so a test can say *which* refusal
it expects without matching on message text.
"""

from __future__ import annotations

__all__ = [
    "BoundaryEscape",
    "ExtractionNotConfigured",
    "ExtractionRefused",
    "ExtractionUnavailable",
    "RecordedExtractionMismatchError",
    "RecordedExtractionMissingError",
    "VendorEndpointRefused",
]


class ExtractionRefused(ValueError):
    """The extraction boundary refused. The message carries no content."""


class BoundaryEscape(ExtractionRefused):
    """Patient text tried to leave its data block (files/10 §5 LLM01).

    Raised before any bytes are assembled, so the escaping string never reaches
    a prompt, a log line or this exception's own message.
    """


class ExtractionNotConfigured(ExtractionRefused):
    """No unambiguous source of completions. Nothing is guessed."""


class VendorEndpointRefused(ExtractionRefused):
    """The configured endpoint is an anthropic/openai/google host.

    CLAUDE.md invariant 19: those adapters are the mock/dev path only and are
    blocked on the PHI path by the egress allow-list. This refusal sits one
    layer earlier — there is no configuration of the extraction gateway that
    points at a vendor, allow-list or not.
    """


class ExtractionUnavailable(ExtractionRefused):
    """The configured self-hosted endpoint could not be reached or answered."""


class RecordedExtractionMissingError(ExtractionRefused):
    """No recorded completion exists for this call under the recording root."""


class RecordedExtractionMismatchError(ExtractionRefused):
    """A recording exists but was made for other text, or another prompt."""
