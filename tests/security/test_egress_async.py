"""INT-329 — the async twin of the INT-018 guarded transport is the same enforcer.

The OTP route is async, and a vendor call inside it must not block the event
loop (audit 2026-09-26 F13). ADR-025 forbids a second implementation of the
egress decision, so the async transport does not have one: it runs the SAME
admission step the sync transport runs — allow-list, purpose, data class,
resolve once, refuse a denied range, pin, write one transfer record — and only
the final send is awaited. The admission step runs in a worker thread because
resolution is a blocking ``getaddrinfo``.

These tests re-prove the INT-018 negatives through the async path, and a parity
table decides the same requests through both transports. Everything runs over
``httpx.MockTransport`` with an injected resolver: no socket, no DNS.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx
import intake_platform.egress as egress
import pytest
from intake_platform.egress import (
    AllowlistEntry,
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    InMemoryTransferLog,
)
from prometheus_client import REGISTRY

PUBLIC_ANSWER = "203.0.113.10"
PACKAGES = EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.NON_PERSONAL)
PYPI = AllowlistEntry(
    name="pypi",
    host="pypi.org",
    port=443,
    protocol="https",
    purpose_id=EgressPurpose.PACKAGE_REGISTRY,
    purpose="Python package index metadata",
    basis="no-personal-data",
)


class Resolver:
    """A table resolver that records each lookup and the thread it ran on."""

    def __init__(self, answers: dict[str, list[str]] | None = None) -> None:
        self.answers = answers if answers is not None else {"pypi.org": [PUBLIC_ANSWER]}
        self.calls: list[tuple[str, int]] = []
        self.threads: list[int] = []

    def __call__(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        self.threads.append(threading.get_ident())
        return tuple(self.answers[host])


class Inner:
    """An async inner transport that records what reached it."""

    def __init__(self, response: httpx.Response | None = None) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response if self.response is not None else httpx.Response(200, json={})

    def transport(self) -> httpx.MockTransport:
        inner = httpx.MockTransport(self.handle)
        original = inner.aclose

        async def aclose() -> None:
            self.closed = True
            await original()

        inner.aclose = aclose  # type: ignore[method-assign]
        return inner


def _client(
    resolver: Resolver,
    inner: Inner,
    context: EgressContext = PACKAGES,
    log: InMemoryTransferLog | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    policy = EgressPolicy([PYPI], "dev", resolver=resolver)
    return egress.guarded_async_client(
        policy,
        context,
        inner=inner.transport(),
        transfer_log=log if log is not None else InMemoryTransferLog(),
        **kwargs,
    )


def _denied_total() -> float:
    value = REGISTRY.get_sample_value("sec_egress_denied_total")
    return 0.0 if value is None else value


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    async with client:
        return await client.get(url)


def test_an_allowed_host_is_pinned_and_recorded() -> None:
    resolver, inner, log = Resolver(), Inner(), InMemoryTransferLog()
    response = asyncio.run(_get(_client(resolver, inner, log=log), "https://pypi.org/simple/"))
    assert response.status_code == 200
    [sent] = inner.requests
    assert sent.url.host == PUBLIC_ANSWER
    assert sent.headers["host"] == "pypi.org"
    assert sent.extensions["sni_hostname"] == "pypi.org"
    assert resolver.calls == [("pypi.org", 443)]
    [record] = log.entries
    assert (record.decision, record.host, record.purpose, record.tier) == (
        "allow",
        "pypi.org",
        EgressPurpose.PACKAGE_REGISTRY,
        "dev",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/",
        "https://169.254.169.254/latest/meta-data/",
        "https://pypi.org:8443/",
    ],
)
def test_a_refused_destination_is_never_resolved_nor_sent(url: str) -> None:
    resolver, inner, log = Resolver(), Inner(), InMemoryTransferLog()
    before = _denied_total()
    with pytest.raises(EgressDenied):
        asyncio.run(_get(_client(resolver, inner, log=log), url))
    assert resolver.calls == [], "a refused name must not become a DNS query"
    assert inner.requests == []
    assert _denied_total() == before + 1
    [record] = log.entries
    assert (record.decision, record.bytes_out) == ("deny", 0)


def test_a_name_resolving_into_a_denied_range_is_refused() -> None:
    resolver, inner = Resolver({"pypi.org": ["127.0.0.1"]}), Inner()
    with pytest.raises(EgressDenied, match="denied range"):
        asyncio.run(_get(_client(resolver, inner), "https://pypi.org/"))
    assert inner.requests == []


@pytest.mark.parametrize(
    "context",
    [
        EgressContext(purpose=EgressPurpose.MODEL_WEIGHTS, data_class=DataClass.NON_PERSONAL),
        EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.PHI),
        EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.PSEUDONYMOUS),
    ],
    ids=["wrong-purpose", "phi", "pseudonymous"],
)
def test_the_right_host_for_the_wrong_reason_is_refused(context: EgressContext) -> None:
    resolver, inner = Resolver(), Inner()
    with pytest.raises(EgressDenied):
        asyncio.run(_get(_client(resolver, inner, context), "https://pypi.org/"))
    assert inner.requests == []


def test_a_personal_data_transport_cannot_delegate_its_pin_to_the_proxy() -> None:
    policy = EgressPolicy([PYPI], "dev", resolver=Resolver())
    context = EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.PHI)
    with pytest.raises(ValueError, match="cannot delegate its pin"):
        egress.guarded_async_transport(policy, context, proxy="http://egress-proxy:3128")


def test_redirects_are_off_by_default_and_every_hop_is_checked_when_on() -> None:
    redirect = httpx.Response(302, headers={"location": "https://evil.example/"})
    inner = Inner(redirect)
    response = asyncio.run(_get(_client(Resolver(), inner), "https://pypi.org/"))
    assert response.status_code == 302, "a redirect is a destination the caller never named"
    with pytest.raises(EgressDenied):
        asyncio.run(
            _get(_client(Resolver(), Inner(redirect), follow_redirects=True), "https://pypi.org/")
        )


def test_resolution_runs_off_the_event_loop_thread() -> None:
    """``getaddrinfo`` blocks; the admission step runs in a worker thread so the
    loop keeps serving other requests while a vendor host is resolved."""
    resolver = Resolver()

    async def scenario() -> int:
        loop_thread = threading.get_ident()
        await _get(_client(resolver, Inner()), "https://pypi.org/")
        return loop_thread

    loop_thread = asyncio.run(scenario())
    assert resolver.threads and all(thread != loop_thread for thread in resolver.threads)


def test_closing_the_client_closes_the_inner_transport() -> None:
    inner = Inner()
    asyncio.run(_get(_client(Resolver(), inner), "https://pypi.org/"))
    assert inner.closed


PARITY: list[tuple[str, EgressContext]] = [
    ("https://pypi.org/simple/", PACKAGES),
    ("https://evil.example/", PACKAGES),
    ("https://10.0.0.1/", PACKAGES),
    ("https://pypi.org/", EgressContext(EgressPurpose.MODEL_WEIGHTS, DataClass.NON_PERSONAL)),
    ("https://pypi.org/", EgressContext(EgressPurpose.PACKAGE_REGISTRY, DataClass.PHI)),
]


@pytest.mark.parametrize(("url", "context"), PARITY)
def test_both_transports_reach_the_same_decision(url: str, context: EgressContext) -> None:
    """One enforcer: the sync and async transports record identical decisions."""
    sync_log, async_log = InMemoryTransferLog(), InMemoryTransferLog()
    policy = EgressPolicy([PYPI], "dev", resolver=Resolver())
    sync_transport = egress.guarded_transport(
        policy,
        context,
        inner=httpx.MockTransport(lambda r: httpx.Response(200)),
        transfer_log=sync_log,
    )
    with httpx.Client(transport=sync_transport) as client:
        try:
            client.get(url)
        except EgressDenied:
            pass
    try:
        asyncio.run(_get(_client(Resolver(), Inner(), context, async_log), url))
    except EgressDenied:
        pass
    [sync_record], [async_record] = sync_log.entries, async_log.entries
    for field in ("decision", "reason", "host", "port", "purpose", "data_class", "tier"):
        assert getattr(sync_record, field) == getattr(async_record, field), field
