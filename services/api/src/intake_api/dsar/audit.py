"""The lawful-basis reference every DSAR audit entry carries (INT-037).

The hash-chained audit's ``consent_scope_ref`` records what authorised the
action. A data-subject request is not authorised by a consent scope — it is a
statutory right under 6698 s. KVKK m.11, answered within the m.13 window
(files/06 §1) — so writing ``scope:core`` there would be a false record of the
basis, and leaving it blank is not an option the chain accepts. The reference
names the basis instead, in the id shape the chain enforces.
"""

from __future__ import annotations

from typing import Final

__all__ = ["DSAR_BASIS_REF"]

#: files/06 §1, row KVKK-11/13.
DSAR_BASIS_REF: Final = "basis:KVKK-11/13"
