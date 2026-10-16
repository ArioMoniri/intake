"""Probe implementations — small functions over injected clients (INT-022).

Every probe takes the client, socket or callable it needs as an argument, so
the unit lane never touches docker; the dev runner composes the real clients
in :func:`intake_probes.runner.build_dev_clients`. A probe reports — it never
raises into the caller: failure is a :class:`Failed` outcome with the cause.
"""

from __future__ import annotations

import re
import socket
import ssl
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from cryptography import x509
from intake_platform.ci import RunnerPools, evaluate_heartbeats
from intake_platform.room_tokens import LiveKitCredentials, mint_room_token

__all__ = [
    "PROBE_IDENTITY",
    "PROBE_ROOM_SESSION",
    "Failed",
    "Ok",
    "Outcome",
    "Skipped",
    "SupportsPing",
    "backup_freshness",
    "cert_expiry_days",
    "fetch_tls_not_after",
    "http_health",
    "livekit_room_join",
    "minio_ready",
    "model_not_served",
    "openbao_seal_status",
    "postgres_select1",
    "redis_ping",
    "runner_heartbeat",
    "target_absent",
    "tcp_connect",
    "voice_synthetic_turn",
]


@dataclass(frozen=True)
class Ok:
    detail: str = "ok"


@dataclass(frozen=True)
class Failed:
    detail: str


@dataclass(frozen=True)
class Skipped:
    """A probe that cannot run here yet — a real status, never a fake result."""

    reason: str


Outcome = Ok | Failed | Skipped


class SupportsPing(Protocol):
    """The one method the redis probe needs — satisfied by redis-py and fakeredis."""

    def ping(self) -> bool: ...


# --- network reachability -----------------------------------------------------------


def tcp_connect(dial: Callable[[], None]) -> Outcome:
    """`dial` opens and closes one TCP connection, raising OSError on failure."""
    try:
        dial()
    except OSError as err:
        return Failed(f"tcp connect failed: {err}")
    return Ok("connected")


def http_health(client: httpx.Client, url: str) -> Outcome:
    """GET `url` expecting 200."""
    try:
        response = client.get(url)
    except httpx.HTTPError as err:
        return Failed(f"http request failed: {err}")
    if response.status_code != 200:
        return Failed(f"expected 200, got {response.status_code}")
    return Ok("200")


# --- the dev-tier services ----------------------------------------------------------


def postgres_select1(select1: Callable[[], int]) -> Outcome:
    """`select1` runs SELECT 1 and returns the scalar — a driver-free seam."""
    try:
        value = select1()
    except Exception as err:  # the injected callable owns its failure modes
        return Failed(f"select 1 failed: {err}")
    if value != 1:
        return Failed(f"SELECT 1 returned {value!r}")
    return Ok("select 1")


def redis_ping(client: SupportsPing) -> Outcome:
    try:
        alive = client.ping()
    except Exception as err:  # redis-py raises its own hierarchy
        return Failed(f"redis ping failed: {err}")
    if not alive:
        return Failed("redis ping returned a falsy reply")
    return Ok("pong")


def minio_ready(client: httpx.Client, base_url: str) -> Outcome:
    """MinIO's own readiness contract: GET /minio/health/ready expecting 200."""
    return http_health(client, f"{base_url.rstrip('/')}/minio/health/ready")


def openbao_seal_status(client: httpx.Client, base_url: str) -> Outcome:
    """GET /v1/sys/seal-status expecting 200 with sealed: false."""
    url = f"{base_url.rstrip('/')}/v1/sys/seal-status"
    try:
        response = client.get(url)
    except httpx.HTTPError as err:
        return Failed(f"http request failed: {err}")
    if response.status_code != 200:
        return Failed(f"expected 200, got {response.status_code}")
    try:
        sealed = bool(response.json()["sealed"])
    except (KeyError, ValueError) as err:
        return Failed(f"seal-status body unreadable: {err}")
    if sealed:
        return Failed("openbao is sealed")
    return Ok("unsealed")


# --- certificates ---------------------------------------------------------------------


def fetch_tls_not_after(host: str, port: int, timeout_s: float = 5.0) -> datetime:
    """Read the peer certificate's notAfter over a real TLS handshake.

    Verification is off on purpose: an expiry probe must read even an
    untrusted or already-expired certificate — refusing the handshake would
    blind the probe exactly when it matters.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout_s) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if der is None:
        raise ssl.SSLError("peer presented no certificate")
    certificate = x509.load_der_x509_certificate(der)
    return certificate.not_valid_after_utc


def cert_expiry_days(
    not_after: Callable[[], datetime],
    min_days: int,
    now: Callable[[], datetime] | None = None,
) -> Outcome:
    """Healthy while the certificate keeps at least `min_days` of validity."""
    current = (now or (lambda: datetime.now(UTC)))()
    try:
        expires = not_after()
    except (OSError, ssl.SSLError, ValueError) as err:
        return Failed(f"certificate unreadable: {err}")
    days_left = (expires - current).total_seconds() / 86400
    if days_left < min_days:
        return Failed(f"certificate expires in {days_left:.1f} days (< {min_days})")
    return Ok(f"certificate valid for {days_left:.0f} more days")


# --- artefacts ------------------------------------------------------------------------


def backup_freshness(
    path: Path,
    max_age_s: float | None,
    now: Callable[[], float] | None = None,
) -> Outcome:
    """Newest file under `path` must exist and, when bounded, be young enough.

    `max_age_s=None` turns this into a pure presence check — the shape used
    for pinned model artefacts, whose mtime is install time, not health.
    """
    if not path.is_dir():
        return Failed(f"no artefact directory at {path}")
    newest: float | None = None
    for candidate in path.rglob("*"):
        if candidate.is_file():
            mtime = candidate.stat().st_mtime
            newest = mtime if newest is None else max(newest, mtime)
    if newest is None:
        return Failed(f"no artefacts under {path}")
    if max_age_s is None:
        return Ok("artefact present")
    age = (now or time.time)() - newest
    if age > max_age_s:
        return Failed(f"newest artefact is {age:.0f}s old (> {max_age_s:.0f}s)")
    return Ok(f"newest artefact is {age:.0f}s old")


# --- voice ----------------------------------------------------------------------------

#: INT-515: the probe's own room, ``intake-<this>``. A fixed id that no visit
#: can have (version-4 shape, all-zero high bits), so the probe never lands in
#: a patient's room and a sweep always validates the same name.
PROBE_ROOM_SESSION = "00000000-0000-4000-8000-000000000515"
#: The probe participant's identity: an id, never a person.
PROBE_IDENTITY = "probe"
#: The probe's token lives a minute; it is minted for one request.
_PROBE_TOKEN_TTL_S = 60
#: Stage codes the runtime reports are closed; only id-shaped ones are repeated.
_CODE_SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def target_absent(reason: str) -> Outcome:
    """INT-515: a row whose target this environment does not name says which
    variable would name it — a typed Skipped, never counted healthy."""
    return Skipped(reason=reason)


def livekit_room_join(
    client: httpx.Client,
    base_url: str,
    credentials: LiveKitCredentials,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> Outcome:
    """The signalling half of a room join: LiveKit's own ``/rtc/validate``.

    A probe participant's token for the probe room — INT-090's grant, one
    minute — sent as a bearer header (never in the URL, which would put a
    credential in any access log on the way). LiveKit answers 200 when the
    token is valid and the join would be admitted. No media and no WebRTC
    stack are needed, which is what lets a sweep run it every minute.
    """
    token = mint_room_token(
        PROBE_ROOM_SESSION, PROBE_IDENTITY, now(), credentials=credentials, ttl_s=_PROBE_TOKEN_TTL_S
    )
    try:
        response = client.get(
            f"{base_url.rstrip('/')}/rtc/validate", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.HTTPError as err:
        return Failed(f"http request failed: {type(err).__name__}")
    if response.status_code != 200:
        # the status is the diagnosis; the body can echo the token's claims
        return Failed(f"join validation answered {response.status_code}")
    return Ok("room join validated")


def voice_synthetic_turn(client: httpx.Client, url: str) -> Outcome:
    """INT-515: ask the voice runtime to run one scripted synthetic turn.

    The runtime runs it on its own bound lanes and answers ids and timings
    (``intake_voice_runtime.synthetic_turn``). 200 with a completed report is
    healthy; a stopped turn is a failure naming its stage and code; the
    runtime's rate limit (one turn per 30 s, so a sweep cannot run up a vendor
    bill) is a typed Skipped, never counted healthy.
    """
    try:
        response = client.post(url)
    except httpx.HTTPError as err:
        return Failed(f"http request failed: {type(err).__name__}")
    if response.status_code == 429:
        return Skipped(reason="rate limited: a turn ran within the last 30 s")
    try:
        report = response.json()
    except ValueError:
        return Failed(f"the runtime answered {response.status_code} without a report")
    stages = report.get("stages") if isinstance(report, dict) else None
    if not isinstance(stages, list):
        return Failed(f"the runtime answered {response.status_code} without a report")
    if response.status_code == 200 and report.get("completed") is True and stages:
        total = sum(float(stage.get("latency_ms", 0.0)) for stage in stages)
        return Ok(f"turn completed in {total:.0f} ms")
    stopped = next((s for s in stages if isinstance(s, dict) and not s.get("ok")), None)
    if stopped is None:
        return Failed(f"the runtime answered {response.status_code} with no completed turn")
    stage = str(stopped.get("stage", ""))
    code = str(stopped.get("code", ""))
    stage = stage if _CODE_SHAPE.fullmatch(stage) else "unrecognised"
    code = code if _CODE_SHAPE.fullmatch(code) else "unrecognised"
    return Failed(f"turn stopped at {stage}: {code}")


# --- models ---------------------------------------------------------------------------


def model_not_served(what: str) -> Outcome:
    """A pinned model that no host serves reports so, and is never healthy.

    INT-124: files/03 §4.9.1 row 9 is pinned and licence-verified in the
    registry and runs nowhere yet. There is no endpoint to probe, and probing
    a guessed one would be a fake result (invariant 17), so the outcome is a
    typed Skipped that says *unavailable* and names what serves it.
    """
    return Skipped(reason=f"unavailable: {what}")


# --- ci -------------------------------------------------------------------------------


def runner_heartbeat(
    pools: RunnerPools, seen: Mapping[str, float], now: float | None = None
) -> Outcome:
    """The self-hosting registry's CI probe (files/08 §6: "runner heartbeat").

    `seen` maps a pool label to the epoch time of its last heartbeat; the
    caller owns how it collected them, which keeps this decision testable with
    a fake clock. With no pool declared the outcome is Skipped and names
    HB-I7 — an empty set reported healthy is how a monitor tells you a service
    is fine when it does not exist.
    """
    report = evaluate_heartbeats(pools, seen, time.time() if now is None else now)
    if not report.checked:
        return Skipped(reason=report.detail)
    if report.healthy:
        return Ok(report.detail)
    return Failed(report.detail)
