"""INT-410 — the synthetic seed is unreachable from the release entry (audit F30).

Acceptance, verbatim:
  "the seed accounts and their fixtures live behind a dev-only module that the
   release bundle excludes (a lazy import in a `__DEV__` branch the bundler
   strips, or a dev-only entry); a bundle test over the production export proves
   no seed identifier, name or fixture string is present, with a near-miss
   control where a planted seed string in a release path fails"
  "invariant 17: no demo data outside tests or fixtures reaches a release build"

The release bundle is checked twice, once in each CI job, because each job has
one toolchain:

* ``apps/mobile/e2e/releaseBundle.spec.ts`` runs in check-ts, which installs
  the workspace. It builds the production export (``expo export``, iOS and
  Android, ``dev=false``, minified) and searches the emitted JavaScript for the
  seed's strings. That is the artefact proof.
* This file runs in check-py and in ``make check-i18n``, where there is no
  Node. It walks the import graph Metro builds from the release entry, and it
  shows that the seed module is not in that graph and that no module in the
  graph carries a seed string.

**The release entry.** ``apps/mobile/package.json`` names ``expo-router/entry``.
That entry builds its routes from a ``require.context`` over ``src/app``
(``expo-router/_ctx.*.js``). The context matches every ``.ts``, ``.tsx``,
``.js`` and ``.jsx`` file except ``+api`` files and the root ``+html`` and
``+middleware``. Each matching file is a root, test files included, because a
test file under ``src/app`` is a route (INT-409's evidence, PR #693, measured
one breaking the export).

**The edges Metro keeps.**

* A static ``import`` or ``export … from`` is an edge unless it is type-only,
  because Babel erases type-only imports.
* A dynamic ``import()`` or ``require()`` is an edge unless it sits inside an
  ``if (__DEV__) {…}`` block. A release build compiles ``__DEV__`` to ``false``
  and folds that block away before Metro collects dependencies
  (``metro-transform-worker`` runs ``inlinePlugin``, then
  ``constantFoldingPlugin``, then ``collectDependencies``). Any other shape of
  dead code is kept as an edge.

The walk can therefore reach more modules than Metro does, never fewer.
Package imports are not followed, because the seed is this app's own module.

**The markers.** The seed's identifying strings are every ``id``, ``name``,
``hospital``, ``text`` and ``title`` value in the seed module. They are read
from it at run time and never spelled here, so this guard cannot become a
second copy of the seed. A seed ``department`` is not a marker, because those
values are the taxonomy's own branch names and the release app ships them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOBILE = REPO / "apps" / "mobile"
SEED_RELATIVE = Path("lib") / "dev" / "accounts.ts"

CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
#: What Metro tries for an extensionless specifier. Every platform variant that
#: exists is kept, so the graph is the union of the release platforms.
EXTENSIONS = tuple(
    f"{platform}{suffix}"
    for platform in ("", ".ios", ".android", ".native", ".web")
    for suffix in CODE_SUFFIXES
)

MARKER_KEYS = ("id", "name", "hospital", "text", "title")
SHARED_KEYS = ("department",)

_ROUTE_EXCLUDED = re.compile(r"\+api\.[tj]sx?$")
_ROOT_EXCLUDED = re.compile(r"^\+(html|middleware)\.[tj]sx?$")
_STATIC = re.compile(
    r"^\s*(?:import|export)\s+(type\s+)?([\w\s{},*$]*?)\s*from\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_SIDE_EFFECT = re.compile(r"^\s*import\s+[\"']([^\"']+)[\"']", re.MULTILINE)
_DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*[\"']([^\"']+)[\"']\s*\)")
_DEV_IF = re.compile(r"\bif\s*\(\s*__DEV__\s*\)\s*\{")


def seed_values(seed: Path, keys: Iterable[str]) -> list[str]:
    """Every string value the seed module assigns to one of ``keys``."""
    pattern = re.compile(r"\b(" + "|".join(keys) + r')\s*:\s*"([^"\\]+)"')
    return sorted({m.group(2) for m in pattern.finditer(seed.read_text(encoding="utf-8"))})


def _string_end(text: str, start: int) -> int:
    quote, index = text[start], start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index
        index += 1
    return len(text)


def _matching_brace(text: str, opening: int) -> int:
    """The index of the ``}`` closing the ``{`` at ``opening``; strings and comments skipped."""
    depth, index = 0, opening
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            index = _string_end(text, index)
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = len(text) if close < 0 else close + 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("an `if (__DEV__) {` block never closes")


def dev_spans(text: str) -> list[tuple[int, int]]:
    """The ``if (__DEV__) {…}`` blocks a release build folds away."""
    return [(m.end() - 1, _matching_brace(text, m.end() - 1)) for m in _DEV_IF.finditer(text)]


def _type_only(keyword: str | None, clause: str) -> bool:
    if keyword:
        return True
    named = clause.strip()
    if not (named.startswith("{") and named.endswith("}")):
        return False
    parts = [part.strip() for part in named[1:-1].split(",") if part.strip()]
    return bool(parts) and all(part.startswith("type ") for part in parts)


@dataclass(frozen=True)
class Specifiers:
    kept: list[str]
    folded: list[str]


def specifiers(text: str) -> Specifiers:
    """The module specifiers a release build keeps, and those it folds away."""
    kept = [m.group(3) for m in _STATIC.finditer(text) if not _type_only(m.group(1), m.group(2))]
    kept += [m.group(1) for m in _SIDE_EFFECT.finditer(text)]
    spans = dev_spans(text)
    folded: list[str] = []
    for m in _DYNAMIC.finditer(text):
        guarded = any(start < m.start() < end for start, end in spans)
        (folded if guarded else kept).append(m.group(1))
    return Specifiers(kept=kept, folded=folded)


@dataclass(frozen=True)
class Tree:
    """An Expo app root: ``src`` with ``src/app`` routes, ``assets`` beside it."""

    root: Path

    @property
    def src(self) -> Path:
        return self.root / "src"

    def routes(self) -> list[Path]:
        app = self.src / "app"
        return sorted(
            path
            for path in app.rglob("*")
            if path.is_file()
            and path.suffix in CODE_SUFFIXES
            and not _ROUTE_EXCLUDED.search(path.name)
            and not (path.parent == app and _ROOT_EXCLUDED.match(path.name))
        )

    def resolve(self, specifier: str, importer: Path) -> list[Path] | None:
        """The files a local specifier names; ``[]`` for a package; ``None`` if unresolved."""
        if specifier.startswith("@/assets/"):
            return []
        if specifier.startswith("@/"):
            base = self.src / specifier[2:]
        elif specifier.startswith("."):
            base = importer.parent / specifier
        else:
            return []
        base = Path(os.path.normpath(base))
        if base.suffix and base.suffix not in CODE_SUFFIXES:
            return []  # json, images, fonts: data, not modules that import
        if base.suffix in CODE_SUFFIXES and base.is_file():
            return [base]
        found = [base.with_name(base.name + ext) for ext in EXTENSIONS]
        found = [path for path in found if path.is_file()]
        if not found and base.is_dir():
            found = [base / f"index{ext}" for ext in EXTENSIONS if (base / f"index{ext}").is_file()]
        return found or None


@dataclass(frozen=True)
class Graph:
    reachable: frozenset[Path]
    folded: list[tuple[Path, str]]
    unresolved: list[tuple[Path, str]]


def release_graph(tree: Tree) -> Graph:
    seen: set[Path] = set()
    folded: list[tuple[Path, str]] = []
    unresolved: list[tuple[Path, str]] = []
    stack = list(tree.routes())
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        found = specifiers(module.read_text(encoding="utf-8"))
        folded += [(module, spec) for spec in found.folded]
        for spec in found.kept:
            targets = tree.resolve(spec, module)
            if targets is None:
                unresolved.append((module, spec))
                continue
            stack += [target for target in targets if target not in seen]
    return Graph(frozenset(seen), folded, unresolved)


def seed_hits(texts: dict[Path, str], markers: Iterable[str]) -> list[tuple[str, str]]:
    """(module, marker) for every marker a module holds as a whole string literal."""
    hits = []
    for path, text in sorted(texts.items()):
        for marker in markers:
            if re.search(r"([\"'`])" + re.escape(marker) + r"\1", text):
                hits.append((path.name, marker))
    return hits


def reachable_hits(graph: Graph, markers: Iterable[str]) -> list[tuple[str, str]]:
    texts = {path: path.read_text(encoding="utf-8") for path in graph.reachable}
    return seed_hits(texts, list(markers))


# --- the real tree --------------------------------------------------------------------

REAL = Tree(MOBILE)
REAL_SEED = REAL.src / SEED_RELATIVE


@pytest.fixture(scope="module")
def graph() -> Graph:
    return release_graph(REAL)


@pytest.fixture(scope="module")
def markers() -> list[str]:
    found = seed_values(REAL_SEED, MARKER_KEYS)
    # Loud, not vacuous: an empty derivation would pass every tree.
    assert len(found) >= 10, f"derived only {found} from {REAL_SEED}"
    return found


def test_the_release_entry_is_the_expo_router_context() -> None:
    package = json.loads((MOBILE / "package.json").read_text(encoding="utf-8"))
    assert package["main"] == "expo-router/entry"


def test_the_seed_module_is_not_in_the_release_graph(graph: Graph) -> None:
    assert REAL_SEED not in graph.reachable


def test_no_release_module_carries_a_seed_string(graph: Graph, markers: list[str]) -> None:
    assert reachable_hits(graph, markers) == []


def test_the_only_folded_edge_to_the_seed_is_the_welcome_screens(graph: Graph) -> None:
    to_seed = [
        module.relative_to(REAL.src).as_posix()
        for module, spec in graph.folded
        for target in (REAL.resolve(spec, module) or [])
        if target == REAL_SEED
    ]
    assert to_seed == ["app/(auth)/welcome.tsx"]


def test_the_walk_is_the_real_app(graph: Graph) -> None:
    # every local specifier resolved, so no subtree was silently dropped
    assert graph.unresolved == []
    names = {path.relative_to(REAL.src).as_posix() for path in graph.reachable}
    assert {"app/(auth)/welcome.tsx", "lib/session.tsx", "components/VisitCard.tsx"} <= names
    # the shapes module is imported for types only, so Babel erases every edge to it
    assert "lib/types/account.ts" not in names
    assert len(names) > 100


# --- controls and near misses, on a planted tree --------------------------------------


def _planted(tmp_path: Path, files: dict[str, str]) -> Tree:
    """A minimal app: one route importing ``lib/screen``, and a copy of the real seed."""
    root = tmp_path / "app-root"
    (root / "src" / SEED_RELATIVE).parent.mkdir(parents=True)
    shutil.copyfile(REAL_SEED, root / "src" / SEED_RELATIVE)
    sources = {"app/index.tsx": 'import { screen } from "@/lib/screen";\n', **files}
    sources.setdefault("lib/screen.ts", "export const screen = 1;\n")
    for relative, text in sources.items():
        path = root / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Tree(root)


def _verdict(tree: Tree, markers: list[str]) -> tuple[bool, list[tuple[str, str]]]:
    graph = release_graph(tree)
    return tree.src / SEED_RELATIVE in graph.reachable, reachable_hits(graph, markers)


def test_control_a_static_import_of_the_seed_is_caught(tmp_path: Path, markers: list[str]) -> None:
    # main's shape before INT-410: the welcome screen's value import
    tree = _planted(tmp_path, {"lib/screen.ts": 'import { testAccounts } from "./dev/accounts";\n'})
    reached, hits = _verdict(tree, markers)
    assert reached is True
    assert sorted({marker for _, marker in hits}) == markers


def test_control_an_unguarded_lazy_import_is_caught(tmp_path: Path, markers: list[str]) -> None:
    tree = _planted(tmp_path, {"lib/screen.ts": 'void import("@/lib/dev/accounts");\n'})
    reached, hits = _verdict(tree, markers)
    assert reached is True
    assert sorted({marker for _, marker in hits}) == markers


def test_control_a_seed_string_planted_in_a_release_module_is_caught(
    tmp_path: Path, markers: list[str]
) -> None:
    name = seed_values(REAL_SEED, ("name",))[0]
    tree = _planted(tmp_path, {"lib/screen.ts": f'export const screen = "{name}";\n'})
    assert _verdict(tree, markers) == (False, [("screen.ts", name)])


def test_near_miss_a_lazy_import_inside_if_dev_is_folded(
    tmp_path: Path, markers: list[str]
) -> None:
    source = (
        "export function load(set: (x: unknown) => void) {\n"
        "  if (__DEV__) {\n"
        '    void import("@/lib/dev/accounts").then((seed) => set(seed.testAccounts));\n'
        "  }\n"
        "}\n"
    )
    assert _verdict(_planted(tmp_path, {"lib/screen.ts": source}), markers) == (False, [])


def test_near_miss_a_type_only_import_is_erased(tmp_path: Path, markers: list[str]) -> None:
    source = (
        'import type { TestAccount } from "./dev/accounts";\n'
        'import { type VisitFixture } from "./dev/accounts";\n'
        "export type Pair = [TestAccount, VisitFixture];\n"
    )
    assert _verdict(_planted(tmp_path, {"lib/screen.ts": source}), markers) == (False, [])


def test_near_miss_a_seed_string_off_the_release_path_passes(
    tmp_path: Path, markers: list[str]
) -> None:
    name = seed_values(REAL_SEED, ("name",))[0]
    tree = _planted(tmp_path, {"lib/unused.ts": f'export const unused = "{name}";\n'})
    assert _verdict(tree, markers) == (False, [])


def test_near_miss_a_string_the_seed_shares_with_the_product_passes(
    tmp_path: Path, markers: list[str]
) -> None:
    shared = seed_values(REAL_SEED, SHARED_KEYS)
    assert shared and not set(shared) & set(markers)
    tree = _planted(tmp_path, {"lib/screen.ts": f'export const screen = "{shared[0]}";\n'})
    assert _verdict(tree, markers) == (False, [])


def test_near_miss_a_marker_inside_a_longer_word_passes(tmp_path: Path, markers: list[str]) -> None:
    padded = ";".join(f'x="k{marker}ri"' for marker in markers)
    tree = _planted(tmp_path, {"lib/screen.ts": f"{padded}\nexport const screen = 1;\n"})
    assert _verdict(tree, markers) == (False, [])
