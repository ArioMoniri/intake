"""INT-297/INT-314 — rewrite ``*_tr`` scalars into locale maps, and back again.

Nine fields, one transformation, applied to whatever shape it finds. INT-297
moved the five that carry a *question*; INT-314 moved the four that carry the
red-flag script's *action* — ``confirm_tr``, ``action_tr``, ``do_nots_tr`` and
``ask_one_tr`` — which is where CLAUDE.md invariant 10's "red-flag action
scripts are spoken verbatim" clause actually bites:

===================  ====================  =============================
field                before                after
===================  ====================  =============================
``text_tr``          ``"metin"``           ``{tr: "metin"}``
``ask_tr``           ``"soru?"``           ``{tr: "soru?"}``
``follow_up_tr``     ``"açar mısınız?"``   ``{tr: "açar mısınız?"}``
``why_tr``           ``"çünkü…"``          ``{tr: "çünkü…"}``
``choices_tr``       ``["evet", "hayır"]`` ``{tr: ["evet", "hayır"]}``
``confirm_tr``       ``"öyle mi?"``        ``{tr: "öyle mi?"}``
``action_tr``        ``"Hemen arayın."``   ``{tr: "Hemen arayın."}``
``ask_one_tr``       ``"hastanede mi?"``   ``{tr: "hastanede mi?"}``
``do_nots_tr``       ``["yatmayın"]``      ``{tr: ["yatmayın"]}``
===================  ====================  =============================

Two properties, and neither is incidental.

**Idempotent.** :func:`migrate_document` recognises an already-migrated field
and leaves it exactly as it found it, so running the migration twice — or over a
tree half of which somebody already converted by hand — cannot double-wrap a
value or reorder a key. :func:`migrate_tree` returns the files it changed, so
"nothing left to do" is an empty tuple rather than a silent pass.

**Reversible.** :func:`unmigrate_document` is the exact inverse for a map of
size one, which is every map in the tree today. Reversibility is what makes the
rewrite reviewable: a diff nobody can undo is a diff nobody can check.

**What it never touches.** The ``kind: text_mirror`` documents (the English
reviewer gloss keyed *by* the tr resource key — files/03; INT-043) and any field
outside the five. A migration that quietly widened its own scope would be
indistinguishable from a content edit, which is the failure this whole issue is
built to catch.

Writing is deliberately not ``yaml.safe_dump``: a round-trip through PyYAML
reflows every quote, comment and block scalar in a pack and buries the five real
changes in three thousand cosmetic ones. The rewrite is a **line edit** against
the YAML source, so ``git diff`` shows exactly the fields that moved — and the
tests still compare the parsed content, so a line edit that lost a byte fails.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from protocols.locale_text import DEFAULT_LOCALE

__all__ = [
    "ALL_LOCALE_FIELDS",
    "MIGRATED_FIELDS",
    "FLAG_FIELDS",
    "SCALAR_FIELDS",
    "SEQUENCE_FIELDS",
    "SPOKEN_FIELDS",
    "SPOKEN_SCALAR_FIELDS",
    "SPOKEN_SEQUENCE_FIELDS",
    "TEXT_SCALAR_FIELDS",
    "migrate_document",
    "migrate_text",
    "migrate_tree",
    "pending",
    "unmigrate_document",
]

TEXT_SCALAR_FIELDS = ("text_tr", "ask_tr", "follow_up_tr", "why_tr")
SEQUENCE_FIELDS = ("choices_tr",)

#: INT-314. The four spoken fields INT-297 left as single strings, and the ones
#: invariant 10's *red-flag action script* clause is actually about:
#: ``confirm_tr`` on a slot, ``action_tr`` and ``do_nots_tr`` on a location
#: branch, ``ask_one_tr`` on the UNKNOWN branch. Kept as their own tuple rather
#: than folded into :data:`MIGRATED_FIELDS` because that set defines INT-297's
#: committed content baseline, and a baseline whose *field set* moved is a
#: baseline that no longer compares the same thing.
SPOKEN_SCALAR_FIELDS = ("confirm_tr", "action_tr", "ask_one_tr")
SPOKEN_SEQUENCE_FIELDS = ("do_nots_tr",)
SPOKEN_FIELDS = (*SPOKEN_SCALAR_FIELDS, *SPOKEN_SEQUENCE_FIELDS)

#: ``allow_paraphrase`` travels with them. The acceptance names it in the same
#: breath — *"``allow_paraphrase`` is per locale"* — because a permission is
#: about a language: it is granted for Turkish, whose register and reading level
#: were checked, and asserts nothing about a language where neither was. It is
#: kept out of :data:`MIGRATED_FIELDS` because that set defines the *content*
#: baseline, and a boolean is not a string a patient hears.
FLAG_FIELDS = ("allow_paraphrase",)

SCALAR_FIELDS = (*TEXT_SCALAR_FIELDS, *FLAG_FIELDS, *SPOKEN_SCALAR_FIELDS)

#: INT-297's five text fields, and nothing else. A field absent from here is a
#: field whose Turkish *that* migration must have left exactly as it found it,
#: which is what ``int297_tr_content_baseline.json`` is a baseline of.
MIGRATED_FIELDS = (*TEXT_SCALAR_FIELDS, *SEQUENCE_FIELDS)

#: Every locale-keyed field in the DSL, whichever issue moved it. This is what
#: the rewrite acts on; the two per-issue tuples above exist for the two
#: baselines, which have to keep comparing what they were taken over.
ALL_LOCALE_FIELDS = (*MIGRATED_FIELDS, *SPOKEN_FIELDS)

_REWRITTEN_FIELDS = (*SCALAR_FIELDS, *SEQUENCE_FIELDS, *SPOKEN_SEQUENCE_FIELDS)

_SKIP_KINDS = frozenset({"text_mirror"})

# ``  ask_tr: value`` — the key at some indent, then the rest of the line. A
# dotted key ("identity_check.subject_role.ask_tr") is a mirror entry and is not
# matched, because the key must start right after the indent.
_SCALAR_LINE = re.compile(
    r"^(?P<indent>[ ]*)(?P<key>" + "|".join(SCALAR_FIELDS) + r"):(?P<rest>|[ ].*)$"
)
_SEQUENCE_LINE = re.compile(
    r"^(?P<indent>[ ]*)(?P<key>"
    + "|".join((*SEQUENCE_FIELDS, *SPOKEN_SEQUENCE_FIELDS))
    + r"):(?P<rest>.*)$"
)


def _is_migrated(value: Any) -> bool:
    return isinstance(value, dict)


# --- document level (the checkable, shape-level transformation) --------------


def migrate_document(node: Any) -> Any:
    """Return ``node`` with every migrated field wrapped, idempotently."""
    if isinstance(node, dict):
        if node.get("kind") in _SKIP_KINDS:
            return node
        out: dict[Any, Any] = {}
        for key, child in node.items():
            if key in _REWRITTEN_FIELDS:
                out[key] = child if _is_migrated(child) else {DEFAULT_LOCALE: child}
            else:
                out[key] = migrate_document(child)
        return out
    if isinstance(node, list):
        return [migrate_document(child) for child in node]
    return node


def unmigrate_document(node: Any) -> Any:
    """The exact inverse for a map of size one; a wider map is left alone.

    A field carrying two locales cannot be expressed in the pre-migration shape
    at all, so reversing it would have to choose one and drop the other. It
    refuses instead: the inverse is total exactly where the forward direction
    lost nothing.
    """
    if isinstance(node, dict):
        if node.get("kind") in _SKIP_KINDS:
            return node
        out: dict[Any, Any] = {}
        for key, child in node.items():
            if (
                key in _REWRITTEN_FIELDS
                and isinstance(child, dict)
                and set(child) == {DEFAULT_LOCALE}
            ):
                out[key] = child[DEFAULT_LOCALE]
            elif key in _REWRITTEN_FIELDS:
                out[key] = child
            else:
                out[key] = unmigrate_document(child)
        return out
    if isinstance(node, list):
        return [unmigrate_document(child) for child in node]
    return node


# --- source level (the line edit that keeps the diff readable) --------------


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _already_a_map(lines: Sequence[str], index: int, indent: str) -> bool:
    """True where the key is followed by a deeper block that opens with ``tr:``."""
    for line in lines[index + 1 :]:
        if not line.strip():
            continue
        if _indent_width(line) <= len(indent):
            return False
        return line.lstrip().startswith(f"{DEFAULT_LOCALE}:")
    return False


def _continuation(lines: Sequence[str], index: int, base: int, *, sequence: bool) -> int:
    """How many following lines belong to the value that started at ``index``.

    A block scalar's body, a plain scalar's wrapped tail and a block sequence's
    items are all *continuation*: deeper than the key, or — for a sequence
    alone — level with it and starting ``-``. Trailing blank lines are given
    back, so a blank line between two slots stays a blank line between two
    slots.
    """
    cursor = index + 1
    last_content = index
    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            cursor += 1
            continue
        width = _indent_width(line)
        if width > base or (sequence and width == base and line.lstrip().startswith("-")):
            last_content = cursor
            cursor += 1
            continue
        break
    return last_content - index


def migrate_text(source: str) -> str:
    """Rewrite one YAML source, touching only the five fields' own lines.

    A line edit rather than a dump: the value's bytes are never re-serialised,
    only moved two columns right under a ``tr:`` key, so the diff a reviewer
    reads is the five fields and nothing else.
    """
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    while index < len(lines):
        body = lines[index].rstrip("\n")
        scalar = _SCALAR_LINE.match(body)
        sequence = _SEQUENCE_LINE.match(body)
        match = scalar or sequence
        if match is None or _already_a_map(lines, index, match["indent"]):
            out.append(lines[index])
            index += 1
            continue
        indent, key, rest = match["indent"], match["key"], match["rest"]
        out.append(f"{indent}{key}:\n")
        out.append(f"{indent}  {DEFAULT_LOCALE}:{rest}\n")
        span = _continuation(lines, index, len(indent), sequence=scalar is None)
        for line in lines[index + 1 : index + 1 + span]:
            out.append(line if not line.strip() else "  " + line)
        index += 1 + span
    tail = "".join(out)
    return tail if source.endswith("\n") or not tail.endswith("\n") else tail[:-1]


def migrate_file(path: Path) -> bool:
    """Migrate one file in place. Returns whether it changed.

    A file the migration cannot parse as one YAML document is left alone rather
    than rewritten blind: a pack is always a single document (``load_pack`` uses
    ``safe_load``), so a multi-document file is not a pack and a file that does
    not parse at all is not something a line edit should be the first to touch.
    """
    source = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(source)
    except yaml.YAMLError:
        return False
    if isinstance(parsed, dict) and parsed.get("kind") in _SKIP_KINDS:
        return False
    rewritten = migrate_text(source)
    if rewritten == source:
        return False
    expected = migrate_document(parsed)
    if yaml.safe_load(rewritten) != expected:
        raise ValueError(
            f"{path}: the line edit and the shape-level migration disagree — refusing "
            "to write, because a rewrite whose parsed result is not the declared "
            "transformation is a content change (INT-297)"
        )
    path.write_text(rewritten, encoding="utf-8")
    return True


def pending(path: Path) -> bool:
    """Whether this file would still change. The ``--check`` half of the CLI."""
    source = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(source)
    except yaml.YAMLError:
        return False
    if isinstance(parsed, dict) and parsed.get("kind") in _SKIP_KINDS:
        return False
    return migrate_text(source) != source


def migrate_tree(root: Path) -> tuple[Path, ...]:
    """Migrate every YAML document under ``root``; return the files it changed."""
    return tuple(path for path in sorted(root.rglob("*.yaml")) if migrate_file(path))
