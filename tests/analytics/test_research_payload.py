"""INT-490 — nothing reachable from the analytics response is free text, an
identifier, or a thin cell (invariant 6; LD-06 ``no_identifiers_free_text_or_drill_down``).

The scan (``assert_payload_safe``) is the API's own last step before it answers,
so these tests hold the production guard, not a test-only copy. Each refusal
has a near miss: the real payload passes; the same payload with one free-text
value, one UUID, one person-shaped key, one cell of nine, or one withheld view
that kept its cells does not.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    ALLOWED_DIMENSION_KEYS,
    ALLOWED_PAYLOAD_KEYS,
    RELEASE_SCHEMA,
    AnalyticsRetention,
    Period,
    Platform,
    Stage,
    UnsafePayload,
    ViewKind,
    assert_payload_safe,
    build_release,
    dimension_key_problem,
    release_payload,
)
from research_population import people

K = K_ANONYMITY_FLOOR
UNDECIDED = AnalyticsRetention(aggregates=None, raw_telemetry=None)


def _payload() -> dict[str, Any]:
    records = [
        *people(10, Stage.INVITED, platform=Platform.IOS),
        *people(10, Stage.SHARED, platform=Platform.ANDROID),
        *people(10, Stage.FINISHED, platform=Platform.IOS, version="v2"),
        *people(3, Stage.SHARED, platform=Platform.IOS, version="v2"),
    ]
    release = build_release(
        records,
        period=Period(2026, 39),
        k=K,
        collected=frozenset({ViewKind.FUNNEL, ViewKind.LOCALE, ViewKind.PLATFORM}),
        not_collected={
            kind: "raw_telemetry_retention_undecided"
            for kind in set(ViewKind) - {ViewKind.FUNNEL, ViewKind.LOCALE, ViewKind.PLATFORM}
        },
        measured_at=datetime(2026, 10, 4, 9, 30, tzinfo=UTC),
    )
    return release_payload(release, retention=UNDECIDED, admitted=1, refused=0)


def test_the_real_payload_passes_the_scan() -> None:
    payload = _payload()
    assert payload["schema"] == RELEASE_SCHEMA
    assert_payload_safe(payload, k=K)
    states = {
        (v["kind"], v["dimensions"]["protocol_version"]): v["state"] for v in payload["views"]
    }
    assert states[("funnel", "v1")] == "shown"
    assert states[("funnel", "v2")] == "withheld"


def test_every_key_in_the_payload_is_on_the_closed_lists() -> None:
    seen: set[str] = set()

    def walk(node: object, under_dimensions: bool = False) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if under_dimensions:
                    assert key in ALLOWED_DIMENSION_KEYS
                else:
                    seen.add(key)
                walk(value, key == "dimensions")
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_payload())
    assert seen <= ALLOWED_PAYLOAD_KEYS


def test_no_uuid_and_no_whitespace_anywhere_in_the_serialised_payload() -> None:
    text = json.dumps(_payload())
    assert "tenant-a" not in text  # the record's tenant key never surfaces
    assert re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}", text) is None
    strings: list[str] = []

    def collect(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)
        elif isinstance(node, str):
            strings.append(node)

    collect(_payload())
    assert strings and all(" " not in s for s in strings)


def _mutated(path: list[object], value: object) -> dict[str, Any]:
    payload = copy.deepcopy(_payload())
    node: Any = payload
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return payload


def _first(state: str) -> int:
    return next(i for i, v in enumerate(_payload()["views"]) if v["state"] == state)


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (["views", 0, "dimensions", "protocol"], "göğüs ağrısı", "value_not_id_shaped"),
        (["views", 0, "dimensions", "protocol"], "4b5e0f8a-1c2d-4a6f-9c31-2d4e6f8a1c2d", "uuid"),
        (["views", 0, "dimensions", "patient_id"], "p1", "dimension_key_refused"),
        (["tenants", "tenant_id"], "t1", "key_refused"),
        (["generated_at"], "yesterday at noon", "value_not_id_shaped"),
        (["k"], 9, "k_below_floor"),
        (["views", 0, "state"], "partially_shown", "view_state_unknown"),
    ],
)
def test_one_bad_value_refuses_the_whole_payload(
    path: list[object], value: object, code: str
) -> None:
    with pytest.raises(UnsafePayload) as refused:
        assert_payload_safe(_mutated(path, value), k=K)
    assert refused.value.code == code
    # the refusal names a class, never the value it refused (invariant 6)
    assert str(value) not in str(refused.value)


def test_a_shown_cell_of_nine_is_refused_at_the_boundary() -> None:
    index = _first("shown")
    payload = _mutated(["views", index, "cells", 0, "subjects"], 9)
    with pytest.raises(UnsafePayload) as refused:
        assert_payload_safe(payload, k=K)
    assert refused.value.code == "thin_cell"


def test_a_withheld_view_that_kept_its_cells_is_refused() -> None:
    index = _first("withheld")
    payload = _mutated(["views", index, "cells"], [{"value": "invited", "subjects": 10}])
    with pytest.raises(UnsafePayload) as refused:
        assert_payload_safe(payload, k=K)
    assert refused.value.code == "withheld_view_carries_cells"


def test_a_float_is_refused_because_every_figure_is_a_count() -> None:
    index = _first("shown")
    payload = _mutated(["views", index, "cells", 0, "subjects"], 10.5)
    with pytest.raises(UnsafePayload):
        assert_payload_safe(payload, k=K)


def test_the_period_links_never_point_at_a_week_still_open() -> None:
    period = _payload()["period"]
    assert period["id"] == "2026-W39"
    assert period["previous"] == "2026-W38"
    # measured on Sunday 4 Oct: 2026-W40 runs to Monday 5 Oct, so it is open
    assert period["following"] is None
    later = build_release(
        [],
        period=Period(2026, 39),
        k=K,
        collected=frozenset(),
        not_collected={kind: "x" for kind in ViewKind},
        measured_at=Period(2026, 41).start + timedelta(hours=1),
    )
    links = release_payload(later, retention=UNDECIDED, admitted=None, refused=0)["period"]
    assert links["following"] == "2026-W40"


def test_the_retention_state_is_reported_never_invented() -> None:
    payload = _payload()
    assert payload["retention"] == {
        "aggregates": {"state": "undecided"},
        "raw_telemetry": {"state": "undecided"},
    }
    decided = AnalyticsRetention(aggregates=timedelta(days=30), raw_telemetry=None)
    release = build_release(
        [],
        period=Period(2026, 39),
        k=K,
        collected=frozenset(),
        not_collected={kind: "x" for kind in ViewKind},
    )
    out = release_payload(release, retention=decided, admitted=None, refused=0)
    assert out["retention"]["aggregates"] == {"state": "set", "days": 30}
    assert out["tenants"] == {"state": "unconfigured"}


@pytest.mark.parametrize(
    "key",
    [
        "patient_id",
        "session_count",
        "device_type",
        "free_text",
        "tenant",
        "question_text",
        "protocol_id",
        "user",
        "answer_value",
        "ProtocolVersion",
    ],
)
def test_near_miss_dimension_keys_are_refused(key: str) -> None:
    assert dimension_key_problem(key) is not None


def test_every_allowed_dimension_key_passes_the_refusal_rule() -> None:
    assert {key: dimension_key_problem(key) for key in ALLOWED_DIMENSION_KEYS} == {
        key: None for key in ALLOWED_DIMENSION_KEYS
    }
