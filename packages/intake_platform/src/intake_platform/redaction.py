"""PII redaction primitives (INT-011; CLAUDE.md invariant 6 — no PHI in logs).

Deterministic, dependency-free text redaction for the identifiers Turkish
telemetry actually leaks: TC Kimlik numbers (validated by the published
checksum so an arbitrary 11-digit order id is not shredded), TR mobile
numbers, and TR IBANs. Free-text *name* redaction is NER territory and
belongs to the de-identification service (Presidio + Turkish recognizers,
INT-015); structured log attributes are constrained by the allow-list in
:mod:`intake_platform.otel` instead.

The OTel collector config (infra/observability/otel-collector.yaml) carries
the same patterns as a second, pipeline-level layer; its statements are
unit-tested against fixture logs from the committed YAML itself. That layer is
OTTL and cannot compute a checksum, so it stays a contiguous-run pattern: the
spoken forms below are masked *here*, in the only tier that can tell an
identity number from an accession number.

Spoken forms (INT-312)
----------------------
``\\b[1-9]\\d{10}\\b`` is a **contiguous** eleven-digit run, and a patient
reading their identity number out loud does not produce one. A recogniser emits
digit groups (``100 000 000 78``), hyphenated runs, Turkish digit words, and
mixtures of all three inside one utterance. :func:`find_spoken_tckn_spans`
assembles those back into candidate digit sequences so the same checksum can
decide.

Three properties hold it in place, and each is a test:

1. **The checksum stays the discriminator.** Candidates are assembled, then
   validated; only what passes is masked. This is not an optimisation — Turkish
   digit words are ordinary clinical speech (*"on beş gündür ağrım var"* is
   fifteen days of pain), and over-masking a symptom description is a clinical
   harm rather than a nuisance, because a redacted duration is a lost history.
2. **The candidate window is token-aligned.** A candidate begins at the first
   digit some token contributed and ends at the last digit some token
   contributed, so no candidate can consume part of a neighbouring number: a
   thirteen-digit barcode arrives as one token and offers no eleven-digit window
   at all, and ``4 100 000 000 78`` yields the identifier without the ``4``.
   Scanning is left to right and resumes after each match, so a second
   identifier in the same utterance is found by the same pass.
3. **It is a redaction concern, not an ASR feature.** This module is text in,
   text out, imports nothing but the standard library, and is not reachable from
   ``services/voice-runtime`` — so nothing here retains audio (invariant 3) or
   can be awaited on the speech critical path (invariant 9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "TCKN_DIGIT_COUNT",
    "TURKISH_DIGIT_WORDS",
    "SpokenTcknSpan",
    "find_spoken_tckn_spans",
    "is_valid_tckn",
    "mask_spoken_tckn",
    "redact_text",
]

_TCKN_CANDIDATE = re.compile(r"\b[1-9][0-9]{10}\b")
# A Turkish mobile however it is written (INT-581). The OTP tier normalises
# every number to E.164 (``+90``, then 5 and nine digits), and the INT-013 pattern this
# replaces (``\b0?5[0-9]{9}\b``) could not see that form at all: the ``+90``
# prefix glued the digits to a word character. It is now taken with the
# international (``+90``, ``0090``, ``90``) or national (``0``) prefix or none,
# written whole or grouped 3-3-2-2 by single spaces or hyphens, and bounded by
# non-digits so it never eats into a longer run. A grouped run of digits that
# starts with 5 is masked too: in a log line that is the right side to err on.
_SEP: Final = "[ \u00a0-]?"
_TR_MOBILE = re.compile(
    rf"(?<![0-9])(?:(?:\+|00)?90{_SEP}|0{_SEP})?"
    rf"5[0-9]{{2}}{_SEP}[0-9]{{3}}{_SEP}[0-9]{{2}}{_SEP}[0-9]{{2}}(?![0-9])"
)
_TR_IBAN = re.compile(r"\bTR[0-9]{24}\b")

#: How many digits a TC Kimlik number has.
TCKN_DIGIT_COUNT: Final = 11

#: The ten digits as an ASR without inverse text normalisation writes them.
#: Only 0–9: ``on``, ``yirmi`` and ``yüz`` are how durations and readings are
#: spoken, and admitting them would put a symptom description one checksum
#: collision away from being deleted.
TURKISH_DIGIT_WORDS: Final[dict[str, str]] = {
    "sıfır": "0",
    "bir": "1",
    "iki": "2",
    "üç": "3",
    "dört": "4",
    "beş": "5",
    "altı": "6",
    "yedi": "7",
    "sekiz": "8",
    "dokuz": "9",
}

# Canonical spelling plus its sentence-initial capitalisation, which is the only
# case variation a recogniser produces. Matching case-insensitively instead
# would drag in Turkish dotted/dotless folding, where ``I`` is both the capital
# of ``ı`` and the ASCII capital of ``i`` — an ambiguity with no right answer
# and no place in a redactor.
_WORD_TOKENS: Final[dict[str, str]] = {
    form: digit for word, digit in TURKISH_DIGIT_WORDS.items() for form in (word, word.capitalize())
}

# One separator character, and only a space, a non-breaking space or a hyphen.
# Anything looser reaches across "0,5 - 5,5 mIU/L" and across a thousands
# separator, which is how a redactor becomes a number shredder by accident.
_SEPARATOR_CLASS: Final = "[ \u00a0-]"
_TOKEN_PATTERN: Final = "(?:[0-9]+|{})".format("|".join(sorted(_WORD_TOKENS)))
_CHAIN = re.compile(rf"\b{_TOKEN_PATTERN}(?:{_SEPARATOR_CLASS}{_TOKEN_PATTERN})*\b")
_TOKEN = re.compile(_TOKEN_PATTERN)


@dataclass(frozen=True)
class SpokenTcknSpan:
    """One checksum-valid identity number, as it was actually said.

    ``start``/``end`` bound the whole spoken run in the source text — separators
    included — because masking the digits and leaving ``100 - 78`` behind is a
    partial leak dressed as a redaction.
    """

    start: int
    end: int
    digits: str


def is_valid_tckn(value: str) -> bool:
    """The published TC Kimlik checksum: 11 digits, no leading zero,
    d10 = ((d1+d3+d5+d7+d9)·7 − (d2+d4+d6+d8)) mod 10, d11 = Σd1..d10 mod 10."""
    if not re.fullmatch(r"[1-9][0-9]{10}", value):
        return False
    digits = [int(c) for c in value]
    odd = sum(digits[0:9:2])
    even = sum(digits[1:8:2])
    if (odd * 7 - even) % 10 != digits[9]:
        return False
    return sum(digits[:10]) % 10 == digits[10]


def _chain_tokens(chain: str, offset: int) -> list[tuple[int, int, str]]:
    """``(start, end, digits)`` for every digit-bearing token in one chain."""
    tokens: list[tuple[int, int, str]] = []
    for match in _TOKEN.finditer(chain):
        raw = match.group(0)
        word = _WORD_TOKENS.get(raw)
        tokens.append((offset + match.start(), offset + match.end(), raw if word is None else word))
    return tokens


def _spans_in_chain(chain: str, offset: int) -> list[SpokenTcknSpan]:
    tokens = _chain_tokens(chain, offset)
    boundaries: list[int] = [0]
    for _start, _end, digits in tokens:
        boundaries.append(boundaries[-1] + len(digits))
    if boundaries[-1] < TCKN_DIGIT_COUNT:
        return []

    assembled = "".join(token[2] for token in tokens)
    # Every token contributes at least one digit, so the boundaries are strictly
    # increasing and this mapping is one-to-one: a window may only end where a
    # token ends.
    boundary_at = {value: index for index, value in enumerate(boundaries)}

    spans: list[SpokenTcknSpan] = []
    first = 0
    while first < len(tokens):
        opening = boundaries[first]
        candidate = assembled[opening : opening + TCKN_DIGIT_COUNT]
        last = boundary_at.get(opening + TCKN_DIGIT_COUNT)
        if last is not None and is_valid_tckn(candidate):
            spans.append(SpokenTcknSpan(tokens[first][0], tokens[last - 1][1], candidate))
            first = last
        else:
            first += 1
    return spans


def find_spoken_tckn_spans(text: str) -> tuple[SpokenTcknSpan, ...]:
    """Every checksum-valid TC Kimlik number in ``text``, however it was said.

    Contiguous runs are found too: a single eleven-digit token is one chain of
    one token, which is the same case as any other.
    """
    found: list[SpokenTcknSpan] = []
    for chain in _CHAIN.finditer(text):
        found.extend(_spans_in_chain(chain.group(0), chain.start()))
    return tuple(found)


def mask_spoken_tckn(text: str, replacement: str = "[TCKN]") -> str:
    """Replace each spoken TC Kimlik run — separators and all — with ``[TCKN]``."""
    spans = find_spoken_tckn_spans(text)
    if not spans:
        return text
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(text[cursor : span.start])
        out.append(replacement)
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


def _mask_tckn(match: re.Match[str]) -> str:
    candidate = match.group(0)
    return "[TCKN]" if is_valid_tckn(candidate) else candidate


def redact_text(text: str) -> str:
    """Mask TCKN/phone/IBAN occurrences in free text. Order matters: IBANs
    first (their digit runs must not be half-eaten), then checksum-validated
    TCKNs written contiguously, then the spoken forms of the same number, then
    mobile numbers."""
    text = _TR_IBAN.sub("[IBAN]", text)
    text = _TCKN_CANDIDATE.sub(_mask_tckn, text)
    text = mask_spoken_tckn(text)
    text = _TR_MOBILE.sub("[PHONE]", text)
    return text
