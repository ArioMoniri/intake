"""INT-037 — the ``docs/legal/strings.yaml`` loader, fail closed (invariant 18).

CLAUDE.md invariant 18: "consent and legal texts render only from docs/legal/
with hash binding; the fixed strings in docs/legal/strings.yaml are verbatim."
files/06 §7 is the home of those strings. This module is the binding half of
that sentence and nothing else: it NEVER authors copy — the strings are
INT-210's human deliverable, awaiting counsel — it only proves which bytes
were shown.

The contract mirrors :mod:`intake_platform.consent.texts` deliberately, so
there is one shape to learn and one failure mode to reason about:

- the hash is the SHA-256 of the **entire file**, front matter included, so a
  version bump alone re-binds and version and hash can never drift apart;
- a missing file, or a required key that is absent or empty, is
  :class:`LegalStringsMissingError` — no text, no document. The mechanism
  exists, the gate fails closed, the content stays empty until a human
  supplies it (HUMAN_BLOCKERS.md rule 2);
- a file that exists but cannot be versioned or whose values are not strings
  is :class:`LegalStringsInvalidError`, never a quiet absence: an unversionable
  legal text cannot participate in the binding contract at all;
- re-rendering a document against copy that has since moved is
  :class:`LegalStringsChangedError` — the document we issued is not the
  document the file would now produce, and saying otherwise would misstate
  what the data subject was shown.

File contract (format only; the copy between the markers is human-authored):
a front-matter block ``---`` / ``legal_strings_version: <token>`` / ``---``
followed by ``key: "value"`` lines. Keys are dotted ids
(``dsar_export.title``); values are single-line quoted strings.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

__all__ = [
    "LegalStrings",
    "LegalStringsCatalog",
    "LegalStringsChangedError",
    "LegalStringsError",
    "LegalStringsInvalidError",
    "LegalStringsMissingError",
]

_FRONT_MATTER = "---"
_VERSION_LINE = re.compile(
    r"^legal_strings_version:\s*(?P<version>[A-Za-z0-9][A-Za-z0-9._-]{0,63})\s*$"
)
_ENTRY_LINE = re.compile(r"^(?P<key>[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*)\s*:\s*(?P<value>.*)$")
_MAX_FRONT_MATTER_LINES = 10


class LegalStringsError(Exception):
    """Base for fixed-string loading failures. Messages carry paths and key
    ids only — never the copy itself (invariant 6)."""


class LegalStringsMissingError(LegalStringsError):
    """The file, or a required key, does not exist yet. Fail closed."""


class LegalStringsInvalidError(LegalStringsError):
    """The file exists but breaks the format contract."""


class LegalStringsChangedError(LegalStringsError):
    """The file no longer hashes to the value a document was bound to."""


@dataclass(frozen=True)
class LegalStrings:
    """One loaded, hash-bound set of fixed strings."""

    version: str
    text_hash: str  # SHA-256 hex over the exact file bytes
    path: Path
    values: Mapping[str, str]


def _unquote(raw: str) -> str | None:
    """Values MUST be quoted: an unquoted YAML scalar can be a number, a bool
    or a date, and a legal string that silently became ``True`` is worse than
    one that failed to load."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return None


def _parse(path: Path, raw: bytes) -> tuple[str, dict[str, str]]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise LegalStringsInvalidError(f"{path}: not valid UTF-8") from exc
    if not lines or lines[0].strip() != _FRONT_MATTER:
        raise LegalStringsInvalidError(f"{path}: missing front-matter block")
    version: str | None = None
    close_at: int | None = None
    for index, line in enumerate(lines[1:_MAX_FRONT_MATTER_LINES], start=1):
        if line.strip() == _FRONT_MATTER:
            close_at = index
            break
        matched = _VERSION_LINE.match(line.strip())
        if matched:
            version = matched.group("version")
    if close_at is None or version is None:
        raise LegalStringsInvalidError(f"{path}: no legal_strings_version in front matter")

    values: dict[str, str] = {}
    for line in lines[close_at + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entry = _ENTRY_LINE.match(stripped)
        if entry is None:
            raise LegalStringsInvalidError(
                f"{path}: line is neither blank, a comment nor a 'key: \"value\"' entry"
            )
        value = _unquote(entry.group("value"))
        if value is None:
            raise LegalStringsInvalidError(
                f"{path}: key {entry.group('key')!r} is not a single-line string"
            )
        values[entry.group("key")] = value
    return version, values


class LegalStringsCatalog:
    """Reads the legal file fresh on every lookup — a string bump must be
    visible immediately, and no export path is latency-critical."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def entry(self, *, required: Sequence[str], expected_hash: str | None = None) -> LegalStrings:
        """The bound strings, or a fail-closed error.

        ``required`` is the key set the caller cannot render without;
        ``expected_hash`` re-binds a previously issued document.
        """
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError as exc:
            raise LegalStringsMissingError(
                f"no fixed legal strings at {self._path} — the strings are authored by "
                "INT-210 (files/06 §7); nothing that renders them may be produced without"
            ) from exc
        version, values = _parse(self._path, raw)
        text_hash = hashlib.sha256(raw).hexdigest()
        if expected_hash is not None and expected_hash != text_hash:
            raise LegalStringsChangedError(
                f"{self._path}: the fixed strings moved since this document was bound "
                "(re-issue rather than restate what was never shown)"
            )
        absent = [key for key in required if not values.get(key, "").strip()]
        if absent:
            raise LegalStringsMissingError(
                f"{self._path}: required fixed strings are absent or empty: "
                + ", ".join(sorted(absent))
            )
        return LegalStrings(
            version=version,
            text_hash=text_hash,
            path=self._path,
            values=MappingProxyType(dict(values)),
        )
