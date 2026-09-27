"""Open items of the verification trail and the packets they name (INT-388).

An open item is a table row, outside code fences, of a verification document that
names a human decider (an HB-C id, a psychiatrist, a paediatrician, the owner, the
clinician, or ``awaiting-human``). The trail is every docs/evidence/verification file
whose title says awaiting-clinical-review, plus docs/evidence/INT-353.md.

Rules, in order:

1. A row of a legend table (its first header cell is ``code``, or its section heading
   names codes or a legend) defines terms, not a decision, and is no open item.
2. A row whose locator cell states a scope over every pack (``all four`` clusters,
   ``all 91`` specialties, ``every generated pack``) is cross-cutting: it is listed
   once in docs/signoff/_cross-cutting.md and signed there, never copied into packets.
3. Any other row is filed under every packet that it, or its section heading, names.
   Only a row that names no packet by name falls back to the slot ids it quotes.
4. A row that names nothing is unassigned and is never forced into a packet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from protocols.loader import load_pack
from signoff_content import GEN, ROOT, Packet, taxonomy

VERIFICATION = ROOT / "docs/evidence/verification"
EXTRA_TRAIL = (ROOT / "docs/evidence/INT-353.md",)
TRAIL_TITLE_MARK = "awaiting-clinical-review"

MARKER = re.compile(
    r"HB-C\d+|psychiatrist|paediatrician|pediatrician|\bowners?\b|clinician|awaiting-human",
    re.IGNORECASE,
)
HB_ID = re.compile(r"\bHB-[A-Z]+\d+[a-z]?\b")
ROLES = ("clinician", "psychiatrist", "paediatrician", "base owner", "owner")
SEPARATOR = re.compile(r"^\|?\s*:?-{3,}")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|(?<!\w)'[^'\n]*'(?!\w)")
BACKTICKED = re.compile(r"`([a-z][a-z0-9_]*)`")
TOKEN = re.compile(r"[a-z0-9_]+")
QREF = re.compile(r"q\d+$")
POSITIONAL_SLOT = re.compile(r"soru_\d+$")
LEGEND_HEADERS = frozenset({"code", "codes", "legend"})
LEGEND_HEADING = re.compile(r"\b(codes|legend)\b", re.IGNORECASE)
LOCATOR_HEADERS = frozenset({"where", "chain", "proposal", "branch", "scope"})
# A scope phrase in a row's locator cell → (scope label, the packet kinds it covers).
# "all four" is scoped by its document: the clusters that document's title names.
SCOPES = (
    ("every generated pack", "all generated packs", "generated"),
    ("all 91", "all specialties", "branch"),
    ("all four", "the clusters this document reviews", "cluster"),
)
_TR_UPPER = str.maketrans({"İ": "i", "I": "ı"})
_ASCII = str.maketrans("ıçğöşüâîû", "icgosuaiu")


def fold(text: str) -> str:
    """Turkish-aware case fold to ASCII (İ→i, I→ı, then ı→i, ş→s …), apostrophes dropped."""
    lowered = text.translate(_TR_UPPER).lower().translate(_ASCII)
    return lowered.replace("'", "").replace("’", "")


def tokens(text: str) -> list[str]:
    return TOKEN.findall(fold(text))


@dataclass(frozen=True)
class Item:
    doc: str
    line: int
    heading: str
    header: tuple[str, ...]
    cells: tuple[str, ...]
    doc_headings: str = ""

    @property
    def locator(self) -> str:
        """The first cell and every cell under a where/chain-style header."""
        cells = [
            c for h, c in zip(self.header, self.cells, strict=False) if h.lower() in LOCATOR_HEADERS
        ]
        return " | ".join([*self.cells[:1], *cells])

    @property
    def scope(self) -> tuple[str, str, str] | None:
        """(phrase, label, packet kind) when the locator states a scope over every pack."""
        low = self.locator.lower()
        return next((s for s in SCOPES if s[0] in low), None)

    @property
    def title(self) -> str:
        return self.doc_headings.split("\n", 1)[0].lstrip("#").strip()

    @property
    def text(self) -> str:
        return " | ".join(self.cells)

    @property
    def ref(self) -> str:
        return f"`{self.doc}` L{self.line}"

    @property
    def deciders(self) -> tuple[str, ...]:
        """The HB ids the row cites, then the roles it names."""
        found = list(dict.fromkeys(HB_ID.findall(self.text)))
        low = self.text.lower().replace("pediatrician", "paediatrician")
        for role in ROLES:
            pattern = r"(?<!base )\bowners?\b" if role == "owner" else rf"\b{role}"
            if re.search(pattern, low):
                found.append(role)
        return tuple(found)


def trail_documents() -> list[Path]:
    """Verification documents awaiting clinical review, then the INT-353 evidence."""
    docs = [
        p
        for p in sorted(VERIFICATION.glob("*.md"))
        if TRAIL_TITLE_MARK in p.read_text(encoding="utf-8").split("\n", 1)[0]
    ]
    return docs + [p for p in EXTRA_TRAIL if p.exists()]


def _cells(line: str) -> tuple[str, ...]:
    parts = [c.strip() for c in CELL_SPLIT.split(line.strip())]
    return tuple(parts[1:-1] if line.strip().endswith("|") else parts[1:])


def is_legend(header: Sequence[str], heading: str) -> bool:
    """A table that defines codes or terms: ``code`` first header cell, or a legend section."""
    first = header[0].strip("`* ").lower() if header else ""
    return first in LEGEND_HEADERS or LEGEND_HEADING.search(heading) is not None


def open_items(docs: Iterable[Path]) -> list[Item]:
    """Every table row (outside code fences and legend tables) that names a human decider."""
    items: list[Item] = []
    for path in docs:
        lines = path.read_text(encoding="utf-8").splitlines()
        name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        headings = "\n".join(line for line in lines if re.match(r"#{1,6} ", line))
        heading, fenced = "", False
        header: tuple[str, ...] = ()
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
            if fenced:
                continue
            if re.match(r"#{1,6} ", line):
                heading = line.lstrip("#").strip()
            if not line.startswith("|"):
                header = ()
                continue
            if SEPARATOR.match(line):
                continue
            if not header and n < len(lines) and SEPARATOR.match(lines[n]):
                header = _cells(line)
                continue
            if MARKER.search(line) and not is_legend(header, heading):
                items.append(Item(name, n, heading, header, _cells(line), headings))
    return items


class NameIndex:
    """Token patterns that name a packet.

    Exact: the packet key, the branch's Turkish name, the cluster id. Prefix, for the
    short names the verification documents use: a leading part of the Turkish name
    (``kadın``, ``iş ve meslek``), of the slug (``klinik_psikoloji``) or the name's
    initials (``KBB``). A prefix names a branch when no other branch shares it, or,
    when several do (``göğüs``), inside a document whose headings name exactly one of
    them. A one-word prefix that ends another name (``cerrahi``) names nothing, and one
    shorter than three letters (``ic``) only in front of a question number (``ic Q5``).
    """

    def __init__(self, all_packets: Sequence[Packet]) -> None:
        names = {b["id"]: tuple(tokens(b["name_tr"])) for b in taxonomy()["branches"]}
        self.exact: dict[tuple[str, ...], set[str]] = {}
        self.prefix: dict[tuple[str, ...], set[str]] = {}
        self.slots: dict[str, set[str]] = {}
        for p in all_packets:
            exact, prefixes = self._patterns(p, names)
            for pattern in exact:
                self.exact.setdefault(pattern, set()).add(p.key)
            for pattern in prefixes:
                self.prefix.setdefault(pattern, set()).add(p.key)
            for sec in load_pack(p.candidate).sections.values():
                for slot in sec.slots:
                    if slot not in GEN.FIXED_SLOTS and not POSITIONAL_SLOT.match(slot):
                        self.slots.setdefault(slot, set()).add(p.key)
        self.longest = max(len(k) for k in [*self.exact, *self.prefix])

    @staticmethod
    def _patterns(
        p: Packet, names: dict[str, tuple[str, ...]]
    ) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
        if p.kind == "cluster":
            words = tuple(p.cluster.split("_"))
            return [(p.key,), (p.cluster,), words], [words[:1]] if words[0] == "allied" else []
        full = names[p.key]
        others = [n for k, n in names.items() if k != p.key]
        prefixes = [
            full[:size]
            for size in range(1, len(full))
            if full[size - 1] != "ve" and not (size == 1 and any(n[-1] == full[0] for n in others))
        ]
        parts = p.key.split("_")
        prefixes += [("_".join(parts[:n]),) for n in range(2, len(parts)) if parts[n - 1] != "ve"]
        core = [t for t in (full[:-1] if full[-1] == "hastaliklari" else full) if t != "ve"]
        if len(core) >= 3:
            prefixes.append(("".join(t[0] for t in core),))
        return [(p.key,), full], prefixes

    def _owner(self, words: Sequence[str], size: int, scope: frozenset[str]) -> str | None:
        pattern = tuple(words[:size])
        exact = self.exact.get(pattern, set())
        if len(exact) == 1:
            return next(iter(exact))
        keys = self.prefix.get(pattern, set())
        keys = keys if len(keys) == 1 else keys & scope
        if len(keys) != 1:
            return None
        short = sum(len(t) for t in pattern) < 3
        if short and not (len(words) > size and QREF.match(words[size])):
            return None
        return next(iter(keys))

    def named(self, text: str, scope: frozenset[str] = frozenset()) -> set[str]:
        """Packets the text names, longest pattern first, each word read once."""
        words = tokens(QUOTED.sub(" ", text))
        hits: set[str] = set()
        i = 0
        while i < len(words):
            for size in range(min(self.longest, len(words) - i), 0, -1):
                key = self._owner(words[i:], size, scope)
                if key:
                    hits.add(key)
                    i += size
                    break
            else:
                i += 1
        return hits

    def by_slot(self, text: str) -> set[str]:
        """Packets whose candidate declares a slot id the text quotes in backticks."""
        return {k for s in BACKTICKED.findall(text) for k in self.slots.get(s, set())}


@dataclass(frozen=True)
class Filing:
    filed: dict[str, list[Item]]
    cross_cutting: list[Item]
    unassigned: list[Item]


def assign(items: Sequence[Item], index: NameIndex) -> Filing:
    """Cross-cutting items by their scope; the rest by the packets they name, or none."""
    filed: dict[str, list[Item]] = {}
    cross: list[Item] = []
    unassigned: list[Item] = []
    scopes: dict[str, frozenset[str]] = {}
    for item in items:
        if item.scope:
            cross.append(item)
            continue
        if item.doc not in scopes:
            scopes[item.doc] = frozenset(index.named(item.doc_headings))
        scope = scopes[item.doc]
        keys = index.named(item.text, scope) | index.named(item.heading, scope)
        keys = keys or index.by_slot(item.text)
        for key in sorted(keys):
            filed.setdefault(key, []).append(item)
        if not keys:
            unassigned.append(item)
    return Filing(filed, cross, unassigned)


def covered(item: Item, packets: Sequence[Packet], index: NameIndex) -> list[str]:
    """The packets a cross-cutting item's stated scope covers."""
    if not item.scope:
        return []
    kind = item.scope[2]
    if kind == "generated":
        return [p.key for p in packets if p.generated]
    if kind == "branch":
        return [p.key for p in packets if p.kind == "branch"]
    named = index.named(item.title)
    return [p.key for p in packets if p.kind == "cluster" and (p.key in named or not named)]


def unassigned_problems(unassigned: Sequence[Item]) -> list[str]:
    """One line per open item that names no packet; the drift test requires none."""
    return [f"{i.ref}: {i.cells[0] if i.cells else ''}" for i in unassigned]
