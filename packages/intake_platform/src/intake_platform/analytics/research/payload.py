"""INT-490 — the release on the wire, and the scan it must pass to leave.

``release_payload`` is the only serialiser of a :class:`Release`. Its output is
counts, closed-vocabulary words, id-shaped dimension values and instants — no
prose at all; the page's copy explains, the payload only states.

``assert_payload_safe`` is run by the API on its own response before answering
(and by the tests on the same object). It walks the whole document and refuses
it, whole, on the first:

- key that is not on :data:`ALLOWED_PAYLOAD_KEYS` (or, under ``dimensions``,
  on :data:`~.catalogue.ALLOWED_DIMENSION_KEYS`);
- string that is neither id-shaped nor an ISO-8601 UTC instant — free text
  fails on its first space — or that is shaped like a UUID, the form every
  person, session and tenant key in this repository takes;
- number that is not a non-negative whole count;
- shown cell holding between 1 and k-1 people, or withheld view still
  carrying cells;
- ``k`` under the product floor.

A refusal names the defect class, never the value it refused (invariant 6).
This scan is defence in depth: :mod:`.release` already cannot build any of
these. Its job is to make the boundary say so independently.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from intake_platform.analytics.k_anonymity import _ID_SHAPE, K_ANONYMITY_FLOOR
from intake_platform.analytics.research.catalogue import ALLOWED_DIMENSION_KEYS
from intake_platform.analytics.research.release import (
    Release,
    ReleasedView,
    ViewId,
    WithheldReason,
)
from intake_platform.analytics.research.retention import AnalyticsRetention

__all__ = [
    "ALLOWED_PAYLOAD_KEYS",
    "RELEASE_SCHEMA",
    "UnsafePayload",
    "assert_payload_safe",
    "release_payload",
]

RELEASE_SCHEMA: Final = "intake.admin.analytics.v1"

#: Every key the document may hold, outside ``dimensions``. Closed.
ALLOWED_PAYLOAD_KEYS: Final = frozenset(
    {
        "schema",
        "generated_at",
        "k",
        "grain",
        "period",
        "id",
        "start",
        "end",
        "previous",
        "following",
        "tenants",
        "state",
        "admitted",
        "refused",
        "retention",
        "aggregates",
        "raw_telemetry",
        "days",
        "views",
        "kind",
        "partition",
        "dimensions",
        "reason",
        "cells",
        "value",
        "subjects",
        "not_collected",
    }
)

_INSTANT: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?\+00:00$")
_UUID: Final = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_VIEW_STATES: Final = frozenset({"shown", "withheld"})


class UnsafePayload(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(f"the analytics payload was refused: {code}")
        self.code = code


def _view(view: ViewId, item: ReleasedView | None, reason: WithheldReason | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": view.kind.value,
        "partition": view.partition,
        "dimensions": view.dimensions(),
    }
    if item is not None:
        out["state"] = "shown"
        out["cells"] = [{"value": cell.value, "subjects": cell.subjects} for cell in item.cells]
    else:
        out["state"] = "withheld"
        out["reason"] = reason.value if reason is not None else None
    return out


def release_payload(
    release: Release,
    *,
    retention: AnalyticsRetention,
    admitted: int | None,
    refused: int,
) -> dict[str, Any]:
    """The wire document. ``admitted`` is ``None`` when no tenant registry is
    configured — said as such, never as zero tenants."""
    period = release.period
    following = period.following
    views: list[tuple[ViewId, ReleasedView | None, WithheldReason | None]] = [
        (item.id, item, None) for item in release.shown
    ]
    views += [(item.id, None, item.reason) for item in release.withheld]
    views.sort(key=lambda entry: entry[0].sort_key())
    return {
        "schema": RELEASE_SCHEMA,
        "generated_at": release.measured_at.isoformat(),
        "k": release.k,
        "grain": "iso_week",
        "period": {
            "id": period.id,
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
            "previous": period.previous.id,
            "following": following.id if following.is_closed(release.measured_at) else None,
        },
        "tenants": (
            {"state": "unconfigured"}
            if admitted is None
            else {"state": "configured", "admitted": admitted, "refused": refused}
        ),
        "retention": retention.as_payload(),
        "views": [_view(view, item, reason) for view, item, reason in views],
        "not_collected": [
            {"kind": item.kind.value, "reason": item.reason} for item in release.not_collected
        ],
    }


def _string(value: str) -> None:
    if _UUID.search(value):
        raise UnsafePayload("uuid")
    if _ID_SHAPE.fullmatch(value) is None and _INSTANT.fullmatch(value) is None:
        raise UnsafePayload("value_not_id_shaped")
    if _INSTANT.fullmatch(value) is not None:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise UnsafePayload("value_not_id_shaped") from None


def _walk(node: object, *, dimensions: bool = False) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if not isinstance(key, str):
                raise UnsafePayload("key_refused")
            if dimensions:
                if key not in ALLOWED_DIMENSION_KEYS:
                    raise UnsafePayload("dimension_key_refused")
                if not isinstance(value, str):
                    raise UnsafePayload("value_not_id_shaped")
            elif key not in ALLOWED_PAYLOAD_KEYS:
                raise UnsafePayload("key_refused")
            _walk(value, dimensions=key == "dimensions" and not dimensions)
    elif isinstance(node, list):
        for item in node:
            _walk(item)
    elif isinstance(node, str):
        _string(node)
    elif isinstance(node, bool) or (node is not None and not isinstance(node, int)):
        raise UnsafePayload("value_not_a_count")
    elif isinstance(node, int) and node < 0:
        raise UnsafePayload("value_not_a_count")


def assert_payload_safe(payload: Mapping[str, Any], *, k: int) -> None:
    """Refuse ``payload`` whole unless every part of it is publishable."""
    if payload.get("schema") != RELEASE_SCHEMA:
        raise UnsafePayload("schema_mismatch")
    stated = payload.get("k")
    if not isinstance(stated, int) or isinstance(stated, bool):
        raise UnsafePayload("k_below_floor")
    if stated < K_ANONYMITY_FLOOR or stated < k:
        raise UnsafePayload("k_below_floor")
    _walk(payload)
    for view in payload.get("views", []):
        state = view.get("state")
        if state not in _VIEW_STATES:
            raise UnsafePayload("view_state_unknown")
        if state == "withheld":
            if "cells" in view:
                raise UnsafePayload("withheld_view_carries_cells")
            if view.get("reason") not in {reason.value for reason in WithheldReason}:
                raise UnsafePayload("withheld_reason_unknown")
            continue
        counts = [cell.get("subjects") for cell in view.get("cells", [])]
        if not counts or any(not isinstance(c, int) or 0 < c < stated for c in counts):
            raise UnsafePayload("thin_cell")
        if sum(counts) < stated:
            raise UnsafePayload("thin_cell")
