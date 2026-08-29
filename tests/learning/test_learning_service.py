"""INT-172 — services/learning as a service: the invariant-15 contract.

CLAUDE.md invariant 15: "every service exposes ``/healthz``, ``/readyz``,
``/metrics``, ``/version`` via ``packages/intake_platform/health``, emits OTel
through the shared setup, declares its SLOs in ``docs/slo/<service>.yaml``, and
has a synthetic probe; a new service without these fails ``make check``".

The generic halves of that gate already exist and bind the moment this
directory lands (tests/platform/test_health_contract.py enumerates
``services/``; tests/observability/test_slo_files.py requires
``docs/slo/learning.yaml``). What is asserted here is the part specific to a
weekly batch job rather than a request-serving API: readiness reports whether
the pipeline can run at all, and today it cannot, because no effect-size floor
has been signed off. A learning job that reported itself ready while unable to
promote anything would be the wrong answer.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient
from intake_platform.health import discover_services, verify_service_declarations
from intake_platform.slo import load_metrics_catalog, load_slo_file

REPO = Path(__file__).resolve().parents[2]


def _client() -> TestClient:
    from intake_learning.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_the_service_mounts_the_four_health_endpoints() -> None:
    client = _client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/version").status_code == 200


def test_readyz_reports_not_ready_while_the_promotion_threshold_is_unsigned() -> None:
    """Fail closed, and say why in the check name rather than in a log."""
    response = _client().get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["promotion_thresholds"] == "error"


def test_the_service_declares_the_intake_contract() -> None:
    declaration = next(s for s in discover_services(REPO / "services") if s.name == "learning")
    verify_service_declarations(declaration)  # must not raise
    data = tomllib.loads((REPO / "services" / "learning" / "pyproject.toml").read_text("utf-8"))
    assert data["tool"]["intake"]["probe"] == "learning.http"


def test_the_service_has_an_slo_file_naming_itself() -> None:
    slo_file = load_slo_file(REPO / "docs" / "slo" / "learning.yaml")
    assert slo_file.service == "learning"
    assert slo_file.slos


def test_the_learning_counters_are_catalogued() -> None:
    """Invariant 13: emit-without-catalogue fails CI. The generic gate only
    sees what the shared health app serves, so the counters this package
    registers are pinned by name here."""
    import intake_learning.architect  # noqa: F401  — registers the counters
    import intake_learning.evidence  # noqa: F401

    catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
    for name in (
        "learning_findings_total",
        "learning_proposals_total",
        "learning_proposals_refused_total",
        "learning_evidence_bundles_total",
    ):
        assert catalog.covers(name), f"{name} is emitted but absent from the catalogue"


def test_the_registry_row_marks_the_job_off_the_phi_path() -> None:
    """files/09 §7: the job reads de-identified views on read-only creds. It
    never reaches a raw table, so it is not a PHI-path component."""
    from intake_probes.registry import load_registry

    entry = load_registry(REPO / "observability" / "registry.yaml").get("learning")
    assert entry.phi_path is False
    assert entry.self_hostable is True


def test_readyz_turns_green_the_moment_the_threshold_is_recorded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The 503 is a missing value, not a broken service.

    Proving the check flips matters: a readiness probe wired to something that
    can only ever be false is indistinguishable from one wired to nothing.
    """
    from intake_learning.architect import EffectSizeFloor, PromotionThresholds
    from intake_learning.evidence import EvidenceSource

    monkeypatch.setattr(
        PromotionThresholds,
        "from_blueprint",
        classmethod(
            lambda cls: cls(
                effect_size_floor=EffectSizeFloor(
                    value=0.5, recorded_in=EvidenceSource.TEST_FIXTURE
                )
            )
        ),
    )
    response = _client().get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["promotion_thresholds"] == "ok"
