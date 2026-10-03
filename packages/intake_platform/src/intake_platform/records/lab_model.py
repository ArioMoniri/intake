"""files/03 §4.9.1 row 9 — the extraction LLM's pin, and the gate before PHI.

§4.9 is canonical: *"a model that is not in §4.9.1 is not pinned"*. Row 9
names ``Qwen/Qwen3.6-35B-A3B`` (alt ``Qwen/Qwen3.8-27B``), Apache-2.0, served
by vLLM with JSON-schema-constrained decoding, *"off the spoken-loop critical
path"*. CLAUDE.md invariant 19 says what a pin **is**: open weights, licence
verified from the raw LICENSE blob and recorded with ``licence_verified_at``,
weights pinned by ``model_id@revision + sha256``. INT-124 wrote that record
into ``observability/registry.yaml`` as component ``qwen3.6-35b-a3b``; this
module reads it back and refuses in one typed way per missing fact.

**Today the PHI gate refuses, and that is the design.** The row carries
``self_hosted_now: false``: no host serves the model (the target GPU is
quota-blocked, INT-381; an in-country host for PHI is HB-I5 / HB-L11).
:func:`require_row9_phi_pin` therefore raises :class:`Row9NotServed`, and
nothing here — or anywhere on this path — falls back to another model or a
vendor endpoint. Invariant 19 makes a cloud fallback on the PHI path a defect,
so the absence of one is the control, not an omission.

**One file, one meaning.** ``intake_probes.registry`` is the authoritative
validator CI runs. This reader is deliberately permissive — it restates no
rule of that validator — and a contract test asserts the two agree field for
field, exactly as ``intake_voice_runtime.adapters.pins`` does for rows 1-2, 7
and 10-11. It lives here rather than there because the document lane sits
below the voice runtime in the dependency graph, and ``services/api`` does not
depend on the voice runtime at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "REGISTRY_PATH",
    "ROW9_COMPONENT",
    "ROW9_MODEL_IDS",
    "ROW9_SERVING_ISSUE",
    "Row9LicenceNotVerified",
    "Row9ModelMismatch",
    "Row9NotOnPhiPath",
    "Row9NotPinned",
    "Row9NotRegistered",
    "Row9NotServed",
    "Row9Pin",
    "Row9Refused",
    "require_phi_ready",
    "require_row9_phi_pin",
    "resolve_row9_pin",
]

#: ``packages/intake_platform/src/intake_platform/records/lab_model.py`` → repo root.
REGISTRY_PATH: Final[Path] = Path(__file__).resolve().parents[5] / "observability" / "registry.yaml"

#: The registry component that serves files/03 §4.9.1 row 9.
ROW9_COMPONENT: Final = "qwen3.6-35b-a3b"

#: The two repo ids row 9 names, verbatim, primary first. A registry row that
#: names anything else is not row 9, whatever its component is called.
ROW9_MODEL_IDS: Final[tuple[str, ...]] = ("Qwen/Qwen3.6-35B-A3B", "Qwen/Qwen3.8-27B")

#: The issue that serves row 9 on the target GPU and flips ``self_hosted_now``.
ROW9_SERVING_ISSUE: Final = "INT-381"


class Row9Refused(RuntimeError):
    """Base for every refusal to hand row 9 a document carrying PHI."""


class Row9NotRegistered(Row9Refused, LookupError):
    """No registry row carries the row-9 component."""


class Row9ModelMismatch(Row9Refused):
    """The registry row names a model that files/03 §4.9.1 row 9 does not."""


class Row9NotPinned(Row9Refused):
    """The row carries no ``model_id@revision`` + ``weights_sha256`` block."""


class Row9LicenceNotVerified(Row9Refused):
    """No dated reading of the raw LICENSE blob is recorded on the row."""


class Row9NotOnPhiPath(Row9Refused):
    """The row is not declared self-hostable and on the PHI path (invariant 19)."""


class Row9NotServed(Row9Refused):
    """The row is pinned and verified, and no host serves it."""


class _RegistryRow(BaseModel):
    """Only the fields the gate reads. Validation proper is intake_probes'."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    component: str
    self_hostable: bool
    self_hosted_now: bool
    phi_path: bool
    model_id: str | None = None
    revision: str | None = None
    weights_sha256: dict[str, str] = Field(default_factory=dict)
    licence_verified_at: date | None = None
    licence_blob_url: str | None = None
    licence_blob_sha256: str | None = None


@dataclass(frozen=True)
class Row9Pin:
    """Row 9 as the registry records it. Each ``None`` is a finding, not a default."""

    component: str
    model_id: str | None
    revision: str | None
    licence_verified_at: date | None
    licence_blob_url: str | None
    licence_blob_sha256: str | None
    self_hostable: bool
    self_hosted_now: bool
    phi_path: bool
    weights_sha256: Mapping[str, str] = field(default_factory=dict)

    @property
    def pinned_id(self) -> str:
        """``model_id@revision`` (files/03 §4.9.4), or a string that is visibly not one."""
        if not (self.model_id and self.revision):
            return f"{self.component}@unpinned"
        return f"{self.model_id}@{self.revision}"


def resolve_row9_pin(*, registry_path: Path | None = None) -> Row9Pin:
    """Row 9 from the registry, verified or not; :class:`Row9NotRegistered` if absent."""
    document = yaml.safe_load((registry_path or REGISTRY_PATH).read_text(encoding="utf-8"))
    for raw in document["components"]:
        if raw.get("component") != ROW9_COMPONENT:
            continue
        row = _RegistryRow.model_validate(raw)
        return Row9Pin(
            component=row.component,
            model_id=row.model_id,
            revision=row.revision,
            weights_sha256=dict(row.weights_sha256),
            licence_verified_at=row.licence_verified_at,
            licence_blob_url=row.licence_blob_url,
            licence_blob_sha256=row.licence_blob_sha256,
            self_hostable=row.self_hostable,
            self_hosted_now=row.self_hosted_now,
            phi_path=row.phi_path,
        )
    raise Row9NotRegistered(
        f"observability/registry.yaml carries no {ROW9_COMPONENT!r} row, so files/03 §4.9.1 "
        "row 9 is pinned nowhere; a revision or a sha256 typed here would be an invented "
        "value (files/HUMAN_BLOCKERS.md Rule 1)"
    )


def require_phi_ready(pin: Row9Pin) -> Row9Pin:
    """The pin, or the one refusal that says which fact is missing."""
    if pin.model_id is not None and pin.model_id not in ROW9_MODEL_IDS:
        raise Row9ModelMismatch(
            f"registry row {pin.component!r} names a model files/03 §4.9.1 row 9 does not; "
            "a model that is not in that table is not pinned"
        )
    if not (pin.model_id and pin.revision and pin.weights_sha256):
        raise Row9NotPinned(
            f"registry row {pin.component!r} carries no model_id@revision + weights_sha256, "
            "so there is nothing to attribute an extraction to (files/03 §4.9.4)"
        )
    if pin.licence_verified_at is None or pin.licence_blob_sha256 is None:
        raise Row9LicenceNotVerified(
            f"registry row {pin.component!r} records no dated reading of the raw LICENSE blob; "
            "a licence is verified from the blob, never a badge or a card tag (CLAUDE.md "
            "invariant 19, files/03 §4.9.0 rule 3)"
        )
    if not (pin.phi_path and pin.self_hostable):
        raise Row9NotOnPhiPath(
            f"registry row {pin.component!r} is not declared self-hostable and on the PHI "
            "path, so it may not read a patient's document (CLAUDE.md invariant 19)"
        )
    if not pin.self_hosted_now:
        raise Row9NotServed(
            f"files/03 §4.9.1 row 9 ({pin.pinned_id}) is pinned and licence-verified and no "
            f"host serves it: {ROW9_SERVING_ISSUE} serves it on the target GPU, and the PHI "
            "path also needs an in-country host (HB-I5, HB-L11). There is no fallback — a "
            "cloud model on the PHI path is exactly what invariant 19 forbids — so the "
            "document stays unextracted"
        )
    return pin


def require_row9_phi_pin(*, registry_path: Path | None = None) -> Row9Pin:
    """The pin a PHI-path extraction may use, or the refusal that stops it."""
    return require_phi_ready(resolve_row9_pin(registry_path=registry_path))
