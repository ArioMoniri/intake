"""The probe runner: one pure sweep + the 60 s loop shell (INT-022).

`run_probes_once` is the tested loop body: registry rows × injected clients →
typed results, each stamped with the instant its probe started (INT-181: the
reliability console shows every probe's last result AND its age, and flags a
result older than three sweeps as stale rather than current).
`build_dev_clients` composes the real dev-tier clients (DB, Redis, MinIO, HAPI,
OpenBao seal, backup freshness, the deid artefact, the LiveKit typed-Skipped
probe, and — when their env targets exist — the LLM health endpoint and the
TLS edge). `main` is the thin scheduler shell that loops with
sleep(SWEEP_INTERVAL_S); the deployment issues wire it into systemd/compose.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from os import environ
from pathlib import Path
from typing import Final

import httpx
from intake_platform.ci import CiPolicyError, RunnerPools, load_runner_pools

from intake_probes import probes
from intake_probes.probes import Failed, Outcome, Skipped, SupportsPing
from intake_probes.registry import Registry, load_registry

__all__ = [
    "SWEEP_INTERVAL_S",
    "DevProbeConfig",
    "ProbeFn",
    "ProbeResult",
    "ProbeStatus",
    "build_dev_clients",
    "main",
    "run_probes_once",
]

ProbeFn = Callable[[], Outcome]

_DEFAULT_REGISTRY = Path("observability") / "registry.yaml"
_DEFAULT_RUNNER_POOLS = Path("infra") / "ci" / "runners.yaml"
_HTTP_TIMEOUT_S = 5.0
#: files/10 §6: "services/probes exercises every model and service every 60 s".
#: The scheduler shell sleeps this long; the console derives staleness from it.
SWEEP_INTERVAL_S: Final = 60


class ProbeStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ProbeResult:
    component: str
    probe: str
    status: ProbeStatus
    latency_ms: float | None
    detail: str
    #: when this probe started (UTC); ``None`` only for a result built by hand
    checked_at: datetime | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "component": self.component,
            "probe": self.probe,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "checked_at": (
                None
                if self.checked_at is None
                else self.checked_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_probes_once(
    registry: Registry,
    clients: Mapping[str, ProbeFn],
    clock: Callable[[], float] = time.perf_counter,
    now: Callable[[], datetime] = _utc_now,
) -> list[ProbeResult]:
    """One sweep over the registry — pure over its inputs, never raises.

    ``clock`` measures latency (monotonic); ``now`` stamps each result with the
    wall-clock instant its probe started, so a reader can tell a result from
    this sweep from one three sweeps old.
    """
    results: list[ProbeResult] = []
    for entry in registry:
        checked_at = now()
        fn = clients.get(entry.component)
        if fn is None:
            results.append(
                ProbeResult(
                    component=entry.component,
                    probe=entry.probe.value,
                    status=ProbeStatus.SKIPPED,
                    latency_ms=None,
                    detail=f"no probe client configured for {entry.component} in this environment",
                    checked_at=checked_at,
                )
            )
            continue
        started = clock()
        try:
            outcome: Outcome = fn()
        except Exception as err:  # a probe reports, it never takes the sweep down
            outcome = Failed(f"probe raised: {err}")
        latency_ms = (clock() - started) * 1000.0
        results.append(
            _to_result(
                entry.component, entry.probe.value, entry.budget_ms, outcome, latency_ms, checked_at
            )
        )
    return results


def _to_result(
    component: str,
    probe: str,
    budget_ms: int,
    outcome: Outcome,
    latency_ms: float,
    checked_at: datetime,
) -> ProbeResult:
    if isinstance(outcome, Skipped):
        return ProbeResult(component, probe, ProbeStatus.SKIPPED, None, outcome.reason, checked_at)
    if isinstance(outcome, Failed):
        return ProbeResult(
            component, probe, ProbeStatus.UNHEALTHY, latency_ms, outcome.detail, checked_at
        )
    if latency_ms > budget_ms:
        return ProbeResult(
            component,
            probe,
            ProbeStatus.UNHEALTHY,
            latency_ms,
            f"healthy but over budget: {latency_ms:.0f}ms > {budget_ms}ms",
            checked_at,
        )
    return ProbeResult(
        component, probe, ProbeStatus.HEALTHY, latency_ms, outcome.detail, checked_at
    )


# --- dev client composition -----------------------------------------------------------


@dataclass(frozen=True)
class DevProbeConfig:
    """Everything the dev wiring may need — injectable so tests stay docker-free."""

    env: Mapping[str, str] = field(default_factory=lambda: dict(environ))
    http_transport: httpx.BaseTransport | None = None
    redis_client: SupportsPing | None = None
    postgres_select1: Callable[[], int] | None = None
    http_timeout_s: float = _HTTP_TIMEOUT_S


def build_dev_clients(registry: Registry, config: DevProbeConfig) -> dict[str, ProbeFn]:
    """Wire the real dev checks for every registry row this environment can reach.

    Rows with nothing to probe here (no daemon, not deployed, no service yet)
    get no client and surface as SKIPPED in every sweep — visible, not faked.
    """
    env = config.env
    http_client = httpx.Client(transport=config.http_transport, timeout=config.http_timeout_s)

    wiring: dict[str, ProbeFn] = {
        "postgres": partial(
            probes.postgres_select1, config.postgres_select1 or _psycopg_select1(env)
        ),
        "redis": partial(probes.redis_ping, config.redis_client or _redis_client(env)),
        "minio": partial(
            probes.minio_ready, http_client, env.get("INTAKE_MINIO_URL", "http://127.0.0.1:9000")
        ),
        "hapi": partial(
            probes.http_health,
            http_client,
            env.get("INTAKE_HAPI_URL", "http://127.0.0.1:8091/fhir/metadata"),
        ),
        "openbao": partial(
            probes.openbao_seal_status,
            http_client,
            env.get("OPENBAO_ADDR", "http://127.0.0.1:8200"),
        ),
        "backups": partial(
            probes.backup_freshness,
            Path(env.get("INTAKE_BACKUP_DIR", ".cache/backups")),
            float(env.get("INTAKE_BACKUP_MAX_AGE_S", "86400")),
        ),
        "deid-tr-ner-v1": partial(
            probes.backup_freshness,
            Path(env.get("INTAKE_DEID_MODEL_DIR", ".cache/deid-tr-ner-v1")),
            None,
        ),
        "voice-runtime": probes.livekit_room_join,
        # INT-206: the CI row. The pool file is committed and always readable;
        # with zero pools declared this reports HB-I7/HB-I5 as a typed Skipped,
        # which is the honest state and never counts healthy. Heartbeats arrive
        # from the runners themselves once a pool exists, so the sweep passes an
        # empty map until there is a collector to read.
        "ci-runners": partial(
            probes.runner_heartbeat,
            _runner_pools(env),
            {},
        ),
    }

    llm_health_url = env.get("INTAKE_LLM_HEALTH_URL", "")
    if llm_health_url:
        wiring["qwen3.5-9b"] = partial(probes.http_health, http_client, llm_health_url)

    # INT-175: the Langfuse tier lives in its own compose file and is not part
    # of `make dev`, so it is wired only where its target exists — otherwise
    # both rows surface as SKIPPED in every sweep, which is the honest state.
    langfuse_health_url = env.get("INTAKE_LANGFUSE_HEALTH_URL", "")
    if langfuse_health_url:
        wiring["langfuse"] = partial(probes.http_health, http_client, langfuse_health_url)
        wiring["langfuse-clickhouse"] = partial(
            probes.http_health,
            http_client,
            env.get("INTAKE_LANGFUSE_CLICKHOUSE_URL", "http://127.0.0.1:8123/ping"),
        )

    # INT-032: the openEHR CDR sits behind the compose `export` profile and no
    # deployment runs it (registry row self_hosted_now: false), so it is wired
    # on the same terms as Langfuse — only where a target has been named, and
    # SKIPPED rather than FAILED everywhere else.
    ehrbase_health_url = env.get("INTAKE_EHRBASE_HEALTH_URL", "")
    if ehrbase_health_url:
        wiring["ehrbase"] = partial(probes.http_health, http_client, ehrbase_health_url)
    # INT-205: the same shape for the SIEM tier. Falco's embedded webserver is
    # the only endpoint in that tier that answers without a credential — the
    # Wazuh manager API returns 401 and the indexer wants TLS plus a password —
    # so it is the only one wired here. The two Wazuh rows carry `tcp_connect`
    # and stay SKIPPED until a sweep runs somewhere the tier is up.
    falco_health_url = env.get("INTAKE_FALCO_HEALTH_URL", "")
    if falco_health_url:
        wiring["falco"] = partial(probes.http_health, http_client, falco_health_url)

    tls_target = env.get("INTAKE_TLS_PROBE_TARGET", "")
    if tls_target:
        host, _, port = tls_target.partition(":")
        min_days = int(env.get("INTAKE_TLS_MIN_DAYS", "14"))
        wiring["edge-tls"] = partial(
            probes.cert_expiry_days,
            partial(probes.fetch_tls_not_after, host, int(port or "443")),
            min_days,
        )

    known = {entry.component for entry in registry}
    return {component: fn for component, fn in wiring.items() if component in known}


def _runner_pools(env: Mapping[str, str]) -> RunnerPools:
    """The declared self-hosted CI runner pools (INT-206).

    An unreadable or absent pool file is reported as "no pools", not raised:
    a probe reports. The policy gate (`make ci-policy`) is where a malformed
    pool file fails the build.
    """
    path = Path(env.get("INTAKE_CI_RUNNERS_FILE", str(_DEFAULT_RUNNER_POOLS)))
    try:
        return load_runner_pools(path)
    except CiPolicyError:
        return RunnerPools()


def _redis_client(env: Mapping[str, str]) -> SupportsPing:
    import redis

    client: SupportsPing = redis.Redis.from_url(
        env.get("INTAKE_REDIS_URL", "redis://127.0.0.1:6379/0"), socket_timeout=2
    )
    return client


def _psycopg_select1(env: Mapping[str, str]) -> Callable[[], int]:
    def select1() -> int:
        try:
            import psycopg
        except ImportError as err:  # pragma: no cover — dev boxes install the extra
            raise RuntimeError(
                "psycopg is not installed — the dev runner needs `intake-probes[runner]`; "
                "the unit lane injects a callable instead"
            ) from err
        conninfo = (
            f"host={env.get('POSTGRES_HOST', '127.0.0.1')} "
            f"port={env.get('POSTGRES_PORT', '5432')} "
            f"dbname={env.get('POSTGRES_DB', 'intake')} "
            f"user={env.get('POSTGRES_USER', 'intake')} "
            f"password={env.get('POSTGRES_PASSWORD', 'intake-dev-only')}"
        )
        with psycopg.connect(conninfo, connect_timeout=2) as conn:
            row = conn.execute("SELECT 1").fetchone()
        return int(row[0]) if row else 0

    return select1


# --- the scheduler shell ---------------------------------------------------------------


def _write_results(results: list[ProbeResult], out: Path | None) -> None:
    payload = json.dumps([result.to_json() for result in results], indent=2)
    if out is None:
        sys.stdout.write(payload + "\n")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="INTAKE synthetic probe runner (INT-022)")
    parser.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=None, help="write results JSON here")
    parser.add_argument(
        "--once", action="store_true", help="one sweep and exit (the release gate's input)"
    )
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    clients = build_dev_clients(registry, DevProbeConfig())

    results = run_probes_once(registry, clients)
    _write_results(results, args.out)
    if args.once:
        return 0

    while True:  # pragma: no cover — the 60 s scheduler shell; the body is tested above
        time.sleep(SWEEP_INTERVAL_S)
        results = run_probes_once(registry, clients)
        _write_results(results, args.out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
