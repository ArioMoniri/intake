"""INT-205 — path scrubbing: keep the shape, drop anything that could be words."""

from __future__ import annotations

import hashlib

from intake_platform.redaction import redact_text
from intake_platform.siem.errors import AlertRefused
from intake_platform.siem.models import SAFE_PATH_COMPONENT_RE, ScrubbedPath

__all__ = ["scrub_path"]

#: Structural components that carry no information about a file and are always
#: safe to keep.
_STRUCTURAL = frozenset({"", ".", ".."})


def _component_is_safe(component: str) -> bool:
    if component in _STRUCTURAL:
        return True
    if not SAFE_PATH_COMPONENT_RE.match(component):
        return False
    # A component can be perfectly identifier-shaped and still be a TC Kimlik
    # number in a filename ("hasta-10000000146-rapor.pdf"). Redaction already
    # knows what those look like; if it would change the component, the
    # component is not ours to keep.
    return redact_text(component) == component


def scrub_path(raw: str) -> ScrubbedPath:
    """Reduce ``raw`` to its longest identifier-shaped prefix plus a digest.

    ``/usr/bin/bash`` survives whole. ``/data/uploads/Ayse-göğüs-ağrısı.txt``
    becomes ``/data/uploads`` plus the sha256 of the full path: a responder can
    still tell two alerts about the same file apart, and can still see where on
    the filesystem it sits, without the name ever being rendered.
    """
    if not raw:
        raise AlertRefused("empty path")

    components = raw.split("/")
    absolute = raw.startswith("/")
    depth = sum(1 for component in components if component not in _STRUCTURAL)

    kept: list[str] = []
    truncated = False
    for component in components:
        if _component_is_safe(component):
            if component != "":
                kept.append(component)
            continue
        truncated = True
        break

    if absolute:
        safe_prefix = "/" + "/".join(kept) if kept else "/"
    else:
        safe_prefix = "/".join(kept)

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest() if truncated else None
    return ScrubbedPath(safe_prefix=safe_prefix, depth=depth, truncated=truncated, digest=digest)
