"""INT-449 round 2: the closed table of render-time emotion tags, per delivery context.

The owner found the round-1 voices not emotional enough (3 Oct 2026). ``eleven_v3``
reads bracketed audio tags written in the request text. This table is the only
place a tag can come from, and a tag exists only on the wire:

- it is prepended to the request text by the request layer, outside ``text_tr``,
  outside the catalogue and outside ``clip_text_hash``, so the words the voice
  speaks are the catalogue's, verbatim (invariant 10);
- ``assert_speakable_tr`` and the markup gate keep running on the catalogue text,
  so no tag can ever be authored into a line;
- RED and instrument carry no tag, on any model (ADR-034; invariant 21 wants RED
  the most stable delivery, and an instrument item is validated wording);
- a tag is one lowercase English word in brackets, and only at the start: never
  mid-line, never ``[pause]``, never a sound effect.

This is the render-time-only proposal recorded as an ADR-034 amendment in
docs/voice/adr-034-amendment-proposal-render-time-tags.md. Nothing served uses
it until the owner accepts that amendment.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from voice_clips.delivery import DELIVERY_CONTEXTS, DeliveryContext

#: Contexts that never carry a tag, on any model.
UNTAGGED: Final = frozenset({"red", "instrument"})
#: One lowercase word in brackets. ``pause`` is refused by name: a pause tag is a
#: timing instruction inside the line, which ADR-034 never allows.
_TAG: Final = re.compile(r"\[[a-z]+\]")
_REFUSED_WORDS: Final = frozenset({"pause"})

TAGS: Final[Mapping[DeliveryContext, tuple[str, ...]]] = MappingProxyType(
    {
        "welcome": ("[warmly]",),
        "routine": ("[calm]",),
        "sensitive": ("[softly]", "[reassuring]"),
        "instrument": (),
        "acknowledgement": ("[gently]",),
        "red": (),
        "closing": ("[warmly]",),
    }
)


class TagRefused(ValueError):
    """A tag outside the closed table, or on a context that never carries one."""


def check_table(table: Mapping[str, tuple[str, ...]] = TAGS) -> None:
    """The table covers the seven contexts; RED and instrument are empty; every
    tag is one bracketed lowercase word that is not a timing instruction."""
    if set(table) != set(DELIVERY_CONTEXTS):
        raise TagRefused("the tag table must name exactly the seven delivery contexts")
    for context, tags in table.items():
        if context in UNTAGGED and tags:
            raise TagRefused(f"{context} never carries a tag (ADR-034)")
        for tag in tags:
            if not _TAG.fullmatch(tag) or tag.strip("[]") in _REFUSED_WORDS:
                raise TagRefused(f"tag {tag!r} is not an allowed delivery tag")


def tag_prefix(context: DeliveryContext) -> str:
    """The wire prefix for a context: its tags and one space, or nothing."""
    tags = TAGS[context]
    return " ".join(tags) + " " if tags else ""


def check_prefix(context: str, prefix: str) -> None:
    """A request prefix is the table's prefix for its context, or empty."""
    if not prefix:
        return
    if context in UNTAGGED or context not in TAGS:
        raise TagRefused(f"{context} never carries a tag")
    if prefix != tag_prefix(context):  # type: ignore[arg-type]
        raise TagRefused(f"prefix {prefix!r} is not the closed table's for {context}")
