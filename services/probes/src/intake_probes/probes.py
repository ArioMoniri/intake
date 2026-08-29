"""Probe implementations — small functions over injected clients (INT-022).

Every probe takes the client, socket or callable it needs as an argument, so
the unit lane never touches docker; the dev runner composes the real clients
in :func:`intake_probes.runner.build_dev_clients`. A probe reports — it never
raises into the caller: failure is a :class:`Failed` outcome with the cause.
"""

from __future__ import annotations

import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from cryptography import x509

__all__ = [
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
    "openbao_seal_status",
    "postgres_select1",
    "redis_ping",
    "tcp_connect",
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


def livekit_room_join() -> Outcome:
    """The room-join probe cannot exist before the LiveKit dev tier does.

    INT-090 lands the LiveKit server+TURN tier this probe must join; probing
    a server that does not exist would mean faking a result, and invariant 17
    forbids fakes outside tests. Until then the runner carries this typed
    Skipped status — visible in every probe sweep, never counted healthy.
    """
    return Skipped(reason="livekit lands with INT-090")
