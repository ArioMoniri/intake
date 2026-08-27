"""De-identification engine (INT-015; KVKK-9/16, sec_row: cloud-boundary).

Two tiers:

- **Pattern tier** (always on, deterministic): checksum-validated TCKN, TR
  mobile numbers (contiguous and spaced), TR IBAN (contiguous and 4-grouped),
  email, and Turkish dates. Dates are **shifted, not masked** — clinical
  intervals matter — with a per-subject deterministic offset (±1..30 days) so
  the same subject's timeline stays internally consistent while the real
  dates never leave.
- **NER tier** (names, addresses): our own fine-tune with recorded provenance
  (model registry row; base MIT via raw blob, data CC-BY-4.0 synthetic),
  loaded from ``INTAKE_DEID_MODEL_DIR`` or an explicit path.

The egress contract: :meth:`Deidentifier.deidentify_for_egress` **fails
closed** when the NER tier is unavailable. Pattern-only scrubbing must never
be mistaken for full de-identification on the cloud boundary — a name that
survives to a third party is the KVKK hole, and a silent fallback is how it
would happen. This function is what the gateways (INT-083+) and Loop-2
exports must call; wiring it there carries its own tests in those issues.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from intake_platform.redaction import is_valid_tckn

__all__ = ["DateShifter", "DeidEntity", "DeidReport", "Deidentifier"]

_MONTHS_TR = [
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]
_MONTH_INDEX = {name.lower(): i + 1 for i, name in enumerate(_MONTHS_TR)}
_MONTH_ALT = "|".join(_MONTHS_TR)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IBAN = re.compile(r"\bTR\d{2}(?:[ ]?\d{4}){5}[ ]?\d{2}\b")
_TCKN = re.compile(r"\b[1-9]\d{10}\b")
_PHONE = re.compile(r"\b0?5\d{2}(?:[ ]?\d{3})(?:[ ]?\d{2}){2}\b|\b0?5\d{9}\b")
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})([./])(\d{1,2})\2(\d{4})\b")
# Title-case and lower-case month names; the corpus and real documents use both.
_DATE_TEXTUAL = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\s+(\d{{4}})\b", re.IGNORECASE)


@dataclass(frozen=True)
class DeidEntity:
    type: str
    start: int
    end: int
    value: str


@dataclass(frozen=True)
class DeidReport:
    entities: tuple[DeidEntity, ...]
    ner_enabled: bool


class _NerBackend(Protocol):
    def __call__(self, text: str) -> list[dict[str, object]]: ...


class DateShifter:
    """Per-subject deterministic date shift: offset in ±1..30 days, derived
    from an HMAC of the subject key — never zero, never stored, and identical
    for every date of the same subject so intervals survive."""

    def __init__(self, subject_key: str, secret: bytes = b"intake-deid-v1") -> None:
        digest = hmac.new(secret, subject_key.encode("utf-8"), hashlib.sha256).digest()
        magnitude = (digest[0] % 30) + 1
        sign = 1 if digest[1] % 2 == 0 else -1
        self._offset = datetime.timedelta(days=sign * magnitude)

    @property
    def offset_days(self) -> int:
        return self._offset.days

    def shift(self, value: datetime.date) -> datetime.date:
        return value + self._offset


class Deidentifier:
    def __init__(
        self,
        ner_model_dir: str | Path | None,
        subject_key: str,
    ) -> None:
        self._shifter = DateShifter(subject_key)
        self._ner: _NerBackend | None = None
        if ner_model_dir is not None:
            self._ner = self._load_ner(Path(ner_model_dir))

    @staticmethod
    def _load_ner(model_dir: Path) -> _NerBackend:
        # Imported lazily: torch/transformers are the [ner] extra, required
        # wherever egress de-identification runs, optional for pattern-only use.
        from transformers import pipeline  # noqa: PLC0415

        ner = pipeline(
            "token-classification",
            model=str(model_dir),
            aggregation_strategy="first",
        )

        def run(text: str) -> list[dict[str, object]]:
            hits: list[dict[str, object]] = [dict(h) for h in ner(text)]
            return hits

        return run

    @property
    def ner_enabled(self) -> bool:
        return self._ner is not None

    # --- analysis -----------------------------------------------------------------

    def _pattern_entities(self, text: str) -> list[DeidEntity]:
        found: list[DeidEntity] = []

        def add(kind: str, match: re.Match[str]) -> None:
            found.append(DeidEntity(kind, match.start(), match.end(), match.group(0)))

        for m in _EMAIL.finditer(text):
            add("EMAIL", m)
        for m in _IBAN.finditer(text):
            add("IBAN", m)
        for m in _DATE_NUMERIC.finditer(text):
            if self._parse_numeric_date(m) is not None:
                add("DATE", m)
        for m in _DATE_TEXTUAL.finditer(text):
            if self._parse_textual_date(m) is not None:
                add("DATE", m)
        for m in _TCKN.finditer(text):
            if is_valid_tckn(m.group(0)):
                add("TCKN", m)
        for m in _PHONE.finditer(text):
            add("PHONE", m)

        # Longest-first overlap resolution: an IBAN's digit run must not be
        # re-claimed as a TCKN, a spaced phone must not half-match.
        found.sort(key=lambda e: (e.start, -(e.end - e.start)))
        resolved: list[DeidEntity] = []
        last_end = -1
        for entity in found:
            if entity.start >= last_end:
                resolved.append(entity)
                last_end = entity.end
        return resolved

    def _ner_entities(self, text: str) -> list[DeidEntity]:
        if self._ner is None:
            return []
        out: list[DeidEntity] = []
        for hit in self._ner(text):
            group = str(hit["entity_group"]).lower()
            if group == "private_person":
                kind = "PERSON"
            elif group == "private_address":
                kind = "ADDRESS"
            else:
                continue  # pattern tier owns the deterministic classes
            start, end = int(str(hit["start"])), int(str(hit["end"]))
            out.append(DeidEntity(kind, start, end, text[start:end]))
        return out

    def analyze(self, text: str) -> DeidReport:
        entities = self._pattern_entities(text) + self._ner_entities(text)
        entities.sort(key=lambda e: e.start)
        return DeidReport(entities=tuple(entities), ner_enabled=self.ner_enabled)

    # --- rewriting ----------------------------------------------------------------

    @staticmethod
    def _parse_numeric_date(m: re.Match[str]) -> datetime.date | None:
        day, sep, month, year = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        del sep
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _parse_textual_date(m: re.Match[str]) -> datetime.date | None:
        month = _MONTH_INDEX.get(m.group(2).lower())
        if month is None:
            return None
        try:
            return datetime.date(int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            return None

    def _rewrite(self, text: str, entity: DeidEntity) -> str:
        if entity.type == "DATE":
            numeric = _DATE_NUMERIC.fullmatch(entity.value)
            if numeric is not None:
                parsed = self._parse_numeric_date(numeric)
                if parsed is None:  # pragma: no cover — analyze() validated it
                    return "[DATE]"
                shifted = self._shifter.shift(parsed)
                sep = numeric.group(2)
                return f"{shifted.day:02d}{sep}{shifted.month:02d}{sep}{shifted.year:04d}"
            textual = _DATE_TEXTUAL.fullmatch(entity.value)
            if textual is not None:
                parsed = self._parse_textual_date(textual)
                if parsed is None:  # pragma: no cover — analyze() validated it
                    return "[DATE]"
                shifted = self._shifter.shift(parsed)
                return f"{shifted.day} {_MONTHS_TR[shifted.month - 1]} {shifted.year}"
            return "[DATE]"
        return f"[{entity.type}]"

    def _apply(self, text: str, entities: tuple[DeidEntity, ...]) -> str:
        for entity in sorted(entities, key=lambda e: e.start, reverse=True):
            text = text[: entity.start] + self._rewrite(text, entity) + text[entity.end :]
        return text

    def deidentify(self, text: str) -> str:
        """Pattern-tier (+ NER when loaded) rewriting for internal use."""
        return self._apply(text, self.analyze(text).entities)

    def deidentify_for_egress(self, text: str) -> str:
        """The cloud-boundary/Loop-2 contract — FAILS CLOSED without NER."""
        if not self.ner_enabled:
            raise RuntimeError(
                "de-identification for egress requires the names/addresses NER tier; "
                "refusing to send pattern-only-scrubbed text to an external model "
                "(set INTAKE_DEID_MODEL_DIR / pass ner_model_dir)"
            )
        return self.deidentify(text)
