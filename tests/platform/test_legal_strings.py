"""INT-037 — the docs/legal fixed-strings loader, fail closed (invariant 18).

Same binding contract as the INT-038 consent-text loader
(``intake_platform.consent.texts``): the copy is a file on disk, the hash is
the SHA-256 of that file's exact bytes, and a missing or moved text is a
refusal rather than a default. This module never authors copy — the strings
are INT-210's human deliverable — so every test here writes a SYNTHETIC
fixture and asserts the binding, never the wording.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from intake_platform.legal import (
    LegalStringsCatalog,
    LegalStringsChangedError,
    LegalStringsInvalidError,
    LegalStringsMissingError,
)

REQUIRED = ("dsar_export.title", "dsar_export.footer")

_FIXTURE = """---
legal_strings_version: test-fixture.1
---
dsar_export.title: "Sentetik test basligi"
dsar_export.footer: "Sentetik test dipnotu"
"""


def _write(root: Path, body: str = _FIXTURE) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "strings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_missing_strings_file_fails_closed(tmp_path: Path) -> None:
    catalog = LegalStringsCatalog(tmp_path / "legal" / "strings.yaml")
    with pytest.raises(LegalStringsMissingError):
        catalog.entry(required=REQUIRED)


def test_hash_covers_the_whole_file_including_the_version(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal")
    catalog = LegalStringsCatalog(path)
    entry = catalog.entry(required=REQUIRED)
    assert entry.text_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry.version == "test-fixture.1"
    assert entry.values["dsar_export.title"] == "Sentetik test basligi"


def test_a_version_bump_alone_moves_the_hash(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal")
    first = LegalStringsCatalog(path).entry(required=REQUIRED).text_hash
    _write(tmp_path / "legal", _FIXTURE.replace("test-fixture.1", "test-fixture.2"))
    assert LegalStringsCatalog(path).entry(required=REQUIRED).text_hash != first


def test_a_required_key_that_is_absent_or_empty_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal", _FIXTURE.replace('"Sentetik test dipnotu"', '""'))
    with pytest.raises(LegalStringsMissingError, match="dsar_export.footer"):
        LegalStringsCatalog(path).entry(required=REQUIRED)
    path = _write(
        tmp_path / "legal",
        "---\nlegal_strings_version: v1\n---\ndsar_export.title: 'x'\n",
    )
    with pytest.raises(LegalStringsMissingError, match="dsar_export.footer"):
        LegalStringsCatalog(path).entry(required=REQUIRED)


def test_a_file_without_a_version_is_invalid_not_merely_absent(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal", "dsar_export.title: 'x'\ndsar_export.footer: 'y'\n")
    with pytest.raises(LegalStringsInvalidError):
        LegalStringsCatalog(path).entry(required=REQUIRED)


def test_a_non_string_value_is_invalid(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "legal",
        "---\nlegal_strings_version: v1\n---\ndsar_export.title: 7\ndsar_export.footer: 'y'\n",
    )
    with pytest.raises(LegalStringsInvalidError):
        LegalStringsCatalog(path).entry(required=REQUIRED)


def test_binding_against_a_moved_hash_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal")
    issued = LegalStringsCatalog(path).entry(required=REQUIRED)
    _write(tmp_path / "legal", _FIXTURE.replace("dipnotu", "dipnotu (revize)"))
    with pytest.raises(LegalStringsChangedError):
        LegalStringsCatalog(path).entry(required=REQUIRED, expected_hash=issued.text_hash)


def test_binding_against_the_same_hash_succeeds(tmp_path: Path) -> None:
    path = _write(tmp_path / "legal")
    issued = LegalStringsCatalog(path).entry(required=REQUIRED)
    again = LegalStringsCatalog(path).entry(required=REQUIRED, expected_hash=issued.text_hash)
    assert again.text_hash == issued.text_hash


def test_error_messages_carry_paths_and_keys_only(tmp_path: Path) -> None:
    """Invariant 6: the loader may name a key or a path, never the copy."""
    body = _FIXTURE.replace("Sentetik test dipnotu", "")
    path = _write(tmp_path / "legal", body)
    with pytest.raises(LegalStringsMissingError) as excinfo:
        LegalStringsCatalog(path).entry(required=REQUIRED)
    assert "Sentetik test basligi" not in str(excinfo.value)
