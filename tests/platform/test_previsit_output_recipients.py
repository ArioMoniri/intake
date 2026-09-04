"""The previsit-output recipient registry — who may fetch, and what that costs.

The registry is the inbound twin of ``intake_connectors.destinations`` and it
exists for the same reason: a share of clinical data to another organisation
is a decision a human takes out of band and records, never a value a caller
supplies. Two properties are asserted here.

1. **A row asserts facts a human has actually produced.** ``dpa_ref``,
   ``approval_ref`` and ``retention_ref`` are required and id-shaped. The
   third is the one this repository could not answer for itself: files/06 §3
   states how long INTAKE keeps a record, and says nothing about how long the
   receiving hospital keeps a copy it fetched — that is a DPA clause, and the
   row is where the clause is named.
2. **The shipped file has zero rows, so every tenant is refused.** That is the
   fail-closed state and not a gap (CLAUDE.md invariant 17).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from intake_platform.previsit_output import (
    RecipientNotRegistered,
    RecipientRegistryError,
    load_recipients,
)

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "infra" / "previsit_output" / "recipients.yaml"

TENANT = uuid.UUID("11111111-2222-4333-8444-555555555555")


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "recipients.yaml"
    path.write_text(body, encoding="utf-8")
    return path


ONE_ROW = """
version: 1
recipients:
  - recipient_id: acibadem-hbys-previsit-read
    tenant_id: 11111111-2222-4333-8444-555555555555
    dpa_ref: dpa/acibadem/2026-01
    approval_ref: approval/tier3/2026-02-14
    retention_ref: dpa/acibadem/2026-01#clause-7.2
"""


def test_the_shipped_registry_has_no_rows_and_refuses_every_tenant() -> None:
    registry = load_recipients(SHIPPED)
    assert registry.rows == ()
    with pytest.raises(RecipientNotRegistered):
        registry.for_tenant(TENANT)


def test_a_registered_tenant_resolves_to_its_row(tmp_path: Path) -> None:
    registry = load_recipients(write(tmp_path, ONE_ROW))
    row = registry.for_tenant(TENANT)
    assert row.recipient_id == "acibadem-hbys-previsit-read"
    assert row.retention_ref == "dpa/acibadem/2026-01#clause-7.2"


def test_a_row_without_a_retention_clause_is_refused(tmp_path: Path) -> None:
    """The retention of the copy the hospital holds is not derivable from this
    repository. A row that omits it would assert a period nobody agreed."""
    body = "\n".join(
        line for line in ONE_ROW.splitlines() if not line.strip().startswith("retention_ref:")
    )
    with pytest.raises(RecipientRegistryError):
        load_recipients(write(tmp_path, body))


def test_a_row_without_a_dpa_or_an_approval_is_refused(tmp_path: Path) -> None:
    for dropped in ("dpa_ref:", "approval_ref:"):
        body = "\n".join(
            line for line in ONE_ROW.splitlines() if not line.strip().startswith(dropped)
        )
        with pytest.raises(RecipientRegistryError):
            load_recipients(write(tmp_path, body))


def test_a_narrative_ref_is_refused(tmp_path: Path) -> None:
    """Registry refs reach the audit chain, so they obey the audit shape:
    ids, never prose (invariant 6)."""
    body = ONE_ROW.replace(
        "dpa/acibadem/2026-01", "the DPA we signed with the hospital last winter"
    )
    with pytest.raises(RecipientRegistryError):
        load_recipients(write(tmp_path, body))


def test_two_rows_for_one_tenant_are_refused(tmp_path: Path) -> None:
    """One registered reader per tenant: a second row would make 'which
    agreement is this fetch under' ambiguous at the moment it is audited."""
    with pytest.raises(RecipientRegistryError):
        load_recipients(write(tmp_path, ONE_ROW + ONE_ROW.split("recipients:", 1)[1]))


def test_a_missing_registry_file_is_a_refusal_not_an_empty_list(tmp_path: Path) -> None:
    with pytest.raises(RecipientRegistryError):
        load_recipients(tmp_path / "absent.yaml")


def test_an_unknown_top_level_key_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RecipientRegistryError):
        load_recipients(write(tmp_path, ONE_ROW + "\nallow_all: true\n"))
