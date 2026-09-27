"""INT-388 — physician sign-off packets per department, generated, never hand-edited.

scripts/dev/signoff_packet.py renders docs/signoff/<packet>.md for every committed
review candidate from the candidate, its proposal and the verification trail. These
tests hold the committed packets to that source: they regenerate byte for byte, every
questions-table row is a candidate slot with its Turkish text byte-equal, every open
item of the trail is filed or listed as unassigned (and the unassigned list must be
empty), legend rows are no items, items scoped to every pack are signed once in
_cross-cutting.md, and the packets carry no invariant 17 marker and no performance claim.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from protocols.compile.resolve import _merge_chain

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "signoff"
REVIEW = ROOT / "packages" / "protocols" / "review"
TRAIL = ROOT / "docs" / "evidence" / "verification"
MARKER = re.compile(
    r"HB-C\d+|psychiatrist|paediatrician|pediatrician|\bowners?\b|clinician|awaiting-human",
    re.IGNORECASE,
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "signoff_packet", ROOT / "scripts/dev/signoff_packet.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SP = _load()
CONTENT = sys.modules["signoff_content"]
TRAILMOD = sys.modules["signoff_trail"]

CANDIDATES = {f"cluster_{p.stem}": p for p in sorted((REVIEW / "cluster").glob("*.yaml"))} | {
    p.stem: p for p in sorted((REVIEW / "specialty").glob("*.yaml"))
}


@cache
def _rendered() -> dict[str, str]:
    rendered: dict[str, str] = SP.render_all()
    return rendered


def _committed(name: str) -> str:
    return (OUT / name).read_text(encoding="utf-8")


def _section(text: str, number: int) -> str:
    match = re.search(rf"^## {number}\. .*?(?=^## |\Z)", text, re.S | re.M)
    assert match, f"no §{number}"
    return match.group(0)


def _unescape(text: str) -> str:
    """Undo the renderer's only escapes: ``\\|`` and numeric HTML entities."""
    return re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text.replace("\\|", "|"))


def _rows(block: str) -> list[list[str]]:
    """Body rows of the first Markdown table in ``block``, cells unescaped."""
    lines = [line for line in block.splitlines() if line.startswith("|")]
    return [
        [_unescape(c.strip()) for c in re.split(r"(?<!\\)\|", line)[1:-1]] for line in lines[2:]
    ]


def _first_table(block: str) -> str:
    lines = block.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("|"))
    end = next((i for i in range(start, len(lines)) if not lines[i].startswith("|")), len(lines))
    return "\n".join(lines[start:end])


def _dash(value: str | None) -> str:
    return value if value else "—"


def _code(value: str | None) -> str:
    return f"`{value}`" if value else "—"


# --- regeneration ---------------------------------------------------------------------


def test_packets_regenerate_byte_identically() -> None:
    assert SP.drift(_rendered()) == [], "run: uv run python scripts/dev/signoff_packet.py"


def test_one_packet_per_review_candidate_plus_readme_and_unassigned() -> None:
    expected = {f"{key}.md" for key in CANDIDATES} | {
        "README.md",
        "_unassigned.md",
        "_cross-cutting.md",
    }
    assert set(_rendered()) == expected
    assert {p.name for p in OUT.glob("*.md")} == expected
    assert len(CANDIDATES) == 99


def test_a_drifted_packet_is_reported(tmp_path: Path) -> None:
    rendered = _rendered()
    for name, text in rendered.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert SP.drift(rendered, tmp_path) == []
    (tmp_path / "kardiyoloji.md").write_text(rendered["kardiyoloji.md"] + " ", encoding="utf-8")
    (tmp_path / "eski_brans.md").write_text("stale\n", encoding="utf-8")
    assert SP.drift(rendered, tmp_path) == ["eski_brans.md", "kardiyoloji.md"]


# --- questions ------------------------------------------------------------------------


def _candidate_slots(path: Path) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        f"{sid}.{key}": (slot, section)
        for sid, section in doc["sections"].items()
        for key, slot in (section.get("slots") or {}).items()
    }


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_every_questions_row_is_a_candidate_slot(key: str) -> None:
    rows = _rows(_first_table(_section(_committed(f"{key}.md"), 1)))
    slots = _candidate_slots(CANDIDATES[key])
    listed = [row[2].strip("`") for row in rows]
    assert sorted(listed) == sorted(slots), "rows and candidate slots differ"
    for position, _q, slot_ref, kind, ask, follow_up, gate, delivery, _layer in rows:
        slot, section = slots[slot_ref.strip("`")]
        assert kind == slot["type"]
        assert ask == _dash(slot.get("ask_tr", {}).get("tr"))
        assert follow_up == _dash(slot.get("follow_up_tr", {}).get("tr"))
        assert gate == _code(slot.get("ask_if"))
        assert delivery == _dash(slot.get("delivery") or section.get("delivery"))
        assert position.isdigit()


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_turkish_text_is_byte_equal_to_the_candidate(key: str) -> None:
    rows = _rows(_first_table(_section(_committed(f"{key}.md"), 1)))
    slots = _candidate_slots(CANDIDATES[key])
    for row in rows:
        slot, _ = slots[row[2].strip("`")]
        for cell_text, field in ((row[4], "ask_tr"), (row[5], "follow_up_tr")):
            source = (slot.get(field) or {}).get("tr")
            if source is not None:
                assert cell_text.encode("utf-8") == source.encode("utf-8")


def test_positions_follow_the_resolved_chain_with_its_reorder_op() -> None:
    for key in CANDIDATES:
        positions = [int(r[0]) for r in _rows(_first_table(_section(_committed(f"{key}.md"), 1)))]
        assert positions == sorted(positions) and len(set(positions)) == len(positions), key
    rows = _rows(_first_table(_section(_committed("kadin_hastaliklari_ve_dogum.md"), 1)))
    at = {r[2].strip("`").split(".")[1]: int(r[0]) for r in rows}
    gated = ("gebelikte_kanama", "bebek_hareketlerinde_azalma", "gebelikte_siddetli_bas_agrisi")
    assert all(at["gebelik_durumu"] < at[slot] for slot in gated)
    # Near-miss: the bare merge, without the candidate's reorder op, asks the gated
    # questions before their gate. The packet shows the op's order, not the merge's.
    packet = next(p for p in CONTENT.packets() if p.key == "kadin_hastaliklari_ve_dogum")
    merged = list(_merge_chain(CONTENT.chain(packet))["sorular"].slots)
    assert all(merged.index(slot) < merged.index("gebelik_durumu") for slot in gated)


# --- sources and red-flag stubs -------------------------------------------------------


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_sources_are_the_proposals_section_one(key: str) -> None:
    proposal = (ROOT / "docs/evidence/proposals" / f"{key}.md").read_text(encoding="utf-8")
    section_one = re.search(r"^## 1\.[^\n]*\n(.*?)(?=^## )", proposal, re.S | re.M)
    assert section_one
    headings = re.findall(r"^### (.+)$", section_one.group(1), re.M)
    block = _section(_committed(f"{key}.md"), 2)
    rows = _rows(_first_table(block)) if headings else []
    assert [r[1] for r in rows] == [h.strip() for h in headings]
    for row in rows:
        for url in filter(None, row[4].split("<br>")):
            assert url == "—" or url in section_one.group(1)


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_red_flag_stubs_keep_their_status_and_flag_a_duration_anchor(key: str) -> None:
    doc = yaml.safe_load(CANDIDATES[key].read_text(encoding="utf-8"))
    block = _section(_committed(f"{key}.md"), 3)
    packet = next(p for p in CONTENT.packets() if p.key == key)
    merged = _merge_chain(CONTENT.chain(packet))
    slots = {k: slot.type.value for sec in merged.values() for k, slot in sec.slots.items()}
    for rule in doc.get("red_flags") or []:
        assert f"### `{rule['id']}`" in block
        assert f"| status | `{rule['status']}` |" in block
    flagged = any(
        slots.get(rule.get("tense_anchor"), "date") != "date" for rule in doc.get("red_flags") or []
    )
    assert ("INT-383 (GitHub #630)" in block) == flagged


def test_the_pending_value_marker_is_rendered_escaped() -> None:
    marker = CONTENT.GEN.PENDING_MARKER
    guarded = CONTENT.guard(f"{marker} x requires clinical sign-off")
    assert marker not in guarded
    assert _unescape(guarded) == f"{marker} x requires clinical sign-off"


# --- open items -----------------------------------------------------------------------


def _independent_scan() -> set[tuple[str, int]]:
    """Marker rows of the trail, found without the packet script's parser."""
    docs = [
        p
        for p in sorted(TRAIL.glob("*.md"))
        if "awaiting-clinical-review" in p.read_text().split("\n")[0]
    ] + [ROOT / "docs/evidence/INT-353.md"]
    found: set[tuple[str, int]] = set()
    for path in docs:
        lines = path.read_text(encoding="utf-8").splitlines()
        fenced, legend, section = False, False, ""
        for n, line in enumerate(lines, 1):
            fenced = fenced != line.lstrip().startswith("```")
            section = line if line.startswith("#") and not fenced else section
            is_row = line.startswith("|") and not re.match(r"^\|\s*:?-{3,}", line)
            is_header = n < len(lines) and re.match(r"^\|\s*:?-{3,}", lines[n]) is not None
            if is_row and is_header:
                first = line.split("|")[1].strip().lower()
                legend = first in {"code", "codes", "legend"} or bool(
                    re.search(r"\b(codes|legend)\b", section, re.I)
                )
            legend = legend and line.startswith("|")
            if not fenced and is_row and not is_header and not legend and MARKER.search(line):
                found.add((path.relative_to(ROOT).as_posix(), n))
    return found


def _filing() -> Any:
    items = TRAILMOD.open_items(TRAILMOD.trail_documents())
    return items, TRAILMOD.assign(items, TRAILMOD.NameIndex(CONTENT.packets()))


def test_every_open_item_is_filed_cross_cutting_or_listed_unassigned() -> None:
    items, filing = _filing()
    assert {(i.doc, i.line) for i in items} == _independent_scan()
    listed, cross = _committed("_unassigned.md"), _committed("_cross-cutting.md")
    packet_texts = {key: _committed(f"{key}.md") for key in CANDIDATES}
    for item in items:
        homes = [key for key, its in filing.filed.items() if item in its]
        places = [bool(homes), item in filing.cross_cutting, item in filing.unassigned]
        assert places.count(True) == 1, item.ref
        for key, text in packet_texts.items():
            assert (f"· {item.ref}\n" in text) == (key in homes), (key, item.ref)
        assert (f"· {item.ref}\n" in cross) == (item in filing.cross_cutting), item.ref
        assert (f"· {item.ref}\n" in listed) == (item in filing.unassigned), item.ref


def test_the_unassigned_list_is_empty() -> None:
    _, filing = _filing()
    assert TRAILMOD.unassigned_problems(filing.unassigned) == []
    assert "### OI-" not in _committed("_unassigned.md")


def test_legend_rows_define_codes_and_are_no_items(tmp_path: Path) -> None:
    near_twin = TRAIL / "near-twin-sweep-582.md"
    lines = near_twin.read_text(encoding="utf-8").splitlines()
    legend = {n for n in range(242, 248) if MARKER.search(lines[n - 1])}
    assert len(legend) == 6 and lines[239].startswith("| code |")
    items, _ = _filing()
    assert not {(i.doc, i.line) for i in items} & {
        ("docs/evidence/verification/near-twin-sweep-582.md", n) for n in legend
    }
    assert TRAILMOD.is_legend(("code", "applies to"), "A. Findings")
    assert TRAILMOD.is_legend(("where", "finding"), "C. Resolution codes")
    # Near-miss control: the same row in a findings table is an open item.
    for header, heading, expected in (("code", "A. Findings", 0), ("where", "A. Findings", 1)):
        doc = tmp_path / f"{header}.md"
        doc.write_text(
            f"# Planted — awaiting-clinical-review\n\n## {heading}\n\n"
            f"| {header} | rule |\n|---|---|\n| **C** | The clinician chooses. |\n",
            encoding="utf-8",
        )
        assert len(TRAILMOD.open_items([doc])) == expected


def _planted(tmp_path: Path, where: str) -> Path:
    doc = tmp_path / "planted.md"
    doc.write_text(
        "# Planted review — awaiting-clinical-review\n\n## A. Findings\n\n"
        "| where | finding | severity |\n|---|---|---|\n"
        f"| {where} | The clinician decides. | NOTE (clinician) |\n"
        "| kardiyoloji Q3 | Wording only. | LOW |\n",
        encoding="utf-8",
    )
    return doc


def test_a_planted_item_naming_no_branch_fails_the_empty_check(tmp_path: Path) -> None:
    index = TRAILMOD.NameIndex(CONTENT.packets())
    unknown = TRAILMOD.open_items([_planted(tmp_path, "zz_bilinmeyen_brans Q1")])
    assert len(unknown) == 1
    filing = TRAILMOD.assign(unknown, index)
    assert filing.filed == {} and filing.cross_cutting == []
    assert TRAILMOD.unassigned_problems(filing.unassigned) != []
    # Near-miss control: the same row naming a real branch is filed, and nothing is left.
    filing = TRAILMOD.assign(TRAILMOD.open_items([_planted(tmp_path, "kardiyoloji Q2")]), index)
    assert list(filing.filed) == ["kardiyoloji"]
    assert TRAILMOD.unassigned_problems(filing.unassigned) == []


def test_a_row_scoped_to_every_pack_is_cross_cutting_and_signed_once(tmp_path: Path) -> None:
    packets = CONTENT.packets()
    index = TRAILMOD.NameIndex(packets)
    for where, label, count in (
        ("all 91", "all specialties", 91),
        ("every generated pack; the generator", "all generated packs", 96),
    ):
        filing = TRAILMOD.assign(TRAILMOD.open_items([_planted(tmp_path, where)]), index)
        assert filing.filed == {} and filing.unassigned == []
        (item,) = filing.cross_cutting
        assert item.scope and item.scope[1] == label
        assert len(TRAILMOD.covered(item, packets, index)) == count
    # A scope phrase outside the locator cell does not make a row cross-cutting.
    doc = _planted(tmp_path, "kardiyoloji Q2")
    doc.write_text(doc.read_text().replace("The clinician", "In all 91 chains the clinician"))
    filing = TRAILMOD.assign(TRAILMOD.open_items([doc]), index)
    assert list(filing.filed) == ["kardiyoloji"] and filing.cross_cutting == []


def test_each_packet_points_to_the_cross_cutting_items_that_cover_it() -> None:
    _, filing = _filing()
    packets = CONTENT.packets()
    index = TRAILMOD.NameIndex(packets)
    covers = [TRAILMOD.covered(i, packets, index) for i in filing.cross_cutting]
    assert len(filing.cross_cutting) == 8
    for p in packets:
        n = sum(p.key in keys for keys in covers)
        noun = "item" if n == 1 else "items"
        pointer = (
            "Cross-cutting items that also apply here: see "
            f"[`_cross-cutting.md`](_cross-cutting.md) ({n} {noun})."
        )
        assert _committed(f"{p.key}.md").count(pointer) == 1, p.key
    cross = _committed("_cross-cutting.md")
    tags = re.findall(r"^### (XC-\d+ · .+)$", cross, re.M)
    signature = _section(cross, 2)
    for field in ("signer", "role", "date"):
        assert f"| {field} |" in signature
    decisions = [r[0] for r in _rows("| item |" + signature.split("\n\n| item |", 1)[1])]
    assert decisions == tags and len(tags) == 8
    for item in filing.cross_cutting:
        assert f"- scope: {item.scope[1]} (stated: “{item.scope[0]}”)" in cross


def test_short_names_resolve_only_where_unambiguous() -> None:
    index = TRAILMOD.NameIndex(CONTENT.packets())
    assert index.named("KBB Q5 and kadın op order") == {
        "kulak_burun_bogaz_hastaliklari",
        "kadin_hastaliklari_ve_dogum",
    }
    assert index.named("plastik cerrahi Q2") == {"plastik_rekonstruktif_ve_estetik_cerrahi"}
    assert index.named("göğüs Q9") == set()
    assert index.named("göğüs Q9", frozenset({"gogus_hastaliklari"})) == {"gogus_hastaliklari"}
    assert index.named("ic Q5") == {"ic_hastaliklari"}
    assert index.named("this is the ic value") == set()
    assert index.named("çocuk enfeksiyon Q2") == {"cocuk_enfeksiyon_hastaliklari"}


# --- signature, gates, README ---------------------------------------------------------


@pytest.mark.parametrize("key", sorted(CANDIDATES))
def test_the_signature_block_has_one_decision_row_per_open_item(key: str) -> None:
    text = _committed(f"{key}.md")
    items = re.findall(r"^### (OI-\d+ · .+)$", _section(text, 4), re.M)
    signature = _section(text, 5)
    for field in ("signer", "role", "date", "candidate sha256"):
        assert f"| {field} |" in signature
    decisions = [r[0] for r in _rows("| item |" + signature.split("\n\n| item |", 1)[1])]
    assert decisions == (items or ["—"])


def test_the_zero_marker_gate_passes_on_every_packet(tmp_path: Path) -> None:
    files = [str(p) for p in sorted(OUT.glob("*.md"))]
    assert len(files) == len(CANDIDATES) + 3
    run = subprocess.run(
        ["bash", "scripts/ci/no_placeholders.sh", *files], cwd=ROOT, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout
    # Near-miss control: the same stub text left unescaped fails the gate.
    bare = tmp_path / "bare.md"
    bare.write_text(
        f"{CONTENT.GEN.PENDING_MARKER} x requires clinical sign-off\n", encoding="utf-8"
    )
    run = subprocess.run(
        ["bash", "scripts/ci/no_placeholders.sh", str(bare)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1


def test_no_performance_claim_in_the_packets(tmp_path: Path) -> None:
    files = [str(p) for p in sorted(OUT.glob("*.md"))]
    assert len(files) == len(CANDIDATES) + 3
    run = subprocess.run(
        ["bash", "scripts/ci/claims_scan.sh", "--copy", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout
    # Near-miss control: a figure next to a performance term in clinician copy fails.
    claim = tmp_path / "claim.md"
    claim.write_text(
        "The intake reached a sensitivity of 94.2 % on the eval set.\n", encoding="utf-8"
    )
    run = subprocess.run(
        ["bash", "scripts/ci/claims_scan.sh", "--copy", str(claim)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1


def test_the_readme_counts_packets_and_items_per_decider() -> None:
    readme = _committed("README.md")
    items, filing = _filing()
    assert f"{len(items)} open items" in readme
    assert f"{len(filing.cross_cutting)} cross-cutting" in readme
    assert f"{len(filing.unassigned)} name no packet" in readme
    rows = {
        r[0].strip("`"): r[1:]
        for r in _rows(_first_table(readme.split("## Open items by decider")[1]))
    }
    for decider, (count, packets, cross, left) in rows.items():
        assert int(count) == sum(decider in i.deciders for i in items)
        assert int(packets) == sum(
            any(decider in i.deciders for i in its) for its in filing.filed.values()
        )
        assert int(cross) == sum(decider in i.deciders for i in filing.cross_cutting)
        assert int(left) == sum(decider in i.deciders for i in filing.unassigned)
    listed = _rows(_first_table(readme.split("## Packets")[1]))
    assert listed[0][0] == "[`_cross-cutting`](_cross-cutting.md)"
    assert len(listed) == len(CANDIDATES) + 1
    for step in ("How to sign", "How decisions flow back", "gen_specialty_packs.py"):
        assert step in readme
