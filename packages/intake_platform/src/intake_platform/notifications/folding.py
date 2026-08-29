"""Turkish-correct case folding and tokenisation for the content-freedom
scan (INT-141).

Python's default casing is wrong for Turkish in exactly the direction that
matters here: ``"KADIN".lower()`` is ``"kadin"``, which does not equal
``"kadın"``, so a scan built on the default fold reports nothing when a
branch label arrives shouted. The dotted/dotless pair is handled explicitly
before lowering; every other Turkish letter round-trips correctly under
``str.lower``.

Kept in its own module so the catalogue can build its vocabulary from it
without importing the scan that reads the vocabulary.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["fold", "tokens"]

# İ → i and I → ı BEFORE lowering; str.lower() then handles ç/ğ/ö/ş/ü. The
# circumflex forms appear in Turkish medical prose (hâl, âdet) and fold to
# their plain vowels so "Hâl" and "hal" are one token.
_TURKISH_FOLD: Final = str.maketrans(
    {"İ": "i", "I": "ı", "Â": "a", "Î": "i", "Û": "u", "â": "a", "î": "i", "û": "u"}
)

#: Maximal runs of letters or digits. Digits are tokens on purpose: a numeral
#: in a notification body is data, and the corpus contains none.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def fold(value: str) -> str:
    """Case-fold for comparison, Turkish dotted/dotless pair included."""
    return value.translate(_TURKISH_FOLD).lower()


def tokens(value: str) -> tuple[str, ...]:
    """Folded word tokens, in order, with repeats kept (callers that want a
    set say so)."""
    return tuple(_TOKEN.findall(fold(value)))
