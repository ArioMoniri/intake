"""The Voice module composite behind ``GET /admin/voice`` (INT-182; files/08 §3).

One JSON document, ``intake.admin.voice.v1``, that ``apps/admin-web`` renders
as tiles. Three sources, all server-side (files/08 §0b F1 — the browser never
names a datasource):

- **Prometheus**, through the fixed :data:`VOICE_QUERIES` table, every series
  catalogued (invariant 13): session starts by profile and route reason and
  the kill switch's in-flight moves (this issue's runtime families), turn
  latency per profile (the catalogued ``voice.round_trip_ms``), speech-call
  errors per component (``voice_speech_calls_total``), and INT-100's
  ``vendor_failovers_total`` / ``vendor_breaker_state``.
- **The voice control store** — every configured tenant's kill switch,
  default profile and canary, with who changed it and who approved it.
- **The four-eyes service** — voice ceremonies awaiting their second key,
  ids and roles only; the brief (with the free text) is its own route.

**Unknown is a state (invariant 17).** A tile whose source is unconfigured,
unreachable, erroring or silent is ``{"state": "unknown", "reason": <code>}``
with no figure. One failing query blanks its own tile only, and the controls
tile fails closed on its own store independently of Prometheus.

**Per profile, closed.** A ``profile`` label outside ``residency_tr``/``typed``
turns its tile unknown rather than painting a profile that does not exist
(invariant 19).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from intake_platform.admin.actions import (
    VOICE_CANARY_SET,
    VOICE_CEREMONIES,
    VOICE_KILL_SWITCH_ENGAGE,
    VOICE_KILL_SWITCH_RELEASE,
    VOICE_PROFILE_SWITCH,
    DangerousAction,
)
from intake_platform.admin.flag_governance import FlagChangeReason
from intake_platform.admin.four_eyes import PendingAction
from intake_platform.voice_control import (
    CANARY_WEIGHT_MAX,
    CANARY_WEIGHT_MIN,
    TenantVoiceControl,
    VoiceControlChange,
    VoiceControlProfile,
    VoiceControlStore,
    VoiceControlUnavailable,
)

from intake_api.admin.ops_prom import (
    PromClient,
    PromSession,
    Sample,
    TileUnknown,
    prom_client_from_env,
)

__all__ = [
    "VOICE_QUERIES",
    "VOICE_SCHEMA",
    "build_voice_console",
    "control_view",
    "load_voice_console",
]

VOICE_SCHEMA: Final = "intake.admin.voice.v1"
WINDOW: Final = "24h"
PROFILES: Final = tuple(profile.value for profile in VoiceControlProfile)

#: The only PromQL this API runs for the Voice module. A caller cannot add to it.
VOICE_QUERIES: Final[Mapping[str, str]] = {
    "sessions": f"sum by (profile, reason) (increase(voice_session_routes_total[{WINDOW}]))",
    "inflight_switches": f"sum by (outcome) (increase(voice_kill_switch_flips_total[{WINDOW}]))",
    "control_read_failures": (
        f"sum by (phase) (increase(voice_control_read_failures_total[{WINDOW}]))"
    ),
    "latency_p50": (
        "histogram_quantile(0.5, sum by (le, profile) "
        f"(rate(voice_round_trip_ms_bucket[{WINDOW}])))"
    ),
    "latency_p95": (
        "histogram_quantile(0.95, sum by (le, profile) "
        f"(rate(voice_round_trip_ms_bucket[{WINDOW}])))"
    ),
    "speech_calls": (
        f"sum by (component, kind, outcome) (increase(voice_speech_calls_total[{WINDOW}]))"
    ),
    "failovers": (
        f"sum by (from_component, to_component) (increase(vendor_failovers_total[{WINDOW}]))"
    ),
    "breakers": "max by (component, state) (vendor_breaker_state)",
}

_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "sessions": frozenset({"profile", "reason"}),
    "inflight_switches": frozenset({"outcome"}),
    "control_read_failures": frozenset({"phase"}),
    "latency_p50": frozenset({"profile"}),
    "latency_p95": frozenset({"profile"}),
    "speech_calls": frozenset({"component", "kind", "outcome"}),
    "failovers": frozenset({"from_component", "to_component"}),
    "breakers": frozenset({"component", "state"}),
}

_ROUTE_REASONS: Final = frozenset({"default", "canary", "kill_switch", "control_unreadable"})
_CALL_OUTCOMES: Final = frozenset({"ok", "failed"})
_CALL_KINDS: Final = frozenset({"asr", "tts"})
#: INT-100's breaker vocabulary, worst last — across replicas the worst wins.
_BREAKER_RANK: Final[Mapping[str, int]] = {"closed": 0, "half_open": 1, "open": 2}


def _count(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def _profile(value: str) -> str:
    if value not in PROFILES:
        raise TileUnknown("unexpected_label")
    return value


def _closed(value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        raise TileUnknown("unexpected_label")
    return value


# --- Prometheus tiles --------------------------------------------------------------


def _sessions(session: PromSession) -> dict[str, Any]:
    samples = session.fetch("sessions")
    if not samples:
        raise TileUnknown("no_series")
    rows = [
        {
            "profile": _profile(s.labels["profile"]),
            "reason": _closed(s.labels["reason"], _ROUTE_REASONS),
            "sessions": _count(s.value),
        }
        for s in sorted(samples, key=lambda s: (s.labels["profile"], s.labels["reason"]))
    ]
    return {"rows": rows}


def _kill_switch_activity(session: PromSession) -> dict[str, Any]:
    inflight = session.fetch("inflight_switches")
    failures = session.fetch("control_read_failures")
    if not inflight and not failures:
        raise TileUnknown("no_series")
    return {
        "inflight": [
            {
                "outcome": _closed(s.labels["outcome"], frozenset({"switched", "not_armed"})),
                "count": _count(s.value),
            }
            for s in sorted(inflight, key=lambda s: s.labels["outcome"])
        ],
        "read_failures": [
            {
                "phase": _closed(s.labels["phase"], frozenset({"start", "poll"})),
                "count": _count(s.value),
            }
            for s in sorted(failures, key=lambda s: s.labels["phase"])
        ],
    }


def _by_profile(samples: tuple[Sample, ...]) -> dict[str, float]:
    return {_profile(s.labels["profile"]): s.value for s in samples}


def _turn_latency(session: PromSession) -> dict[str, Any]:
    p50 = _by_profile(session.fetch("latency_p50"))
    p95 = _by_profile(session.fetch("latency_p95"))
    if not p50 and not p95:
        raise TileUnknown("no_series")
    return {
        "rows": [
            {
                "profile": profile,
                "p50_ms": round(p50[profile], 1) if profile in p50 else None,
                "p95_ms": round(p95[profile], 1) if profile in p95 else None,
            }
            for profile in PROFILES
            if profile in p50 or profile in p95
        ]
    }


def _speech_errors(session: PromSession) -> dict[str, Any]:
    samples = session.fetch("speech_calls")
    if not samples:
        raise TileUnknown("no_series")
    tally: dict[tuple[str, str], dict[str, int]] = {}
    for s in samples:
        kind = _closed(s.labels["kind"], _CALL_KINDS)
        outcome = _closed(s.labels["outcome"], _CALL_OUTCOMES)
        counts = tally.setdefault((s.labels["component"], kind), {"ok": 0, "failed": 0})
        counts[outcome] += _count(s.value) or 0
    rows = []
    for (component, kind), counts in sorted(tally.items()):
        calls = counts["ok"] + counts["failed"]
        rows.append(
            {
                "component": component,
                "kind": kind,
                "calls": calls,
                "failures": counts["failed"],
                "error_ratio": round(counts["failed"] / calls, 4) if calls else None,
            }
        )
    return {"rows": rows}


def _failovers(session: PromSession) -> dict[str, Any]:
    samples = session.fetch("failovers")
    if not samples:
        raise TileUnknown("no_series")
    return {
        "rows": [
            {
                "from_component": s.labels["from_component"],
                "to_component": s.labels["to_component"],
                "count": _count(s.value),
            }
            for s in sorted(
                samples, key=lambda s: (s.labels["from_component"], s.labels["to_component"])
            )
        ]
    }


def _breakers(session: PromSession) -> dict[str, Any]:
    samples = session.fetch("breakers")
    if not samples:
        raise TileUnknown("no_series")
    current: dict[str, str | None] = {}
    for s in samples:
        state = s.labels["state"]
        if state not in _BREAKER_RANK:
            raise TileUnknown("unexpected_label")
        held = current.setdefault(s.labels["component"], None)
        if s.value >= 1 and (held is None or _BREAKER_RANK[state] > _BREAKER_RANK[held]):
            current[s.labels["component"]] = state
    return {
        "rows": [{"component": name, "state": state} for name, state in sorted(current.items())]
    }


_PROM_TILES: Final[Mapping[str, tuple[Callable[[PromSession], dict[str, Any]], dict[str, Any]]]] = {
    "sessions": (_sessions, {"window": WINDOW, "rows": []}),
    "kill_switch_activity": (
        _kill_switch_activity,
        {"window": WINDOW, "inflight": [], "read_failures": []},
    ),
    "turn_latency": (
        _turn_latency,
        {"metric_id": "voice.round_trip_ms", "window": WINDOW, "rows": []},
    ),
    "speech_errors": (_speech_errors, {"window": WINDOW, "rows": []}),
    "failovers": (_failovers, {"window": WINDOW, "rows": []}),
    "breakers": (_breakers, {"rows": []}),
}


# --- the store and the ceremony -----------------------------------------------------


def control_view(control: TenantVoiceControl) -> dict[str, Any]:
    """One tenant's control as the console and the write routes show it."""
    return {
        "tenant_id": control.tenant_id,
        "kill_switch": control.kill_switch,
        "default_profile": control.default_profile.value,
        "canary_profile": control.canary_profile.value if control.canary_profile else None,
        "canary_weight": control.canary_weight,
        "effective_profile": control.effective_profile.value,
        "revision": control.revision,
        "changed_at": control.changed_at.isoformat() if control.changed_at else None,
        "changed_by": control.changed_by,
        "approved_by": control.approved_by,
        "last_change": control.last_change.value if control.last_change else None,
    }


def _controls(store: VoiceControlStore | None) -> tuple[dict[str, Any], str]:
    if store is None:
        return {"state": "unknown", "reason": "voice_control_unconfigured", "tenants": []}, (
            "unconfigured"
        )
    try:
        tenants = store.tenants()
    except VoiceControlUnavailable as failure:
        return {"state": "unknown", "reason": failure.code, "tenants": []}, "unreachable"
    rows = [control_view(control) for control in tenants]
    return {"state": "ok", "reason": None, "tenants": rows}, "ok"


def _pending(actions: Sequence[PendingAction]) -> dict[str, Any]:
    rows = []
    for pending in actions:
        if pending.action not in VOICE_CEREMONIES:
            continue
        evidence = pending.evidence
        weight = evidence.get("weight")
        rows.append(
            {
                "action_id": pending.id,
                "dangerous_action_id": pending.action.id,
                "tier": int(pending.action.tier),
                "tenant_id": evidence["tenant"],
                "control": evidence["control"],
                "profile": evidence.get("profile"),
                "weight": int(weight) if weight is not None else None,
                "requested_role": pending.actor.role.value,
                "created_at": pending.created_at.isoformat(),
                "expires_at": pending.expires_at.isoformat(),
            }
        )
    return {"state": "ok", "reason": None, "actions": rows}


_CATALOGUE: Final[tuple[tuple[VoiceControlChange, DangerousAction, str], ...]] = (
    (
        VoiceControlChange.KILL_SWITCH_ENGAGE,
        VOICE_KILL_SWITCH_ENGAGE,
        "POST /admin/voice/kill-switch",
    ),
    (
        VoiceControlChange.KILL_SWITCH_RELEASE,
        VOICE_KILL_SWITCH_RELEASE,
        "POST /admin/voice/kill-switch/release",
    ),
    (VoiceControlChange.DEFAULT_PROFILE, VOICE_PROFILE_SWITCH, "PUT /admin/voice/profile/{tenant}"),
    (VoiceControlChange.CANARY, VOICE_CANARY_SET, "PUT /admin/voice/canary/{tenant}"),
)


def _control_catalogue() -> list[dict[str, Any]]:
    """What each control is, read off the ``DangerousAction`` registry — the
    page renders who may request and who may approve from this, not from a
    list of its own."""
    rows: list[dict[str, Any]] = []
    for change, action, route in _CATALOGUE:
        row: dict[str, Any] = {
            "control": change.value,
            "dangerous_action_id": action.id,
            "route": route,
            "tier": int(action.tier),
            "direction": action.direction.value,
            "actor_roles": sorted(role.value for role in action.actor_roles),
            "approver_roles": sorted(role.value for role in action.approver_roles),
        }
        if change is VoiceControlChange.CANARY:
            row["weight_bounds"] = {"min": CANARY_WEIGHT_MIN, "max": CANARY_WEIGHT_MAX}
        rows.append(row)
    return rows


def build_voice_console(
    *,
    prom: PromClient | None,
    controls: VoiceControlStore | None,
    pending: Sequence[PendingAction],
    now: datetime,
    prom_misconfigured: bool = False,
) -> dict[str, Any]:
    """The whole ``intake.admin.voice.v1`` document."""
    controls_tile, controls_source = _controls(controls)
    tiles: dict[str, Any] = {"controls": controls_tile, "pending": _pending(pending)}
    session = PromSession(prom, VOICE_QUERIES, _LABELS) if prom is not None else None
    for tile_id, (builder, empty) in _PROM_TILES.items():
        if session is None:
            reason = "prometheus_misconfigured" if prom_misconfigured else "prometheus_unconfigured"
            tiles[tile_id] = {"state": "unknown", "reason": reason, **empty}
            continue
        try:
            tiles[tile_id] = {"state": "ok", "reason": None, **empty, **builder(session)}
        except TileUnknown as unknown:
            tiles[tile_id] = {"state": "unknown", "reason": unknown.reason, **empty}
    if session is None:
        prometheus = "misconfigured" if prom_misconfigured else "unconfigured"
    else:
        prometheus = "unreachable" if session.unreachable else "ok"
    return {
        "schema": VOICE_SCHEMA,
        "generated_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profiles": list(PROFILES),
        # INT-188's closed change-reason set, served so the page's forms offer
        # exactly what the write routes accept rather than a copy of it
        "reason_classes": [reason.value for reason in FlagChangeReason],
        "sources": {"prometheus": prometheus, "controls": controls_source},
        "control_catalogue": _control_catalogue(),
        "tiles": tiles,
    }


def load_voice_console(
    now: datetime,
    *,
    controls: VoiceControlStore | None,
    pending: Sequence[PendingAction],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Wire the composite from the process environment (the same Prometheus
    variable as the ops and reliability composites). A malformed URL is
    ``prometheus_misconfigured``, never a crash and never a guess."""
    env = os.environ if env is None else env
    try:
        prom, misconfigured = prom_client_from_env(env), False
    except ValueError:
        prom, misconfigured = None, True
    return build_voice_console(
        prom=prom,
        controls=controls,
        pending=pending,
        now=now,
        prom_misconfigured=misconfigured,
    )
