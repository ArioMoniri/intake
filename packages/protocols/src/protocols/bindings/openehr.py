"""The openEHR operational-template binding layer (INT-041; files/12 §8.1).

files/05 §2.1 keeps openEHR as a P3 export (ADR-002) and keeps **the
archetype-path annotation on every slot** as the migration plan. files/12
§8.1 says how that annotation is checked: *"Generating an OPT is hard and
Java-bound; parsing one is an afternoon — Template.xsd is 5 KB and frozen
since 2010. The compiler emits only slot → aql_path bindings, and a pure-
Python walker validates every declared path against the committed .opt,
asserting both resolution and rm_type match."*

Two integrity properties, in this order:

1. **The pin comes first.** ``load_opt`` verifies the file's sha256 against
   :data:`OPT_SHA256` *before* parsing it, so the XML this module hands to
   the standard-library parser is always the committed, reviewed artefact —
   never arbitrary input. ``test_opt_is_pinned`` (files/12 §8.1) keeps the
   constant honest, and a re-authored template therefore forces a new
   questionnaire_definition version rather than drifting silently.
2. **Resolution is exact.** ``resolve`` returns the ``rm_type_name`` of the
   node a path addresses, or ``None``. It never guesses: the committed
   template carries archetype ROOTS only (no invented ``atNNNN`` node), so a
   leaf path fails closed instead of resolving against a fabrication.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ElementTree  # noqa: S405
from pathlib import Path
from types import MappingProxyType
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = [
    "OPT_PATH",
    "OPT_SHA256",
    "OPT_TEMPLATE_ID",
    "OperationalTemplate",
    "OptError",
    "load_opt",
]

_NS: Final = "{http://schemas.openehr.org/v1}"

OPT_PATH: Final = Path("packages/protocols/openehr/previsit_intake.v1.opt")
"""The committed template (files/12 §1 directory layout), repo-root relative."""

OPT_TEMPLATE_ID: Final = "previsit_intake.v1"
OPT_SHA256: Final = "8194139f2dfd2a7cc8899fea0265231c23b2bc083b006e116b3eaa3262e1fb87"
"""sha256 of :data:`OPT_PATH`. Bumping this is the review surface for a
re-authored template (files/12 §8.1)."""


class OptError(ValueError):
    """The committed template is missing, off its pin, or malformed."""


class OperationalTemplate(FrozenModel):
    """The parsed, pinned template: template id, digest, and the archetype
    roots it constrains, each with its RM type."""

    template_id: str = Field(description="OPT ``template_id`` (files/12 §8 opt_template_id).")
    sha256: str = Field(description="Digest of the committed file (files/12 §8 opt_sha256).")
    roots: dict[str, str] = Field(
        description="``archetype_id -> rm_type_name`` for every C_ARCHETYPE_ROOT "
        "under the composition's ``content`` attribute."
    )

    def resolve(self, aql_path: str) -> str | None:
        """Return the ``rm_type`` a declared path addresses, or ``None``.

        The supported form is the archetype-root path
        ``/content[<archetype_id>]`` — exactly the granularity files/05 §2.1
        calls "the archetype-path annotation". A deeper path addresses an
        archetype-internal node, which the committed template deliberately
        does not carry, so it does not resolve (invariant 31 fails closed).
        """
        if not aql_path.startswith("/content[") or not aql_path.endswith("]"):
            return None
        archetype_id = aql_path[len("/content[") : -1]
        if not archetype_id or "[" in archetype_id or "/" in archetype_id:
            return None
        return self.roots.get(archetype_id)


def _text(node: ElementTree.Element | None, tag: str) -> str | None:
    if node is None:
        return None
    child = node.find(f"{_NS}{tag}")
    if child is None or child.text is None:
        return None
    return child.text.strip()


def load_opt(path: Path, *, expected_sha256: str = OPT_SHA256) -> OperationalTemplate:
    """Verify the digest, then parse. Integrity precedes parsing on purpose."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OptError(f"{path}: operational template not readable: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise OptError(
            f"{path}: sha256 {digest} does not match the pin {expected_sha256} — a "
            "re-authored template needs a new definition version, never a silent "
            "rebind (files/12 §8.1)"
        )
    try:
        # The bytes are the committed artefact whose digest was just verified
        # against the pin above, so this is repo-owned input, not untrusted
        # input; ElementTree resolves no external entities either.
        root = ElementTree.fromstring(raw)  # noqa: S314
    except ElementTree.ParseError as exc:
        raise OptError(f"{path}: malformed operational template: {exc}") from exc
    template_id = _text(root.find(f"{_NS}template_id"), "value")
    if template_id is None:
        raise OptError(f"{path}: no template_id/value element (Template.xsd)")
    definition = root.find(f"{_NS}definition")
    if definition is None:
        raise OptError(f"{path}: no definition element (Template.xsd)")
    roots: dict[str, str] = {}
    for attributes in definition.findall(f"{_NS}attributes"):
        if _element_text(attributes, "rm_attribute_name") != "content":
            continue
        for child in attributes.findall(f"{_NS}children"):
            archetype_id = _text(child.find(f"{_NS}archetype_id"), "value")
            rm_type = _element_text(child, "rm_type_name")
            if archetype_id is None or rm_type is None:
                raise OptError(
                    f"{path}: a content child is missing archetype_id or rm_type_name "
                    "— the binding walker refuses a partially typed template"
                )
            roots[archetype_id] = rm_type
    return OperationalTemplate(
        template_id=template_id,
        sha256=digest,
        roots=dict(MappingProxyType(roots)),
    )


def _element_text(parent: ElementTree.Element, tag: str) -> str | None:
    child = parent.find(f"{_NS}{tag}")
    if child is None or child.text is None:
        return None
    return child.text.strip()
