"""files/03 §4.9.1 rows → the pins that actually exist, or a refusal.

§4.9 is canonical — *"a model that is not in §4.9.1 is not pinned, whatever
another section, an ADR or a deploy guide says"* — and CLAUDE.md invariant 19
says what a pin **is**: open weights, commercially usable, and licence-verified
**from the raw LICENSE blob**, recorded with ``licence_verified_at``. So this
module addresses a model by its §4.9.1 **row number**, resolves it against
``observability/registry.yaml`` (the self-hosting registry INT-022 owns and
INT-243 extended with the provenance block), and refuses in two distinct ways:

- :class:`PinNotRegistered` — the row names a model no registry row carries.
  Today that is **row 1**, ``nvidia/nemotron-3.5-asr-streaming-0.6b``: it is
  served nowhere, mirrored nowhere and pinned nowhere, and writing a revision
  or a sha256 for it would be exactly the plausible invented number
  files/HUMAN_BLOCKERS.md Rule 1 forbids. The refusal is the artefact.
- :class:`LicenceNotVerified` — the row resolves, and its ``licence_verified_at``
  field is empty. Today that is **row 2**,
  ``turkmedstt/whisper-large-v3-turkish-medical``, whose registry row says
  ``UNVERIFIED (card tag apache-2.0, no blob)`` in as many words — a card tag
  is the badge §4.9.0 rule 3 refuses — and **row 7**, ``Qwen/Qwen3.5-9B``,
  whose row says *"Apache-2.0 (LICENSE blob verified @c202236)"* **in prose**
  and carries no ``licence_verified_at``, no ``licence_blob_sha256`` and no
  ``weights_sha256``. Invariant 19 says "recorded with ``licence_verified_at``
  in the model registry", and a sentence in a ``license`` string is not that
  record: an auditor cannot re-read the bytes somebody read, because the row
  does not say which bytes they were. Backfilling the three structured fields
  needs a blob reading and weight hashes from the serving host — it is a task,
  not a value to type — so the rows stay as they are and this refuses.

Only rows **10 and 11** (``openbmb/VoxCPM2``, one component for both tiers)
carry the full block today, and they carry it because INT-243 did the work:
blob url, blob sha256, two weight hashes, and a note recording that the
weights repo has no LICENSE file at any revision so the grant was read from
the vendor source repo instead.

**The PHI gate is where the refusal bites, and only there.** ``resolve_pin``
returns whatever the registry holds, verified or not, because a dev/synthetic
bridge legitimately runs an unverified artefact and the registry rows say so
in their own ``host`` fields. ``require_phi_path_pin`` is the one an adapter
calls when it is about to carry patient speech, and it raises. That is
CLAUDE.md's shape for an open blocker: build the mechanism, wire the gate,
make it fail closed, leave the content empty.

**One file, one meaning.** The authoritative validator for the registry is
``intake_probes.registry`` (INT-022/INT-243) — it is what CI runs, and it
enforces "``model_id`` implies revision + weight hashes + a dated licence
verification" and "``licence_verified_at`` implies a named, hashed blob". This
module deliberately does **not** restate those rules; it reads the same file
with a permissive model and a contract test asserts the two agree row for row.
A second validator would be a second opinion about a licence.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "COMPONENT_OF",
    "REGISTRY_PATH",
    "LicenceNotVerified",
    "ModelPin",
    "ModelStackRow",
    "PinNotPinned",
    "PinNotRegistered",
    "PinRefused",
    "require_phi_path_pin",
    "resolve_pin",
    "unverified_rows",
]

#: The repository's self-hosting registry. Four parents up from this file:
#: ``services/voice-runtime/src/intake_voice_runtime/adapters/pins.py``.
REGISTRY_PATH: Final[Path] = Path(__file__).resolve().parents[5] / "observability" / "registry.yaml"


class ModelStackRow(enum.IntEnum):
    """The files/03 §4.9.1 rows the ``residency_tr`` profile is built from.

    Exactly the five rows INT-095's title names — 1-2, 7, 10-11. Rows 3-6 and
    8-21 exist in §4.9.1 and are other issues' (turn detection is row 6 and
    proprietary; the observer lanes are rows 14-19; OCR is rows 20-21). An
    enum rather than bare integers so a caller cannot ask for "row 12" by
    typing a number that means something else in another file.
    """

    ASR_PRIMARY = 1
    ASR_SHADOW = 2
    TALKER_LLM = 7
    TTS_CLIP = 10
    TTS_DYNAMIC = 11


#: Which registry component serves each row. ``None`` means **no row exists**
#: — not "not running", which is what ``self_hosted_now: false`` means. Rows
#: 10 and 11 map to the same component on purpose: §4.9.1 row 11 says *"same
#: weights, same ``voice_id`` … never split the two tiers across two models"*,
#: and one component is how that becomes unrepresentable rather than reviewed.
COMPONENT_OF: Final[Mapping[ModelStackRow, str | None]] = {
    ModelStackRow.ASR_PRIMARY: None,
    ModelStackRow.ASR_SHADOW: "whisper-tr-medical",
    ModelStackRow.TALKER_LLM: "qwen3.5-9b",
    ModelStackRow.TTS_CLIP: "voxcpm2-tts",
    ModelStackRow.TTS_DYNAMIC: "voxcpm2-tts",
}


class PinRefused(RuntimeError):
    """Base for every refusal to hand out a model pin."""


class PinNotRegistered(PinRefused, LookupError):
    """The §4.9.1 row has no row in the self-hosting registry."""


class LicenceNotVerified(PinRefused):
    """The row resolves, and no dated blob reading is recorded on it."""


class PinNotPinned(PinRefused):
    """The row's licence is verified and its model provenance block is absent."""


class _RegistryRow(BaseModel):
    """Only the fields a pin needs. Validation proper is intake_probes'."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    component: str
    license: str
    host: str
    phi_path: bool
    model_id: str | None = None
    revision: str | None = None
    weights_sha256: dict[str, str] = Field(default_factory=dict)
    licence_verified_at: date | None = None
    licence_blob_url: str | None = None
    licence_blob_sha256: str | None = None


@dataclass(frozen=True)
class ModelPin:
    """One §4.9.1 row as the registry actually records it.

    ``model_id``, ``revision`` and the licence fields are all optional, and
    each ``None`` is a *finding* rather than a default: it says the registry
    row does not carry that fact. :attr:`pinned` and :attr:`licence_verified`
    read those findings, and :func:`require_phi_path_pin` is where they bite.
    """

    row: ModelStackRow
    component: str
    model_id: str | None
    revision: str | None
    weights_sha256: Mapping[str, str]
    licence: str
    host: str
    licence_verified_at: date | None
    licence_blob_url: str | None
    licence_blob_sha256: str | None

    @property
    def licence_verified(self) -> bool:
        """True only when a dated blob reading is recorded (§4.9.0 rule 3)."""
        return self.licence_verified_at is not None and self.licence_blob_sha256 is not None

    @property
    def pinned(self) -> bool:
        """True when the row carries ``model_id@revision`` + weight hashes."""
        return bool(self.model_id and self.revision and self.weights_sha256)

    @property
    def pinned_id(self) -> str:
        """``model_id@revision`` — the form files/03 §4.9.4 asks for.

        A row with no structured provenance answers ``<component>@unpinned``.
        That string is deliberately not a plausible revision: it is what goes
        on a trace span, and an auditor reading it must see a gap rather than
        a hash they might try to look up.
        """
        if not self.pinned:
            return f"{self.component}@unpinned"
        return f"{self.model_id}@{self.revision}"


@lru_cache(maxsize=4)
def _rows(path: Path) -> Mapping[str, _RegistryRow]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = [_RegistryRow.model_validate(entry) for entry in document["components"]]
    return {row.component: row for row in rows}


def resolve_pin(row: ModelStackRow, *, registry_path: Path | None = None) -> ModelPin:
    """The pin for one §4.9.1 row, verified or not.

    Raises :class:`PinNotRegistered` when the row names no component, when the
    named component is missing from the registry, or when that component
    carries no model provenance at all.
    """
    component = COMPONENT_OF[row]
    if component is None:
        raise PinNotRegistered(
            f"files/03 §4.9.1 row {int(row)} ({row.name}) has no row in the "
            "self-hosting registry: the model is served nowhere, mirrored nowhere "
            "and pinned nowhere. A revision or a sha256 written here would be an "
            "invented value (files/HUMAN_BLOCKERS.md Rule 1), so the row refuses"
        )
    rows = _rows(registry_path or REGISTRY_PATH)
    entry = rows.get(component)
    if entry is None:
        raise PinNotRegistered(
            f"files/03 §4.9.1 row {int(row)} names component {component!r}, which is "
            "not in observability/registry.yaml"
        )
    return ModelPin(
        row=row,
        component=entry.component,
        model_id=entry.model_id,
        revision=entry.revision,
        weights_sha256=dict(entry.weights_sha256),
        licence=entry.license,
        host=entry.host,
        licence_verified_at=entry.licence_verified_at,
        licence_blob_url=entry.licence_blob_url,
        licence_blob_sha256=entry.licence_blob_sha256,
    )


def require_phi_path_pin(row: ModelStackRow, *, registry_path: Path | None = None) -> ModelPin:
    """The pin, or a refusal, for a lane about to carry patient speech."""
    pin = resolve_pin(row, registry_path=registry_path)
    if not pin.licence_verified:
        raise LicenceNotVerified(
            f"files/03 §4.9.1 row {int(row)} (registry row {pin.component!r}) records no "
            f"licence_verified_at, so no raw LICENSE blob reading is on file; the row "
            f"carries {pin.licence!r}. CLAUDE.md invariant 19 verifies a licence from "
            "the blob — never from a badge, a card tag or a sentence — and records the "
            "date and the blob's own sha256 so an auditor can re-read the same bytes. "
            "Until somebody does, this lane may not carry PHI: it is a blocker row, "
            "not a default"
        )
    if not pin.pinned:
        raise PinNotPinned(
            f"files/03 §4.9.1 row {int(row)} (registry row {pin.component!r}) carries no "
            "model_id@revision + weights_sha256 block, so there is nothing to pin a "
            "PHI-path lane to. Adding one means reading the artefacts on the serving "
            "host and hashing them, never writing a plausible sha256"
        )
    return pin


def unverified_rows(*, registry_path: Path | None = None) -> tuple[ModelStackRow, ...]:
    """Every row that cannot serve the PHI path today, in row order.

    The operational form of the two blockers above: a deployment check, a
    release note or a test can read this rather than re-deriving the list.
    """
    blocked: list[ModelStackRow] = []
    for row in sorted(ModelStackRow):
        try:
            require_phi_path_pin(row, registry_path=registry_path)
        except PinRefused:
            blocked.append(row)
    return tuple(blocked)
