"""Shared fixtures for the INT-162 inbound HBYS/SBYS adapter-kit suite.

A module rather than a ``conftest.py`` for the same reason the outbound
``connector_harness`` is one: every inbound test imports the *same* registered
source row and the *same* sample HL7v2 message by name, so no two files can
drift on what "a registered source" or "an ORU message" looks like.

Everything here is fixture material and never ships. The HL7 sample is
synthetic: the patient name and the analyte values are invented for the test
and are deliberately unremarkable, because a fixture that carried a real
identifier would be the exact leak invariant 6 forbids.
"""

from __future__ import annotations

from collections.abc import Sequence

from intake_connectors.inbound import InboundSource, InboundSourceRegistry

TENANT = "tenant-acibadem"
SOURCE_ID = "acibadem-hbys-oru"
FILE_SOURCE_ID = "acibadem-hbys-filedrop"


def inbound_source(**overrides: object) -> InboundSource:
    base: dict[str, object] = {
        "source_id": SOURCE_ID,
        "tenant_id": TENANT,
        "channel_id": "hl7v2-oru",
        "transport": "mtls",
        "consent_scope": "ingest.hospital_result",
        "dpa_ref": "DPA-FIXTURE-1",
        "approval_ref": "APPROVAL-FIXTURE-1",
    }
    base.update(overrides)
    return InboundSource.model_validate(base)


def registry_of(*rows: InboundSource) -> InboundSourceRegistry:
    return InboundSourceRegistry(rows)


#: A minimal, well-formed ORU^R01 in ER7 encoding. Segment terminator is the
#: HL7 carriage return; the encoding characters are declared in MSH-2 and read
#: from the message rather than assumed. Two OBX results: a glucose (numeric)
#: and a text observation, so a test can exercise both value types.
SAMPLE_ORU = (
    "MSH|^~\\&|LIS|ACIBADEM|INTAKE|VIZITE|20260901101500||ORU^R01|MSG00001|P|2.5.1\r"
    "PID|1||PT0F3A^^^ACIBADEM^MR||DENEME^HASTA||19800101|M\r"
    "OBR|1||ORD-42|1552^Glukoz^L|||20260901090000\r"
    "OBX|1|NM|14749-6^Glucose^LN||95|mg/dL|70-110|N|||F|||20260901093000\r"
    "OBX|2|ST|55233-1^Note^LN||stabil||||||F\r"
)


def oru_bytes(text: str = SAMPLE_ORU) -> bytes:
    return text.encode("utf-8")


def dns_table(hosts: Sequence[str]) -> dict[str, Sequence[str]]:
    return {host: ("203.0.113.20",) for host in hosts}
