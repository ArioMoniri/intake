"""Instrument licence registry stub (INT-040).

Statuses are copied verbatim from the files/04 header licence table
(corrected 25 Aug 2026) and HUMAN_BLOCKERS.md: an instrument whose licence
is not ``GO`` does not compile into a pack (CLAUDE.md clinical content
rules; invariant 45 ``instrument_licence_gate`` per HB-L2). Lookups fail
CLOSED: an instrument this registry does not know is ``UNKNOWN``, never GO.

This is licensing metadata only — no instrument content (items, wording,
scoring) exists anywhere in this package (INT-040 is mechanism-only).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType

__all__ = ["INSTRUMENT_LICENCES", "InstrumentLicence", "LicenceTable", "instrument_licence"]


class InstrumentLicence(enum.StrEnum):
    """Licence verdicts of the files/04 header table, plus the fail-closed
    ``UNKNOWN`` for anything the registry has never recorded."""

    GO = "GO"
    NEEDS_PERMISSION = "NEEDS_PERMISSION"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


type LicenceTable = Mapping[str, InstrumentLicence]
"""An instrument-licence lookup table (id → verdict); tests may inject one."""


INSTRUMENT_LICENCES: Mapping[str, InstrumentLicence] = MappingProxyType(
    {
        # files/04 header: Pfizer's blanket permission covers PHQ/GAD.
        "PHQ-9": InstrumentLicence.GO,
        "PHQ-2": InstrumentLicence.GO,
        "GAD-7": InstrumentLicence.GO,
        "GAD-2": InstrumentLicence.GO,
        # HB-L2: Clario holds the exclusive RFMH electronic licence.
        "C-SSRS": InstrumentLicence.BLOCKED,
        # HB-L3: CC BY-NC-SA 3.0 IGO since 2024 — NonCommercial.
        "WHO-5": InstrumentLicence.BLOCKED,
        # HB-L4: Stanford's permission covers the English version only.
        "HAQ-DI": InstrumentLicence.NEEDS_PERMISSION,
    }
)


def instrument_licence(
    instrument_id: str, registry: LicenceTable | None = None
) -> InstrumentLicence:
    """Look up an instrument's licence status, failing closed to UNKNOWN.

    ``registry`` lets tests inject a synthetic table; production callers use
    the default, whose rows carry the files/04 header citations above.
    """
    table = INSTRUMENT_LICENCES if registry is None else registry
    return table.get(instrument_id, InstrumentLicence.UNKNOWN)
