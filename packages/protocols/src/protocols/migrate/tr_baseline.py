"""INT-297 — the pre/post-migration baseline of everything a Turkish patient hears.

The migration in :mod:`protocols.migrate.locale_maps` turns five authored fields
into locale-keyed maps. The danger is not the mechanics: *a migration that
changes one Turkish string is a content change wearing a refactor's clothes*,
and only a diff can tell the two apart.

So this module extracts, from a pack tree, exactly the text a patient can hear
or read, in a form that is **shape-agnostic** — it reads the raw YAML and
accepts both the pre-migration plain string and the post-migration ``{tr: ...}``
map, taking the ``tr`` entry either way. Run before the migration it produced
the committed baseline; run after, it must produce the same bytes.

Each entry carries the authored string *and* its ``expand_tr`` expansion, which
is what actually reaches TTS (CLAUDE.md invariant 22). A refusal to expand is
recorded rather than skipped, because a string whose expansion outcome moved is
a diff even when the authored bytes did not.

All 93 packs are ``maturity: L0`` (HB-C1) and the compiler's serve interlock
refuses them, so this is the only projection of their content that can be taken
at all — and it is the complete one: every one of the five fields, in every
document in the tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from protocols.compile.tr_orthography import TrExpansionError, expand_tr
from protocols.locale_text import DEFAULT_LOCALE
from protocols.migrate.locale_maps import MIGRATED_FIELDS

__all__ = ["authored_baseline"]

TR = DEFAULT_LOCALE


def _tr_of(value: Any) -> Any:
    """The ``tr`` content of a field in either shape.

    Pre-migration a scalar field is a plain string and ``choices_tr`` a list;
    post-migration both are maps keyed by locale. Reading the ``tr`` entry out
    of either is what makes one script able to check both trees.
    """
    if isinstance(value, dict):
        return value.get(TR)
    return value


def _walk(node: Any, path: tuple[str, ...], fields: tuple[str, ...]) -> Iterator[tuple[str, Any]]:
    """Every field of ``fields`` in the document, with a stable pointer."""
    if isinstance(node, dict):
        for key, child in node.items():
            here = (*path, str(key))
            if key in fields:
                yield "/".join(here), _tr_of(child)
            else:
                yield from _walk(child, here, fields)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _walk(child, (*path, str(index)), fields)


def _expansion(text: str) -> str:
    """What reaches TTS, or the refusal that stopped it reaching TTS.

    A string that failed expansion before and fails identically after is
    unchanged content; a string whose *outcome* moved is a diff, which is the
    whole point of recording the refusal rather than skipping the entry.
    """
    try:
        return expand_tr(text).text
    except TrExpansionError as exc:
        return f"!tr-expansion-refused: {type(exc).__name__}: {exc}"


def _rendered(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [{"authored": str(item), "expanded": _expansion(str(item))} for item in value]
    return {"authored": str(value), "expanded": _expansion(str(value))}


def authored_baseline(
    tree: Path, root: Path, fields: tuple[str, ...] = MIGRATED_FIELDS
) -> dict[str, Any]:
    """Every field of ``fields`` in every YAML document under ``tree``.

    Keys are paths relative to ``root`` so the baseline is portable between
    checkouts and readable in a diff.

    ``fields`` defaults to INT-297's five so its committed baseline keeps
    comparing exactly what it was taken over. INT-314 passes
    :data:`~protocols.migrate.locale_maps.SPOKEN_FIELDS` and takes its own
    baseline: one function, two field sets, because a comparator that silently
    widened would make both baselines fail for a reason that is not a content
    change — and a comparator that could not widen at all would have left the
    four spoken fields checked by nothing but a human reading a diff.
    """
    out: dict[str, Any] = {}
    for path in sorted(tree.resolve().rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        entries = {pointer: _rendered(value) for pointer, value in _walk(raw, (), fields)}
        if entries:
            out[str(path.relative_to(root))] = dict(sorted(entries.items()))
    return out
