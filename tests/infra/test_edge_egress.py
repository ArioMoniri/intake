"""INT-203 — the production egress proxy: the same control, one tier out.

files/10 §4 records this control's history and its defect: the allow-list *"did
not cover server-side fetches the console itself provokes"*, so a
``tenant_admin`` could name a destination our own server would then fetch from
inside the PHI network. INT-018 built the in-process guard and the dev proxy;
INT-160 added the tenant dimension; INT-161 added the SMART token endpoint —
*"the same egress bypass in a third form"*. This file is the fourth place the
same control has to hold, and it is deliberately **not** a fourth
implementation: every assertion below runs through ``intake_platform.egress``
and the one rendered proxy configuration, because a security control
implemented twice is one that will diverge.

The clauses under test are files/10 §4's own, in its words:

* *"the proxy denies literal IPs and private / link-local / metadata ranges"*;
* *"resolves once and pins, re-validating on connect"* — the DNS-rebinding
  clause, and the one that passes trivially if only registration is checked;
* *"disables redirects"*;
* egress denials are a hard alert (§7), which needs a metric that exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from intake_connectors.destinations import ConnectorDestination
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    InMemoryTransferLog,
    guarded_client,
    guarded_transport,
    load_allowlist,
)
from prometheus_client import REGISTRY

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"
SQUID_CONF = REPO / "infra" / "security" / "squid" / "squid.conf"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
PROD_COMPOSE = REPO / "infra" / "docker-compose.edge.yml"

PUSH = EgressContext(purpose=EgressPurpose.CLINICAL_RECORD_PUSH, data_class=DataClass.PHI)


def _destination(host: str = "fhir.hospital.example") -> ConnectorDestination:
    """One registered destination, in the only shape the registry accepts.

    There is no free-text URL anywhere in this constructor, which is the
    point: files/10 §4's answer to the console SSRF is that the box does not
    exist.
    """
    return ConnectorDestination(
        tenant_id="tenant-a",
        endpoint_id="fhir-primary",
        adapter_id="fhir_r4_push",
        host=host,
        port=443,
        protocol="https",
        base_path="/fhir",
        auth_mode="mtls",
        consent_scope="share.clinician.previsit",
        dpa_ref="DPA-2026-001",
        approval_ref="SEC-APPROVAL-2026-014",
        credential_ref="connectors/tenant-a/fhir-primary/token",
        client_cert_ref="connectors/tenant-a/fhir-primary/mtls",
        receiver_idempotency="honoured_per_dpa",
    )


def _policy(resolver: Any) -> EgressPolicy:
    return EgressPolicy(
        [_destination().egress_entry()], "connector:fhir-primary", resolver=resolver
    )


def _fixed(*addresses: str) -> Any:
    def resolve(host: str, port: int) -> Sequence[str]:
        return addresses

    return resolve


@pytest.fixture(autouse=True)
def _runtime_phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The INT-018 runtime double-gate, satisfied explicitly.

    A ``phi_allowed`` row denies unless an operator has also said so at
    runtime. Every test below is about a *different* layer — the range check,
    the rebinding re-validation, the redirect rule — so the outer gate is
    opened deliberately here rather than left to make each of them pass for
    the wrong reason. ``tests/security/test_egress_policy.py`` owns the gate
    itself.
    """
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


# --- a registered destination is reachable; nothing else is -------------------------


def test_egress_to_a_registered_destination_succeeds() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.host))
        return httpx.Response(201)

    with guarded_client(
        _policy(_fixed("203.0.113.10")),
        PUSH,
        inner=httpx.MockTransport(handler),
        transfer_log=InMemoryTransferLog(),
    ) as client:
        response = client.post("https://fhir.hospital.example/fhir/Bundle", content=b"{}")

    assert response.status_code == 201
    # The socket was aimed at the pinned address, not at the name: no second
    # lookup exists for a rebinding attack to win.
    assert seen == ["203.0.113.10"]


@pytest.mark.parametrize(
    ("host", "answer", "why"),
    [
        ("fhir.hospital.example", ("169.254.169.254",), "cloud metadata"),
        ("fhir.hospital.example", ("10.4.1.9",), "RFC 1918"),
        ("fhir.hospital.example", ("127.0.0.1",), "loopback"),
        ("fhir.hospital.example", ("::ffff:169.254.169.254",), "metadata in v6 clothing"),
        ("fhir.hospital.example", ("203.0.113.10", "192.168.1.5"), "a split answer"),
    ],
)
def test_a_destination_that_resolves_into_a_denied_range_is_refused(
    host: str, answer: tuple[str, ...], why: str
) -> None:
    authorization = _policy(_fixed(*answer)).authorize(host, 443, PUSH)
    assert not authorization.allowed, why
    assert authorization.pin is None


def test_a_literal_ip_never_becomes_a_destination_at_all() -> None:
    """Two layers, and the first one is the schema: there is no row a literal
    IP fits into, so the runtime check below is the second net rather than the
    only one."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _destination(host="169.254.169.254")

    decision = _policy(_fixed("203.0.113.10")).check("169.254.169.254", 443, PUSH)
    assert not decision.allowed
    assert "literal IP" in decision.reason


# --- the rebinding clause -----------------------------------------------------------


class _RebindingResolver:
    """Public at registration, ``127.0.0.1`` on connect.

    This is the shape files/10 §4 means by *"re-validating on connect"*. A
    guard that resolves when the destination is registered and trusts that
    answer later is defeated by a DNS record with a short TTL, and every test
    that only registers a destination passes against such a guard.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, host: str, port: int) -> Sequence[str]:
        self.calls += 1
        return ("203.0.113.10",) if self.calls == 1 else ("127.0.0.1",)


def test_a_host_that_rebinds_between_registration_and_connect_is_denied() -> None:
    resolver = _RebindingResolver()
    policy = _policy(resolver)

    registration = policy.authorize("fhir.hospital.example", 443, PUSH)
    assert registration.allowed, "the public answer must be accepted, or the test is vacuous"

    connect = policy.authorize("fhir.hospital.example", 443, PUSH)
    assert not connect.allowed
    assert "denied range" in connect.decision.reason


def test_every_request_resolves_again_rather_than_reusing_a_pin() -> None:
    """The property underneath the clause: the pin is authorised per request
    and never outlives it, so there is no cached answer to poison."""
    resolver = _RebindingResolver()
    log = InMemoryTransferLog()
    client = guarded_client(
        _policy(resolver),
        PUSH,
        inner=httpx.MockTransport(lambda request: httpx.Response(201)),
        transfer_log=log,
    )
    with client:
        assert client.post("https://fhir.hospital.example/fhir/Bundle").status_code == 201
        with pytest.raises(EgressDenied):
            client.post("https://fhir.hospital.example/fhir/Bundle")
    assert resolver.calls == 2
    assert [record.decision for record in log.entries] == ["allow", "deny"]


# --- redirects ----------------------------------------------------------------------


def test_a_redirect_to_a_non_allow_listed_host_is_not_followed() -> None:
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if request.url.host == "203.0.113.10":
            return httpx.Response(302, headers={"Location": "https://collector.example/drop"})
        raise AssertionError("the second hop must never reach the transport")

    log = InMemoryTransferLog()
    with guarded_client(
        _policy(_fixed("203.0.113.10")),
        PUSH,
        inner=httpx.MockTransport(handler),
        transfer_log=log,
    ) as client:
        response = client.post("https://fhir.hospital.example/fhir/Bundle")

    assert response.status_code == 302
    assert response.has_redirect_location, "the fixture must actually redirect"
    # One hop attempted, one transfer recorded: the 3xx is handed back to the
    # caller rather than acted on, so `collector.example` was never resolved,
    # never connected to and never logged as a destination.
    assert len(hops) == 1
    assert [record.host for record in log.entries] == ["fhir.hospital.example"]


def test_following_redirects_by_choice_still_cannot_leave_the_allow_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://collector.example/drop"})

    with guarded_client(
        _policy(_fixed("203.0.113.10")),
        PUSH,
        inner=httpx.MockTransport(handler),
        transfer_log=InMemoryTransferLog(),
        follow_redirects=True,
    ) as client:
        with pytest.raises(EgressDenied, match="collector.example"):
            client.post("https://fhir.hospital.example/fhir/Bundle")


# --- the alert (files/10 §7: egress denials are a hard alert) -----------------------


def test_a_denied_egress_moves_the_metric_the_catalogue_declares() -> None:
    before = REGISTRY.get_sample_value("sec_egress_denied_total") or 0.0
    transport = guarded_transport(
        _policy(_fixed("203.0.113.10")),
        PUSH,
        inner=httpx.MockTransport(lambda request: httpx.Response(200)),
        transfer_log=InMemoryTransferLog(),
    )
    with pytest.raises(EgressDenied):
        transport.handle_request(httpx.Request("POST", "https://collector.example/drop"))
    after = REGISTRY.get_sample_value("sec_egress_denied_total") or 0.0
    assert after == before + 1

    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    row = next(m for m in catalog["metrics"] if m["name"] == "sec_egress_denied_total")
    assert row["status"] == "live"
    assert row["target"].startswith("0")


def test_the_transfer_record_of_a_denial_carries_no_path_or_query() -> None:
    log = InMemoryTransferLog()
    transport = guarded_transport(
        _policy(_fixed("203.0.113.10")),
        PUSH,
        inner=httpx.MockTransport(lambda request: httpx.Response(200)),
        transfer_log=log,
    )
    with pytest.raises(EgressDenied):
        transport.handle_request(
            httpx.Request("POST", "https://collector.example/drop?tckn=10000000146")
        )
    (record,) = log.entries
    rendered = repr(record)
    assert "10000000146" not in rendered
    assert "/drop" not in rendered


# --- the proxy tier: a PHI-class call may not delegate its pinning ------------------


def test_a_phi_class_transport_refuses_to_run_behind_the_forward_proxy() -> None:
    """The fourth form of the bypass, closed at the seam it would arrive
    through.

    ``guarded_transport(proxy=...)`` deliberately hands the resolve-and-pin
    job to the network tier, because behind the proxy the hostname has to
    survive to the CONNECT line. That composition is right for a package pull
    and wrong for a clinical push: the vendor allow-list the proxy enforces has
    no connector rows and its PHI tier is empty, so a PHI-class call routed
    through it would lose the in-process pin and gain nothing. It is refused at
    construction rather than at the first send.
    """
    with pytest.raises(ValueError, match="pin"):
        guarded_transport(
            _policy(_fixed("203.0.113.10")),
            PUSH,
            inner=httpx.MockTransport(lambda request: httpx.Response(200)),
            transfer_log=InMemoryTransferLog(),
            proxy="http://egress-proxy:3128",
        )


def test_a_non_personal_call_may_still_use_the_proxy() -> None:
    """The near-miss control: the rule above must not disable the tier it is
    guarding. Package and model pulls are exactly what the proxy exists for."""
    allowlist = load_allowlist(ALLOWLIST_PATH)
    policy = EgressPolicy.for_tier(allowlist, "dev", resolver=_fixed("203.0.113.10"))
    context = EgressContext(
        purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.NON_PERSONAL
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.host))
        return httpx.Response(200)

    transport = guarded_transport(
        policy,
        context,
        inner=httpx.MockTransport(handler),
        transfer_log=InMemoryTransferLog(),
        proxy="http://egress-proxy:3128",
    )
    transport.handle_request(httpx.Request("GET", "https://pypi.org/simple/"))
    assert seen == ["pypi.org"], "the hostname must survive to the CONNECT line"


# --- the proxy configuration re-validates on connect --------------------------------


def _squid_directives() -> list[str]:
    return [
        line.strip()
        for line in SQUID_CONF.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_proxy_re_resolves_for_every_request_it_authorises() -> None:
    """*"resolves once and pins, re-validating on connect"* at the network
    tier. squid's ``dst`` ACL is evaluated against its IP cache, whose default
    positive TTL is six hours — long enough that a rebinding record can be
    authorised against one answer and connected against another. Disabling the
    cache is what makes the ACL and the connect share a single lookup."""
    directives = _squid_directives()
    assert "ipcache_size 0" in directives
    assert any(line.startswith("positive_dns_ttl") for line in directives)
    ttl = next(line for line in directives if line.startswith("positive_dns_ttl"))
    assert ttl.split()[1:] == ["1", "second"], ttl
    assert "dns_defnames off" in directives


def test_the_denied_ranges_are_the_same_list_at_both_enforcement_points() -> None:
    from intake_platform.egress import DENIED_RANGES

    acl = next(line for line in _squid_directives() if line.startswith("acl denied_nets dst"))
    rendered = set(acl.split()[3:])
    assert rendered == {cidr for cidr, _ in DENIED_RANGES}


def test_the_denied_ranges_acl_is_evaluated_before_any_allow() -> None:
    directives = _squid_directives()
    access = [line for line in directives if line.startswith("http_access")]
    assert access[0] == "http_access deny denied_nets"
    assert access[-1] == "http_access deny all"
