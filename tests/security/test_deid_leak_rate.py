"""INT-015 — de-identification: pattern tier + leak-rate gate (KVKK-9/16).

Acceptance, verbatim:
  "recognizers: TCKN (checksum), TR phone, IBAN, names (TR NER), addresses,
   date shifting; sits in front of every cloud model call and Loop-2 exports"
  "synthetic corpus with labels; measured leak rate < 0.1 percent gate in CI"

This module gates the deterministic tier (TCKN/PHONE/IBAN/EMAIL/DATE) on the
authored synthetic corpus and on the vendored Apache-2.0 corpus. The NER tier
(names/addresses — our own fine-tune, provenance in the model registry) is
gated in test_deid_ner.py, and `deidentify_for_egress` FAILS CLOSED when the
NER model is absent: pattern-only scrubbing must never be mistaken for full
de-identification on the cloud boundary.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from intake_platform.deid import DateShifter, Deidentifier

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "deid" / "pattern_corpus.jsonl"
VENDORED = REPO / "tests" / "fixtures" / "deid" / "vendor" / "pii_corpus.jsonl"

PATTERN_TYPES = {"TCKN", "PHONE", "IBAN", "EMAIL", "DATE"}


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _engine() -> Deidentifier:
    return Deidentifier(ner_model_dir=None, subject_key="test-subject-1")


# --- fixture integrity ------------------------------------------------------------


def test_fixture_offsets_are_exact() -> None:
    for row in _rows(CORPUS):
        for e in row["entities"]:
            assert row["text"][e["start"] : e["end"]] == e["value"], row["text"]


# --- the leak gate ----------------------------------------------------------------


def test_pattern_leak_rate_below_gate() -> None:
    engine = _engine()
    leaks: list[str] = []
    total = 0
    for row in _rows(CORPUS):
        masked = engine.deidentify(row["text"])
        for e in row["entities"]:
            if e["type"] not in PATTERN_TYPES:
                continue
            total += 1
            if e["value"] in masked:
                leaks.append(f"{e['type']}: {e['value']!r} survived in {masked!r}")
    assert total >= 25, "corpus shrank — the gate needs its cases"
    leak_rate = len(leaks) / total
    assert leak_rate < 0.001, f"leak rate {leak_rate:.4f} over gate; leaks:\n" + "\n".join(leaks)


def test_distractors_are_not_overmasked() -> None:
    engine = _engine()
    for row in _rows(CORPUS):
        if row["entities"]:
            continue
        masked = engine.deidentify(row["text"])
        assert masked == row["text"], (
            f"over-masking a non-PII line costs the note its clinical content: {masked!r}"
        )


def test_vendored_apache_corpus_checksum_classes() -> None:
    # fevziegeyurtsevenler/turkish-pii-corpus @ 2e770a83 (Apache-2.0), vendored
    # with attribution. We gate the classes our pattern tier claims; its other
    # classes (VKN, PLAKA, CREDIT_CARD) are out of INT-015's acceptance list.
    engine = _engine()
    ours = {"TCKN": "TCKN", "IBAN": "IBAN", "PHONE": "PHONE", "EMAIL": "EMAIL"}
    leaks = 0
    total = 0
    for row in _rows(VENDORED):
        masked = engine.deidentify(row["text"])
        for e in row.get("entities", []):
            if e["type"] not in ours:
                continue
            total += 1
            if e["value"] in masked:
                leaks += 1
    assert total >= 50, f"vendored corpus gave too few cases ({total})"
    assert leaks / total < 0.001, f"{leaks}/{total} leaked from the vendored corpus"


# --- date shifting ----------------------------------------------------------------


def test_date_shift_is_deterministic_bounded_and_interval_preserving() -> None:
    shifter = DateShifter(subject_key="patient-abc")
    d1 = shifter.shift(date(2026, 8, 15))
    d2 = shifter.shift(date(2026, 8, 22))
    assert d1 == shifter.shift(date(2026, 8, 15)), "same subject, same date → same output"
    assert (d2 - d1).days == 7, "intervals must survive the shift"
    offset = (d1 - date(2026, 8, 15)).days
    assert 1 <= abs(offset) <= 30, "offset must be bounded and never zero"
    other = DateShifter(subject_key="patient-xyz").shift(date(2026, 8, 15))
    assert other != d1, "different subjects should not share an offset (2^-? chance caught here)"


def test_dates_in_text_are_shifted_not_masked() -> None:
    engine = _engine()
    masked = engine.deidentify("Kontrol 12.09.2026 tarihinde yapılacak.")
    assert "12.09.2026" not in masked
    assert "[DATE]" not in masked, "dates shift (clinical intervals matter); they are not masked"
    assert any(ch.isdigit() for ch in masked), "a shifted date must still be a date"


def test_turkish_month_names_shift() -> None:
    engine = _engine()
    masked = engine.deidentify("Taburcu 15 Ağustos 2026, kontrol 22 Ağustos 2026.")
    assert "15 Ağustos 2026" not in masked
    assert "22 Ağustos 2026" not in masked


# --- the egress contract ----------------------------------------------------------


def test_egress_fails_closed_without_ner() -> None:
    engine = _engine()
    try:
        engine.deidentify_for_egress("Hasta Ayşe Yılmaz bugün geldi.")
    except RuntimeError as err:
        assert "NER" in str(err)
    else:
        raise AssertionError(
            "egress de-identification without the names/addresses model must fail closed — "
            "pattern-only scrubbing on the cloud boundary is the KVKK hole, not a fallback"
        )


def test_analyze_reports_ner_disabled() -> None:
    engine = _engine()
    report = engine.analyze("TCKN 72096654290")
    assert report.ner_enabled is False
    assert any(e.type == "TCKN" for e in report.entities)
