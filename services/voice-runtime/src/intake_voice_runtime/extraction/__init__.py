"""INT-083 — Extraction Work: a schema-constrained LLM behind a gateway, with
the data boundary that makes patient speech data rather than instructions.

sec_row: `llm-boundary` (docs/security/threat-model.md). legal: KVKK-9.
"""

from intake_voice_runtime.extraction.boundary import (
    BOUNDARY_NAME,
    DATA_TAG,
    ESCAPE_REASON,
    INJECTION_SUSPECTED_TOTAL,
    SENTINEL_PREFIX,
    PatientData,
    injection_event,
    render_data_block,
    wrap_patient_data,
)
from intake_voice_runtime.extraction.errors import (
    BoundaryEscape,
    CodeSlotUnbound,
    ExtractionNotConfigured,
    ExtractionRefused,
    ExtractionUnavailable,
    RecordedExtractionMismatchError,
    RecordedExtractionMissingError,
    VendorEndpointRefused,
)
from intake_voice_runtime.extraction.gateway import (
    COMPLETION_PATH,
    DEFAULT_TIMEOUT_S,
    ENV_EXTRACTION_ENDPOINT,
    ENV_EXTRACTION_RECORDED_DIR,
    Completion,
    ExtractionCall,
    ExtractionGateway,
    HttpExtractionGateway,
    RecordedExtractionGateway,
    extraction_gateway_from_env,
    render_request_payload,
)
from intake_voice_runtime.extraction.parse import parse_extraction
from intake_voice_runtime.extraction.result import (
    ExtractionFlag,
    ExtractionResult,
    FlagReason,
    SlotUpdate,
    SlotValue,
)
from intake_voice_runtime.extraction.schema import (
    EXTRACTION_SCHEMA_ID,
    PROMPT_VERSION,
    TOP_LEVEL_KEYS,
    build_instructions,
    slot_output_schema,
    unbound_code_slots,
)
from intake_voice_runtime.extraction.work import (
    CANDIDATE_FLAG_LEVEL,
    NO_CANDIDATE_LEVEL,
    ExtractionContext,
    ExtractionOutcome,
    run_extraction,
)

__all__ = [
    "BOUNDARY_NAME",
    "CANDIDATE_FLAG_LEVEL",
    "COMPLETION_PATH",
    "DATA_TAG",
    "DEFAULT_TIMEOUT_S",
    "ENV_EXTRACTION_ENDPOINT",
    "ENV_EXTRACTION_RECORDED_DIR",
    "ESCAPE_REASON",
    "EXTRACTION_SCHEMA_ID",
    "INJECTION_SUSPECTED_TOTAL",
    "NO_CANDIDATE_LEVEL",
    "PROMPT_VERSION",
    "SENTINEL_PREFIX",
    "TOP_LEVEL_KEYS",
    "BoundaryEscape",
    "CodeSlotUnbound",
    "Completion",
    "ExtractionCall",
    "ExtractionContext",
    "ExtractionFlag",
    "ExtractionGateway",
    "ExtractionNotConfigured",
    "ExtractionOutcome",
    "ExtractionRefused",
    "ExtractionResult",
    "ExtractionUnavailable",
    "FlagReason",
    "HttpExtractionGateway",
    "PatientData",
    "RecordedExtractionGateway",
    "RecordedExtractionMismatchError",
    "RecordedExtractionMissingError",
    "SlotUpdate",
    "SlotValue",
    "VendorEndpointRefused",
    "build_instructions",
    "extraction_gateway_from_env",
    "injection_event",
    "parse_extraction",
    "render_data_block",
    "render_request_payload",
    "run_extraction",
    "slot_output_schema",
    "unbound_code_slots",
    "wrap_patient_data",
]
