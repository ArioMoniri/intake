"""Readiness keyed on the lane registry (INT-515).

The synthetic host's voice runtime is pointed at its model lanes — ASR, TTS
and the extraction LLM — by the lane registry, not by an endpoint written into
this service. The registry is ``intake_platform.model_lanes`` (INT-428, ADR-035):
an admin-console-controlled store of which provider and model serves each lane,
whose seam other services call is ``ModelResolver.resolve(role, *, tenant_id)``
returning an assignment with ``available`` and ``reason``. Every gate a lane
must clear — the ADR-035 guard, both kill switches, the provider's deployment,
allow-list row and key, the model's attestation, a self-hosted lane's
``/identity`` — has already been cleared when ``available`` is true, so the
runtime re-derives none of them and reads that one answer.

**When the registry is absent the answer is still an answer.** On a tree
without ``intake_platform.model_lanes`` (main before #751), every lane is not
ready with the reason ``lane_registry_absent``. With the package but no control
store, ``lane_store_unconfigured``; with a store the builder cannot load,
``lane_registry_unloadable``; with a resolver that raises, ``lane_registry_
unreachable``. A refused lane carries the registry's own refusal code
(``hosted_key_not_set``, ``identity_mismatch``, …). Each reaches ``/readyz`` as
the check ``lane_<lane>`` and ``/metrics`` as
``voice_lane_ready{lane, reason}``, so "why is voice not ready" is answered
without reading a log — the brief's *"failing closed with a clear readiness
reason if a lane is missing"*.

**Reasons are ids or nothing.** A code that is not id-shaped becomes
``lane_refused`` before it is a label: a registry that one day put a provider
message in ``reason`` must not carry it to a metric (invariant 6).

The resolver is reached by module name, only when the package exists — the
way #751's own wiring reaches the synthetic image's hosted adapters — so this
module imports nothing from an unmerged branch and a type checker sees no
dependency on it.
"""

from __future__ import annotations

import contextlib
import enum
import importlib
import importlib.util
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol

from intake_voice_runtime.metrics import VOICE_LANE_READY
from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "LANES_FOR_PROFILE",
    "MODEL_LANES_PACKAGE",
    "MODEL_LANES_WIRING",
    "REASON_READY",
    "REASON_REFUSED",
    "REASON_REGISTRY_ABSENT",
    "REASON_REGISTRY_UNLOADABLE",
    "REASON_REGISTRY_UNREACHABLE",
    "REASON_STORE_UNCONFIGURED",
    "LaneAssignment",
    "LaneGate",
    "LaneResolver",
    "LaneStatus",
    "SpeechLane",
    "lane_gate_from_env",
]

logger = logging.getLogger("intake_voice_runtime.lanes")

#: The lane registry's package (INT-428) and the module holding its one builder.
MODEL_LANES_PACKAGE: Final = "intake_platform.model_lanes"
MODEL_LANES_WIRING: Final = "intake_platform.model_lanes.wiring"

REASON_READY: Final = "ready"
REASON_REGISTRY_ABSENT: Final = "lane_registry_absent"
REASON_STORE_UNCONFIGURED: Final = "lane_store_unconfigured"
REASON_REGISTRY_UNLOADABLE: Final = "lane_registry_unloadable"
REASON_REGISTRY_UNREACHABLE: Final = "lane_registry_unreachable"
#: What a refusal code that is not an id becomes before it is a label.
REASON_REFUSED: Final = "lane_refused"

_ID_SHAPE = re.compile(r"[a-z][a-z0-9_]{0,63}")


class SpeechLane(enum.StrEnum):
    """The three lanes a voice turn runs on — #751's ``Lane`` values."""

    ASR = "asr"
    TTS = "tts"
    LLM = "llm"


#: Which lanes a worker of each profile needs. A typed worker hears and speaks
#: nothing, so it needs the extraction lane alone (files/03 §4.4).
LANES_FOR_PROFILE: Final[Mapping[VoiceProfile, frozenset[SpeechLane]]] = {
    VoiceProfile.RESIDENCY_TR: frozenset(SpeechLane),
    VoiceProfile.TYPED: frozenset({SpeechLane.LLM}),
}


class LaneAssignment(Protocol):
    """The two fields of #751's ``ModelAssignment`` this gate reads."""

    @property
    def available(self) -> bool: ...

    @property
    def reason(self) -> str: ...


class LaneResolver(Protocol):
    """#751's ``ModelResolver`` seam: ``role → assignment``."""

    def resolve(self, role: str, *, tenant_id: str | None) -> LaneAssignment: ...


@dataclass(frozen=True)
class LaneStatus:
    lane: SpeechLane
    ready: bool
    reason: str


def _id_or_refused(reason: str) -> str:
    return reason if _ID_SHAPE.fullmatch(reason) else REASON_REFUSED


class LaneGate:
    """Each lane's readiness, read from the registry at every ``/readyz``.

    ``resolver`` is ``None`` when there is no registry to ask; ``absent_reason``
    then says why, for every lane alike.
    """

    def __init__(
        self, resolver: LaneResolver | None, *, absent_reason: str = REASON_REGISTRY_ABSENT
    ) -> None:
        self._resolver = resolver
        self._absent_reason = _id_or_refused(absent_reason)
        self._published: dict[SpeechLane, str] = {}

    def status(self, lane: SpeechLane) -> LaneStatus:
        """Ask the registry; publish the answer; never raise."""
        if self._resolver is None:
            status = LaneStatus(lane, ready=False, reason=self._absent_reason)
        else:
            try:
                # no tenant: readiness is the deployment's, not one tenant's
                assignment = self._resolver.resolve(lane.value, tenant_id=None)
            except Exception as err:  # noqa: BLE001 — a readiness probe reports
                logger.warning(
                    "lane registry unreachable",
                    extra={"lane": lane.value, "error": type(err).__name__},
                )
                status = LaneStatus(lane, ready=False, reason=REASON_REGISTRY_UNREACHABLE)
            else:
                if assignment.available:
                    status = LaneStatus(lane, ready=True, reason=REASON_READY)
                else:
                    status = LaneStatus(lane, ready=False, reason=_id_or_refused(assignment.reason))
        self._publish(status)
        return status

    def _publish(self, status: LaneStatus) -> None:
        previous = self._published.get(status.lane)
        if previous is not None and previous != status.reason:
            # already gone if another gate in this process replaced it first
            with contextlib.suppress(KeyError):
                VOICE_LANE_READY.remove(status.lane.value, previous)
        VOICE_LANE_READY.labels(lane=status.lane.value, reason=status.reason).set(
            1.0 if status.ready else 0.0
        )
        self._published[status.lane] = status.reason


def lane_gate_from_env(
    env: Mapping[str, str],
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> LaneGate:
    """The gate over the deployment's lane registry, or over none and why.

    #751's builder is ``model_lanes_from_env(env, *, kv, root)``: ``None`` when
    no control store is configured, otherwise a wiring whose ``router`` is the
    resolver. The runtime hands it no key store of its own (``kv=None``): a
    hosted route it could not authenticate is reported by the registry's own
    refusal code rather than worked around here. ``root`` is the image's
    working directory, where the registry's committed files sit.
    """
    if find_spec(MODEL_LANES_PACKAGE) is None:
        return LaneGate(None, absent_reason=REASON_REGISTRY_ABSENT)
    try:
        wiring = import_module(MODEL_LANES_WIRING).model_lanes_from_env(env, kv=None, root=Path())
    except Exception as err:  # noqa: BLE001 — the class name says what is missing
        logger.warning("lane registry unloadable", extra={"error": type(err).__name__})
        return LaneGate(None, absent_reason=REASON_REGISTRY_UNLOADABLE)
    if wiring is None:
        return LaneGate(None, absent_reason=REASON_STORE_UNCONFIGURED)
    router: LaneResolver = wiring.router
    return LaneGate(router)
