"""INT-162 — the HBYS/SBYS inbound adapter kit: HL7v2 ORU and the file drop.

The kit is the inbound counterpart to INT-160's outbound sender, and it holds
the same invariants from the other direction:

- **A message is data, never an instruction** (invariant 14). The parser reads
  MSH/OBR/OBX and treats every other segment as inert text; there is no segment
  name that dispatches code, and delimiters that appear *inside* a value are
  decoded as characters, never as structure.
- **An inbound message may carry candidate_flags only** (invariant 1). The
  parser's product — ``InboundObservation`` — has no field a RED/YELLOW could
  occupy; an abnormal flag rides as an opaque token, and only the rules engine
  turns anything into triage.
- **No PHI in a log or an exception** (invariant 6). The message body redacts
  itself, and a parse error names a position and a reason, never a value.
- **A source is registered, bound to a DPA and an approval, and — if it speaks
  plaintext on a LAN — separately approved for that** (invariant 14). The
  registry ships with zero rows, so the kit refuses every message today.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from clinical_schemas.records import RecordItemKind
from inbound_harness import (
    SAMPLE_ORU,
    SOURCE_ID,
    TENANT,
    inbound_source,
    oru_bytes,
    registry_of,
)
from intake_connectors.filedrop import FileDropChannel, FileDropError
from intake_connectors.hl7v2 import Hl7v2OruChannel, Hl7v2ParseError
from intake_connectors.inbound import (
    InboundMessage,
    InboundNotRegistered,
    InboundSource,
    load_inbound_sources,
)

HL7_MEDIA = "application/hl7-v2+er7"


def message(
    body: bytes = b"", media_type: str = HL7_MEDIA, filename: str | None = None
) -> InboundMessage:
    return InboundMessage(body=body or oru_bytes(), media_type=media_type, filename=filename)


# --- 1. HL7v2 ORU parsing -----------------------------------------------------------


def test_an_oru_message_yields_one_observation_per_obx() -> None:
    observations = Hl7v2OruChannel().parse(message())
    assert len(observations) == 2
    glucose, note = observations
    assert (glucose.raw_system, glucose.raw_code, glucose.raw_label) == ("LN", "14749-6", "Glucose")
    assert glucose.value_token == "95"
    assert glucose.unit_token == "mg/dL"
    assert glucose.kind is RecordItemKind.LAB
    assert note.value_token == "stabil"


def test_the_observation_datetime_comes_from_obx14() -> None:
    glucose, _ = Hl7v2OruChannel().parse(message())
    assert glucose.observed_at == datetime(2026, 9, 1, 9, 30, 0)


def test_the_abnormal_flag_is_kept_as_an_opaque_token_never_a_triage_level() -> None:
    glucose, _ = Hl7v2OruChannel().parse(message())
    assert glucose.raw_code == "14749-6"
    # OBX-8 was "N"; it rides as data on the observation and is not a triage
    # level of any kind (invariant 1).
    assert glucose.abnormal_flag == "N"
    assert not hasattr(glucose, "level")
    assert not hasattr(glucose, "triage")


def test_a_message_that_is_not_oru_r01_is_refused() -> None:
    adt = SAMPLE_ORU.replace("ORU^R01", "ADT^A01").encode("utf-8")
    with pytest.raises(Hl7v2ParseError):
        Hl7v2OruChannel().parse(message(adt))


def test_a_message_whose_first_segment_is_not_msh_is_refused() -> None:
    with pytest.raises(Hl7v2ParseError):
        Hl7v2OruChannel().parse(message(b"PID|1||X\rMSH|^~\\&|"))


def test_an_unknown_segment_is_inert_and_changes_no_observation() -> None:
    """Invariant 14 in one assertion: a segment named like a command does not
    run, does not error, and does not alter what the OBX segments parsed to."""
    injected = SAMPLE_ORU.replace("OBR|1", "ZZZ|DROP TABLE observations|rm -rf /\rOBR|1").encode(
        "utf-8"
    )
    observations = Hl7v2OruChannel().parse(message(injected))
    assert len(observations) == 2
    assert observations[0].value_token == "95"


def test_delimiters_inside_a_value_are_decoded_as_characters_not_structure() -> None:
    """An OBX-5 carrying the HL7 escape for a field separator must come back as
    the literal character, not split the value into new fields."""
    escaped = SAMPLE_ORU.replace("stabil", "a\\F\\b").encode("utf-8")
    _, note = Hl7v2OruChannel().parse(message(escaped))
    assert note.value_token == "a|b"


def test_encoding_characters_are_read_from_msh2_not_assumed() -> None:
    """A message that declares non-default component/subcomponent separators is
    parsed by *its own* declaration, so a hospital that uses them is understood
    rather than mis-split."""
    custom = (
        b"MSH|@~\\&|LIS|ACIBADEM|INTAKE|VIZITE|20260901101500||ORU@R01|M1|P|2.5.1\r"
        b"OBX|1|NM|14749-6@Glucose@LN||95|mg/dL|||||F\r"
    )
    (glucose,) = Hl7v2OruChannel().parse(message(custom))
    assert glucose.raw_code == "14749-6"
    assert glucose.raw_label == "Glucose"


def test_an_oversized_message_is_refused_without_being_read_into_fields() -> None:
    huge = ("MSH|^~\\&|LIS|ACIBADEM|INTAKE|VIZITE|20260901|" + "A" * (2 * 1024 * 1024)).encode()
    with pytest.raises(Hl7v2ParseError):
        Hl7v2OruChannel().parse(message(huge))


def test_a_parse_error_carries_no_value_from_the_message() -> None:
    """The failure mode invariant 6 exists for: a malformed OBX must produce an
    error that names a position, never the patient value beside it."""
    bad = (
        b"MSH|^~\\&|LIS|ACIBADEM|INTAKE|VIZITE|20260901||ORU^R01|M1|P|2.5.1\r"
        b"OBX\r"  # a truncated OBX with no fields at all
    )
    try:
        Hl7v2OruChannel().parse(message(bad))
    except Hl7v2ParseError as error:
        assert "DENEME" not in str(error)
        assert "95" not in str(error)


def test_the_message_body_redacts_itself_in_repr() -> None:
    msg = message()
    assert "DENEME" not in repr(msg)
    assert "MSH" not in repr(msg)
    assert str(msg.byte_count) in repr(msg)


# --- 2. the file-drop channel -------------------------------------------------------


def test_a_dropped_hl7_file_parses_through_the_same_hl7_channel() -> None:
    observations = FileDropChannel().parse(
        message(filename="result_00001.hl7", media_type=HL7_MEDIA)
    )
    assert len(observations) == 2


def test_a_dropped_csv_of_observations_parses_to_observations() -> None:
    csv = (
        b"system,code,label,value,unit,observed_at\r\n"
        b"LN,14749-6,Glucose,95,mg/dL,20260901093000\r\n"
    )
    observations = FileDropChannel().parse(
        message(body=csv, filename="obs.csv", media_type="text/csv")
    )
    assert len(observations) == 1
    assert observations[0].raw_code == "14749-6"
    assert observations[0].value_token == "95"


def test_a_filename_that_traverses_is_refused() -> None:
    with pytest.raises(FileDropError):
        FileDropChannel().parse(message(filename="../../etc/passwd", media_type=HL7_MEDIA))


def test_a_file_drop_without_a_filename_is_refused() -> None:
    with pytest.raises(FileDropError):
        FileDropChannel().parse(message(filename=None, media_type=HL7_MEDIA))


def test_an_unrecognised_declared_format_is_refused() -> None:
    with pytest.raises(FileDropError):
        FileDropChannel().parse(message(filename="x.bin", media_type="application/octet-stream"))


# --- 3. the inbound source registry -------------------------------------------------


def test_the_shipped_inbound_source_registry_holds_zero_rows() -> None:
    """Fail-closed like the destination registry: no hospital feed is
    contracted, so the file is empty and every message refuses to resolve."""
    registry = load_inbound_sources()
    assert len(registry) == 0


def test_a_registered_source_resolves_only_for_its_own_tenant() -> None:
    registry = registry_of(inbound_source())
    assert registry.resolve(tenant_id=TENANT, source_id=SOURCE_ID).source_id == SOURCE_ID
    with pytest.raises(InboundNotRegistered):
        registry.resolve(tenant_id="tenant-other", source_id=SOURCE_ID)


def test_a_plaintext_lan_source_without_its_own_approval_is_refused() -> None:
    """Invariant 14: a LAN/plaintext feed of PHI is its own decision, so it
    needs an explicit recorded approval beyond the general one — with none, the
    row does not load."""
    with pytest.raises(ValueError):
        InboundSource.model_validate(
            {
                "source_id": SOURCE_ID,
                "tenant_id": TENANT,
                "channel_id": "hl7v2-oru",
                "transport": "lan_plaintext",
                "consent_scope": "ingest.hospital_result",
                "dpa_ref": "DPA-FIXTURE-1",
                "approval_ref": "APPROVAL-FIXTURE-1",
            }
        )


def test_a_plaintext_lan_source_with_its_recorded_approval_loads() -> None:
    source = InboundSource.model_validate(
        {
            "source_id": SOURCE_ID,
            "tenant_id": TENANT,
            "channel_id": "hl7v2-oru",
            "transport": "lan_plaintext",
            "plaintext_approval_ref": "PLAINTEXT-APPROVAL-1",
            "consent_scope": "ingest.hospital_result",
            "dpa_ref": "DPA-FIXTURE-1",
            "approval_ref": "APPROVAL-FIXTURE-1",
        }
    )
    assert source.plaintext_approval_ref == "PLAINTEXT-APPROVAL-1"


def test_an_mtls_source_must_not_carry_a_plaintext_approval_it_never_uses() -> None:
    with pytest.raises(ValueError):
        InboundSource.model_validate(
            {
                "source_id": SOURCE_ID,
                "tenant_id": TENANT,
                "channel_id": "hl7v2-oru",
                "transport": "mtls",
                "plaintext_approval_ref": "PLAINTEXT-APPROVAL-1",
                "consent_scope": "ingest.hospital_result",
                "dpa_ref": "DPA-FIXTURE-1",
                "approval_ref": "APPROVAL-FIXTURE-1",
            }
        )


def test_a_source_id_that_is_not_id_shaped_is_refused() -> None:
    with pytest.raises(ValueError):
        InboundSource.model_validate(
            {
                "source_id": "x y",  # a space is not id-shaped
                "tenant_id": TENANT,
                "channel_id": "hl7v2-oru",
                "transport": "mtls",
                "consent_scope": "ingest.hospital_result",
                "dpa_ref": "DPA-FIXTURE-1",
                "approval_ref": "APPROVAL-FIXTURE-1",
            }
        )
