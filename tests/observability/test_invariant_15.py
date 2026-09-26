"""INT-021 — CLAUDE.md invariant 15 as one executable gate.

The invariant, verbatim:

    "every service exposes /healthz, /readyz, /metrics, /version via
     packages/intake_platform/health, emits OTel through the shared setup,
     declares its SLOs in docs/slo/<service>.yaml, and has a synthetic probe;
     a new service without these fails make check"

Four requirements. Before this file they were checked in two places and two of
them nowhere: tests/platform/test_health_contract.py held the ``[tool.intake]``
declaration and tests/observability/test_slo_files.py held the SLO file, while
**"emits OTel through the shared setup"** and **"has a synthetic probe"** had no
gate at all — a service could declare ``probe = "anything"``, never import
``intake_platform.otel``, and pass ``make check``. services/probes did exactly
that, and its SLO was written over an ``http_requests_total{service="probes"}``
series the service never emitted.

So this file is the single gate, run over the real services/ tree by
:func:`intake_platform.health.verify_service_contract`, and it is what makes the
invariant's last clause ("a new service without these fails make check") true.
The negative controls run the same function over fixture services that each
break exactly one requirement, so the gate's ability to FAIL is proven and not
assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from intake_platform.health import (
    ServiceContractError,
    discover_services,
    scan_service_sources,
    verify_service_contract,
)
from intake_platform.slo import load_slo_file, sli_service_labels
from intake_probes.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
SERVICES_ROOT = REPO / "services"
SLO_DIR = REPO / "docs" / "slo"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
FIXTURES = REPO / "tests" / "fixtures" / "services"


def _probe_components() -> frozenset[str]:
    return frozenset(entry.component for entry in load_registry(REGISTRY_PATH).components)


def _services() -> list:  # type: ignore[type-arg]
    services = discover_services(SERVICES_ROOT)
    assert services, "services/ must hold at least one service package"
    return services


# --- the gate over the real tree --------------------------------------------------


def test_every_service_satisfies_all_four_requirements() -> None:
    probe_components = _probe_components()
    for service in _services():
        verify_service_contract(service, slo_dir=SLO_DIR, probe_components=probe_components)


def test_every_service_mounts_the_four_endpoints_via_the_shared_module() -> None:
    for service in _services():
        findings = scan_service_sources(service)
        assert findings.mounts_health, (
            f"{service.name} never calls intake_platform.health.mount_health — the four "
            "endpoints must come from the shared module, not be re-implemented"
        )


def test_every_service_emits_otel_through_the_shared_setup() -> None:
    for service in _services():
        findings = scan_service_sources(service)
        assert findings.calls_setup_otel, (
            f"{service.name} never calls intake_platform.otel.setup_otel — a service whose "
            "spans and logs skip the shared setup skips the redaction with it (inv. 6)"
        )


def test_every_service_declares_its_slos() -> None:
    for service in _services():
        path = SLO_DIR / f"{service.name}.yaml"
        assert path.is_file(), f"{service.name} has no docs/slo/{service.name}.yaml"
        assert load_slo_file(path).service == service.name


def test_every_service_has_a_synthetic_probe_row_in_the_registry() -> None:
    probe_components = _probe_components()
    for service in _services():
        assert service.name in probe_components, (
            f"{service.name} has no row in observability/registry.yaml, so nothing probes it "
            "every 60 s — declaring a probe id in pyproject.toml is not having a probe"
        )


# --- the cross-check that closes the silent hole ----------------------------------


def test_every_http_sli_is_emitted_by_the_service_it_names() -> None:
    """An SLI pinned to ``service="x"`` needs x to label its HTTP metrics "x".

    docs/slo/probes.yaml declared an availability objective over
    ``http_requests_total{service="probes"}`` while services/probes never called
    ``mount_http_metrics`` — an error budget over a series that could not exist.
    The SLI-to-catalogue check cannot see this: the family IS catalogued; it is
    the *label value* that nobody emits.
    """
    emitters = {service.name: scan_service_sources(service) for service in _services()}
    for path in sorted(SLO_DIR.glob("*.yaml")):
        slo_file = load_slo_file(path)
        for slo in slo_file.slos:
            for labelled in sorted(sli_service_labels(slo.sli)):
                if labelled not in emitters:
                    continue
                assert labelled in emitters[labelled].http_metric_service_labels, (
                    f"{path.name}:{slo.name} measures service={labelled!r} on the shared HTTP "
                    f"families, but services/{labelled} never calls "
                    f"mount_http_metrics(app, {labelled!r}) — the series is catalogued and "
                    "the label value is never emitted"
                )


# --- negative controls: the gate can fail -----------------------------------------


def _fixture(name: str):  # type: ignore[no-untyped-def]
    return next(s for s in discover_services(FIXTURES) if s.name == name)


def test_fixture_service_meeting_all_four_passes() -> None:
    verify_service_contract(
        _fixture("good_service"),
        slo_dir=FIXTURES / "slo",
        probe_components=frozenset({"good_service"}),
    )


def test_service_without_the_declaration_fails() -> None:
    with pytest.raises(ServiceContractError, match="health"):
        verify_service_contract(
            _fixture("bad_service"),
            slo_dir=FIXTURES / "slo",
            probe_components=frozenset({"bad_service"}),
        )


def test_service_without_shared_otel_fails() -> None:
    with pytest.raises(ServiceContractError, match="setup_otel"):
        verify_service_contract(
            _fixture("otelless_service"),
            slo_dir=FIXTURES / "slo",
            probe_components=frozenset({"otelless_service"}),
        )


def test_service_without_an_slo_file_fails() -> None:
    with pytest.raises(ServiceContractError, match="docs/slo"):
        verify_service_contract(
            _fixture("good_service"),
            slo_dir=FIXTURES / "slo_empty",
            probe_components=frozenset({"good_service"}),
        )


def test_service_without_a_probe_row_fails() -> None:
    with pytest.raises(ServiceContractError, match="probe"):
        verify_service_contract(
            _fixture("good_service"),
            slo_dir=FIXTURES / "slo",
            probe_components=frozenset(),
        )


def test_the_error_names_every_failing_requirement_at_once() -> None:
    """One run, every gap — an operator fixing a new service should not have to
    re-run the gate four times to discover four missing things."""
    with pytest.raises(ServiceContractError) as caught:
        verify_service_contract(
            _fixture("bad_service"),
            slo_dir=FIXTURES / "slo_empty",
            probe_components=frozenset(),
        )
    message = str(caught.value)
    for fragment in ("health", "setup_otel", "docs/slo", "probe"):
        assert fragment in message, f"contract error does not mention {fragment!r}: {message}"
