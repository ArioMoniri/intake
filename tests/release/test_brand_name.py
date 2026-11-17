"""INT-420 — the product is Önvizit, and the old brand name does not come back.

Acceptance (GitHub #712), with the old name written as <old>:
  "Every brand use of <old> on main reads Önvizit (ASCII identifier
   `onvizit`) [...] The Turkish common noun "<old>" is kept wherever it is
   used as a word and not as the brand [...] A guard test fails on any new
   brand-case "<old>"."

The old brand was not an invented word. It is a Turkish noun: *vizit* (a
doctor's visit) with the suffix ``-e``, which is both the dative ("to a visit")
and the TDK noun for the visit or its fee. The app still speaks that word: the
records screen says documents are added *to a visit*, and a reminder says *your
visit* is coming up. A blanket ban would ban Turkish. A case-sensitive ban
would miss both the sentence-initial common noun and the upper-case identifiers
(an env-var prefix, an HL7 facility id).

So the rule is exact rather than clever. Every tracked text line that carries
the old spelling, in any letter case, must be named in ``brand_allowlist.yaml``
with its kind and the reason it stays:

* ``common_noun``: the Turkish word, used as a word.
* ``former_name``: a dated record (an evidence file, a PROGRESS entry, an
  audit), or the rename's own title, naming the product as it was called then.
  A record says what was true on its date and is not rewritten.

An entry that no longer matches any line also fails, so the list tracks what is
really there and only shrinks as records are retired.

Two files are exempt as a whole, and the set is frozen here, not in the YAML:
the allow-list itself (it has to quote what it allows) and the rename's own
evidence (it lists every kept occurrence, which is the point of it).

The token is derived, never spelled, not even in this docstring. A guard that
names the string it forbids is the first line it flags, and the first hit a
reviewer's grep finds.
The new brand's ASCII form followed by a capital E (a camelCase
``...Embed`` key) lower-cases into the old spelling, so the pattern refuses
a match that the new brand's ``on``/``ön`` prefix owns.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("brand_allowlist.yaml")

#: The Turkish noun the old brand was built from. It stays in the language,
#: so the noun itself is not forbidden, only its old-brand form.
VISIT_NOUN = "vizit"
#: The old brand: the noun with the dative/nominal ``-e``. Derived, never spelled.
OLD_BRAND = VISIT_NOUN.capitalize() + "e"
NEW_BRAND = "Önvizit"
NEW_ASCII = "onvizit"

#: Any letter case. The lookbehinds leave the new brand's own spelling alone:
#: ``Önvizit`` + ``e...`` is the new name plus a suffix or a camelCase word.
OLD_PATTERN = re.compile(rf"(?<!on)(?<!ön){re.escape(OLD_BRAND)}", re.IGNORECASE)

KINDS = frozenset({"common_noun", "former_name"})

WHOLE_FILE_EXEMPT = frozenset(
    {
        "tests/release/brand_allowlist.yaml",
        "docs/evidence/INT-420.md",
    }
)


@dataclass(frozen=True)
class Hit:
    path: str
    number: int
    line: str

    def key(self) -> tuple[str, str]:
        return (self.path, self.line.strip())

    def __str__(self) -> str:
        return f"{self.path}:{self.number}: {self.line.strip()}"


def _tracked_paths() -> list[str]:
    out = subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 — git on PATH, as every repo gate
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    paths = [p.decode("utf-8") for p in out.split(b"\0") if p]
    assert len(paths) > 1000, "git ls-files returned almost nothing; the scan would be vacuous"
    return paths


def _text_lines(path: Path) -> list[str] | None:
    """The file's lines, or None for a binary (a NUL byte) or a vanished path."""
    try:
        data = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return None
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def hits_in(files: Iterable[tuple[str, Iterable[str]]]) -> list[Hit]:
    """Every line in ``files`` (path, lines) that carries the old spelling."""
    found: list[Hit] = []
    for path, lines in files:
        for number, line in enumerate(lines, 1):
            if OLD_PATTERN.search(line):
                found.append(Hit(path, number, line))
    return found


def repo_hits() -> list[Hit]:
    files: list[tuple[str, list[str]]] = []
    for rel in _tracked_paths():
        if rel in WHOLE_FILE_EXEMPT:
            continue
        lines = _text_lines(REPO / rel)
        if lines is not None:
            files.append((rel, lines))
    return hits_in(files)


def load_allowlist() -> list[dict[str, str]]:
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))
    entries = data["entries"]
    assert isinstance(entries, list) and entries, "the allow-list parsed to nothing"
    return entries


def unlisted(hits: Iterable[Hit], entries: Iterable[Mapping[str, str]]) -> list[Hit]:
    allowed = {(e["path"], e["line"]) for e in entries}
    return [h for h in hits if h.key() not in allowed]


def stale(hits: Iterable[Hit], entries: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    present = {h.key() for h in hits}
    return [e for e in entries if (e["path"], e["line"]) not in present]


# --- the derivation, and the near-miss controls that give it its meaning -------------


def test_the_forbidden_token_is_derived_not_spelled() -> None:
    assert len(OLD_BRAND) == len(VISIT_NOUN) + 1 and OLD_BRAND[0].isupper()
    source = Path(__file__).read_text(encoding="utf-8")
    assert not OLD_PATTERN.search(source), "the guard spells the token it forbids"


@pytest.mark.parametrize(
    "line",
    [
        f"{OLD_BRAND} konuşuyor",
        f"{OLD_BRAND.lower()} tanı koymaz",
        f"{OLD_BRAND.upper()}_ADMIN_TOKEN",
        f"POST /{OLD_BRAND.lower()}/ticket",
        f"button[data-{OLD_BRAND.lower()}-embed]",
        f'dataset["{OLD_BRAND.lower()}Embed"]',
        f"MSH|^~\\&|LIS|ACIBADEM|INTAKE|{OLD_BRAND.upper()}|20260901",
        f"{OLD_BRAND.lower()}niz yaklaşıyor",
        f"{OLD_BRAND}'yi kullanmayı bırakırsanız",
    ],
)
def test_the_pattern_catches_every_case_and_identifier_shape(line: str) -> None:
    assert OLD_PATTERN.search(line), line


@pytest.mark.parametrize(
    "line",
    [
        f"{NEW_BRAND} konuşuyor",
        f"{NEW_BRAND}'e ekleyin",
        f"{NEW_BRAND.upper()} tanı koymaz",
        f"{NEW_ASCII.upper()}_ADMIN_TOKEN",
        f'dataset["{NEW_ASCII}Embed"]',
        f"{NEW_ASCII}Error",
        f"button[data-{NEW_ASCII}-embed]",
        f"{VISIT_NOUN.capitalize()}lerim",
        f"geçmiş {VISIT_NOUN}iniz yok",
    ],
)
def test_the_new_brand_and_the_bare_noun_are_not_caught(line: str) -> None:
    assert not OLD_PATTERN.search(line), line


def test_a_planted_occurrence_is_reported_and_a_listed_one_is_not() -> None:
    entries = [{"path": "a.md", "line": f"{OLD_BRAND.lower()}niz yarın.", "kind": "common_noun"}]
    files = [
        ("a.md", ["giriş", f"  {OLD_BRAND.lower()}niz yarın.  "]),
        ("b.ts", [f'"app.name": "{OLD_BRAND}",']),
        ("c.md", [f"{NEW_BRAND} tanı koymaz."]),
    ]
    found = hits_in(files)
    assert [(h.path, h.number) for h in found] == [("a.md", 2), ("b.ts", 1)]
    assert [(h.path, h.number) for h in unlisted(found, entries)] == [("b.ts", 1)]
    assert stale(found, entries) == []
    assert stale([], entries) == entries


# --- the repository -----------------------------------------------------------------


def test_every_occurrence_in_the_repository_is_allow_listed() -> None:
    offenders = unlisted(repo_hits(), load_allowlist())
    assert offenders == [], (
        f"the product is {NEW_BRAND} (ASCII `{NEW_ASCII}`); rename these, or, if one is "
        "the Turkish common noun or a dated record, add it to "
        "tests/release/brand_allowlist.yaml with its kind and why:\n"
        + "\n".join(str(h) for h in offenders)
    )


def test_every_allow_list_entry_still_names_a_real_line() -> None:
    gone = stale(repo_hits(), load_allowlist())
    assert gone == [], "remove these allow-list entries; their line is gone:\n" + "\n".join(
        f"{e['path']}: {e['line']}" for e in gone
    )


def test_every_allow_list_entry_is_well_formed() -> None:
    tracked = set(_tracked_paths())
    seen: set[tuple[str, str]] = set()
    for entry in load_allowlist():
        assert set(entry) == {"path", "kind", "line", "why"}, entry
        assert entry["kind"] in KINDS, entry
        assert entry["why"].strip(), entry
        assert entry["path"] in tracked, f"{entry['path']} is not a tracked file"
        assert entry["path"] not in WHOLE_FILE_EXEMPT, entry
        assert OLD_PATTERN.search(entry["line"]), f"entry holds no occurrence: {entry}"
        key = (entry["path"], entry["line"])
        assert key not in seen, f"duplicate entry: {entry}"
        seen.add(key)


#: A common noun sits in running text: nothing word-like glued on before it and,
#: after it, at most a Turkish suffix in one letter case (``-niz``/``-NİZ``),
#: then the end of the word. Never ``_``, ``-``, ``/``, a camelCase capital or a
#: ``.x`` glued on, which is how an identifier, a path or a host looks.
_WORD_USE = re.compile(
    rf"(?<![\w/\-.]){re.escape(OLD_BRAND)}(?-i:[a-zçğıöşü]*|[A-ZÇĞİÖŞÜ]*)(?![\w/\-]|\.\w)",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    ("line", "is_word"),
    [
        (f"Belgeler bir {OLD_BRAND.lower()} eklenir", True),
        (f'"{OLD_BRAND} ekleyin"', True),
        (f"{OLD_BRAND}niz yaklaşıyor.", True),
        (f"KADIN {OLD_BRAND.upper().replace('I', 'İ')}NİZ YARIN.", True),
        (f"{OLD_BRAND.lower()}Embed", False),
        (f"{OLD_BRAND.upper()}_ADMIN_TOKEN", False),
        (f"/{OLD_BRAND.lower()}/ticket", False),
        (f"https://{OLD_BRAND.lower()}.example/n/1", False),
        (f"data-{OLD_BRAND.lower()}-embed", False),
    ],
)
def test_the_word_use_shape_separates_a_noun_from_an_identifier(line: str, is_word: bool) -> None:
    assert OLD_PATTERN.search(line), line
    assert bool(_WORD_USE.search(line)) is is_word, line


def test_a_common_noun_entry_is_a_word_in_running_text_not_an_identifier() -> None:
    nouns = [e for e in load_allowlist() if e["kind"] == "common_noun"]
    assert nouns, "no common-noun entries; the kind split would be untested"
    for entry in nouns:
        uses = OLD_PATTERN.findall(entry["line"])
        words = _WORD_USE.findall(entry["line"])
        assert len(words) == len(uses), f"not a word use: {entry}"


def test_the_whole_file_exemptions_exist() -> None:
    for rel in WHOLE_FILE_EXEMPT:
        assert (REPO / rel).is_file(), f"{rel} is exempt but missing"
