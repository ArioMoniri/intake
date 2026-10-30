"""INT-488 — the App Review reviewer's processing record and notice (legal lane).

The reviewer is a real person, so the review sign-in is processing of their
personal data. Two files under ``docs/legal/store/review/`` carry it, both
hash-bound (CLAUDE.md invariant 18):

- ``app-review-signin-notes.en.md`` — the one text the owner pastes into App
  Store Connect's review notes: the sign-in steps and the reviewer's notice
  (aydınlatma). ``infra/staging/review_signin.sh --reveal-to-owner`` prints it
  byte for byte and refuses on a hash mismatch;
- ``review-signin.yaml`` — {purpose, basis, retention, recipients,
  transfer_route, notice_sha256, reviewed_by, reviewed_on}.

:func:`review_record_problem` is what ``review_cli on`` asks: it refuses while
any field is null or empty, or while ``notice_sha256`` is not the notice's
sha256. ``transfer_route`` is counsel's (INT-528's open questions, HB-L11), so
today every opening refuses here and says so. Nothing here prints a value.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import yaml

__all__ = [
    "RECORD_FIELDS",
    "REVIEW_NOTES_PATH",
    "REVIEW_RECORD_PATH",
    "review_record_problem",
]

#: Repo-relative, as every legal path the API reads (the image carries docs/legal).
REVIEW_RECORD_PATH: Final = Path("docs/legal/store/review/review-signin.yaml")
REVIEW_NOTES_PATH: Final = Path("docs/legal/store/review/app-review-signin-notes.en.md")
RECORD_FIELDS: Final = (
    "purpose",
    "basis",
    "retention",
    "recipients",
    "transfer_route",
    "notice_sha256",
    "reviewed_by",
    "reviewed_on",
)
_OWNERS: Final = "INT-528, HB-L11"


def _empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | dict):
        return not value or any(
            _empty(item) for item in (value.values() if isinstance(value, dict) else value)
        )
    return False


def review_record_problem(
    record_path: Path = REVIEW_RECORD_PATH, notes_path: Path = REVIEW_NOTES_PATH
) -> str | None:
    """Why a review window may not open under this record, or None."""
    where = record_path.as_posix()
    try:
        document = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return f"the reviewer's processing record {where} is unreadable ({_OWNERS})"
    if not isinstance(document, dict):
        return f"the reviewer's processing record {where} is not a mapping ({_OWNERS})"
    missing = [name for name in RECORD_FIELDS if _empty(document.get(name))]
    if missing:
        return f"the reviewer's processing record {where} has no {', '.join(missing)} ({_OWNERS})"
    try:
        digest = hashlib.sha256(notes_path.read_bytes()).hexdigest()
    except OSError:
        return f"the reviewer's notice {notes_path.as_posix()} is unreadable ({_OWNERS})"
    if digest != document["notice_sha256"]:
        return (
            f"the reviewer's notice {notes_path.as_posix()} does not match the record's "
            f"notice_sha256 ({_OWNERS})"
        )
    return None
