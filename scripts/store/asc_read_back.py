"""INT-495 — read the App Store Connect draft back and compare it with the plan.

After ``asc_listing.py --apply`` the owner (or the agent holding the owner's go)
runs ``--read-back``. Every planned field is read from App Store Connect and
compared with the served copy. The report names the resource, locale and field,
the sha256 of the live value and MATCH or DIFFER. It never prints a listing value.

It also reports the app record's primary language. The en-US product page shows
the primary language's screenshots (INT-502), so a primary language other than
Turkish is reported for the owner to decide. This module only reads: every
request passes :func:`asc_client.guard`, which refuses any change to it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from asc_client import ApplyError, Transport, pick_editable
from asc_plan import Plan

__all__ = ["Report", "Row", "read_back", "render"]


@dataclass(frozen=True)
class Row:
    resource: str
    locale: str | None
    field: str
    #: sha256 of the live value: UTF-8 for a string, canonical JSON otherwise.
    sha256: str
    matches: bool


@dataclass(frozen=True)
class Report:
    primary_locale: str | None
    rows: tuple[Row, ...]

    @property
    def all_match(self) -> bool:
        return all(row.matches for row in self.rows)


def _digest(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _by_locale(rows: Any) -> dict[str, Mapping[str, Any]]:
    return {str(row["attributes"]["locale"]): row["attributes"] for row in rows or []}


def read_back(plan: Plan, transport: Transport, *, app_id: str) -> Report:
    """Every planned field, read from App Store Connect and compared with the plan."""

    def get(path: str, what: str) -> Any:
        status, data = transport.request("GET", path, None)
        if status >= 300:
            raise ApplyError(f"GET {what} answered {status}; read-back stopped")
        return (data or {}).get("data")

    app = get(f"/v1/apps/{app_id}", "app") or {}
    app_attributes: Mapping[str, Any] = app.get("attributes") or {}
    infos = get(f"/v1/apps/{app_id}/appInfos?include=primaryCategory", "appInfos")
    info = pick_editable(infos, "state", "appInfo")
    info_row = next(row for row in infos if row["id"] == info)
    versions = get(f"/v1/apps/{app_id}/appStoreVersions?filter[platform]=IOS", "versions")
    version = pick_editable(versions, "appVersionState", "App Store version")
    localized = {
        "appInfoLocalizations": _by_locale(
            get(f"/v1/appInfos/{info}/appInfoLocalizations", "locales")
        ),
        "appStoreVersionLocalizations": _by_locale(
            get(f"/v1/appStoreVersions/{version}/appStoreVersionLocalizations", "locales")
        ),
    }
    relationships = info_row.get("relationships") or {}
    category = (relationships.get("primaryCategory") or {}).get("data") or {}
    rating = get(f"/v1/appInfos/{info}/ageRatingDeclaration", "ageRating") or {}
    single: dict[str, Mapping[str, Any]] = {
        "appInfos": {"primaryCategory": category.get("id")},
        "apps": app_attributes,
        "ageRatingDeclarations": rating.get("attributes") or {},
    }
    rows: list[Row] = []
    for step in plan.steps:
        if step.resource in localized:
            live = localized[step.resource].get(step.locale or "", {})
        elif step.resource in single:
            live = single[step.resource]
        else:
            raise ApplyError(f"no read-back for {step.resource}")
        expected = plan.values[(step.resource, step.locale)]
        for field in step.fields:
            actual = live.get(field)
            rows.append(
                Row(step.resource, step.locale, field, _digest(actual), actual == expected[field])
            )
    primary = app_attributes.get("primaryLocale")
    return Report(None if primary is None else str(primary), tuple(rows))


def render(report: Report) -> str:
    """Field names, hashes and MATCH or DIFFER; never a listing value."""
    if report.primary_locale == "tr":
        lines = ["primaryLocale tr"]
    else:
        lines = [
            f"primaryLocale {report.primary_locale}, not tr: the owner's call; "
            "this tool never changes it"
        ]
    for row in report.rows:
        where = f"{row.resource}[{row.locale}]" if row.locale else row.resource
        verdict = "MATCH" if row.matches else "DIFFER"
        lines.append(f"{verdict} {where} {row.field} sha256={row.sha256}")
    differ = sum(not row.matches for row in report.rows)
    lines.append(f"read-back: {len(report.rows) - differ} match, {differ} differ")
    return "\n".join(lines) + "\n"
