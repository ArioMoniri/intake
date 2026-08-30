"""The extraction boundary: a schema-constrained LLM behind a gateway (INT-083).

files/03 §1 lists ``LLMGateway`` among the cross-cutting concerns, beside
``Security``, ``PolicyGuard``, ``Audit`` and ``Consent`` — and every one of
those already lives in this package (:mod:`intake_platform.egress`,
:mod:`intake_platform.deid`, :mod:`intake_platform.audit`,
:mod:`intake_platform.consent`,
:mod:`intake_platform.observability.spans`). This boundary composes four of
them, so it lives with them rather than in a package of its own.

*Why not a separate ``packages/llm-gateway``, given that the TTS gateway is
one?* Because the TTS gateway is separate for a reason that does not apply
here: ``packages/protocols`` must stay free of I/O and of clients, and two
import-boundary tests enforce that, so its clip gateway had to move out. The
extraction gateway has no such constraint and three hard dependencies inside
``intake_platform``; a new package would import all of them and gain nothing.
ADR-006 fixes the *adapter shape*, which this module follows exactly
(Protocol + HTTP adapter + recorded adapter + fail-closed factory) — it does
not fix the package, so no new ADR is owed.

The five modules, in the order a request crosses them:

* :mod:`~intake_platform.llm.slot_schema` — the closed JSON Schema, built
  from the protocol's own typed slots. No property a triage level could
  occupy.
* :mod:`~intake_platform.llm.boundary` — the nonced fence that makes the
  transcript data and not instructions (invariant 14).
* :mod:`~intake_platform.llm.gateway` — the adapter seam; recorded in CI,
  self-hosted vLLM in production, vendor hosts refused in-process by the
  egress allow-list (invariant 19).
* :mod:`~intake_platform.llm.extraction` — validation, the invariant-1
  refusal, and the Work orchestration.
* :mod:`~intake_platform.llm.trace` — the structural span and score row; no
  content carrier, and no live trace store is reached (invariant 6).

:mod:`~intake_platform.llm.units` sits beside them: the ingestion guard for
extracted magnitudes (invariant 22).
"""

from __future__ import annotations

from intake_platform.llm.boundary import (
    DATA_RULE,
    FENCE_MARKER,
    PROMPT_TEMPLATE_VERSION,
    DataBlock,
    ExtractionPrompt,
    build_extraction_prompt,
    wrap_as_data,
)
from intake_platform.llm.errors import (
    DeidentificationRequired,
    DelimiterCollisionError,
    IdentifierInTraceError,
    LlmError,
    LlmNotConfiguredError,
    LlmRefusedError,
    LlmUnavailableError,
    RecordedCompletionMismatch,
    RecordedCompletionMissing,
    SchemaError,
    SchemaViolation,
    TriageAssertionRefused,
    UnpinnedModelError,
)
from intake_platform.llm.extraction import (
    INJECTION_SIGNAL_REFUSALS,
    LEVEL_SHAPED_KEYS,
    TOP_LEVEL_KEYS,
    ExtractionOutput,
    ExtractionRun,
    ExtractionWork,
    is_injection_signal,
    parse_extraction,
)
from intake_platform.llm.gateway import (
    CHAT_COMPLETIONS_PATH,
    ENV_LLM_ENDPOINT,
    ENV_LLM_MODEL_ID,
    ENV_LLM_MODEL_REVISION,
    ENV_LLM_RECORDED_DIR,
    PINNED_EXTRACTION_MODELS,
    GatewayTier,
    HttpLlmGateway,
    LlmCompletion,
    LlmGateway,
    RecordedLlmGateway,
    llm_gateway_from_env,
)
from intake_platform.llm.slot_schema import (
    CONFIDENCE_PATTERN,
    DATE_PATTERN,
    DECIMAL_PATTERN,
    DURATION_PATTERN,
    MAX_FREE_TEXT_CHARS,
    SlotSchema,
    SlotSpec,
    SlotValueType,
    build_slot_schema,
)
from intake_platform.llm.trace import (
    PERMITTED_RECORD_LEVELS,
    emit_extraction_span,
    extraction_record,
    extraction_span,
)
from intake_platform.llm.units import (
    ANALYTE_NAMES,
    Analyte,
    AnalyteAmbiguous,
    QuantityResolution,
    render_quantity,
    resolve_analyte,
    resolve_quantity,
)

__all__ = [
    "ANALYTE_NAMES",
    "CHAT_COMPLETIONS_PATH",
    "CONFIDENCE_PATTERN",
    "DATA_RULE",
    "DATE_PATTERN",
    "DECIMAL_PATTERN",
    "DURATION_PATTERN",
    "ENV_LLM_ENDPOINT",
    "ENV_LLM_MODEL_ID",
    "ENV_LLM_MODEL_REVISION",
    "ENV_LLM_RECORDED_DIR",
    "FENCE_MARKER",
    "INJECTION_SIGNAL_REFUSALS",
    "LEVEL_SHAPED_KEYS",
    "MAX_FREE_TEXT_CHARS",
    "PERMITTED_RECORD_LEVELS",
    "PINNED_EXTRACTION_MODELS",
    "PROMPT_TEMPLATE_VERSION",
    "TOP_LEVEL_KEYS",
    "Analyte",
    "AnalyteAmbiguous",
    "DataBlock",
    "DeidentificationRequired",
    "DelimiterCollisionError",
    "ExtractionOutput",
    "ExtractionPrompt",
    "ExtractionRun",
    "ExtractionWork",
    "GatewayTier",
    "HttpLlmGateway",
    "IdentifierInTraceError",
    "LlmCompletion",
    "LlmError",
    "LlmGateway",
    "LlmNotConfiguredError",
    "LlmRefusedError",
    "LlmUnavailableError",
    "QuantityResolution",
    "RecordedCompletionMismatch",
    "RecordedCompletionMissing",
    "RecordedLlmGateway",
    "SchemaError",
    "SchemaViolation",
    "SlotSchema",
    "SlotSpec",
    "SlotValueType",
    "TriageAssertionRefused",
    "UnpinnedModelError",
    "build_extraction_prompt",
    "build_slot_schema",
    "emit_extraction_span",
    "extraction_record",
    "extraction_span",
    "is_injection_signal",
    "llm_gateway_from_env",
    "parse_extraction",
    "render_quantity",
    "resolve_analyte",
    "resolve_quantity",
    "wrap_as_data",
]
