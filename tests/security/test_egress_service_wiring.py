"""INT-018 — the egress guard is *composed by the services*, not merely correct.

Acceptance clause under test, verbatim:
  "only allow-listed vendor hosts reachable from PHI-path services"
  "test: call to unlisted host is refused and logged"

``tests/security/test_egress_policy.py`` proves the policy library is right.
This file proves it is **called**: a policy that is correct and uncalled is
exactly the failure mode the clause exists to catch, and until this landed the
only consumer in the tree was the LLM gateway (INT-083). Every refusal below
goes through the service's *own* client — ``EhrbaseClient.status()``,
``SecretsProvider.check_ready()``, ``UnleashProvider.get_bool()`` — never
through the library in isolation.

What a PHI-path client is allowed to reach, and why it is not the vendor
allow-list. EHRbase, OpenBao and Unleash are all **inside the deployment
boundary** (files/10 §2 "services"; the ehrbase module header: "inside the
deployment boundary and addressed over loopback in dev... no PHI egress
path"), and ``phi_path: []`` in the allow-list says the PHI path reaches no
vendor at all (invariant 19 / 00_STATE D11). So the guard these clients carry
is the *boundary* policy: their own configured in-boundary destination, and
nothing else — no vendor host, no public FQDN, no routable IP literal, no
cloud metadata address. That is strictly narrower than the vendor allow-list,
which is what "the PHI path reaches no vendor" means in code.

No socket is opened anywhere in this file: a denial is decided before the
inner transport is ever consulted, so the default (real) transport is safe to
exercise for every refusal.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import httpx
import pytest
from intake_platform.egress import (
    VENDOR_LLM_DOMAINS,
    EgressDenied,
    EgressPolicy,
    load_allowlist,
)
from intake_platform.egress_boundary import (
    BOUNDARY_SUFFIXES,
    BoundaryPolicy,
    boundary_transport,
    is_boundary_host,
)
from intake_platform.ehrbase import EhrbaseClient, EhrbaseConfig
from intake_platform.flags import InMemoryProvider, UnleashProvider
from intake_platform.secrets import SecretsProvider

REPO = Path(__file__).resolve().parents[2]
PLATFORM_SRC = REPO / "packages" / "intake_platform" / "src" / "intake_platform"
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"

#: An external host nothing in this repo may reach. Not a real vendor string:
#: scripts/ci/assert_no_vendor_calls.sh refuses live vendor endpoints outside
#: files/, and a family-shaped host is a broader control anyway.
UNLISTED = "evil.example.com"

#: Cloud instance metadata — files/10 §4 names it as the SSRF payoff a
#: server-side fetch inside the PHI network hands an attacker.
METADATA_HOST = "169.254.169.254"


def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == event]


def _assert_denial_record(caplog: pytest.LogCaptureFixture, host: str) -> None:
    denied = _records(caplog, "sec.egress_denied")
    assert len(denied) == 1, [record.getMessage() for record in caplog.records]
    record = denied[0]
    assert record.host == host  # type: ignore[attr-defined]
    assert record.decision == "deny"  # type: ignore[attr-defined]
    assert record.bytes_out == 0  # type: ignore[attr-defined]
    assert record.levelno == logging.WARNING
    # invariant 6 — the register feed carries ids, never content
    for forbidden in ("payload", "body", "content", "url", "query", "path"):
        assert forbidden not in record.__dict__


# --- the boundary rule itself -----------------------------------------------------


class TestBoundaryHost:
    @pytest.mark.parametrize(
        "host",
        [
            "ehrbase",  # a compose / k8s service label: no public TLD exists
            "openbao",
            "unleash.internal",  # ICANN-reserved private-use suffix
            "ehrbase.invalid",  # RFC 6761 — never delegated
            "transit.test",  # RFC 6761 — never delegated
            "bao.localhost",  # RFC 6761
            "ehrbase.intake.svc.cluster.local",  # RFC 6762 mDNS suffix
            "127.0.0.1",
            "::1",
        ],
    )
    def test_in_boundary_names_are_accepted(self, host: str) -> None:
        assert is_boundary_host(host) is True

    @pytest.mark.parametrize(
        "host",
        [
            UNLISTED,
            "pypi.org",  # on the *vendor* allow-list, still not in-boundary
            "huggingface.co",
            "llm.openai.com",
            "ehrbase.invalid.evil.example.com",  # lookalike: the suffix decides
            "ehrbase-internal.example.com",
            "notlocalhost.example.com",
            METADATA_HOST,
            "10.0.0.5",  # routable inside a private network is still routable
            "8.8.8.8",
            "",
        ],
    )
    def test_out_of_boundary_names_are_refused(self, host: str) -> None:
        assert is_boundary_host(host) is False

    def test_every_declared_suffix_is_a_non_resolvable_special_use_name(self) -> None:
        # The rule is not a list of conveniences: each suffix is reserved by a
        # standard so that it cannot exist in the public DNS. A suffix that
        # resolves globally would be an exfiltration destination.
        assert BOUNDARY_SUFFIXES == frozenset(
            {".internal", ".invalid", ".local", ".localhost", ".test"}
        )


class TestBoundaryPolicy:
    def test_permits_exactly_the_configured_destination(self) -> None:
        policy = BoundaryPolicy.for_base_url(
            service="ehrbase", purpose="unit fixture", base_url="http://ehrbase.invalid:8080/x"
        )
        assert policy.check("ehrbase.invalid", 8080).allowed is True
        assert policy.check("ehrbase.invalid", 8081).allowed is False
        assert policy.check("other.invalid", 8080).allowed is False

    def test_an_out_of_boundary_base_url_reaches_nothing_at_all(self) -> None:
        policy = BoundaryPolicy.for_base_url(
            service="ehrbase", purpose="unit fixture", base_url=f"https://{UNLISTED}"
        )
        decision = policy.check(UNLISTED, 443)
        assert decision.allowed is False
        assert "boundary" in decision.reason

    def test_scheme_default_ports_are_inferred(self) -> None:
        policy = BoundaryPolicy.for_base_url(
            service="unleash", purpose="unit fixture", base_url="http://unleash.internal"
        )
        assert policy.check("unleash.internal", 80).allowed is True
        assert policy.check("unleash.internal", 443).allowed is False

    def test_a_redirect_to_another_host_is_refused_on_the_new_hop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # httpx re-enters the transport for every redirect hop, so each hop is
        # checked independently — the classic open-redirect exfiltration path.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "unleash.internal":
                return httpx.Response(302, headers={"location": f"https://{UNLISTED}/steal"})
            return httpx.Response(200)

        transport = boundary_transport(
            service="unleash",
            purpose="unit fixture",
            base_url="https://unleash.internal",
            inner=httpx.MockTransport(handler),
        )
        with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
            with httpx.Client(transport=transport, follow_redirects=True) as client:
                with pytest.raises(EgressDenied):
                    client.get("https://unleash.internal/api/client/features/x")
        assert _records(caplog, "sec.egress_denied")[0].host == UNLISTED  # type: ignore[attr-defined]


# --- per service: refused through that service's own client -----------------------


class TestEhrbaseClient:
    """EHRbase carries openEHR compositions — clinical content. INT-032."""

    def test_unlisted_host_is_refused_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        client = EhrbaseClient(
            EhrbaseConfig(base_url=f"https://{UNLISTED}", username="u", password="p")
        )
        with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
            with pytest.raises(EgressDenied):
                client.status()
        _assert_denial_record(caplog, UNLISTED)

    def test_vendor_llm_host_is_refused(self) -> None:
        # invariant 19 through the client: no PHI-path client can be pointed
        # at an anthropic/openai/google adapter host.
        client = EhrbaseClient(
            EhrbaseConfig(base_url="https://llm.openai.com", username="u", password="p")
        )
        with pytest.raises(EgressDenied):
            client.status()

    def test_lookalike_of_the_configured_host_is_refused(self) -> None:
        # near-miss negative control: a host that merely *resembles* the
        # in-boundary destination is a different host.
        client = EhrbaseClient(
            EhrbaseConfig(
                base_url="https://ehrbase.invalid.evil.example.com", username="u", password="p"
            )
        )
        with pytest.raises(EgressDenied):
            client.status()

    def test_metadata_address_is_refused(self) -> None:
        client = EhrbaseClient(
            EhrbaseConfig(base_url=f"http://{METADATA_HOST}", username="u", password="p")
        )
        with pytest.raises(EgressDenied):
            client.status()

    def test_the_in_boundary_destination_still_works(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=(
                    b"<status><ehrbase_version>2.35.1</ehrbase_version>"
                    b"<openehr_sdk_version>2.20.0</openehr_sdk_version></status>"
                ),
            )

        client = EhrbaseClient(
            EhrbaseConfig(base_url="http://ehrbase.invalid:8080", username="u", password="p"),
            transport=httpx.MockTransport(handler),
        )
        with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
            assert client.status().ehrbase_version == "2.35.1"
        allowed = _records(caplog, "sec.egress_allowed")
        assert allowed and allowed[0].host == "ehrbase.invalid"  # type: ignore[attr-defined]

    def test_an_injected_transport_does_not_bypass_the_guard(self) -> None:
        # the `transport` seam is the *inner* transport, never a way around
        # the policy — otherwise every exercised path is unguarded again.
        client = EhrbaseClient(
            EhrbaseConfig(base_url=f"https://{UNLISTED}", username="u", password="p"),
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        )
        with pytest.raises(EgressDenied):
            client.status()


class TestSecretsProvider:
    """OpenBao holds every credential and the transit KEKs (files/10 §2)."""

    def test_unlisted_host_is_refused_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        provider = SecretsProvider(addr=f"https://{UNLISTED}", token="unit")
        with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
            with pytest.raises(EgressDenied):
                provider.check_ready()
        _assert_denial_record(caplog, UNLISTED)

    def test_metadata_address_is_refused(self) -> None:
        provider = SecretsProvider(addr=f"http://{METADATA_HOST}", token="unit")
        with pytest.raises(EgressDenied):
            provider.get_kv("anything")

    def test_vendor_llm_host_is_refused(self) -> None:
        provider = SecretsProvider(addr="https://llm.anthropic.com", token="unit")
        with pytest.raises(EgressDenied):
            provider.check_ready()

    def test_the_dev_loopback_default_is_still_reachable(self) -> None:
        provider = SecretsProvider(addr="http://127.0.0.1:8200", token="unit")
        policy = BoundaryPolicy.for_base_url(
            service="openbao", purpose="unit fixture", base_url=provider.addr
        )
        assert policy.check("127.0.0.1", 8200).allowed is True


class TestUnleashProvider:
    """Feature flags gate safety behaviour (kill switch, lanes) — files/08."""

    def test_unlisted_host_is_refused_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        provider = UnleashProvider(f"https://{UNLISTED}", fallback=InMemoryProvider())
        with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
            with pytest.raises(EgressDenied):
                provider.get_bool("greeting_v2", False)
        _assert_denial_record(caplog, UNLISTED)
        provider.close()

    def test_vendor_llm_host_is_refused(self) -> None:
        provider = UnleashProvider("https://llm.openai.com", fallback=InMemoryProvider())
        with pytest.raises(EgressDenied):
            provider.get_bool("greeting_v2", False)
        provider.close()

    def test_the_in_boundary_destination_still_works(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"name": "greeting_v2", "enabled": True})

        provider = UnleashProvider(
            "http://unleash.internal:4242", transport=httpx.MockTransport(handler)
        )
        assert provider.get_bool("greeting_v2", False) is True
        provider.close()


# --- the anti-regression gate: no unguarded httpx client may be added -------------


class TestNoUnguardedClient:
    def test_every_httpx_client_in_intake_platform_composes_a_guard(self) -> None:
        """A library that is correct and uncalled is the failure mode INT-018
        exists to catch. Any module that builds an ``httpx.Client`` must build
        it over ``guarded_transport`` (the vendor allow-list) or
        ``boundary_transport`` (the in-boundary form)."""
        offenders: list[str] = []
        for path in sorted(PLATFORM_SRC.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "httpx.Client(" not in source and "httpx.AsyncClient(" not in source:
                continue
            if path.name in {"egress.py", "egress_boundary.py"}:
                continue  # the guards themselves
            if "guarded_transport(" in source or "boundary_transport(" in source:
                continue
            offenders.append(str(path.relative_to(REPO)))
        assert offenders == [], f"unguarded httpx client(s): {offenders}"

    def test_the_three_phi_path_clients_are_the_ones_wired(self) -> None:
        wired = {
            path.name
            for path in sorted(PLATFORM_SRC.rglob("*.py"))
            if "boundary_transport(" in path.read_text(encoding="utf-8")
            and path.name != "egress_boundary.py"
        }
        assert wired == {"ehrbase.py", "flags.py", "secrets.py"}

    def test_the_module_graph_has_no_second_definition_of_the_guard(self) -> None:
        # one chokepoint, not a family of near-copies
        definitions = 0
        for path in sorted(PLATFORM_SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in {
                    "guarded_transport",
                    "boundary_transport",
                }:
                    definitions += 1
        assert definitions == 2


# --- the vendor allow-list, seen from the PHI path -------------------------------


class TestPhiPathReachesNoVendor:
    def test_phi_path_tier_denies_every_vendor_family(self) -> None:
        policy = EgressPolicy.for_tier(load_allowlist(ALLOWLIST_PATH), "phi_path")
        for domain in sorted(VENDOR_LLM_DOMAINS):
            assert policy.check(f"llm.{domain}", 443).allowed is False

    def test_dev_tier_refuses_a_lookalike_of_an_allow_listed_host(self) -> None:
        policy = EgressPolicy.for_tier(load_allowlist(ALLOWLIST_PATH), "dev")
        assert policy.check("pypi.org", 443).allowed is True
        for lookalike in ("pypi.org.evil.example.com", "notpypi.org", "evilhf.co", "hf.co"):
            assert policy.check(lookalike, 443).allowed is False, lookalike
