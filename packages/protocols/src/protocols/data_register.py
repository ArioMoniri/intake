"""The per-category data register (INT-349), read fail closed.

Owner decision D3 (2026-09-26) approved eight categories of personal data for
the specialty review queue (:class:`protocols.types.DataCategory`) and left
the legal half open. For each category, counsel names the KVKK m.6 basis, a
separate basis and notice where another person is the data subject, the
retention, the recipients and the consent scope; the VERBİS entry (INT-211) is
built from the same answers. docs/legal/data-categories.yaml holds one row per
category with those fields. Engineering fills ``purpose`` from D3 and nothing
else.

A row is complete only when every counsel field is filled and counsel's review
date is recorded. The compiler refuses to serve a slot whose category row is
not complete (:mod:`protocols.compile.data_categories`). An empty field is the
honest state of a decision nobody has taken yet. It is never a gap to be
closed with a plausible basis (CLAUDE.md invariants 17 and 18; HUMAN_BLOCKERS
Rule 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Final

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, ValidationError

from protocols.types import DataCategory

__all__ = [
    "COUNSEL_FIELDS",
    "DATA_REGISTER_PATH",
    "NO_REGISTER",
    "OTHER_SUBJECT_CATEGORIES",
    "DataCategoryRegister",
    "DataCategoryRow",
    "DataRegisterError",
    "load_data_register",
]

DATA_REGISTER_PATH: Final[Path] = Path("docs/legal/data-categories.yaml")
"""Repo-root relative, like the CLI's other defaults."""

OTHER_SUBJECT_CATEGORIES: Final[frozenset[DataCategory]] = frozenset(
    {
        DataCategory.HOUSEHOLD,
        DataCategory.RELATIVES_HEALTH,
        DataCategory.PARTNER_FERTILITY,
    }
)
"""D3 §3: the categories where another person is the data subject (household
members, relatives, the partner). Their rows need a separate basis and notice
for that person as well as the patient's own."""

COUNSEL_FIELDS: Final[tuple[str, ...]] = (
    "basis",
    "retention",
    "recipients",
    "consent_scope",
    "other_subject_basis_and_notice",
    "counsel_reviewed_at",
)
"""The fields only counsel fills, in the order a refusal names them."""

_TOP_LEVEL: Final[frozenset[str]] = frozenset({"register_version", "categories"})


class DataRegisterError(ValueError):
    """The register is absent or malformed, so no tagged slot can be served."""


class DataCategoryRow(FrozenModel):
    """One category's row. Every key is required and every counsel value may be
    null, so the file shows an empty decision as empty instead of omitting it."""

    category: DataCategory = Field(description="The category this row governs.")
    purpose: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Why the intake asks, from owner decision D3. Engineering's to state."
    )
    basis: str | None = Field(description="KVKK m.6 ground. Counsel's.")
    retention: str | None = Field(description="Retention and destruction clock. Counsel's.")
    recipients: str | None = Field(description="Who may receive the answers. Counsel's.")
    consent_scope: str | None = Field(
        description="The files/06 §2 consent purpose the answers ride. Counsel's."
    )
    other_subject_basis_and_notice: str | None = Field(
        description="Basis and notice for the other data subject; required where "
        "D3 names one (OTHER_SUBJECT_CATEGORIES). Counsel's."
    )
    counsel_reviewed_at: date | None = Field(description="When counsel signed the row off.")

    def missing(self) -> tuple[str, ...]:
        """Counsel fields still empty. ``()`` means the row is complete."""
        needed = tuple(
            name
            for name in COUNSEL_FIELDS
            if name != "other_subject_basis_and_notice" or self.category in OTHER_SUBJECT_CATEGORIES
        )
        return tuple(name for name in needed if _is_empty(getattr(self, name)))


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class DataCategoryRegister:
    """The loaded register: one row per non-general category."""

    version: str
    rows: Mapping[DataCategory, DataCategoryRow]

    def missing(self, category: DataCategory) -> tuple[str, ...]:
        """What stands between ``category`` and being servable. ``general_health``
        needs no row: the ``slots.value`` column inventory governs it."""
        if category is DataCategory.GENERAL_HEALTH:
            return ()
        row = self.rows.get(category)
        if row is None:
            return ("the whole row",)
        return row.missing()


NO_REGISTER: Final[DataCategoryRegister] = DataCategoryRegister(
    version="none-supplied", rows=MappingProxyType({})
)
"""What the compiler reads when no register is passed: no rows, so every
category except ``general_health`` refuses."""


def load_data_register(path: Path) -> DataCategoryRegister:
    """Read the register, refusing every shape that could let an incomplete
    row pass for a complete one."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataRegisterError(
            f"no data-category register at {path}. INT-349: a slot tagged with any "
            "category other than general_health is not servable without it"
        ) from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DataRegisterError(f"{path}: not valid YAML") from exc
    if not isinstance(loaded, Mapping):
        raise DataRegisterError(f"{path}: the register must be a mapping")
    unknown = sorted(set(loaded) - _TOP_LEVEL)
    if unknown:
        raise DataRegisterError(f"{path}: unknown top-level keys {unknown}")
    version = loaded.get("register_version")
    if not isinstance(version, str) or not version.strip():
        raise DataRegisterError(f"{path}: no register_version")
    raw_rows = loaded.get("categories")
    if not isinstance(raw_rows, list):
        raise DataRegisterError(f"{path}: 'categories' must be a list")
    rows: dict[DataCategory, DataCategoryRow] = {}
    for index, raw in enumerate(raw_rows):
        try:
            row = DataCategoryRow.model_validate(raw)
        except ValidationError as exc:
            raise DataRegisterError(f"{path}: categories[{index}]: {exc}") from exc
        if row.category is DataCategory.GENERAL_HEALTH:
            raise DataRegisterError(
                f"{path}: general_health has no row here; the slots.value column "
                "inventory (intake_platform.db.models) governs it"
            )
        if row.category in rows:
            raise DataRegisterError(f"{path}: two rows for {row.category.value}")
        rows[row.category] = row
    absent = [
        c.value for c in DataCategory if c is not DataCategory.GENERAL_HEALTH and c not in rows
    ]
    if absent:
        raise DataRegisterError(
            f"{path}: no row for {', '.join(absent)}. Every category of the closed set "
            "has exactly one row, so none can be forgotten"
        )
    return DataCategoryRegister(version=version.strip(), rows=MappingProxyType(rows))
