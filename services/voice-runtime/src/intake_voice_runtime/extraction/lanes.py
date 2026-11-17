"""``ExtractionGateway`` over the model lanes (INT-428, ADR-035).

The ``extract_slots`` seam keeps its interface: :class:`LaneRoutedExtractionGateway`
*is* an :class:`~intake_voice_runtime.extraction.gateway.ExtractionGateway`,
so the handler, the parser and PolicyGuard downstream are untouched (invariant
2), and the parser's schema still has no field a triage level could occupy
(invariant 1). What changes is which backend answers, decided by
:func:`intake_platform.model_lanes.dispatch` from the console's control — once
per session when a :class:`~intake_platform.model_lanes.SessionLanes` is given:

- ``self_hosted`` — the configured :class:`HttpExtractionGateway` (or, in CI
  and the no-GPU dev path, the recorded one), whose vendor-host refusal is
  unchanged: a vendor cannot be configured as the *self-hosted* endpoint;
- ``hosted:<provider>`` — a :class:`~intake_platform.model_lanes.HostedBackend`
  (present only in the synthetic image), asked for the resolved dated
  snapshot by name, with the instructions in the system role and the
  delimited transcript in the user role, rendered by the same
  :func:`render_data_block` the self-hosted lane uses (invariant 14). The
  model the provider says answered is checked against the one asked for.

A lane that cannot serve raises :class:`ExtractionUnavailable` carrying the
routing code only — never a transcript fragment (invariant 6).
"""

from __future__ import annotations

from collections.abc import Mapping

from intake_platform.model_lanes import (
    HostedBackend,
    HostedLaneUnavailable,
    HostedUsage,
    Lane,
    LaneRefused,
    LaneResult,
    LaneRouter,
    ModelAssignment,
    ProviderId,
    RouteKind,
    SessionLanes,
    dispatch,
    verify_served_model,
)

from intake_voice_runtime.extraction.boundary import render_data_block
from intake_voice_runtime.extraction.errors import (
    ExtractionUnavailable,
    RecordedExtractionMissingError,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall, ExtractionGateway
from intake_voice_runtime.extraction.schema import EXTRACTION_SCHEMA_ID

__all__ = ["LaneRoutedExtractionGateway"]


class LaneRoutedExtractionGateway:
    """One ``complete`` per call, routed through the model lanes."""

    def __init__(
        self,
        router: LaneRouter,
        *,
        tenant_id: str | None,
        self_hosted: ExtractionGateway | None,
        hosted: Mapping[ProviderId, HostedBackend],
        session: SessionLanes | None = None,
        role: str = Lane.LLM.value,
    ) -> None:
        self._router = router
        self._tenant_id = tenant_id
        self._self_hosted = self_hosted
        self._hosted = hosted
        self._session = session
        self._role = role

    def _run(self, call: ExtractionCall, assignment: ModelAssignment) -> LaneResult[Completion]:
        route = assignment.route
        if route is not None and route.kind is RouteKind.SELF_HOSTED:
            if self._self_hosted is None:
                raise ExtractionUnavailable("no self-hosted extraction endpoint is configured")
            done = self._self_hosted.complete(call)
            return LaneResult(done, HostedUsage(done.input_tokens, done.output_tokens))
        provider = self._hosted.get(route.provider) if route and route.provider else None
        data_class = assignment.egress_data_class
        if provider is None or data_class is None or assignment.model is None:
            raise HostedLaneUnavailable("hosted_lane_unconfigured")
        chat = provider.chat_json(
            instructions=call.instructions,
            data_block=render_data_block(call.data),
            schema_name=EXTRACTION_SCHEMA_ID.replace(".", "_"),
            json_schema=call.json_schema,
            data_class=data_class,
            model=assignment.model.wire,
        )
        verify_served_model(assignment, chat.model)
        completion = Completion(
            text=chat.text,
            input_tokens=chat.usage.input_tokens,
            output_tokens=chat.usage.output_tokens,
        )
        return LaneResult(completion, chat.usage)

    def complete(self, call: ExtractionCall) -> Completion:
        try:
            return dispatch(
                self._router,
                self._role,
                tenant_id=self._tenant_id,
                call=lambda assignment: self._run(call, assignment),
                failures=(ExtractionUnavailable, RecordedExtractionMissingError),
                session=self._session,
            )
        except LaneRefused as refused:
            raise ExtractionUnavailable(f"the llm lane refused the call: {refused.code}") from None
