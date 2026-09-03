"""INT-312 — a TC Kimlik number said aloud (CLAUDE.md invariants 6 and 14).

Both redaction tiers matched ``\\b[1-9]\\d{10}\\b`` — a **contiguous** eleven-
digit run. A patient reading their identity number out loud does not produce
one: a recogniser emits digit groups, hyphenated runs, Turkish digit words, and
mixtures of all three inside a single utterance. INT-102's adversarial suite
committed the reproduction rather than pre-normalising its own input; this
module is the unit-level half of closing it.

**The checksum is the whole discriminator, and that is a deliberate design
constraint rather than an optimisation.** Turkish digit words are ordinary
clinical speech — *"on beş gündür ağrım var"* is fifteen days of pain — and
over-masking a symptom description is a clinical harm, not a nuisance: a
redacted duration is a lost history. So candidates are assembled, the published
checksum is applied, and only what passes is masked.

**The candidate window is token-aligned.** A candidate begins at the first digit
some token contributed and ends at the last digit some token contributed, so no
candidate can consume part of a neighbouring number: a thirteen-digit barcode
contributes thirteen digits in one token and therefore offers no eleven-digit
window at all, and ``4 100 000 000 78`` yields the identifier without the ``4``.

**It is a redaction concern, not an ASR feature.** The module is text-in,
text-out, lives in ``intake_platform`` where both tiers already are, and is
asserted here to be unreachable from the voice runtime — nothing about it
touches audio (invariant 3) or sits on the speech critical path (invariant 9).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from intake_platform import redaction
from intake_platform.deid import Deidentifier
from intake_platform.redaction import (
    TURKISH_DIGIT_WORDS,
    find_spoken_tckn_spans,
    is_valid_tckn,
    mask_spoken_tckn,
    redact_text,
)

REPO = Path(__file__).resolve().parents[2]

VALID = "10000000078"  # 100000000 + the two digits the published algorithm forces
FAILING = "98765432101"  # eleven digits, checksum fails — a lab accession number


def _words(value: str) -> str:
    order = ("sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
    return " ".join(order[int(char)] for char in value)


# --- the shapes speech produces ---------------------------------------------------


@pytest.mark.parametrize(
    "transcript",
    [
        "100 000 000 78",
        "10-000-000-078",
        "100-000 000 78",
        _words(VALID),
        f"bir sıfır sıfır 000 000 {_words('78')}",
        "100\u00a0000\u00a0000\u00a078",  # NBSP: what a keyboard-safe renderer emits
    ],
    ids=["spaced", "hyphenated", "mixed-separators", "words", "words-and-groups", "nbsp"],
)
def test_every_spoken_shape_is_one_span_covering_the_whole_run(transcript: str) -> None:
    text = f"Kimlik numaram {transcript}, kayıt için."
    spans = find_spoken_tckn_spans(text)
    assert len(spans) == 1
    assert text[spans[0].start : spans[0].end] == transcript
    assert spans[0].digits == VALID
    assert mask_spoken_tckn(text) == "Kimlik numaram [TCKN], kayıt için."


def test_a_capitalised_first_word_is_still_a_digit_word() -> None:
    """A recogniser capitalises the first word of an utterance."""
    text = _words(VALID).capitalize()
    assert text.startswith("Bir ")
    assert mask_spoken_tckn(text) == "[TCKN]"


# --- the checksum is the discriminator --------------------------------------------


@pytest.mark.parametrize(
    "transcript",
    ["987 654 321 01", "98-765-432-101", "987 654 321 01", "98765432101"],
    ids=["spaced", "hyphenated", "spaced-again", "contiguous"],
)
def test_the_same_shapes_with_a_failing_checksum_are_untouched(transcript: str) -> None:
    assert not is_valid_tckn(FAILING)
    text = f"Numune kabul no {transcript} olarak kaydedildi."
    assert find_spoken_tckn_spans(text) == ()
    assert mask_spoken_tckn(text) == text


def test_a_spoken_duration_is_not_an_identifier() -> None:
    text = "On beş gündür ağrım var, iki üç gece de uyuyamadım."
    assert mask_spoken_tckn(text) == text


def test_a_leading_zero_is_refused_so_a_spoken_phone_is_not_a_tckn() -> None:
    """``is_valid_tckn`` requires ``[1-9]`` first; a mobile number said aloud is
    eleven digits and starts with a zero. The phone pattern owns it, not this."""
    spoken_phone = _words("05321114455")
    assert mask_spoken_tckn(spoken_phone) == spoken_phone


# --- the window cannot swallow a neighbour ----------------------------------------


def test_a_thirteen_digit_barcode_offers_no_window_at_all() -> None:
    """Token alignment, stated as a test: thirteen digits arrive as one token,
    so there is no eleven-digit candidate inside it to test a checksum on."""
    text = "Ürün barkodu 8690123456789 stokta görünüyor."
    assert find_spoken_tckn_spans(text) == ()
    assert mask_spoken_tckn(text) == text


def test_a_neighbouring_number_is_left_beside_the_mask() -> None:
    """``4 100 000 000 78`` is twelve digits across five tokens. The only
    token-aligned eleven-digit window starts after the ``4``."""
    text = f"Oda 4 {'100 000 000 78'} numaralı hasta."
    masked = mask_spoken_tckn(text)
    assert masked == "Oda 4 [TCKN] numaralı hasta."


def test_a_duration_touching_the_identifier_survives() -> None:
    text = f"{_words(VALID)} beş gündür ağrım var."
    assert mask_spoken_tckn(text) == "[TCKN] beş gündür ağrım var."


def test_two_identifiers_in_one_utterance_are_two_spans() -> None:
    second = "20000000046"
    assert is_valid_tckn(second)
    text = f"Benimki {'100 000 000 78'}, eşiminki {_words(second)}."
    spans = find_spoken_tckn_spans(text)
    assert [span.digits for span in spans] == [VALID, second]
    assert mask_spoken_tckn(text) == "Benimki [TCKN], eşiminki [TCKN]."


def test_two_identifiers_with_nothing_between_them_are_still_two_spans() -> None:
    text = "100 000 000 78 100 000 000 78"
    assert [span.digits for span in find_spoken_tckn_spans(text)] == [VALID, VALID]
    assert mask_spoken_tckn(text) == "[TCKN] [TCKN]"


# --- what does not chain ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "100, 000 000 78",
        "100.000 000 78",
        "100  000 000 78",
        "100 - 000 000 78",
        "100/000 000 78",
    ],
    ids=["comma", "dot", "double-space", "spaced-hyphen", "slash"],
)
def test_only_a_single_space_or_hyphen_joins_two_tokens(text: str) -> None:
    """One separator character between tokens, and only space, NBSP or hyphen.

    A looser rule reaches across ``0.5 - 5.5 mIU/L`` and across a thousands
    separator, which is how a redactor becomes a number shredder by accident.
    """
    assert mask_spoken_tckn(text) == text


def test_a_digit_run_glued_to_a_word_is_not_a_token() -> None:
    text = "ABC100 000 000 78"
    assert mask_spoken_tckn(text) == text


def test_a_number_word_above_nine_is_not_a_digit_word() -> None:
    """``on``/``yirmi``/``yüz`` are how durations and readings are spoken."""
    assert set(TURKISH_DIGIT_WORDS) == {
        "sıfır",
        "bir",
        "iki",
        "üç",
        "dört",
        "beş",
        "altı",
        "yedi",
        "sekiz",
        "dokuz",
    }
    assert "on" not in TURKISH_DIGIT_WORDS
    assert "yüz" not in TURKISH_DIGIT_WORDS


def test_text_with_no_digit_bearing_token_is_returned_unchanged() -> None:
    text = "Karnımın sağ alt tarafı ağrıyor."
    assert find_spoken_tckn_spans(text) == ()
    assert mask_spoken_tckn(text) == text


# --- both tiers use it ------------------------------------------------------------


def test_both_redaction_tiers_mask_the_spoken_form() -> None:
    text = "Kimlik numaram 100 000 000 78, kayıt için."
    assert redact_text(text) == "Kimlik numaram [TCKN], kayıt için."
    assert Deidentifier(None, subject_key="int-312").deidentify(text) == (
        "Kimlik numaram [TCKN], kayıt için."
    )


def test_the_deid_tier_reports_the_spoken_run_as_one_tckn_entity() -> None:
    report = Deidentifier(None, subject_key="int-312").analyze("no 100 000 000 78 var")
    assert [(e.type, e.value) for e in report.entities] == [("TCKN", "100 000 000 78")]


def test_an_iban_keeps_its_digits_from_the_spoken_tier() -> None:
    """A grouped IBAN is one entity; its digit run must not be re-claimed."""
    text = "İade TR33 0006 1005 1978 6457 8413 26 hesabına yapılacaktır."
    masked = Deidentifier(None, subject_key="int-312").deidentify(text)
    assert masked == "İade [IBAN] hesabına yapılacaktır."


# --- the boundary this may not cross ----------------------------------------------


def test_the_module_is_text_in_text_out_and_imports_nothing_but_the_checksum() -> None:
    """The narrowest statement of "a redaction concern, not an ASR feature".

    Text in, text out, and an import set that admits no transport, no model and
    no runtime — so there is nothing here that could hold a buffer (invariant 3)
    or be awaited by the Talker (invariant 9).
    """
    for func in (find_spoken_tckn_spans, mask_spoken_tckn):
        params = list(inspect.signature(func).parameters.values())
        assert [p.annotation for p in params if p.name == "text"] == ["str"]
        assert inspect.signature(func).return_annotation != inspect.Signature.empty

    tree = ast.parse(Path(redaction.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported == {"__future__", "dataclasses", "re", "typing"}


def test_nothing_in_the_voice_runtime_reaches_the_normalisation() -> None:
    """Invariant 9: identifier handling stays off the speech critical path.

    The normalisation is a redaction concern and runs where the whole utterance
    is already at rest. If a future change wires it into the runtime it will
    fail here first, with the reason written down.
    """
    runtime = REPO / "services" / "voice-runtime" / "src"
    assert runtime.is_dir()
    reached = sorted(
        path.relative_to(REPO).as_posix()
        for path in runtime.rglob("*.py")
        for name in ("intake_platform.redaction", "mask_spoken_tckn", "find_spoken_tckn_spans")
        if name in path.read_text(encoding="utf-8")
    )
    assert reached == [], (
        "the redaction tier is not reachable from the voice runtime, and the spoken "
        "normalisation must not be the change that makes it so"
    )
