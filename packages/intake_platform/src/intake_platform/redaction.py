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
unit-tested against fixture logs from the committed YAML itself.
"""

from __future__ import annotations

import re

__all__ = ["is_valid_tckn", "redact_text"]

_TCKN_CANDIDATE = re.compile(r"\b[1-9][0-9]{10}\b")
_TR_MOBILE = re.compile(r"\b0?5[0-9]{9}\b")
_TR_IBAN = re.compile(r"\bTR[0-9]{24}\b")


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


def _mask_tckn(match: re.Match[str]) -> str:
    candidate = match.group(0)
    return "[TCKN]" if is_valid_tckn(candidate) else candidate


def redact_text(text: str) -> str:
    """Mask TCKN/phone/IBAN occurrences in free text. Order matters: IBANs
    first (their digit runs must not be half-eaten), then checksum-validated
    TCKNs, then mobile numbers."""
    text = _TR_IBAN.sub("[IBAN]", text)
    text = _TCKN_CANDIDATE.sub(_mask_tckn, text)
    text = _TR_MOBILE.sub("[PHONE]", text)
    return text
