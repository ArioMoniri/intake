"""Counsel drafts under ``docs/legal/drafts/`` are proposals, and nothing serves them.

CLAUDE.md invariant 18: consent and legal texts render only from ``docs/legal/``
with hash binding. The drafts tree sits inside ``docs/legal/`` so that the
invariant-20 claims gates scan it, but it holds text nobody has signed. A
draft that a loader could reach would read exactly like counsel's own words,
which is the failure ``docs/legal/COUNSEL_BRIEF.md`` §5 and
``docs/legal/documents.yaml`` warn about. So this suite pins:

1. every file in the drafts tree starts with the draft banner, so a reader who
   meets one out of context still sees what it is;
2. no source under ``packages/``, ``services/``, ``apps/`` or ``infra/`` names
   the drafts tree or a draft file, so no loader reads it; a planted reference
   is caught (the near-miss control) and an unrelated "drafts" is not;
3. the draft data-category register is refused by the served register loader,
   so pointing that loader at it fails closed, and every row still carries
   ``counsel_reviewed_at: null``;
4. the owner's fill-in marker appears only on the two feedback lines of the
   accessibility statement draft, and nowhere else;
5. the accessibility statement draft names every criterion the conformance
   report does not fully support, and claims no blanket conformance;
6. the drafts carry no performance claim (invariant 20).

Moving a draft to its served location is a separate PR after counsel signs
(``docs/legal/drafts/README.md``). That PR deletes the draft or its banner
line; it never teaches a loader to read this tree.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from intake_platform.legal.claims import SCANNED_TREES, scan_tree
from protocols.data_register import (
    OTHER_SUBJECT_CATEGORIES,
    DataRegisterError,
    load_data_register,
)
from protocols.types import DataCategory

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "docs" / "legal" / "drafts"
REGISTER_DRAFT = DRAFTS / "data-categories.draft.yaml"
STATEMENT_DRAFT = DRAFTS / "accessibility-statement.tr.draft.md"

BANNER = (
    "TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force"
)

#: The one fill-in marker the drafts may carry, and the only lines it may sit on.
OWNER_MARKER = "[sahibi tarafından doldurulacak]"
OWNER_MARKER_LINES = ("- **Geri bildirim adresi:**", "- **Yanıt süresi:**")

#: The trees whose code could load a legal text.
CODE_TREES = ("packages", "services", "apps", "infra")
_SKIP_DIRS = frozenset(
    {"node_modules", ".venv", "__pycache__", "dist", "build", ".expo", ".turbo", ".next"}
)
_CODE_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".toml", ".sh", ".env"}
)

# Derived from the path, not typed out, so the pattern moves with the tree.
_PARENT, _LEAF = DRAFTS.relative_to(REPO).parts[-2:]
_TREE_REFERENCE = re.compile(rf"{_PARENT}\W{{1,8}}{_LEAF}", re.IGNORECASE)
_DRAFT_FILE_REFERENCE = re.compile(r"\.draft\.(ya?ml|md)\b", re.IGNORECASE)


def _draft_files() -> list[Path]:
    return sorted(p for p in DRAFTS.rglob("*") if p.is_file())


def _code_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for tree in CODE_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix in _CODE_SUFFIXES:
                    found.append(path)
    return found


def _references(root: Path) -> list[str]:
    hits: list[str] = []
    for path in _code_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _TREE_REFERENCE.search(line) or _DRAFT_FILE_REFERENCE.search(line):
                hits.append(f"{path.relative_to(root)}:{line_no}")
    return hits


# ---------------------------------------------------------------- the banner


def test_the_drafts_tree_exists_and_is_not_empty() -> None:
    assert DRAFTS.is_dir()
    assert len(_draft_files()) >= 6


def test_every_draft_starts_with_the_banner() -> None:
    missing = []
    for path in _draft_files():
        first = path.read_text(encoding="utf-8").splitlines()[0]
        if first.lstrip("#> ").strip() != BANNER:
            missing.append(str(path.relative_to(REPO)))
    assert missing == []


def test_no_draft_carries_consent_front_matter() -> None:
    """The consent loader wants ``---`` on line 1 (texts.py). The banner holds
    line 1, so no draft can be mistaken for a loadable consent text."""
    for path in _draft_files():
        assert path.read_text(encoding="utf-8").splitlines()[0].strip() != "---"


# ---------------------------------------------------------------- no loader


def test_no_code_names_the_drafts_tree_or_a_draft_file() -> None:
    assert _references(REPO) == []


def test_the_reference_scan_catches_a_planted_loader(tmp_path: Path) -> None:
    """The near-miss control: three ways code could reach a draft are caught,
    and an unrelated use of the word is not."""
    pkg = tmp_path / "packages" / "x"
    pkg.mkdir(parents=True)
    (pkg / "joined.py").write_text(
        f'ROOT = Path("docs") / "{_PARENT}" / "{_LEAF}"\n', encoding="utf-8"
    )
    (pkg / "literal.ts").write_text(f'const root = "docs/{_PARENT}/{_LEAF}/";\n', encoding="utf-8")
    svc = tmp_path / "services" / "y"
    svc.mkdir(parents=True)
    (svc / "named.yaml").write_text("text: accessibility-statement.tr.draft.md\n", encoding="utf-8")
    (svc / "benign.ts").write_text("// crypto-shreds the offline drafts\n", encoding="utf-8")
    hits = _references(tmp_path)
    assert sorted(hits) == sorted(
        ["packages/x/joined.py:1", "packages/x/literal.ts:1", "services/y/named.yaml:1"]
    )


# ---------------------------------------------------------------- the register draft


def _register_draft() -> dict[str, Any]:
    loaded = yaml.safe_load(REGISTER_DRAFT.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_served_register_loader_refuses_the_draft() -> None:
    with pytest.raises(DataRegisterError):
        load_data_register(REGISTER_DRAFT)


def test_the_draft_covers_exactly_the_closed_category_set() -> None:
    rows = _register_draft()["categories"]
    names = [row["category"] for row in rows]
    expected = sorted(c.value for c in DataCategory if c is not DataCategory.GENERAL_HEALTH)
    assert sorted(names) == expected
    assert len(names) == len(set(names))


def test_no_draft_row_is_signed_and_each_states_its_article_and_rationale() -> None:
    for row in _register_draft()["categories"]:
        assert row["counsel_reviewed_at"] is None, row["category"]
        assert str(row["article_relied_on"]).strip(), row["category"]
        assert str(row["rationale"]).strip(), row["category"]
        proposal = row["proposal"]
        for key in ("basis", "retention", "recipients", "consent_scope"):
            assert str(proposal[key]).strip(), (row["category"], key)


def test_other_subject_rows_and_only_those_propose_a_separate_basis_and_notice() -> None:
    others = {c.value for c in OTHER_SUBJECT_CATEGORIES}
    for row in _register_draft()["categories"]:
        value = row["proposal"]["other_subject_basis_and_notice"]
        if row["category"] in others:
            assert isinstance(value, str) and value.strip(), row["category"]
        else:
            assert value is None, row["category"]


# ---------------------------------------------------------------- the owner's marker


def test_the_owner_marker_sits_only_on_the_statement_feedback_lines() -> None:
    carriers = [p for p in _draft_files() if OWNER_MARKER in p.read_text(encoding="utf-8")]
    assert carriers == [STATEMENT_DRAFT]
    marked = [
        line
        for line in STATEMENT_DRAFT.read_text(encoding="utf-8").splitlines()
        if OWNER_MARKER in line
    ]
    assert len(marked) == len(OWNER_MARKER_LINES)
    for line, label in zip(marked, OWNER_MARKER_LINES, strict=True):
        assert line.startswith(label)


# ---------------------------------------------------------------- the statement draft


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "render_a11y_report_for_drafts", REPO / "scripts" / "compliance" / "render_a11y_report.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_SHORT = ("Partially Supports", "Does Not Support", "Not Evaluated")


def _names(text: str, label: str) -> bool:
    # "SC 1.4.1" must not be satisfied by "SC 1.4.10"; "11.5.2.1" not by "11.5.2.13".
    return re.search(rf"{re.escape(label)}(?![0-9]|\.[0-9])", text) is not None


def test_the_statement_draft_names_every_criterion_the_report_does_not_support() -> None:
    source = _load_renderer().load_source()
    text = STATEMENT_DRAFT.read_text(encoding="utf-8")
    wcag = [f"SC {r['sc']}" for r in source["wcag"] if r["status"] in _SHORT]
    en = [f"EN 301 549 {r['clause']}" for r in source["en301549"] if r["status"] in _SHORT]
    assert wcag and en
    assert [label for label in wcag + en if not _names(text, label)] == []


def test_the_statement_name_check_does_not_match_a_longer_number() -> None:
    assert _names("bkz. SC 1.4.1.", "SC 1.4.1")
    assert not _names("SC 1.4.10 ve SC 1.4.11", "SC 1.4.1")
    assert not _names("EN 301 549 11.5.2.13", "EN 301 549 11.5.2.1")


def test_the_statement_draft_claims_no_blanket_conformance() -> None:
    text = STATEMENT_DRAFT.read_text(encoding="utf-8")
    warm = re.compile(
        r"tam(amen)? uyumlu|tamamen erişilebilir|%\s?100|100\s?%|eksiksiz erişilebilir"
        r"|fully (conformant|compliant|accessible)",
        re.IGNORECASE,
    )
    assert warm.search(text) is None
    assert "kısmen uyumlu" in text


# ---------------------------------------------------------------- invariant 20


def test_the_drafts_carry_no_performance_claim() -> None:
    groups = next(tree.groups for tree in SCANNED_TREES if tree.path == "docs/legal")
    assert scan_tree(DRAFTS, groups, relative_to=REPO) == ()
