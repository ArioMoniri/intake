"""INT-141 — /v1/me/notifications: the patient's own opt-out and quiet-hours
register (files/10 §9 row "Notifications / reminders"; sec_row
``notifications``).

Why these routes are NOT behind a consent scope, and why that is the safer
reading rather than the looser one: this surface is the message-refusal
register. Gate it on ``core`` and you build a state in which a patient who
withdrew a consent can no longer reach the switch that stops the messages —
the same trap the DSAR routes documented (a withdrawal must not make the
right it provokes unreachable) and the same shape as the consent-management
cage. So the routes carry an explicit ``notification_preference`` marker,
caged to their own prefix, and the route-table scan still refuses silence.

Everything else stays: patient-only, own rows only, audited, ids in logs.
And the state must SURVIVE A RESTART — a quiet-hours setting that lives in a
process is a quiet-hours setting that stops working at the next deploy, at
3 a.m., for everyone at once.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from fastapi import FastAPI
from intake_api.consent_guard import (
    NOTIFICATION_PREFERENCE_PREFIX,
    notification_preference,
    notification_preference_routes,
    unguarded_data_routes,
)
from intake_api.dev_fixture import DEV_PATIENT_ID
from intake_platform.db.inventory import INVENTORY_FIELDS, INVENTORY_KEY
from intake_platform.db.models import Base, NotificationPreference

PATH = "/v1/me/notifications"


def _restart(tmp_path: Path) -> Iterator[ApiHarness]:
    """A second process over the same database file: the closest a unit lane
    gets to `systemctl restart`, and enough to catch state that only ever
    lived in memory."""
    return build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


class TestDefaults:
    def test_a_fresh_patient_is_not_opted_out_and_has_no_window(self, harness: ApiHarness) -> None:
        """No row yet is not an error and not an invented window: it is the
        honest "the patient has said nothing"."""
        response = harness.client.get(PATH, headers=harness.patient())
        assert response.status_code == 200
        assert response.json() == {"opted_out": False, "quiet_start": None, "quiet_end": None}


class TestPatientControl:
    def test_a_patient_sets_a_window_and_reads_it_back(self, harness: ApiHarness) -> None:
        put = harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": False, "quiet_start": "22:00", "quiet_end": "08:00"},
        )
        assert put.status_code == 200
        assert put.json() == {
            "opted_out": False,
            "quiet_start": "22:00",
            "quiet_end": "08:00",
        }
        assert harness.client.get(PATH, headers=harness.patient()).json() == put.json()

    def test_opting_out_is_one_call_and_needs_no_window(self, harness: ApiHarness) -> None:
        """Withdrawal as easy as grant (files/06 §2): one field, one call."""
        response = harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": True, "quiet_start": None, "quiet_end": None},
        )
        assert response.status_code == 200
        assert response.json()["opted_out"] is True

    def test_a_second_write_replaces_rather_than_accumulating(self, harness: ApiHarness) -> None:
        harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": True, "quiet_start": "22:00", "quiet_end": "08:00"},
        )
        harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": False, "quiet_start": "23:30", "quiet_end": "07:15"},
        )
        assert harness.client.get(PATH, headers=harness.patient()).json() == {
            "opted_out": False,
            "quiet_start": "23:30",
            "quiet_end": "07:15",
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"opted_out": False, "quiet_start": "22:00", "quiet_end": None},
            {"opted_out": False, "quiet_start": None, "quiet_end": "08:00"},
            {"opted_out": False, "quiet_start": "22:00", "quiet_end": "22:00"},
            {"opted_out": False, "quiet_start": "24:00", "quiet_end": "08:00"},
            {"opted_out": False, "quiet_start": "9:00", "quiet_end": "08:00"},
        ],
    )
    def test_a_half_or_malformed_window_is_refused(
        self, harness: ApiHarness, body: dict[str, object]
    ) -> None:
        """Half a window is not a window: accepting one end and defaulting
        the other is exactly the invented value rule 1 forbids."""
        response = harness.client.put(PATH, headers=harness.patient(), json=body)
        assert response.status_code == 422
        assert "22:00" not in response.text, "a 422 must not echo the input back (inv. 6)"


class TestDurability:
    def test_the_setting_survives_a_restart(self, tmp_path: Path) -> None:
        first = _restart(tmp_path)
        harness = next(iter(first))
        harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": True, "quiet_start": "22:00", "quiet_end": "08:00"},
        )
        for _ in first:  # drain the generator: closes the client and engine
            pass

        second = _restart(tmp_path)
        restarted = next(iter(second))
        try:
            assert restarted.client.get(PATH, headers=restarted.patient()).json() == {
                "opted_out": True,
                "quiet_start": "22:00",
                "quiet_end": "08:00",
            }
        finally:
            for _ in second:
                pass


class TestAccess:
    def test_the_clinic_admin_has_no_notification_preferences(self, harness: ApiHarness) -> None:
        """A non-subject principal has no row here to read or write: this is
        the patient's own register, not a clinic setting."""
        assert harness.client.get(PATH, headers=harness.admin()).status_code == 403
        assert (
            harness.client.put(
                PATH,
                headers=harness.admin(),
                json={"opted_out": True, "quiet_start": None, "quiet_end": None},
            ).status_code
            == 403
        )

    def test_an_unauthenticated_caller_gets_nothing(self, harness: ApiHarness) -> None:
        assert harness.client.get(PATH).status_code == 401

    def test_withdrawing_core_does_not_lock_the_patient_out_of_the_switch(
        self, harness: ApiHarness
    ) -> None:
        """The whole reason this surface carries a marker rather than a
        scope. A patient who withdrew everything must still be able to say
        "stop messaging me" — and to see that we heard."""
        harness.revoke_consent("core")
        assert harness.client.get(PATH, headers=harness.patient()).status_code == 200
        assert (
            harness.client.put(
                PATH,
                headers=harness.patient(),
                json={"opted_out": True, "quiet_start": None, "quiet_end": None},
            ).status_code
            == 200
        )


class TestDeclarationAndAudit:
    def test_the_routes_declare_themselves_to_the_consent_scan(self, harness: ApiHarness) -> None:
        app = harness.client.app
        assert isinstance(app, FastAPI)
        assert unguarded_data_routes(app) == []
        assert notification_preference_routes(app) == [
            "GET /v1/me/notifications",
            "PUT /v1/me/notifications",
        ]
        for route in notification_preference_routes(app):
            assert route.split(" ", 1)[1].startswith(NOTIFICATION_PREFERENCE_PREFIX)

    def test_the_marker_cannot_be_borrowed_outside_its_prefix(self) -> None:
        """Near-miss negative control, the same shape the other four cages
        carry: a data route elsewhere that mounts this marker is still
        reported as undeclared, and a lookalike prefix does not qualify."""
        app = FastAPI()

        @app.get("/v1/sneaky", dependencies=[notification_preference()])
        async def sneaky() -> dict[str, str]:
            return {}

        @app.get("/v1/me/notificationsish", dependencies=[notification_preference()])
        async def lookalike() -> dict[str, str]:
            return {}

        assert sorted(unguarded_data_routes(app)) == [
            "GET /v1/me/notificationsish",
            "GET /v1/sneaky",
        ]

    def test_every_change_is_audited_and_carries_no_content(self, harness: ApiHarness) -> None:
        harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": True, "quiet_start": "22:00", "quiet_end": "08:00"},
        )
        entries = harness.audit_store.entries()
        actions = [entry.action for entry in entries]
        assert "api.notification_prefs.update" in actions
        for entry in entries:
            assert "22:00" not in entry.resource_ref
            assert str(DEV_PATIENT_ID) in entry.resource_ref or entry.resource_ref.startswith(
                ("visit:", "tenant:", "patient:")
            )


class TestInventory:
    def test_the_new_table_is_registered_and_fully_annotated(self) -> None:
        """Invariant 18: a new persisted field with no {category, purpose,
        basis, retention, recipients} is a field nobody can defend."""
        table = Base.metadata.tables["notification_preferences"]
        for column in table.columns:
            annotation = column.info.get(INVENTORY_KEY)
            assert isinstance(annotation, dict), column.name
            assert set(annotation) == set(INVENTORY_FIELDS), column.name

    def test_the_preference_row_is_operational_metadata_not_health_data(self) -> None:
        table = Base.metadata.tables["notification_preferences"]
        for column in table.columns:
            assert column.info[INVENTORY_KEY]["category"] == "operational_metadata"

    def test_the_row_holds_no_identifier_and_no_free_text(self) -> None:
        """A quiet window is two integers and a flag. Nothing here is a
        phone number, a device token or a narrative (invariant 14)."""
        table = Base.metadata.tables["notification_preferences"]
        assert set(table.columns.keys()) == {
            "id",
            "tenant_id",
            "patient_id",
            "opted_out",
            "quiet_start_minute",
            "quiet_end_minute",
            "updated_at",
        }
        assert NotificationPreference.__tablename__ == "notification_preferences"

    def test_the_row_is_keyed_one_per_patient_per_tenant(self) -> None:
        table = Base.metadata.tables["notification_preferences"]
        unique = [
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]
        assert ("patient_id", "tenant_id") in unique

    def test_the_migration_brings_its_own_rls(self) -> None:
        """A tenant-scoped table added by a later revision that forgets RLS
        is a table the scan reports the strongest possible pass for."""
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (Path(__file__).resolve().parents[2] / "migrations" / "versions").glob("*.py")
            )
        )
        for statement in (
            "ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE notification_preferences FORCE ROW LEVEL SECURITY",
            "CREATE POLICY notification_preferences_tenant_isolation",
        ):
            assert statement in source


class TestTenantIsolation:
    def test_a_foreign_tenants_row_is_never_read(self, harness: ApiHarness) -> None:
        """Query-level isolation in the unit lane; RLS proves the same live
        in the integration lane."""
        harness.client.put(
            PATH,
            headers=harness.patient(),
            json={"opted_out": True, "quiet_start": "22:00", "quiet_end": "08:00"},
        )
        _seed_foreign_preference(harness)
        assert harness.client.get(PATH, headers=harness.patient()).json()["opted_out"] is True


def _seed_foreign_preference(harness: ApiHarness) -> None:
    from api_harness import run
    from sqlalchemy.ext.asyncio import AsyncSession

    async def _seed() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            session.add(
                NotificationPreference(
                    tenant_id=uuid.uuid4(),
                    patient_id=DEV_PATIENT_ID,
                    opted_out=False,
                    quiet_start_minute=None,
                    quiet_end_minute=None,
                )
            )

    run(_seed())
