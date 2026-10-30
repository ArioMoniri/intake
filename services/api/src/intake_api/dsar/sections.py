"""The DSAR export's section lines that read the record directly (INT-037;
INT-395).

Split from :mod:`intake_api.dsar.export` when INT-395 added the tables the
inventory annotations put under the subject's access right, so that module
stays under the 500-line ceiling (CLAUDE.md). The visit and note lines stay
there, because they render the decrypted views the FHIR resources are built
from. Everything here renders a row of the subject sweep
(:class:`~intake_api.dsar.store.SubjectRecord`) straight into its section.

Every line leads with ``<ref>:<id>`` and is built from sanitised cells
(invariant 47, :func:`intake_platform.export_safety.sanitise_cells`), so the
patient can name any row back to us, and nothing the patient or a third
party typed can become a spreadsheet formula on the way out.

Three things are deliberately NOT in a line:

- **a Doctor Link's recipient label.** It is the name of a third party, typed
  by the patient into an envelope. The line carries the recipient as a role,
  ``clinician`` — the same rule files/10 §3 sets for the access log over the
  same grant ("the patient sees a role, never a name") — and files/06 has no
  export clause that asks for more. The patient can still read the label on
  the link list itself (``GET …/note/doctor-links``).
- **a guardian's account reference**, for the same reason: it identifies the
  other person in the link, not the subject.
- **a record-index vector's numbers** (INT-123). The line names the row, the
  document and page it was read from, the item it indexes, its kind and the
  model; the coordinates are a model's encoding of an item the listed
  document already carries, and the sweep never loads them. Whether the reply
  should carry them is a reviewer's call, recorded in docs/evidence/INT-395.md.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from clinical_schemas.common import decode_json_value
from intake_platform.access_log import AccessorRole
from intake_platform.db.envelope_json import encrypted_field_from_json
from intake_platform.envelope import EnvelopeCipher
from intake_platform.export_safety import sanitise_cells
from intake_platform.notifications import QuietWindow
from intake_platform.records.numbers import render_quantity

from intake_api.dsar.store import SubjectRecord

__all__ = [
    "EXPORT_LOCALE",
    "decrypt_json",
    "learned_value_text",
    "previsit_output_lines",
    "record_section_lines",
]

#: The reader every number in a line is written for. The export's fixed
#: strings are Turkish (files/06 §7) and ``tr`` is the source of truth
#: (invariant 5), so a learned value of 38.5 reads ``38,5`` (invariant 22).
EXPORT_LOCALE: Final = "tr"


def decrypt_json(cipher: EnvelopeCipher, tenant_id: uuid.UUID, payload: Mapping[str, Any]) -> Any:
    return json.loads(_decrypt_text(cipher, tenant_id, payload))


def _decrypt_text(cipher: EnvelopeCipher, tenant_id: uuid.UUID, payload: Mapping[str, Any]) -> str:
    field = encrypted_field_from_json(payload)
    return cipher.decrypt_field(str(tenant_id), field).decode("utf-8")


def _stamp(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _line(cells: Iterable[object]) -> str:
    return " · ".join(sanitise_cells(cells))


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _number(value: Decimal | float) -> str:
    return render_quantity(
        value if isinstance(value, Decimal) else Decimal(str(value)), locale=EXPORT_LOCALE
    )


def learned_value_text(value: Any) -> str:
    """A learned fact's value, decoded from its INT-309 wire form and written
    for :data:`EXPORT_LOCALE`: a Decimal never reaches the line as ``~d38.5``."""
    if isinstance(value, bool):
        return _flag(value)
    if isinstance(value, Decimal | float):
        return _number(value)
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(learned_value_text(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}={learned_value_text(item)}" for key, item in sorted(value.items()))
    return str(value)


def previsit_output_lines(record: SubjectRecord) -> tuple[str, ...]:
    """INT-392's frozen projection of each sent note, listed under the notes
    it was frozen from. Its content is the note's, which the notes section
    already carries; the line says that a copy was frozen, when, in which
    schema, and its hash — the one a hospital that fetched it can check."""
    return tuple(
        _line(
            [
                f"previsit_output:{row.id}",
                f"visit:{row.session_id}",
                row.schema_version,
                f"sha256:{row.payload_sha256}",
                f"completed:{_stamp(row.completed_at)}",
            ]
        )
        for row in record.previsit_outputs
    )


def _share_lines(record: SubjectRecord) -> tuple[str, ...]:
    shares = tuple(
        _line(
            [
                f"share:{share.id}",
                f"note:{share.note_id}",
                ",".join(str(item) for item in share.scope_sections.get("section_ids", ())),
                f"expires:{_stamp(share.expires_at)}",
                f"revoked:{_stamp(share.revoked_at)}",
            ]
        )
        for share in record.shares
    )
    # INT-395: a Doctor Link is one addressed, expiring way of reaching a
    # share, so it is listed with the shares — never with its recipient label.
    links = tuple(
        _line(
            [
                f"doctor_link:{link.id}",
                f"share:{link.share_id}",
                f"recipient:{AccessorRole.CLINICIAN.value}",
                f"created:{_stamp(link.created_at)}",
                f"expires:{_stamp(link.expires_at)}",
                f"revoked:{_stamp(link.revoked_at)}",
            ]
        )
        for link in record.doctor_links
    )
    return shares + links


def _learned_fact_lines(
    record: SubjectRecord, *, cipher: EnvelopeCipher, tenant_id: uuid.UUID
) -> tuple[str, ...]:
    """files/09 §3: the overlay is "versioned, patient-owned, exported/
    deletable". Each confirmed fact with its value, its confidence and where
    it came from; then the version the overlay stands at."""
    facts: list[str] = []
    for fact in record.overlay_facts:
        body = decrypt_json(cipher, tenant_id, dict(fact.payload))
        facts.append(
            _line(
                [
                    f"learned_fact:{fact.id}",
                    fact.fact_key,
                    learned_value_text(decode_json_value(body.get("value"))),
                    f"confidence:{learned_value_text(body.get('confidence'))}",
                    f"source:{fact.source}",
                    f"from:{fact.source_ref}",
                    f"confirmed:{_stamp(fact.confirmed_at)}",
                    f"shared:{_flag(fact.shared)}",
                ]
            )
        )
    headers = (
        _line(
            [
                f"overlay:{header.id}",
                f"version:{header.version}",
                f"updated:{_stamp(header.updated_at)}",
            ]
        )
        for header in record.overlay_headers
    )
    return (*facts, *headers)


def _feedback_lines(
    record: SubjectRecord, *, cipher: EnvelopeCipher, tenant_id: uuid.UUID
) -> tuple[str, ...]:
    """The satisfaction comment in the patient's own words (INT-240), as it
    was stored: after the redaction baseline, inside its envelope."""
    return tuple(
        _line(
            [
                f"csat_text:{row.id}",
                f"visit:{row.session_id}",
                f"created:{_stamp(row.created_at)}",
                _decrypt_text(cipher, tenant_id, dict(row.payload)),
            ]
        )
        for row in record.csat_texts
    )


def _preference_lines(record: SubjectRecord) -> tuple[str, ...]:
    def quiet(start: int | None, end: int | None) -> str:
        if start is None or end is None:
            return "none"
        return "-".join(QuietWindow(start_minute=start, end_minute=end).as_text())

    return tuple(
        _line(
            [
                f"notification_preference:{row.id}",
                f"opted_out:{_flag(row.opted_out)}",
                f"quiet:{quiet(row.quiet_start_minute, row.quiet_end_minute)}",
                f"updated:{_stamp(row.updated_at)}",
            ]
        )
        for row in record.notification_preferences
    )


def _passkey_lines(record: SubjectRecord) -> tuple[str, ...]:
    """INT-582: the public half of each passkey, as stored — a credential id
    and a public key are the subject's data and no secret, so the answer to
    KVKK m.11 carries them whole."""
    return tuple(
        _line(
            [
                f"passkey:{row.id}",
                f"credential:{row.credential_id}",
                f"public_key:{row.public_key}",
                f"sign_count:{row.sign_count}",
                f"backup_eligible:{_flag(row.backup_eligible)}",
                f"backup_state:{_flag(row.backup_state)}",
                f"created:{_stamp(row.created_at)}",
                f"last_used:{_stamp(row.last_used_at)}",
                f"recovery_requested:{_stamp(row.recovery_requested_at)}",
            ]
        )
        for row in record.passkeys
    )


def _guardian_lines(record: SubjectRecord) -> tuple[str, ...]:
    return tuple(
        _line(
            [
                f"guardian_link:{row.id}",
                f"relationship:{row.relationship_ref}",
                f"verified:{_stamp(row.verified_at)}",
                f"revoked:{_stamp(row.revoked_at)}",
                f"created:{_stamp(row.created_at)}",
            ]
        )
        for row in record.guardian_links
    )


def _document_lines(record: SubjectRecord) -> tuple[str, ...]:
    documents = tuple(
        _line(
            [
                f"document:{doc.id}",
                doc.media_type,
                f"sha256:{doc.sha256}",
                _stamp(doc.created_at),
            ]
        )
        for doc in record.documents
    )
    # INT-123: each record-index row is listed with the documents, because it
    # was read from one of them (module docstring, third point).
    index = tuple(
        _line(
            [
                f"record_index:{row.id}",
                row.document_ref,
                f"page:{row.page}",
                f"item:{row.item_ref}",
                f"kind:{row.kind.value}",
                f"model:{row.model_ref}",
                f"created:{_stamp(row.created_at)}",
            ]
        )
        for row in record.record_index
    )
    return documents + index


def record_section_lines(
    record: SubjectRecord, *, cipher: EnvelopeCipher, tenant_id: uuid.UUID
) -> dict[str, tuple[str, ...]]:
    """Every section rendered from the record's rows, keyed by section id."""
    return {
        "documents": _document_lines(record),
        "consents": tuple(
            _line(
                [
                    f"consent:{consent.id}",
                    consent.scope,
                    consent.version,
                    f"text_hash:{consent.text_hash or ''}",
                    f"channel:{consent.channel or ''}",
                    _stamp(consent.granted_at),
                    f"revoked:{_stamp(consent.revoked_at)}",
                ]
            )
            for consent in record.consents
        ),
        "shares": _share_lines(record),
        "rectifications": tuple(
            _line(
                [
                    f"rectification:{entry.id}",
                    entry.target_ref,
                    _stamp(entry.created_at),
                    str(decrypt_json(cipher, tenant_id, dict(entry.payload))["correction"]),
                ]
            )
            for entry in record.rectifications
        ),
        "requests": tuple(
            _line(
                [
                    f"dsar-request:{request.id}",
                    request.kind.value,
                    request.status.value,
                    f"received:{_stamp(request.received_at)}",
                    f"due:{_stamp(request.due_at)}",
                    f"grace_ends:{_stamp(request.grace_ends_at)}",
                    f"completed:{_stamp(request.completed_at)}",
                ]
            )
            for request in record.requests
        ),
        "learned_facts": _learned_fact_lines(record, cipher=cipher, tenant_id=tenant_id),
        "feedback": _feedback_lines(record, cipher=cipher, tenant_id=tenant_id),
        "preferences": _preference_lines(record),
        "guardians": _guardian_lines(record),
        "passkeys": _passkey_lines(record),
    }
