"""INT-224 — the data inventory, both halves, as store-neutral facts.

files/06 §1 row ``STORE``: *"privacy labels generated from the single data
inventory so they can never drift from reality"*. This module is that single
source, read rather than re-typed.

**The half everyone remembers** is invariant 18's schema annotation: every
column of every table carries ``{category, purpose, basis, retention,
recipients}`` in ``Column.info`` (:mod:`intake_platform.db.inventory`). Folding
those by ``(category, recipients)`` gives the persisted facts.

**The half that makes the label true** has no column. Invariant 3 forbids
writing raw audio anywhere, so there is no audio row in the schema — and a
declaration derived from the schema alone would tell Apple and Google that this
product does not process voice, which is false in the one direction a reviewer
notices. The same is true of the health-platform reads that stay on the
handset, of the uploaded document bytes that live in object storage rather than
in a column, and of crash diagnostics. Those are :data:`OFF_SCHEMA_FLOWS`, and
they carry exactly the same five fields, because an inventory row is a shape,
not a table.

Nothing here maps a fact to a vendor's data type — that is the vendors'
published taxonomy and it lives in :mod:`intake_platform.store.taxonomy`,
behind a committed snapshot. What this module produces is ours: what we
process, why, on what ground, for how long, and who can end up seeing it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from intake_platform.db import models
from intake_platform.db.inventory import (
    BASIS_AWAITING_HUMAN_DIAGNOSTICS,
    BASIS_HEALTH_CONSENT,
    CAT_HEALTH,
    CAT_OPERATIONAL,
    INVENTORY_KEY,
    REC_AUDITOR,
    REC_CLINICIAN,
    REC_GUARDIAN_INTERNAL,
    REC_INTERNAL,
    REC_ON_DEVICE,
    REC_PATIENT_CLINICIAN,
    RET_RECORD,
    InventoryAnnotation,
    inv,
)

__all__ = [
    "OFF_SCHEMA_FLOWS",
    "PERMISSION_CLASSIFICATION",
    "RECIPIENT_SHARING",
    "DataFact",
    "OffSchemaFlow",
    "PermissionClassification",
    "Sharing",
    "UnclassifiedRecipientError",
    "data_facts",
    "declared_app_permissions",
    "inactive_flow_drift",
    "sharing_for",
    "unclassified_permissions",
]


class Sharing(StrEnum):
    """Who can end up holding the data, stated store-neutrally.

    Whether a given value counts as "sharing" on a particular form is that
    form's published definition and is decided by the committed taxonomy
    snapshot, never here.
    """

    NONE = "none"
    ON_PATIENT_DIRECTION = "on_patient_direction"
    ON_LAWFUL_REQUEST = "on_lawful_request"


class UnclassifiedRecipientError(ValueError):
    """A recipient string nobody has classified. A new recipient is a new
    disclosure, so it stops the build instead of defaulting to 'not shared'."""


RECIPIENT_SHARING: Final[Mapping[str, Sharing]] = MappingProxyType(
    {
        REC_INTERNAL: Sharing.NONE,
        REC_GUARDIAN_INTERNAL: Sharing.NONE,
        REC_ON_DEVICE: Sharing.NONE,
        REC_CLINICIAN: Sharing.ON_PATIENT_DIRECTION,
        REC_PATIENT_CLINICIAN: Sharing.ON_PATIENT_DIRECTION,
        REC_AUDITOR: Sharing.ON_LAWFUL_REQUEST,
    }
)


def sharing_for(recipients: str) -> Sharing:
    try:
        return RECIPIENT_SHARING[recipients]
    except KeyError as exc:
        raise UnclassifiedRecipientError(
            "unclassified recipient — a new recipient string is a new disclosure and "
            "must be classified in RECIPIENT_SHARING before any label is generated"
        ) from exc


# --- the off-schema half of the inventory ---------------------------------------------


@dataclass(frozen=True)
class OffSchemaFlow:
    """Personal data this product processes without a database column."""

    flow_id: str
    what: str
    annotation: InventoryAnnotation
    persisted: bool
    #: False when the flow exists in the tree but is switched off in the
    #: shipped configuration. ``inactive_flow_drift`` re-checks the claim.
    active: bool
    #: A repo file that states the facts above, so the row is read rather than
    #: remembered.
    source_path: str
    source: str


_VOICE_AUDIO = OffSchemaFlow(
    flow_id="voice_audio",
    what="microphone audio captured during a voice intake turn",
    annotation=inv(
        CAT_HEALTH,
        "carry the patient's spoken answers to the transcriber; the audio is a "
        "transport for the words, never a record of them",
        BASIS_HEALTH_CONSENT,
        "never written to disk, database, object store or logs; memory buffers "
        "<= 60 s, mlocked, zeroed on every trigger (CLAUDE.md invariant 3)",
        REC_INTERNAL,
    )[INVENTORY_KEY],
    persisted=False,
    active=True,
    source_path="tests/voice/test_audio_retention_guard.py",
    source="CLAUDE.md invariant 3 and files/06 §3 'Raw audio: never written', proved by "
    "the audio_no_write_guard suite named here",
)

_HEALTH_PLATFORM_READS = OffSchemaFlow(
    flow_id="health_platform_reads",
    what="step, resting heart rate and sleep summaries read from HealthKit / Health Connect",
    annotation=inv(
        CAT_HEALTH,
        "show the patient their own recent activity on the device and let them "
        "choose to add a summary to the visit note",
        BASIS_HEALTH_CONSENT,
        "nothing is written by this flow; once the patient adds a summary to the "
        "note the notes.payload row's clock applies (06 §3)",
        REC_ON_DEVICE,
    )[INVENTORY_KEY],
    persisted=False,
    active=True,
    source_path="apps/mobile/src/lib/health/healthKitConnector.ts",
    source="the connector is read-only by design — steps, resting heart rate and sleep, "
    "nothing else, and 'nothing here writes, uploads or persists'",
)

_DOCUMENT_OBJECT = OffSchemaFlow(
    flow_id="document_object",
    what="the bytes of a patient-uploaded document in the object store",
    annotation=inv(
        CAT_HEALTH,
        "hold the patient's own uploaded report so its values can be parsed for "
        "the patient to confirm, and shown to a clinician under a share",
        BASIS_HEALTH_CONSENT,
        RET_RECORD,
        REC_PATIENT_CLINICIAN,
    )[INVENTORY_KEY],
    persisted=True,
    active=True,
    source_path="packages/intake_platform/src/intake_platform/documents.py",
    source="the MinIO document store: quarantine/ then clean/, keys carry no "
    "patient-supplied filename",
)

_CRASH_DIAGNOSTICS = OffSchemaFlow(
    flow_id="crash_diagnostics",
    what="mobile crash and error diagnostics read through a closed allow-list of keys",
    annotation=inv(
        CAT_OPERATIONAL,
        "diagnose a crash from fields the scrubber is allowed to read; no PHI by "
        "construction (invariant 6)",
        BASIS_AWAITING_HUMAN_DIAGNOSTICS,
        "no retention applies while the reporter has no endpoint; the period is "
        "set with the basis (HB-L21)",
        REC_INTERNAL,
    )[INVENTORY_KEY],
    persisted=False,
    active=False,
    source_path="apps/mobile/src/lib/telemetry/expoTelemetry.ts",
    source="the reporter is inert by default: extra.glitchtipDsn is empty and there is "
    "no default endpoint (files/10 §3-§4, INT-145)",
)

OFF_SCHEMA_FLOWS: Final[Mapping[str, OffSchemaFlow]] = MappingProxyType(
    {
        flow.flow_id: flow
        for flow in (_VOICE_AUDIO, _HEALTH_PLATFORM_READS, _DOCUMENT_OBJECT, _CRASH_DIAGNOSTICS)
    }
)


# --- the facts ------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class DataFact:
    """One store-neutral row of the inventory, ready to be mapped."""

    fact_id: str
    category: str
    sharing: Sharing
    persisted: bool
    origin: str  # "schema" | "flow"
    purposes: tuple[str, ...]
    bases: tuple[str, ...]
    retentions: tuple[str, ...]
    recipients: tuple[str, ...]
    columns: tuple[str, ...]


def _schema_facts() -> list[DataFact]:
    grouped: dict[tuple[str, Sharing], dict[str, set[str]]] = {}
    for table_name, table in models.Base.metadata.tables.items():
        for column in table.columns:
            annotation = column.info[INVENTORY_KEY]
            key = (annotation["category"], sharing_for(annotation["recipients"]))
            bucket = grouped.setdefault(
                key,
                {
                    "purposes": set(),
                    "bases": set(),
                    "retentions": set(),
                    "recipients": set(),
                    "columns": set(),
                },
            )
            bucket["purposes"].add(annotation["purpose"])
            bucket["bases"].add(annotation["basis"])
            bucket["retentions"].add(annotation["retention"])
            bucket["recipients"].add(annotation["recipients"])
            bucket["columns"].add(f"{table_name}.{column.name}")
    return [
        DataFact(
            fact_id=f"schema:{category}:{sharing}",
            category=category,
            sharing=sharing,
            persisted=True,
            origin="schema",
            purposes=tuple(sorted(bucket["purposes"])),
            bases=tuple(sorted(bucket["bases"])),
            retentions=tuple(sorted(bucket["retentions"])),
            recipients=tuple(sorted(bucket["recipients"])),
            columns=tuple(sorted(bucket["columns"])),
        )
        for (category, sharing), bucket in grouped.items()
    ]


def _flow_fact(flow: OffSchemaFlow) -> DataFact:
    annotation = flow.annotation
    return DataFact(
        fact_id=f"flow:{flow.flow_id}",
        category=annotation["category"],
        sharing=sharing_for(annotation["recipients"]),
        persisted=flow.persisted,
        origin="flow",
        purposes=(annotation["purpose"],),
        bases=(annotation["basis"],),
        retentions=(annotation["retention"],),
        recipients=(annotation["recipients"],),
        columns=(),
    )


def data_facts(*, include_inactive: bool = False) -> tuple[DataFact, ...]:
    """Every fact a store declaration is built from, sorted and deterministic.

    Inactive flows are excluded by default: a label must describe what the app
    does today, and declaring a capability that ships switched off is the same
    class of error as omitting one that ships on.
    """
    facts = _schema_facts()
    facts.extend(
        _flow_fact(flow) for flow in OFF_SCHEMA_FLOWS.values() if flow.active or include_inactive
    )
    return tuple(sorted(facts))


# --- the app's own manifest, cross-checked --------------------------------------------


@dataclass(frozen=True)
class PermissionClassification:
    """What a declared platform capability means for the inventory."""

    permission: str
    flow_id: str | None
    reason: str


_CLASSIFICATIONS: Final[tuple[PermissionClassification, ...]] = (
    PermissionClassification(
        "android.permission.RECORD_AUDIO",
        "voice_audio",
        "captures the microphone — the whole point of the voice lane",
    ),
    PermissionClassification(
        "android.permission.MODIFY_AUDIO_SETTINGS",
        None,
        "switches the audio mode and routes the output; reads no personal data",
    ),
    PermissionClassification(
        "android.permission.ACCESS_NETWORK_STATE",
        None,
        "detects network transitions so ICE can restart; reads no personal data",
    ),
    PermissionClassification(
        "android.permission.BLUETOOTH_CONNECT",
        None,
        "routes audio to an already-paired headset; reads no personal data",
    ),
    PermissionClassification(
        "android.permission.health.READ_STEPS",
        "health_platform_reads",
        "reads step totals from Health Connect",
    ),
    PermissionClassification(
        "android.permission.health.READ_RESTING_HEART_RATE",
        "health_platform_reads",
        "reads resting heart rate from Health Connect",
    ),
    PermissionClassification(
        "android.permission.health.READ_SLEEP",
        "health_platform_reads",
        "reads sleep sessions from Health Connect",
    ),
    PermissionClassification(
        "android.permission.CAMERA",
        "document_object",
        "photographs the patient's own report so it can be uploaded as a document; "
        "this app requests no photo-library access and stores the capture nowhere but "
        "the upload, and strips its EXIF/XMP container — orientation excepted — before "
        "the bytes leave the device (INT-138). What the handset's own camera app does "
        "with the frame it captured is outside this app's control: on Android the OEM "
        "app servicing ACTION_IMAGE_CAPTURE commonly writes its own copy to DCIM, and "
        "no application flag prevents it",
    ),
    PermissionClassification(
        "NSMicrophoneUsageDescription",
        "voice_audio",
        "the iOS side of the microphone capture",
    ),
    PermissionClassification(
        "NSCameraUsageDescription",
        "document_object",
        "the iOS side of the document capture",
    ),
    PermissionClassification(
        "NSHealthShareUsageDescription",
        "health_platform_reads",
        "the iOS side of the health-platform reads",
    ),
)

PERMISSION_CLASSIFICATION: Final[Mapping[str, PermissionClassification]] = MappingProxyType(
    {entry.permission: entry for entry in _CLASSIFICATIONS}
)


def declared_app_permissions(app_json: Path, locale_files: Sequence[Path]) -> tuple[str, ...]:
    """Every platform capability the shipped manifest asks for.

    Android permissions come from ``expo.android.permissions``; the iOS usage
    descriptions come from the config-plugin blocks and from the localised
    ``expo.locales`` files, which is where a Turkish-first app keeps them
    (apps/mobile/plugins/withVoiceAudio.js explains why).
    """
    config = json.loads(app_json.read_text(encoding="utf-8"))["expo"]
    declared: set[str] = set(config.get("android", {}).get("permissions", []))
    for plugin in config.get("plugins", []):
        if isinstance(plugin, list) and len(plugin) == 2 and isinstance(plugin[1], dict):
            declared.update(
                key
                for key, value in plugin[1].items()
                if key.startswith("NS") and key.endswith("UsageDescription") and value
            )
    for locale_file in locale_files:
        strings = json.loads(locale_file.read_text(encoding="utf-8"))
        declared.update(
            key
            for key, value in strings.items()
            if key.startswith("NS") and key.endswith("UsageDescription") and value
        )
    return tuple(sorted(declared))


def unclassified_permissions(app_json: Path, locale_files: Sequence[Path]) -> tuple[str, ...]:
    """Capabilities the app asks for that no inventory row accounts for."""
    return tuple(
        permission
        for permission in declared_app_permissions(app_json, locale_files)
        if permission not in PERMISSION_CLASSIFICATION
    )


def inactive_flow_drift(app_json: Path) -> tuple[str, ...]:
    """Flows declared inactive that the shipped configuration has switched on.

    Today the only such flow is the crash reporter, and its switch is the
    ``extra.glitchtipDsn`` value: empty means no endpoint, so nothing leaves
    the handset. The day someone fills it in, the declaration is wrong and this
    is what says so.
    """
    extra = json.loads(app_json.read_text(encoding="utf-8"))["expo"].get("extra", {})
    dsn = str(extra.get("glitchtipDsn", "")).strip()
    drifted: list[str] = []
    if dsn and not OFF_SCHEMA_FLOWS["crash_diagnostics"].active:
        drifted.append("crash_diagnostics")
    return tuple(drifted)
