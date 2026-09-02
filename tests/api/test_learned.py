"""INT-170 — ``/v1/me/learned``: *Me → Hakkımda öğrendikleri* (files/09 §3).

The route is the patient's own view of what the system has learned about
them, and the surface through which they confirm, re-confirm, re-scope and
delete it. Three properties make it a data route like any other:

- **Invariant 4** — it is a read of clinical data, so it goes through the ONE
  ``ensure_consent`` path under ``core``. A withdrawn consent closes it; a
  refused read is not a read and is not audited.
- **Invariant 6** — every audit entry, every error body and every log line
  carries ids. A fact's value never appears in any of them.
- **Invariant 12** — the route cannot mint a clinician provenance. The request
  body carries no ``source`` field at all: the patient's principal supplies
  the confirming actor and the body picks between the two provenances a
  patient can establish, so ``clinician_accepted_note`` is unspellable here
  rather than filtered.

Every key, value and Turkish string below is synthetic (files/04 §7).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from api_harness import ApiHarness, run
from intake_api.consent_guard import route_policies
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_api.dsar.shred import execute_due_shreds
from intake_api.dsar.sla import SHRED_GRACE
from intake_platform.db.envelope_json import encrypted_field_from_json
from intake_platform.db.inventory import INVENTORY_FIELDS, INVENTORY_KEY
from intake_platform.db.models import Base, OverlayFact, PatientOverlayHeader
from intake_platform.envelope import CryptoShredError, shred_field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PATH = "/v1/me/learned"

#: The planted adversary (INT-175 via INT-172/INT-205), so this gate agrees
#: with every other PHI gate in the tree on what patient narrative looks like.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."


def _body(
    key: str = "oyku.belirti_var",
    value: object = True,
    *,
    origin: str = "intake_extraction",
    origin_ref: str = "sentetik-oturum",
    source_ref: str = "sentetik-onay-karti",
    confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "key": key,
        "value": value,
        "origin": origin,
        "origin_ref": origin_ref,
        "source_ref": source_ref,
        "confidence": confidence,
        "observed_at": "2026-08-30T09:00:00Z",
    }


def _rows[Row](harness: ApiHarness, model: type[Row]) -> list[Row]:
    """Every row of one table, read straight from the database."""

    async def _read() -> list[Row]:
        async with AsyncSession(harness.engine) as session:
            return list(await session.scalars(select(model)))

    result: list[Row] = run(_read())
    return result


def _blob(value: object) -> str:
    """Decoded, so an ASCII-escaped Turkish sentence cannot pass the sweep."""
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


class TestProvenanceIsShown:
    def test_a_fresh_patient_has_an_empty_versioned_overlay(self, harness: ApiHarness) -> None:
        response = harness.client.get(PATH, headers=harness.patient())
        assert response.status_code == 200
        assert response.json() == {"version": 1, "facts": []}

    def test_a_confirmed_fact_comes_back_with_its_where_from(self, harness: ApiHarness) -> None:
        """files/09 §3: "every learned fact shows 'where from'"."""
        posted = harness.client.post(PATH, headers=harness.patient(), json=_body())
        assert posted.status_code == 201

        listed = harness.client.get(PATH, headers=harness.patient())
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["version"] == 2
        assert len(payload["facts"]) == 1
        fact = payload["facts"][0]
        confirmed_at = fact.pop("confirmed_at")
        assert fact == {
            "key": "oyku.belirti_var",
            "value": True,
            "source": "confirmed_intake_extraction",
            "source_ref": "sentetik-onay-karti",
            "confirmed_by": "patient",
            "confidence": 0.9,
            "shared": True,
            "needs_reconfirmation": False,
        }
        # the confirmation instant is when the PATIENT confirmed, never the
        # instant the proposal was observed: the twelve-month clock runs from
        # the human act (files/09 §3), so a year-old draft confirmed today is
        # in date and a fact confirmed a year ago is not.
        assert datetime.fromisoformat(confirmed_at) > datetime.fromisoformat(
            _body()["observed_at"].replace("Z", "+00:00")  # type: ignore[union-attr]
        )

    def test_the_patient_can_re_scope_and_delete_a_fact(self, harness: ApiHarness) -> None:
        harness.client.post(PATH, headers=harness.patient(), json=_body())

        rescope = harness.client.patch(
            f"{PATH}/oyku.belirti_var", headers=harness.patient(), json={"shared": False}
        )
        assert rescope.status_code == 200
        assert rescope.json()["shared"] is False

        deleted = harness.client.delete(f"{PATH}/oyku.belirti_var", headers=harness.patient())
        assert deleted.status_code == 204
        assert harness.client.get(PATH, headers=harness.patient()).json()["facts"] == []
        assert (
            harness.client.delete(f"{PATH}/oyku.belirti_var", headers=harness.patient()).status_code
            == 404
        )


class TestConfirmationRules:
    def test_the_route_cannot_mint_a_clinician_provenance(self, harness: ApiHarness) -> None:
        """Invariant 12: a patient confirms a patient provenance. The clinician
        one is established by note acceptance, not by a request body, and it is
        not a value this endpoint's ``origin`` vocabulary can carry."""
        response = harness.client.post(
            PATH, headers=harness.patient(), json=_body(origin="clinician_accepted_note")
        )
        assert response.status_code == 422

    def test_a_source_field_in_the_body_is_refused_outright(self, harness: ApiHarness) -> None:
        body = _body()
        body["source"] = "clinician_accepted_note"
        assert harness.client.post(PATH, headers=harness.patient(), json=body).status_code == 422

    def test_an_imported_record_is_the_other_patient_confirmable_provenance(
        self, harness: ApiHarness
    ) -> None:
        response = harness.client.post(
            PATH, headers=harness.patient(), json=_body(origin="imported_record")
        )
        assert response.status_code == 201
        facts = harness.client.get(PATH, headers=harness.patient()).json()["facts"]
        assert facts[0]["source"] == "confirmed_imported_record"
        assert facts[0]["confirmed_by"] == "patient"

    def test_re_confirming_replaces_the_fact_and_bumps_the_version(
        self, harness: ApiHarness
    ) -> None:
        harness.client.post(PATH, headers=harness.patient(), json=_body(value=True))
        harness.client.post(PATH, headers=harness.patient(), json=_body(value=False))
        payload = harness.client.get(PATH, headers=harness.patient()).json()
        assert payload["version"] == 3
        assert len(payload["facts"]) == 1
        assert payload["facts"][0]["value"] is False

    def test_a_clinic_admin_cannot_read_the_patients_learned_facts(
        self, harness: ApiHarness
    ) -> None:
        """The overlay is patient-owned (files/09 §3). The clinic side sees a
        SHARED note, never the learning object behind it."""
        harness.client.post(PATH, headers=harness.patient(), json=_body())
        assert harness.client.get(PATH, headers=harness.admin()).status_code == 403


class TestConsentAndAudit:
    def test_the_routes_declare_the_core_scope(self, harness: ApiHarness) -> None:
        policies = route_policies(harness.client.app)  # type: ignore[arg-type]
        declared = {path: policy for (_, path), policy in policies.items() if path.startswith(PATH)}
        assert declared, "the /v1/me/learned routes declare no consent policy"
        for policy in declared.values():
            assert "core" in policy.enforced

    def test_a_withdrawn_core_consent_closes_the_surface_and_audits_nothing(
        self, harness: ApiHarness
    ) -> None:
        harness.client.post(PATH, headers=harness.patient(), json=_body())
        harness.revoke_consent("core")
        before = len(harness.audit_store.entries())

        response = harness.client.get(PATH, headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "consent_required", "scope": "core"}
        # a refused read is not a read: nothing was disclosed, nothing to audit
        assert len(harness.audit_store.entries()) == before

    def test_every_read_and_every_change_lands_on_the_hash_chain(self, harness: ApiHarness) -> None:
        harness.client.post(PATH, headers=harness.patient(), json=_body())
        harness.client.get(PATH, headers=harness.patient())
        harness.client.patch(
            f"{PATH}/oyku.belirti_var", headers=harness.patient(), json={"shared": False}
        )
        harness.client.delete(f"{PATH}/oyku.belirti_var", headers=harness.patient())

        actions = [entry.action for entry in harness.audit_store.entries()]
        for action in (
            "api.learned.confirm",
            "api.learned.read",
            "api.learned.rescope",
            "api.learned.forget",
        ):
            assert action in actions

    def test_no_fact_value_reaches_the_audit_chain(self, harness: ApiHarness) -> None:
        harness.client.post(
            PATH, headers=harness.patient(), json=_body(key="oyku.not_metni", value=TURKISH_SYMPTOM)
        )
        harness.client.get(PATH, headers=harness.patient())
        entries = harness.audit_store.entries()
        blob = _blob(
            [
                {
                    "actor": entry.actor,
                    "action": entry.action,
                    "resource_ref": entry.resource_ref,
                    "consent_scope_ref": entry.consent_scope_ref,
                }
                for entry in entries
            ]
        )
        for probe in (TURKISH_SYMPTOM, "Göğsümde", "ağrı"):
            assert probe not in blob
        assert any(entry.resource_ref == f"patient:{DEV_PATIENT_ID}" for entry in entries)


class TestInventory:
    def test_the_new_tables_are_registered_and_fully_annotated(self) -> None:
        for name in ("patient_overlays", "overlay_facts"):
            table = Base.metadata.tables[name]
            for column in table.columns:
                annotation = column.info.get(INVENTORY_KEY)
                assert isinstance(annotation, dict), f"{name}.{column.name}"
                assert set(annotation) == set(INVENTORY_FIELDS), f"{name}.{column.name}"

    def test_the_fact_value_column_is_health_data_on_the_record_clock(self) -> None:
        table = Base.metadata.tables["overlay_facts"]
        payload = table.columns["payload"].info[INVENTORY_KEY]
        assert payload["category"] == "special_category_health"
        assert "EncryptedField" in payload["purpose"]

    def test_the_tables_hold_no_direct_identifier(self) -> None:
        assert PatientOverlayHeader.__tablename__ == "patient_overlays"
        assert OverlayFact.__tablename__ == "overlay_facts"
        assert set(Base.metadata.tables["overlay_facts"].columns.keys()) == {
            "id",
            "tenant_id",
            "patient_id",
            "fact_key",
            "payload",
            "source",
            "source_ref",
            "confirmed_at",
            "shared",
            "created_at",
        }


class TestErasure:
    """KVKK m.11 (the issue's ``legal`` row) — a learned fact is part of the
    subject's record, so an erasure has to reach it.

    files/09 §3 makes the overlay *"patient-owned, exported/deletable"*. An
    erasure that swept the notes and the slots but left the learning object
    standing would leave behind exactly the health data the patient asked us to
    destroy, and it would do it in the one place nobody thinks to look.
    """

    def test_a_dsar_erasure_crypto_shreds_and_removes_the_learned_facts(
        self, harness: ApiHarness
    ) -> None:
        harness.client.post(
            PATH,
            headers=harness.patient(),
            json=_body(key="oyku.not_metni", value=TURKISH_SYMPTOM),
        )
        before = _rows(harness, OverlayFact)
        assert len(before) == 1
        payload_before = dict(before[0].payload)
        assert _rows(harness, PatientOverlayHeader)

        filed = harness.client.post("/v1/me/dsar/delete", headers=harness.patient())
        assert filed.status_code == 201, filed.text
        report = run(
            execute_due_shreds(
                harness.engine,
                tenant_id=DEV_TENANT_ID,
                audit=harness.client.app.state.api.audit,  # type: ignore[attr-defined]
                remove_object=lambda ref: None,
                now=datetime.now(UTC) + SHRED_GRACE + timedelta(minutes=1),
            )
        )
        assert report.shredded_requests == 1

        # crypto-shred first: the ciphertext captured before the run can never
        # be opened again, even from a copy of the row
        with pytest.raises(CryptoShredError):
            harness.cipher.decrypt_field(
                str(DEV_TENANT_ID), shred_field(encrypted_field_from_json(payload_before))
            )
        # then the rows go, header included
        assert _rows(harness, OverlayFact) == []
        assert _rows(harness, PatientOverlayHeader) == []
