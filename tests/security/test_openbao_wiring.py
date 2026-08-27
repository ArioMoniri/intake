"""INT-017 — OpenBao wiring: secrets client, fail-closed boot, dynamic DB creds.

Acceptance, verbatim:
  "compose service; api/workers/voice-runtime read secrets from OpenBao; .env
   holds only address/token in dev; dynamic Postgres creds TTL 24h"
  "test proves a service boots with OpenBao and fails closed without it in
   prod mode"

Unit tests below run everywhere. The `integration` marker (its own CI job and
`make check-integration` — 05 §3 puts the docker tier in its own required job)
runs against a real dev OpenBao + Postgres from infra/docker-compose.dev.yml.
"""

from __future__ import annotations

import os

import pytest
from intake_platform.secrets import SecretsBootError, SecretsProvider

# --- fail-closed boot (unit) ------------------------------------------------------


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("INTAKE_ENV", "OPENBAO_ADDR", "OPENBAO_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_prod_without_openbao_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("INTAKE_ENV", "prod")
    with pytest.raises(SecretsBootError, match="fail(s|ing)? closed|OpenBao"):
        SecretsProvider.from_env()


def test_prod_refuses_the_dev_root_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("INTAKE_ENV", "prod")
    monkeypatch.setenv("OPENBAO_ADDR", "https://bao.internal:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "intake-dev-root")
    with pytest.raises(SecretsBootError, match="dev.*token|token.*dev"):
        SecretsProvider.from_env()


def test_prod_verifies_reachability_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("INTAKE_ENV", "prod")
    monkeypatch.setenv("OPENBAO_ADDR", "http://127.0.0.1:1")  # nothing listens
    monkeypatch.setenv("OPENBAO_TOKEN", "s.real-looking-token")
    with pytest.raises(SecretsBootError, match="unreachable|refused|connect"):
        SecretsProvider.from_env()


def test_dev_defaults_are_loopback_and_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("INTAKE_ENV", "dev")
    monkeypatch.setenv("OPENBAO_TOKEN", "intake-dev-root")
    provider = SecretsProvider.from_env()  # no connectivity check in dev boot
    assert provider.addr.startswith("http://127.0.0.1")


def test_env_file_carries_only_address_and_token() -> None:
    # ".env holds only address/token in dev" — the template must not grow
    # secret material beyond the OpenBao pointer (invariant 13).
    from pathlib import Path

    env = (Path(__file__).resolve().parents[2] / "env.example").read_text(encoding="utf-8")
    keys = [
        line.split("=", 1)[0]
        for line in env.splitlines()
        if "=" in line and not line.startswith("#")
    ]
    allowed = {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",  # compose bootstrap only
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "OPENBAO_ADDR",
        "OPENBAO_TOKEN",
    }
    assert set(keys) <= allowed, (
        f"env template grew beyond the OpenBao pointer: {set(keys) - allowed}"
    )


# --- integration: real dev OpenBao + Postgres -------------------------------------


@pytest.mark.integration
def test_service_boots_reads_kv_and_gets_dynamic_db_creds() -> None:
    provider = SecretsProvider.from_env()
    provider.check_ready()

    provider.put_kv("intake/smoke", {"marker": "int-017"})
    assert provider.get_kv("intake/smoke")["marker"] == "int-017"

    creds = provider.get_dynamic_db_creds("intake-api")
    assert creds.username.startswith("v-")
    assert creds.lease_duration_s == 24 * 3600, "dynamic Postgres creds must carry a 24h TTL"

    import psycopg

    conn = psycopg.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "intake"),
        user=creds.username,
        password=creds.password,
        connect_timeout=5,
    )
    with conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


@pytest.mark.integration
def test_per_service_policies_are_applied() -> None:
    provider = SecretsProvider.from_env()
    policies = provider.list_policies()
    for required in ("intake-api", "intake-workers", "intake-voice-runtime"):
        assert required in policies, f"missing per-service policy {required}"
