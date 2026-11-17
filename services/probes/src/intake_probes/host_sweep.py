"""The probes service's sweep of the host it runs on (INT-560).

:func:`~intake_probes.runner.build_dev_clients` wires the dev tier on loopback
ports. A deployed host is different: its components sit behind compose names
on internal networks, and the inventory (:mod:`intake_probes.inventory`) says
which ones this host runs. :func:`build_host_clients` wires exactly that:

- a component the host runs is probed at the inventory's compose name, with
  the registry row's own probe id, so the page's *probe* column names what
  actually ran;
- a component the host does not run gets a typed ``skipped`` that names the
  host — every registry row has a result every sweep, and none is silent;
- a deployed component the probes service cannot reach (the egress proxy)
  is a ``skipped`` that names why.

**Credentials are the probe's own, least-privilege, from the environment.**
Postgres is probed as ``svc_probe`` (LOGIN and CONNECT, no table grant) and
Redis as ``intake-probe`` (PING only); the passwords arrive as
:data:`ENV_POSTGRES_PASSWORD` and :data:`ENV_REDIS_PASSWORD`, never from the
committed inventory. A missing one is a ``skipped`` that names the variable —
never a ``healthy`` and never a guess.

**What leaves the sweep is scrubbed (invariant 6).** A probe target is
infrastructure and never carries a patient's data, but a failure text is
whatever a server or a library chose to say. :func:`scrub_detail` masks
anything identifier-shaped (TCKN, phone, IBAN), every email address and every
credential inside a URL, and caps the length before the text reaches the
results file. Metric labels are registry component ids, nothing else.

**The results file is replaced atomically.** :func:`write_sweep` writes beside
the target and renames over it, so the API never reads half a sweep.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import httpx
from intake_platform.redaction import redact_text
from prometheus_client import Gauge, Histogram

from intake_probes import probes
from intake_probes.inventory import HostInventory, InventoryComponent
from intake_probes.probes import Outcome, Skipped, SupportsPing
from intake_probes.registry import ProbeId, Registry
from intake_probes.runner import (
    SWEEP_INTERVAL_S,
    ProbeFn,
    ProbeResult,
    ProbeStatus,
    run_probes_once,
)

__all__ = [
    "ENV_POSTGRES_PASSWORD",
    "ENV_REDIS_PASSWORD",
    "ENV_TLS_SERVER_NAME",
    "HostProbeConfig",
    "PostgresTarget",
    "RedisTarget",
    "build_host_clients",
    "record_metrics",
    "run_host_sweeps",
    "scrub_detail",
    "sweep_host_once",
    "write_sweep",
]

logger = logging.getLogger("intake_probes.host_sweep")

ENV_POSTGRES_PASSWORD: Final = "INTAKE_PROBE_POSTGRES_PASSWORD"  # noqa: S105 — a variable name
ENV_REDIS_PASSWORD: Final = "INTAKE_PROBE_REDIS_PASSWORD"  # noqa: S105 — a variable name
#: The public name the edge's certificate is issued for (STAGING_HOSTNAME).
ENV_TLS_SERVER_NAME: Final = "INTAKE_PROBE_TLS_SERVER_NAME"

_HTTP_TIMEOUT_S: Final = 5.0
_CONNECT_TIMEOUT_S: Final = 2.0
#: files/10 §6 — a certificate with fewer days left than this is a finding.
_TLS_MIN_DAYS: Final = 14
_DETAIL_MAX: Final = 240

# --- the series the sweep emits (observability/metrics_catalog.yaml) -----------------

#: 1 healthy, 0 not; absent when the component was not probed this sweep.
PROBE_STATUS: Final = Gauge(
    "probe_status", "Synthetic probe status by component (1 = healthy).", ["component"]
)
PROBE_LATENCY_MS: Final = Histogram(
    "probe_latency_ms",
    "Synthetic probe latency by component, in milliseconds.",
    ["component"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)


@dataclass(frozen=True)
class PostgresTarget:
    host: str
    port: int
    user: str
    dbname: str


@dataclass(frozen=True)
class RedisTarget:
    host: str
    port: int
    username: str
    db: int


def _psycopg_select1(target: PostgresTarget, password: str) -> Callable[[], int]:
    def select1() -> int:
        import psycopg

        with psycopg.connect(
            host=target.host,
            port=target.port,
            dbname=target.dbname,
            user=target.user,
            password=password,
            connect_timeout=int(_CONNECT_TIMEOUT_S),
        ) as conn:
            row = conn.execute("SELECT 1").fetchone()
        return int(row[0]) if row else 0

    return select1


def _redis_client(target: RedisTarget, password: str) -> SupportsPing:
    import redis

    client: SupportsPing = redis.Redis(
        host=target.host,
        port=target.port,
        db=target.db,
        username=target.username,
        password=password,
        socket_timeout=_CONNECT_TIMEOUT_S,
        socket_connect_timeout=_CONNECT_TIMEOUT_S,
    )
    return client


def _dial(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT_S):
        return


def _tls_not_after(host: str, port: int, server_name: str) -> datetime:
    return probes.fetch_tls_not_after(host, port, server_name=server_name)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class HostProbeConfig:
    """Everything the host wiring dials through — injectable, so no test opens a socket."""

    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    http_transport: httpx.BaseTransport | None = None
    postgres_select1: Callable[[PostgresTarget, str], Callable[[], int]] = _psycopg_select1
    redis_client: Callable[[RedisTarget, str], SupportsPing] = _redis_client
    dial: Callable[[str, int], None] = _dial
    tls_not_after: Callable[[str, int, str], datetime] = _tls_not_after
    now: Callable[[], datetime] = _utc_now
    http_timeout_s: float = _HTTP_TIMEOUT_S


def _skip(reason: str) -> Outcome:
    return Skipped(reason=reason)


def _credential(env: Mapping[str, str], variable: str) -> str | None:
    value = env.get(variable, "").strip()
    return value or None


def _wire(
    probe: ProbeId,
    placement: InventoryComponent,
    address: str,
    config: HostProbeConfig,
    http: httpx.Client,
) -> ProbeFn:
    """One deployed component's probe, dialling ``address``, its compose name."""
    host, port = placement.dial_host(), placement.dial_port() or 0
    if probe is ProbeId.HTTP_HEALTH:
        return partial(probes.http_health, http, address)
    if probe is ProbeId.MINIO_READY:
        return partial(probes.minio_ready, http, address)
    if probe is ProbeId.OPENBAO_SEAL_STATUS:
        return partial(probes.openbao_seal_status, http, address)
    if probe is ProbeId.TCP_CONNECT:
        return partial(probes.tcp_connect, partial(config.dial, host, port))
    if probe is ProbeId.POSTGRES_SELECT1:
        password = _credential(config.env, ENV_POSTGRES_PASSWORD)
        if password is None:
            return partial(_skip, f"no probe credential: {ENV_POSTGRES_PASSWORD} is unset")
        parts = urlsplit(address)
        database = PostgresTarget(host, port, parts.username or "", parts.path.lstrip("/"))
        return partial(probes.postgres_select1, config.postgres_select1(database, password))
    if probe is ProbeId.REDIS_PING:
        password = _credential(config.env, ENV_REDIS_PASSWORD)
        if password is None:
            return partial(_skip, f"no probe credential: {ENV_REDIS_PASSWORD} is unset")
        parts = urlsplit(address)
        db = parts.path.lstrip("/")
        store = RedisTarget(host, port, parts.username or "", int(db) if db.isdigit() else 0)
        return partial(probes.redis_ping, config.redis_client(store, password))
    if probe is ProbeId.CERT_EXPIRY_DAYS:
        server_name = _credential(config.env, ENV_TLS_SERVER_NAME)
        if server_name is None:
            return partial(_skip, f"no server name: {ENV_TLS_SERVER_NAME} is unset")
        return partial(
            probes.cert_expiry_days,
            partial(config.tls_not_after, host, port, server_name),
            _TLS_MIN_DAYS,
            config.now,
        )
    # load_host_inventory refuses a probe the host cannot run, so this is a
    # registry edit racing a running sweep: say so, never pretend
    return partial(_skip, f"probe {probe.value} has no host wiring")


def build_host_clients(
    registry: Registry, inventory: HostInventory, config: HostProbeConfig
) -> dict[str, ProbeFn]:
    """A client for every registry row: a probe, or a skip that says why."""
    http = httpx.Client(transport=config.http_transport, timeout=config.http_timeout_s)
    host = inventory.host_id
    clients: dict[str, ProbeFn] = {}
    for entry in registry:
        placement = inventory.placement(entry.component)
        if placement is None:
            clients[entry.component] = partial(_skip, f"not deployed on {host}")
        elif placement.probe_at is None:
            reason = placement.unprobed.value if placement.unprobed is not None else "unprobed"
            clients[entry.component] = partial(_skip, f"deployed on {host}; not probed: {reason}")
        else:
            clients[entry.component] = _wire(
                entry.probe, placement, placement.probe_at, config, http
            )
    return clients


# --- scrubbing, writing, metrics ----------------------------------------------------------

_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def scrub_detail(text: str) -> str:
    """A failure text with nothing identifier- or secret-shaped left in it."""
    text = _URL_USERINFO.sub(r"\1", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = redact_text(text)
    return text if len(text) <= _DETAIL_MAX else text[: _DETAIL_MAX - 1] + "…"


def sweep_host_once(
    registry: Registry,
    clients: Mapping[str, ProbeFn],
    now: Callable[[], datetime] = _utc_now,
    clock: Callable[[], float] = time.perf_counter,
) -> list[ProbeResult]:
    """One sweep, every detail scrubbed before it can be written anywhere."""
    return [
        ProbeResult(
            result.component,
            result.probe,
            result.status,
            result.latency_ms,
            scrub_detail(result.detail),
            result.checked_at,
        )
        for result in run_probes_once(registry, clients, clock=clock, now=now)
    ]


def write_sweep(results: list[ProbeResult], out: Path) -> None:
    """Replace ``out`` with this sweep, atomically (write beside it, then rename)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([result.to_json() for result in results], indent=2) + "\n"
    handle, temp = tempfile.mkstemp(prefix=".sweep-", suffix=".json", dir=out.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temp, out)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def record_metrics(results: list[ProbeResult]) -> None:
    """``probe_status`` / ``probe_latency_ms`` for what was probed; clear the rest."""
    for result in results:
        if result.status is ProbeStatus.SKIPPED:
            try:
                PROBE_STATUS.remove(result.component)
            except KeyError:
                pass
            continue
        PROBE_STATUS.labels(result.component).set(
            1.0 if result.status is ProbeStatus.HEALTHY else 0.0
        )
        if result.latency_ms is not None:
            PROBE_LATENCY_MS.labels(result.component).observe(result.latency_ms)


# --- the loop the probes app runs ---------------------------------------------------------


def _cycle(registry: Registry, clients: Mapping[str, ProbeFn], out: Path) -> None:
    try:
        results = sweep_host_once(registry, clients)
        write_sweep(results, out)
        record_metrics(results)
    except Exception as exc:  # noqa: BLE001 — a failed write is logged; the loop goes on
        logger.warning("host sweep not written (%s)", type(exc).__name__)


async def run_host_sweeps(
    registry: Registry,
    clients: Mapping[str, ProbeFn],
    out: Path,
    stop: asyncio.Event,
    interval_s: float = SWEEP_INTERVAL_S,
) -> None:
    """Sweep now, then every ``interval_s`` until ``stop`` is set. Off the event loop."""
    while not stop.is_set():
        await asyncio.to_thread(_cycle, registry, clients, out)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            continue
