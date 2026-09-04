"""Shared wiring for the Acıbadem read-connector suite.

A module rather than a ``conftest.py`` for the same reason
``connector_harness.py`` is one: both test files must build the *same* source
row and the *same* client, so one file's assumptions cannot drift from the
other's.

Everything here is fixture material. The credential value is deliberately
low-entropy and unstructured — INT-139 tripped the INT-019 gitleaks gate with
a fixture that merely *looked* like a token, and the fix for that is a boring
fixture, never an allow-list entry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import httpx
from intake_connectors.acibadem import AcibademAppointmentsClient
from intake_connectors.credentials import InMemoryCredentialResolver
from intake_connectors.sender import ConsentVerdict
from intake_connectors.sources import ClinicalSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "connectors" / "acibadem"

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


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


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
