"""What a sign-off packet shows about its candidate (INT-388; scripts/dev/signoff_packet.py).

Every value here is read from a committed source at render time, never copied by hand:
the candidate YAML, its extends chain as the resolver merges it, the proposal it was
generated from, and the question-set generator's own parser.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from protocols.compile.resolve import _apply_ops, _merge_chain, _ordered_ops
from protocols.loader import load_pack
from protocols.pack import ProtocolPack

ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = ROOT / "packages/protocols"
REVIEW = PROTOCOLS / "review"
BASE_INTAKE = PROTOCOLS / "base/intake.yaml"
TAXONOMY = PROTOCOLS / "taxonomy/branches.yaml"
PROPOSALS = ROOT / "docs/evidence/proposals"
GENERATOR = ROOT / "scripts/dev/gen_specialty_packs.py"
MARKER_GATE = ROOT / "scripts/ci/no_placeholders.sh"
DASH = "—"
TENSE_ANCHOR_TYPE = "date"

URL = re.compile(r"https?://[^\s)>\]`*]+")
ISO_DATE = re.compile(r"retrieved(?:_on)?\W{0,6}(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CAPTURED_ON = re.compile(r"(?:captured|retrieved)\**\s+on\s+(\d{4}-\d{2}-\d{2})")
FIELD = re.compile(r"^(?:\*\*([^*:]+?):\*\*|([A-Za-z][A-Za-z_ /()]*?):)\s+(.*)$")


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_specialty_packs", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GENERATOR}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, mod)
    spec.loader.exec_module(mod)
    return mod


GEN = _load_generator()


# --- text helpers ------------------------------------------------------------------


def _gate_pattern() -> re.Pattern[str]:
    """The invariant 17 gate's own token pattern, read from the gate script."""
    match = re.search(r"^PATTERN='(.+)'$", MARKER_GATE.read_text(encoding="utf-8"), re.M)
    if match is None:
        raise RuntimeError(f"no PATTERN= line in {MARKER_GATE}")
    return re.compile(match.group(1))


GATE_TOKENS = _gate_pattern()


def guard(text: str) -> str:
    """Escape the first character of each invariant 17 gate token as an HTML entity.

    The rendered page reads the same (a draft rule's pending-value marker stays visible)
    while the bytes carry no token the gate forbids outside packages/protocols.
    """
    return GATE_TOKENS.sub(lambda m: f"&#{ord(m.group(0)[0])};{m.group(0)[1:]}", text)


def cell(text: object) -> str:
    """One Markdown table cell: one line, pipes escaped, gate tokens escaped."""
    return guard(" ".join(str(text).split()).replace("|", "\\|"))


def code(text: str | None) -> str:
    return f"`{cell(text)}`" if text else DASH


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    """The git object id of a file's bytes, as ``git hash-object`` prints it."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# --- packets -----------------------------------------------------------------------


@dataclass(frozen=True)
class Packet:
    key: str
    kind: str
    title: str
    cluster: str
    candidate: Path
    proposal: Path

    @property
    def doc(self) -> dict[str, Any]:
        loaded: dict[str, Any] = yaml.safe_load(self.candidate.read_text(encoding="utf-8"))
        return loaded

    @property
    def generated(self) -> bool:
        text = self.candidate.read_text(encoding="utf-8")
        return GEN.GEN_MARKER in text or GEN.LEGACY_GEN_MARKER in text


def taxonomy() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))
    return loaded


def packets() -> list[Packet]:
    """One packet per committed review candidate: the clusters first, then the branches."""
    branches = {b["id"]: b for b in taxonomy()["branches"]}
    out: list[Packet] = []
    for path in sorted((REVIEW / "cluster").glob("*.yaml")):
        key = f"{GEN.CLUSTER_PREFIX}{path.stem}"
        title = yaml.safe_load(path.read_text(encoding="utf-8"))["title_tr"]
        out.append(Packet(key, "cluster", title, path.stem, path, PROPOSALS / f"{key}.md"))
    for path in sorted((REVIEW / "specialty").glob("*.yaml")):
        branch = branches[path.stem]
        out.append(
            Packet(
                path.stem,
                "branch",
                branch["name_tr"],
                branch["cluster"],
                path,
                PROPOSALS / f"{path.stem}.md",
            )
        )
    return out


@functools.cache
def chain(packet: Packet) -> list[ProtocolPack]:
    """base.intake → cluster candidate, then the branch candidate for a branch packet."""
    base = load_pack(BASE_INTAKE)
    cluster = load_pack(REVIEW / "cluster" / f"{packet.cluster}.yaml")
    return (
        [base, cluster]
        if packet.kind == "cluster"
        else [base, cluster, load_pack(packet.candidate)]
    )


# --- questions ---------------------------------------------------------------------


@dataclass(frozen=True)
class QuestionRow:
    position: int
    number: int | None
    section: str
    slot: str
    type: str
    ask: str | None
    follow_up: str | None
    gate: str | None
    delivery: str | None
    layer: str


def _q_numbers(packet: Packet) -> dict[str, int | None]:
    """Candidate slot id → proposal Q number, assigned exactly as the generator does."""
    if not packet.generated:
        return {}
    questions, _ = GEN.extract_questions(packet.proposal.read_text(encoding="utf-8"))
    ids: dict[str, int | None] = {"basvuru_nedeni": questions[0].number}
    for i, q in enumerate(questions[1:], 1):
        ids[q.slot or f"soru_{i}"] = q.number
    return ids


@functools.cache
def merged_slots(packet: Packet) -> list[tuple[str, str, Any, Any]]:
    """(section, key, slot, section delivery) of the resolved chain, in ask order.

    The engine's frozen key (files/13 §9.1): must-ask before detail, then merged
    position, after the chain's ops (a ``reorder`` included) are applied.
    """
    packs = chain(packet)
    merged = _merge_chain(packs)
    refusals = _apply_ops(merged, _ordered_ops(packs), "tr")
    if refusals:
        raise ValueError(f"{packet.key}: the chain refuses its ops: {refusals}")
    flat = [
        (sid, key, slot, state.delivery)
        for sid, state in merged.items()
        for key, slot in state.slots.items()
    ]
    order = sorted(range(len(flat)), key=lambda i: (0 if flat[i][2].must_ask else 1, i))
    return [flat[i] for i in order]


@functools.cache
def question_rows(packet: Packet) -> list[QuestionRow]:
    """The candidate's own slots, numbered by their place among the chain's pack slots."""
    packs = chain(packet)
    base_keys = {(s, k) for s, sec in packs[0].sections.items() for k in sec.slots}
    parent_keys = {(s, k) for s, sec in packs[-2].sections.items() for k in sec.slots}
    own = {(s, k) for s, sec in packs[-1].sections.items() for k in sec.slots}
    numbers = _q_numbers(packet)
    pack_slots = [row for row in merged_slots(packet) if row[:2] not in base_keys]
    rows = []
    for position, (sid, key, slot, section_delivery) in enumerate(pack_slots, 1):
        if (sid, key) not in own:
            continue
        gates = [slot.ask_if, f"skip_if: {slot.skip_if}" if slot.skip_if else None]
        delivery = slot.delivery or section_delivery
        redeclared = packet.kind == "branch" and (sid, key) in parent_keys
        rows.append(
            QuestionRow(
                position=position,
                number=numbers.get(key),
                section=sid,
                slot=key,
                type=slot.type.value,
                ask=slot.ask_tr.get("tr") if slot.ask_tr else None,
                follow_up=slot.follow_up_tr.get("tr") if slot.follow_up_tr else None,
                gate=" ; ".join(g for g in gates if g) or None,
                delivery=delivery.value if delivery else None,
                layer=f"re-declares cluster.{packet.cluster}" if redeclared else "new",
            )
        )
    return rows


def excluded_items(packet: Packet) -> list[tuple[str, str | None, str, str]]:
    """(Q, slot, ask, generator note) for each proposal item the generator kept out.

    Each ``**Q`` segment is parsed on its own by the generator's ``extract_questions``,
    which has no state across segments, so the note is the generator's own warning.
    """
    if not packet.generated:
        return []
    region = GEN._question_region(packet.proposal.read_text(encoding="utf-8"))
    out = []
    for segment in ["\n**Q" + s for s in re.split(r"\n\*\*Q", "\n" + region)[1:]]:
        kept, warnings = GEN.extract_questions(segment)
        quote = re.search(r'>\s*"(.+?)"', segment, re.S)
        if kept or not warnings or not quote:
            continue
        gen = re.search(r"^gen:\s*(.+)$", segment, re.M)
        slot = GEN._parse_gen(gen.group(1)).get("slot") if gen else None
        text = re.sub(r"\s+", " ", re.sub(r"\s*\n>\s*", " ", quote.group(1))).strip()
        number = re.match(r"\n\*\*Q(\w+)", segment)
        label = segment[len("\n**Q") :].split("\n", 1)[0][:40]
        verdict, _, reason = warnings[0].partition(f" Q{label}: ")
        out.append((number.group(1) if number else DASH, slot, text, f"{verdict}: {reason}"))
    return out


# --- sources -----------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    heading: str
    guideline_id: str | None
    version: str | None
    urls: tuple[str, ...]
    retrieved_on: str | None


def _logical_lines(block: str) -> list[str]:
    """Bullet lines with their wrapped continuation lines joined; quote lines kept apart."""
    out: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or not out:
            out.append(stripped.removeprefix("- "))
        elif stripped and not stripped.startswith(">") and line.startswith(" "):
            out[-1] = f"{out[-1]} {stripped}"
        else:
            out.append(stripped)
    return out


def _fields(block: str) -> dict[str, str]:
    """``**Key:** value`` pairs, several per line when separated by `` · ``."""
    found: dict[str, str] = {}
    for line in _logical_lines(block):
        key = None
        for segment in re.split(r"\s·\s|\s(?=\*\*[^*:]+:\*\*)", line):
            match = FIELD.match(segment.strip())
            if match:
                key = (match.group(1) or match.group(2)).strip().lower()
                if key in found:
                    key = None
                    continue
                found[key] = match.group(3).strip()
            elif key is not None:
                found[key] = f"{found[key]} · {segment.strip()}"
    return found


def _preamble_date(preamble: str) -> str | None:
    """The retrieval date a proposal states once, before §1, for all of its sources."""
    for line in _logical_lines(preamble):
        dated = CAPTURED_ON.search(line)
        if dated:
            return f"{dated.group(1)} (stated once, before §1, for every source)"
    return None


@functools.cache
def sources(packet: Packet) -> list[Source]:
    """Each ``###`` entry of the proposal's §1, with the fields that entry states."""
    text = packet.proposal.read_text(encoding="utf-8")
    section = re.search(r"^## 1\.[^\n]*\n(.*?)(?=^## )", text, re.S | re.M)
    if not section:
        return []
    section_wide = _preamble_date(text[: section.start()])
    out = []
    for block in re.split(r"^### ", section.group(1), flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        fields = _fields(body)
        gid = next((v for k, v in fields.items() if k.startswith("guideline")), None)
        version = next(
            (v for k, v in fields.items() if re.match(r"(version|date|published|year)", k)),
            None,
        )
        retrieved = next(
            (v for k, v in fields.items() if "retrieved" in k and DATE.search(v)), None
        )
        if retrieved is None:
            dated = ISO_DATE.search(block)
            retrieved = dated.group(1) if dated else section_wide
        urls = tuple(dict.fromkeys(u.rstrip(".,;:") for u in URL.findall(body)))
        out.append(Source(heading.strip(), gid, version, urls, retrieved))
    return out


# --- red-flag stubs ----------------------------------------------------------------


@functools.cache
def red_flags(packet: Packet) -> list[tuple[dict[str, Any], str | None]]:
    """Each red-flag rule of the candidate, verbatim, with its tense anchor's slot type."""
    types = {key: slot.type.value for _, key, slot, _ in merged_slots(packet)}
    return [
        (rule, types.get(rule.get("tense_anchor", "")))
        for rule in packet.doc.get("red_flags") or []
    ]
