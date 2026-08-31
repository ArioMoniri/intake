"""How an identifier looks once it has been said out loud (INT-102).

files/04 line 203 RT-13: *"transcript contains a TC Kimlik number spoken aloud
— de-identification masks it before any cloud call and in logs"*.

INT-083 recorded why this one is sharp: a TCKN is **id-shaped** — eleven
digits, no spaces — so the trace boundary's ref-shape rule would admit one,
which is why every string span value is run through the redactor first. Said
aloud it does not even arrive in that shape. An ASR transcript of somebody
reading their kimlik gives digit *groups* ("one hundred, zero zero zero…") or
Turkish digit *words*, and both are what the patient actually said.

This module renders those two forms and inverts them. It is an **adversarial
probe**, not a de-identification tier: its job is to demonstrate that the
identifier is fully present and fully recoverable in the transcript, so a test
can then ask what the real boundary does about it. It is deliberately not
wired into anything on the serving path — a probe that also became the fix
would leave the fix untested.

The Turkish digit words are not typed here. They come from
:func:`protocols.compile.tr_orthography.turkish_cardinal`, the committed
lexicon the protocol compiler expands numerals with (CLAUDE.md invariant 22),
so this module cannot disagree with the product about how a digit is spelt.
"""

from __future__ import annotations

from protocols.compile.tr_orthography import parse_turkish_cardinal, turkish_cardinal

__all__ = [
    "DIGIT_GROUPING",
    "digits_from_spoken",
    "spaced_digit_groups",
    "spoken_turkish_digits",
]

#: How an eleven-digit identifier falls out of a person's mouth: three, three,
#: three, then the last two. Fixed, so the fixture is deterministic.
DIGIT_GROUPING = (3, 3, 3, 2)


def _require_digits(value: str) -> str:
    if not value or not value.isdigit():
        raise ValueError("a spoken-identifier rendering takes a run of digits")
    return value


def spaced_digit_groups(digits: str, grouping: tuple[int, ...] = DIGIT_GROUPING) -> str:
    """``"10000000146"`` → ``"100 000 001 46"`` — the transcript's shape.

    The point of this rendering is that it is one space away from the
    contiguous run the pattern tier matches, and a space is not something the
    patient chose.
    """
    _require_digits(digits)
    out: list[str] = []
    index = 0
    for size in grouping:
        if index >= len(digits):
            break
        out.append(digits[index : index + size])
        index += size
    if index < len(digits):
        out.append(digits[index:])
    return " ".join(out)


def spoken_turkish_digits(digits: str) -> str:
    """``"10000000146"`` → ``"bir sıfır sıfır …"`` — digit by digit, in Turkish."""
    return " ".join(turkish_cardinal(int(digit)) for digit in _require_digits(digits))


def digits_from_spoken(text: str) -> str:
    """Recover the digit run from either rendering — the attacker's half.

    Permissive by design: it walks a whole sentence and keeps what is a digit
    or a single Turkish digit word, ignoring everything else. That is what
    makes it evidence — the identifier is recoverable from ordinary transcript
    text, without knowing where in the sentence it starts.
    """
    out: list[str] = []
    for token in text.replace(",", " ").split():
        if token.isdigit():
            out.append(token)
            continue
        try:
            value = parse_turkish_cardinal(token)
        except ValueError:
            continue
        if 0 <= value <= 9:
            out.append(str(value))
    return "".join(out)
