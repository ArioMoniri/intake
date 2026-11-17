"""INT-449: the closed table of emotion tags, per delivery context, for the casting tools.

Since the owner's pick of the cast take E04 (3 Oct 2026; D20; the ADR-034
render-time-tags amendment, Accepted), the table is the served one: every row
of ``voice_clips.delivery.DELIVERY_PROFILES`` carries its tags, the profile
refuses a malformed tag or a tag on RED or an instrument, and the ADR-028
gateway prepends them on the wire only. This module is a read-only view of that
table for the casting tools, plus :func:`check_table`, which states the table's
rules in one place so a test can try to break them.

A tag exists only on the wire: never in ``text_tr``, the catalogue or
``clip_text_hash``, so the words the voice speaks are the script's, verbatim
(invariant 10).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from voice_clips.delivery import (
    DELIVERY_CONTEXTS,
    DELIVERY_PROFILES,
    UNTAGGED_CONTEXTS,
    DeliveryContext,
)

_TAG: Final = re.compile(r"\[[a-z]+\]")
_REFUSED_WORDS: Final = frozenset({"pause"})

#: The served table's tags, per context.
TAGS: Final[Mapping[DeliveryContext, tuple[str, ...]]] = MappingProxyType(
    {context: DELIVERY_PROFILES[context].tags for context in DELIVERY_CONTEXTS}
)


class TagRefused(ValueError):
    """A table that breaks the rules: a tag on RED or an instrument, or a bad tag."""


def check_table(table: Mapping[str, tuple[str, ...]] = TAGS) -> None:
    """The table covers the seven contexts; RED and instrument are empty; every
    tag is one bracketed lowercase word that is not a timing instruction."""
    if set(table) != set(DELIVERY_CONTEXTS):
        raise TagRefused("the tag table must name exactly the seven delivery contexts")
    for context, tags in table.items():
        if context in UNTAGGED_CONTEXTS and tags:
            raise TagRefused(f"{context} never carries a tag (ADR-034)")
        for tag in tags:
            if not _TAG.fullmatch(tag) or tag.strip("[]") in _REFUSED_WORDS:
                raise TagRefused(f"tag {tag!r} is not an allowed delivery tag")


def tag_prefix(context: DeliveryContext) -> str:
    """The wire prefix for a context: the served row's tags and one space, or nothing."""
    return DELIVERY_PROFILES[context].wire_prefix
