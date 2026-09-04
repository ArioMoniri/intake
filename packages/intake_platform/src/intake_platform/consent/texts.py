"""INT-038 — the docs/legal consent-text loader, fail closed (invariant 18).

Consent texts render ONLY from ``docs/legal`` with hash binding: the shown
copy is a file on disk, ``text_hash`` is the SHA-256 of that file's exact
bytes, and what was shown is therefore provable (files/06 §2). This module
never authors copy — the texts are INT-210's human deliverable — it only
binds. Three consequences:

- a missing text is ``ConsentTextMissingError``: no text, no grant. The
  mechanism exists, the gate fails closed, the content stays empty until a
  human supplies it (HUMAN_BLOCKERS.md rule 2);
- a text the loader cannot version is ``ConsentTextInvalidError`` even on
  the tolerant lookup — an unversionable text cannot participate in the
  re-prompt-on-change contract, so treating it as absent-but-quiet would
  hide a defect in the legal tree;
- the hash covers the ENTIRE file (front matter included), so a version
  edit alone re-binds too: version and hash can never drift apart.

File contract (format only — the copy between the markers is human-authored):
the file starts with a front-matter block ``---`` /
``consent_text_version: <token>`` / ``---`` followed by non-empty Turkish
copy. Filenames map from purpose ids with ``:`` → ``.`` plus the ``.tr.md``
suffix (``lane:affect`` → ``lane.affect.tr.md``); a ``share:<qualifier>``
scope binds to the ``share`` family text, whose parameters live on the
grant, not in the copy.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from intake_platform.consent.registry import resolve_scope

__all__ = [
    "BoundLegalText",
    "ConsentText",
    "ConsentTextCatalog",
    "ConsentTextError",
    "ConsentTextInvalidError",
    "ConsentTextMissingError",
    "bind_legal_document",
    "text_filename",
]

_FRONT_MATTER_OPEN = "---"
_VERSION_LINE = re.compile(
    r"^consent_text_version:\s*(?P<version>[A-Za-z0-9][A-Za-z0-9._-]{0,63})\s*$"
)
_MAX_FRONT_MATTER_LINES = 10


class ConsentTextError(Exception):
    """Base for consent-text loading failures. Messages carry paths and
    purpose ids only — never file content (invariant 6)."""


class ConsentTextMissingError(ConsentTextError):
    """The docs/legal file for a purpose does not exist. Fail closed: a
    consent that cannot be shown cannot be granted."""


class ConsentTextInvalidError(ConsentTextError):
    """The file exists but violates the format contract (no version front
    matter, empty copy, or undecodable bytes)."""


@dataclass(frozen=True)
class ConsentText:
    """One loadable consent text: the binding row of files/06 §2."""

    purpose: str
    version: str
    text_hash: str  # SHA-256 hex over the exact file bytes
    path: Path
    # The shown Turkish copy (everything after the front matter) — what the
    # patient-facing surfaces render; the hash still covers the WHOLE file.
    body: str


@dataclass(frozen=True)
class BoundLegalText:
    """A hash-bound legal text that is NOT a files/06 §2 consent purpose — an
    aydınlatma/disclosure shown to a data subject (e.g. the embed partner-
    processor statement, INT-320). Same binding as :class:`ConsentText` (the
    hash covers the whole file, front matter included), but it carries no
    ``purpose`` because it is displayed, never granted through the ledger."""

    version: str
    text_hash: str  # SHA-256 hex over the exact file bytes
    body: str


def text_filename(purpose_id: str) -> str:
    """``lane:affect`` → ``lane.affect.tr.md`` — Turkish-first (invariant 5),
    colon-free for the filesystem."""
    return purpose_id.replace(":", ".") + ".tr.md"


def bind_legal_document(path: Path) -> BoundLegalText:
    """Bind a legal text by path with the SAME hash-binding as a consent purpose
    (invariant 18) but WITHOUT the closed-registry ``resolve_scope`` check —
    for a disclosure that is shown to the patient but never granted (INT-320's
    partner-processor statement). Fail closed exactly like the catalog: an
    absent file is :class:`ConsentTextMissingError`, an unversionable one is
    :class:`ConsentTextInvalidError`. Never authors copy; only binds."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ConsentTextMissingError(
            f"no legal document at {path} — texts are authored into the legal tree; "
            "nothing may be shown without one"
        ) from exc
    version, body = _parse(path, raw)
    return BoundLegalText(
        version=version,
        text_hash=hashlib.sha256(raw).hexdigest(),
        body=body,
    )


def _parse(path: Path, raw: bytes) -> tuple[str, str]:
    """(version, body) from the file contract, or a fail-closed error."""
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ConsentTextInvalidError(f"{path}: not valid UTF-8") from exc
    if not lines or lines[0].strip() != _FRONT_MATTER_OPEN:
        raise ConsentTextInvalidError(f"{path}: missing front-matter block")
    version: str | None = None
    close_at: int | None = None
    for index, line in enumerate(lines[1:_MAX_FRONT_MATTER_LINES], start=1):
        if line.strip() == _FRONT_MATTER_OPEN:
            close_at = index
            break
        matched = _VERSION_LINE.match(line.strip())
        if matched:
            version = matched.group("version")
    if close_at is None or version is None:
        raise ConsentTextInvalidError(f"{path}: no consent_text_version in front matter")
    body = "\n".join(lines[close_at + 1 :])
    if not body.strip():
        raise ConsentTextInvalidError(f"{path}: no consent copy after front matter")
    return version, body


class ConsentTextCatalog:
    """Reads the legal tree fresh on every lookup — the re-prompt-on-change
    contract needs a text bump to be visible immediately, and consent
    evaluation is far off any latency-critical path."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def entry(self, scope: str) -> ConsentText:
        """The binding for ``scope``'s purpose, or a fail-closed error."""
        purpose = resolve_scope(scope).id
        path = self._root / text_filename(purpose)
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise ConsentTextMissingError(
                f"no consent text for purpose {purpose!r} at {path} — texts are authored "
                "into docs/legal by INT-210; nothing may be granted without one"
            ) from exc
        version, body = _parse(path, raw)
        return ConsentText(
            purpose=purpose,
            version=version,
            text_hash=hashlib.sha256(raw).hexdigest(),
            path=path,
            body=body,
        )

    def try_entry(self, scope: str) -> ConsentText | None:
        """``None`` when the text does not exist yet (the pre-INT-210 state
        the guard must tolerate for already-recorded grants); an INVALID
        text still raises — see the module docstring."""
        try:
            return self.entry(scope)
        except ConsentTextMissingError:
            return None
