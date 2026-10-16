"""Model lanes: self-hosted or hosted, provider and model, from the console (INT-428).

ADR-035 records the owner's decision and its scope, as narrowed by the binding
medical and AI/ML reviews: a hosted provider may serve the ``llm``, ``asr`` and
``tts`` lanes only in the **synthetic** deployment (its image alone carries the
``intake_hosted_lanes`` adapters), until the GPU lanes are healthy; in a
real-PHI deployment a hosted lane is unrepresentable.

- :mod:`.model` — the control record, roles, the closed route vocabulary;
- :mod:`.guard` — the ADR-035 guard and the immutable data class;
- :mod:`.models` — dated-snapshot hosted allow-lists, attested self-hosted models;
- :mod:`.qualifications` — the per-model-version swap gate (red-flag goldens);
- :mod:`.routing` — the pure decision table;
- :mod:`.health` — self-hosted identity probes;
- :mod:`.dispatch` — running a call, metering, fallback;
- :mod:`.router` — :class:`~.router.ModelResolver` (``role →
  (provider, model)``, the seam other services call), sessions, dispatch;
- :mod:`.hosted` — the vendor-free Protocol hosted adapters implement;
- :mod:`.store` — the Redis control store (compare-and-set);
- :mod:`.keys` — provider keys in OpenBao, never echoed;
- :mod:`.metrics` — the catalogued series.
"""

from intake_platform.model_lanes.dispatch import LaneResult, dispatch, verify_served_model
from intake_platform.model_lanes.guard import (
    ENV_DEPLOYMENT_DATA_CLASS,
    HostedLaneRefused,
    HostedPermit,
    check_hosted_permitted,
    deployment_data_class,
    effective_data_class,
)
from intake_platform.model_lanes.health import (
    LaneIdentityMismatch,
    LaneRefused,
    SelfHostedHealth,
    ServedIdentity,
    self_hosted_endpoints_from_env,
)
from intake_platform.model_lanes.hosted import (
    NO_ANSWER,
    HostedBackend,
    HostedChat,
    HostedLanes,
    HostedLaneUnavailable,
    HostedProviderInfo,
    HostedSpeech,
    HostedTranscript,
    HostedUsage,
)
from intake_platform.model_lanes.keys import (
    KeyStatus,
    KeyVaultUnavailable,
    ProviderApiKey,
    ProviderKeyMalformed,
    ProviderKeyVault,
)
from intake_platform.model_lanes.model import (
    LANES,
    Lane,
    LaneRoute,
    LaneSetting,
    ModelLanesChange,
    ModelLanesControl,
    ModelLanesRefused,
    ModelRole,
    ProviderId,
    RouteKind,
    TenantDataClass,
    parse_lane,
    parse_model_key,
    parse_provider,
    parse_role,
    parse_route,
)
from intake_platform.model_lanes.models import (
    HostedModel,
    ModelCatalogue,
    ModelRef,
    ModelSelectionRefused,
    SelfHostedModel,
)
from intake_platform.model_lanes.qualifications import Qualification, QualificationRegistry
from intake_platform.model_lanes.router import (
    LaneRouter,
    ModelAssignment,
    ModelResolver,
    SessionLanes,
)
from intake_platform.model_lanes.routing import RouteDecision, decide_route
from intake_platform.model_lanes.store import (
    ENV_MODEL_LANES_REDIS_URL,
    InMemoryModelLanesStore,
    ModelLanesConflict,
    ModelLanesReader,
    ModelLanesStore,
    ModelLanesUnavailable,
    RedisModelLanesStore,
    model_lanes_store_from_env,
)

__all__ = [
    "ENV_DEPLOYMENT_DATA_CLASS",
    "ENV_MODEL_LANES_REDIS_URL",
    "LANES",
    "NO_ANSWER",
    "HostedBackend",
    "HostedChat",
    "HostedLaneRefused",
    "HostedLaneUnavailable",
    "HostedLanes",
    "HostedModel",
    "HostedPermit",
    "HostedProviderInfo",
    "HostedSpeech",
    "HostedTranscript",
    "HostedUsage",
    "InMemoryModelLanesStore",
    "KeyStatus",
    "KeyVaultUnavailable",
    "Lane",
    "LaneIdentityMismatch",
    "LaneRefused",
    "LaneResult",
    "LaneRoute",
    "LaneRouter",
    "LaneSetting",
    "ModelAssignment",
    "ModelCatalogue",
    "ModelLanesChange",
    "ModelLanesConflict",
    "ModelLanesControl",
    "ModelLanesReader",
    "ModelLanesRefused",
    "ModelLanesStore",
    "ModelLanesUnavailable",
    "ModelRef",
    "ModelResolver",
    "ModelRole",
    "ModelSelectionRefused",
    "ProviderApiKey",
    "ProviderId",
    "ProviderKeyMalformed",
    "ProviderKeyVault",
    "Qualification",
    "QualificationRegistry",
    "RedisModelLanesStore",
    "RouteDecision",
    "RouteKind",
    "SelfHostedHealth",
    "SelfHostedModel",
    "ServedIdentity",
    "SessionLanes",
    "TenantDataClass",
    "check_hosted_permitted",
    "decide_route",
    "deployment_data_class",
    "dispatch",
    "effective_data_class",
    "model_lanes_store_from_env",
    "parse_lane",
    "parse_model_key",
    "parse_provider",
    "parse_role",
    "parse_route",
    "self_hosted_endpoints_from_env",
    "verify_served_model",
]
