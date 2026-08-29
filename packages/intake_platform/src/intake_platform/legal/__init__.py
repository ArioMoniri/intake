"""Legal-text binding (invariant 18): docs/legal is the only source, and the
hash proves which bytes were shown. Consent copy has its own loader in
:mod:`intake_platform.consent.texts`; this package holds the fixed strings of
files/06 §7."""

from __future__ import annotations

from intake_platform.legal.strings import (
    LegalStrings,
    LegalStringsCatalog,
    LegalStringsChangedError,
    LegalStringsError,
    LegalStringsInvalidError,
    LegalStringsMissingError,
)

__all__ = [
    "LegalStrings",
    "LegalStringsCatalog",
    "LegalStringsChangedError",
    "LegalStringsError",
    "LegalStringsInvalidError",
    "LegalStringsMissingError",
]
