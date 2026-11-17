"""Shared wiring for the Acıbadem read-connector suite.

A module rather than a ``conftest.py`` for the same reason
``connector_harness.py`` is one: both test files must build the *same* source
row and the *same* client, so one file's assumptions cannot drift from the
other's.

Everything here is fixture material. The credential value is deliberately
low-entropy and unstructured — INT-139 tripped the INT-019 gitleaks gate with
a fixture that merely *looked* like a token, and the fix for that is a boring
fixture, never an allow-list entry.

The three recorded payloads live in this module rather than under
``tests/fixtures/`` for the same reason the credential values do, and it is a
rule of this repository rather than a convenience: a checksum-valid TC Kimlik
is indistinguishable from a real one, so ``scripts/ci/phi_scan.sh`` refuses
the whole of ``tests/fixtures/**`` and ``docs/**`` outside an allow-list that
may only shrink. Synthetic checksum-valid identifiers therefore live in *test
code*, which is where ``tests/research/test_export_gates.py`` and
``tests/infra/test_ci_no_phi.py`` already keep theirs.

Nothing here is real. The numbers are constructed to satisfy the published
check digits and belong to nobody; the *shapes* are transcribed from a probe
of the live schema — the twelve-character ``905`` mobile spelling, the
null-heavy TC column, the ``DD-MM-YYYY`` dates, the ``HH:MM``
``randevu_saati``, the five-minute ``start_time`` slot index including the
sentinel that decodes to ``25:00``, a visit from 2021 because the per-patient
endpoint returns the whole history, and one handset shared by two patients
with the same surname.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import httpx
from intake_connectors.acibadem import AcibademAppointmentsClient
from intake_connectors.credentials import InMemoryCredentialResolver
from intake_connectors.sender import ConsentVerdict
from intake_connectors.sources import ClinicalSource

TENANT = "tenant-acibadem"
SOURCE_ID = "acibadem-appointments-lan"
CREDENTIAL_REF = "connectors/tenant-acibadem/acibadem-appointments-lan/api-key"
FAKE_API_KEY = "fixture-key-material"

#: The measured upstream: an on-premises host addressed by its private IPv4
#: literal, over plaintext HTTP, on a non-standard port. Every one of those
#: three properties is refused by the vendor allow-list, which is why this
#: source class exists at all (see intake_connectors.sources).
ADDRESS = "10.150.0.42"
PORT = 8091


UPCOMING: dict[str, Any] = {
    "date_range": {"from": "2026-09-04", "to": "2026-09-06"},
    "count": 8,
    "data": [
        {
            "patient_number": "40000001",
            "patient_name": "MEHMET",
            "patient_surname": "YILMAZ",
            "cell_phone": "905321110001",
            "tckimlik_no": "10000000146",
        },
        {
            "patient_number": "40000002",
            "patient_name": "AYSE",
            "patient_surname": "YILMAZ",
            "cell_phone": "905321110001",
            "tckimlik_no": "12345678950",
        },
        {
            "patient_number": "40000003",
            "patient_name": "FATMA",
            "patient_surname": "KAYA",
            "cell_phone": "905321110003",
            "tckimlik_no": None,
        },
        {
            "patient_number": "40000004",
            "patient_name": "ALI",
            "patient_surname": "DEMIR",
            "cell_phone": "905321110004",
            "tckimlik_no": None,
        },
        {
            "patient_number": "40000005",
            "patient_name": "ZEYNEP",
            "patient_surname": "CELIK",
            "cell_phone": None,
            "tckimlik_no": "22222222220",
        },
        {
            "patient_number": "40000006",
            "patient_name": "CAN",
            "patient_surname": "OZTURK",
            "cell_phone": "905321110006",
            "tckimlik_no": "31415926562",
        },
        {
            "patient_number": "40000007",
            "patient_name": "EMRE",
            "patient_surname": "ARSLAN",
            "cell_phone": "905321110007",
            "tckimlik_no": None,
        },
        {
            "patient_number": "40000008",
            "patient_name": "SELIN",
            "patient_surname": "ARSLAN",
            "cell_phone": "905321110007",
            "tckimlik_no": None,
        },
    ],
}

PATIENT_DETAIL: dict[str, Any] = {
    "patient_number": "40000003",
    "count": 3,
    "data": [
        {
            "patient_number": "40000003",
            "tckimlik_no": None,
            "app_date": "05-09-2026",
            "start_time": 156,
            "unplanned_app": None,
            "doctor_id": 31663,
            "cell_phone": "905321110003",
            "patient_name": "FATMA",
            "patient_surname": "KAYA",
            "facility_name": "Acıbadem Hst. Ataşehir",
            "specialty_name": "Kardiyoloji",
            "randevu_saati": "13:00",
        },
        {
            "patient_number": "40000003",
            "tckimlik_no": None,
            "app_date": "05-09-2026",
            "start_time": 300,
            "unplanned_app": "13:05",
            "doctor_id": 79072,
            "cell_phone": "905321110003",
            "patient_name": "FATMA",
            "patient_surname": "KAYA",
            "facility_name": "Acıbadem Hst. Ataşehir",
            "specialty_name": "Kadın Hastalıkları ve Doğum",
            "randevu_saati": "13:05",
        },
        {
            "patient_number": "40000003",
            "tckimlik_no": None,
            "app_date": "11-10-2021",
            "start_time": 99,
            "unplanned_app": None,
            "doctor_id": None,
            "cell_phone": "905321110003",
            "patient_name": "FATMA",
            "patient_surname": "KAYA",
            "facility_name": "Acıbadem Hst. Kartal",
            "specialty_name": "Göz Hastalıkları",
            "randevu_saati": "08:15",
        },
    ],
}

PATIENT_DETAIL_WITH_A_FOREIGN_ROW: dict[str, Any] = {
    "patient_number": "40000006",
    "count": 2,
    "data": [
        {
            "patient_number": "40000006",
            "tckimlik_no": "31415926562",
            "app_date": "06-09-2026",
            "start_time": 120,
            "unplanned_app": None,
            "doctor_id": 79072,
            "cell_phone": "905321110006",
            "patient_name": "CAN",
            "patient_surname": "OZTURK",
            "facility_name": "Acıbadem Hst. Altunizade",
            "specialty_name": "İç Hastalıkları",
            "randevu_saati": "10:00",
        },
        {
            "patient_number": "40000004",
            "tckimlik_no": None,
            "app_date": "06-09-2026",
            "start_time": 126,
            "unplanned_app": None,
            "doctor_id": 31663,
            "cell_phone": "905321110004",
            "patient_name": "ALI",
            "patient_surname": "DEMIR",
            "facility_name": "Acıbadem Hst. Altunizade",
            "specialty_name": "Ortopedi ve Travmatoloji",
            "randevu_saati": "10:30",
        },
    ],
}


_PAYLOADS: dict[str, dict[str, Any]] = {
    "upcoming.json": UPCOMING,
    "patient_40000003.json": PATIENT_DETAIL,
    "patient_40000006_foreign_row.json": PATIENT_DETAIL_WITH_A_FOREIGN_ROW,
}


def load(name: str) -> dict[str, Any]:
    """One recorded payload, deep-copied so a mutating test cannot reach the next."""
    return copy.deepcopy(_PAYLOADS[name])


def source(**overrides: object) -> ClinicalSource:
    base: dict[str, object] = {
        "source_id": SOURCE_ID,
        "tenant_id": TENANT,
        "adapter_id": "acibadem-appointments",
        "address": ADDRESS,
        "port": PORT,
        "protocol": "http",
        "base_path": "",
        "consent_scope": "core",
        "credential_ref": CREDENTIAL_REF,
        "dpa_ref": "DPA-FIXTURE-1",
        "approval_ref": "APPROVAL-FIXTURE-1",
        "plaintext_approval": "APPROVAL-FIXTURE-PLAINTEXT-1",
    }
    base.update(overrides)
    return ClinicalSource.model_validate(base)


def credentials(document: Mapping[str, str] | None = None) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        {CREDENTIAL_REF: dict(document) if document is not None else {"api_key": FAKE_API_KEY}}
    )


def granted(**_: object) -> ConsentVerdict:
    return ConsentVerdict(allowed=True, scope="core", reason="granted")


def denied(**_: object) -> ConsentVerdict:
    return ConsentVerdict(allowed=False, scope="core", reason="absent")


def client(
    handler: httpx.MockTransport,
    *,
    src: ClinicalSource | None = None,
    resolver: InMemoryCredentialResolver | None = None,
    **kwargs: object,
) -> AcibademAppointmentsClient:
    return AcibademAppointmentsClient(
        source=src if src is not None else source(),
        credentials=resolver if resolver is not None else credentials(),
        transport=handler,
        **kwargs,  # type: ignore[arg-type]
    )


def json_route(routes: Mapping[str, tuple[int, object]]) -> httpx.MockTransport:
    """A transport that answers exactly the paths it is given, and 404s the rest.

    Requests are keyed by path alone: the whole point of several tests is that
    the client aimed at the registered address and nowhere else, and a route
    table keyed by URL would make that assertion vacuous.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        entry = routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, json={"detail": "no such fixture route"})
        status, body = entry
        if isinstance(body, (bytes, str)):
            return httpx.Response(
                status, content=body, headers={"content-type": "application/json"}
            )
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)
