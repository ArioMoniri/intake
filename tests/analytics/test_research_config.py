"""INT-490 — the two LD-06 decisions this build may not make, and the tenant
admission it must make.

**Retention (LD-06 ``retention.aggregates`` / ``retention.raw_telemetry``,
both ``draft``).** Configuration with no default. Unset is the fail-closed
state: retention is a property of something KEPT, so while the aggregate
period is undecided nothing keeps an aggregate (no snapshot, no export, no
Loop-2 evidence bundle — :class:`RetentionUndecided`), and while the raw
telemetry period is undecided nothing records raw telemetry (the per-question
views report ``raw_telemetry_retention_undecided``). A value that is not a
positive whole number of days is refused rather than read as unset.

**Admission (LD-06 ``improvement.hospital_deployment_needs_controller_authorisation``).**
A tenant enters a vendor-side aggregate only when INTAKE is its controller, or
when a DPA authorisation is recorded for it; the tenants table's own
``kvkk_role`` decides which, never the registry.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from intake_platform.analytics.research import (
    ENV_AGGREGATE_RETENTION_DAYS,
    ENV_RAW_TELEMETRY_RETENTION_DAYS,
    AnalyticsRetention,
    RetentionConfigRefused,
    RetentionUndecided,
)
from intake_platform.analytics.research.admission import (
    ENV_TENANT_REGISTRY,
    AdmittedTenant,
    TenantRegistry,
    TenantRegistryRefused,
    admission_refusal,
)
from intake_platform.db.models import KvkkRole

# --- retention ----------------------------------------------------------------------


def test_retention_has_no_default_at_all() -> None:
    with pytest.raises(TypeError):
        AnalyticsRetention()  # type: ignore[call-arg]


def test_unset_retention_is_undecided_and_keeps_nothing() -> None:
    retention = AnalyticsRetention.from_env({})
    assert retention == AnalyticsRetention(aggregates=None, raw_telemetry=None)
    with pytest.raises(RetentionUndecided) as undecided:
        retention.require_keeping()
    assert undecided.value.which == "aggregates"
    assert retention.raw_telemetry_reason() == "raw_telemetry_retention_undecided"


def test_an_empty_variable_is_unset_not_zero() -> None:
    retention = AnalyticsRetention.from_env({ENV_AGGREGATE_RETENTION_DAYS: "  "})
    assert retention.aggregates is None


def test_a_decided_period_is_read_in_whole_days() -> None:
    retention = AnalyticsRetention.from_env(
        {ENV_AGGREGATE_RETENTION_DAYS: "30", ENV_RAW_TELEMETRY_RETENTION_DAYS: "7"}
    )
    assert retention.require_keeping() == timedelta(days=30)
    assert retention.raw_telemetry == timedelta(days=7)
    # set, but nothing on this branch records raw telemetry
    assert retention.raw_telemetry_reason() == "raw_telemetry_not_recorded"


@pytest.mark.parametrize("raw", ["0", "-3", "abc", "1.5", "30d", "007", "1e3"])
def test_a_value_that_is_not_a_positive_whole_number_of_days_is_refused(raw: str) -> None:
    for name in (ENV_AGGREGATE_RETENTION_DAYS, ENV_RAW_TELEMETRY_RETENTION_DAYS):
        with pytest.raises(RetentionConfigRefused) as refused:
            AnalyticsRetention.from_env({name: raw})
        assert raw not in str(refused.value)  # the refusal names the variable only


# --- tenant admission --------------------------------------------------------------

TENANT = uuid.UUID("0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d")


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tenants.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_an_unset_registry_admits_nobody() -> None:
    assert TenantRegistry.from_env({}) is None


def test_a_registry_lists_tenants_and_their_dpa_authorisation(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"tenants:\n  - tenant_id: {TENANT}\n    dpa_authorisation_ref: null\n",
    )
    registry = TenantRegistry.from_env({ENV_TENANT_REGISTRY: str(path)})
    assert registry is not None
    assert registry.tenants == (AdmittedTenant(tenant_id=TENANT, dpa_authorisation_ref=None),)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("tenants: nope\n", "registry_malformed"),
        (
            "tenants:\n  - tenant_id: not-a-uuid\n    dpa_authorisation_ref: null\n",
            "tenant_id_malformed",
        ),
        (
            f"tenants:\n  - tenant_id: {TENANT}\n    dpa_authorisation_ref: null\n"
            "    name: Clinic\n",
            "registry_malformed",
        ),
        (
            f"tenants:\n  - tenant_id: {TENANT}\n    dpa_authorisation_ref: clause 4 b\n",
            "dpa_authorisation_ref_malformed",
        ),
        (
            f"tenants:\n  - tenant_id: {TENANT}\n    dpa_authorisation_ref: null\n"
            f"  - tenant_id: {TENANT}\n    dpa_authorisation_ref: null\n",
            "tenant_duplicated",
        ),
        ("other: []\n", "registry_malformed"),
    ],
)
def test_a_malformed_registry_is_refused(tmp_path: Path, text: str, code: str) -> None:
    with pytest.raises(TenantRegistryRefused) as refused:
        TenantRegistry.from_yaml(_write(tmp_path, text))
    assert refused.value.code == code


def test_an_unreadable_registry_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TenantRegistryRefused) as refused:
        TenantRegistry.from_env({ENV_TENANT_REGISTRY: str(tmp_path / "absent.yaml")})
    assert refused.value.code == "registry_unreadable"


def test_a_controller_tenant_is_admitted() -> None:
    tenant = AdmittedTenant(tenant_id=TENANT, dpa_authorisation_ref=None)
    assert admission_refusal(tenant, KvkkRole.CONTROLLER) is None


def test_a_processor_tenant_needs_a_recorded_dpa_authorisation() -> None:
    bare = AdmittedTenant(tenant_id=TENANT, dpa_authorisation_ref=None)
    assert admission_refusal(bare, KvkkRole.PROCESSOR) == "processor_without_dpa_authorisation"
    authorised = AdmittedTenant(tenant_id=TENANT, dpa_authorisation_ref="dpa.clause.7")
    assert admission_refusal(authorised, KvkkRole.PROCESSOR) is None


def test_a_listed_tenant_the_database_does_not_know_is_refused() -> None:
    tenant = AdmittedTenant(tenant_id=TENANT, dpa_authorisation_ref=None)
    assert admission_refusal(tenant, None) == "tenant_unknown"
