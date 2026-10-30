"""INT-495: reading the App Store Connect draft back after a write.

The write is checked by reading every planned field back and comparing it with the
served copy. The report carries field names, sha256 and MATCH or DIFFER, never a
value. It also reports the app record's primary language, because the en-US product
page shows the primary language's screenshots (INT-502). The read-back only reads;
the guard still refuses any change to the primary language.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from store_drafts_harness import REPO, promote

STORE_SCRIPTS = REPO / "scripts" / "store"
sys.path.insert(0, str(STORE_SCRIPTS))

import asc_client  # noqa: E402
import asc_plan  # noqa: E402
import asc_read_back  # noqa: E402


@pytest.fixture()
def served(tmp_path: Path) -> Path:
    root = promote(tmp_path / "repo")
    (root / "apps" / "mobile").mkdir(parents=True)
    shutil.copy(REPO / "apps" / "mobile" / "app.json", root / "apps" / "mobile" / "app.json")
    return root


class LiveDraft:
    """App Store Connect holding exactly what the plan wrote, unless told to differ."""

    def __init__(
        self, plan: asc_plan.Plan, *, primary_locale: str = "tr", drift: str | None = None
    ) -> None:
        self.plan = plan
        self.primary_locale = primary_locale
        self.drift = drift
        self.calls: list[tuple[str, str]] = []

    def _values(self, resource: str, locale: str | None) -> dict[str, Any]:
        values = dict(self.plan.values[(resource, locale)])
        if self.drift in values:
            values[self.drift] = "something else"
        return values

    def _localizations(self, resource: str, prefix: str) -> list[dict[str, Any]]:
        return [
            {"id": f"{prefix}-{loc}", "attributes": {"locale": loc, **self._values(res, loc)}}
            for res, loc in self.plan.values
            if res == resource
        ]

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        asc_client.guard(method, path, body)
        self.calls.append((method, path))
        if method != "GET":
            return 200, {"data": {"id": "written"}}
        category = self._values("appInfos", None)["primaryCategory"]
        canned: dict[str, Any] = {
            "/v1/apps/APP": {
                "id": "APP",
                "attributes": {"primaryLocale": self.primary_locale, **self._values("apps", None)},
            },
            "/v1/apps/APP/appInfos": [
                {"id": "info-live", "attributes": {"state": "READY_FOR_DISTRIBUTION"}},
                {
                    "id": "info-1",
                    "attributes": {"state": "PREPARE_FOR_SUBMISSION"},
                    "relationships": {
                        "primaryCategory": {"data": {"type": "appCategories", "id": category}}
                    },
                },
            ],
            "/v1/apps/APP/appStoreVersions": [
                {"id": "v-1", "attributes": {"appVersionState": "PREPARE_FOR_SUBMISSION"}}
            ],
            "/v1/appInfos/info-1/appInfoLocalizations": self._localizations(
                "appInfoLocalizations", "ail"
            ),
            "/v1/appStoreVersions/v-1/appStoreVersionLocalizations": self._localizations(
                "appStoreVersionLocalizations", "avl"
            ),
            "/v1/appInfos/info-1/ageRatingDeclaration": {
                "id": "age-1",
                "attributes": self._values("ageRatingDeclarations", None),
            },
        }
        return 200, {"data": canned[path.split("?", 1)[0]]}


def test_a_faithful_draft_reads_back_as_match_for_every_planned_field(served: Path) -> None:
    plan = asc_plan.build_plan(served)
    report = asc_read_back.read_back(plan, LiveDraft(plan), app_id="APP")
    assert report.primary_locale == "tr"
    planned = {(s.resource, s.locale, f) for s in plan.steps for f in s.fields}
    assert {(r.resource, r.locale, r.field) for r in report.rows} == planned
    assert all(row.matches for row in report.rows)
    description = plan.values[("appStoreVersionLocalizations", "en-US")]["description"]
    row = next(r for r in report.rows if (r.locale, r.field) == ("en-US", "description"))
    assert row.sha256 == hashlib.sha256(description.encode("utf-8")).hexdigest()


def test_a_drifted_field_reads_back_as_differ_and_the_report_holds_no_value(
    served: Path,
) -> None:
    plan = asc_plan.build_plan(served)
    report = asc_read_back.read_back(plan, LiveDraft(plan, drift="keywords"), app_id="APP")
    differ = {(r.locale, r.field) for r in report.rows if not r.matches}
    assert differ == {("tr", "keywords"), ("en-US", "keywords")}
    text = asc_read_back.render(report)
    assert "DIFFER appStoreVersionLocalizations[tr] keywords" in text
    for values in plan.values.values():
        for value in values.values():
            if isinstance(value, str) and len(value) > 12:
                assert value not in text


def test_a_primary_language_other_than_turkish_is_reported_never_changed(
    served: Path,
) -> None:
    plan = asc_plan.build_plan(served)
    live = LiveDraft(plan, primary_locale="en-US")
    report = asc_read_back.read_back(plan, live, app_id="APP")
    assert report.primary_locale == "en-US"
    assert "primaryLocale en-US, not tr" in asc_read_back.render(report)
    assert {method for method, _ in live.calls} == {"GET"}
    # Near miss: changing it is not an edit this writer may make.
    body = {"data": {"type": "apps", "id": "APP", "attributes": {"primaryLocale": "tr"}}}
    with pytest.raises(asc_client.ForbiddenRequest, match="primaryLocale"):
        asc_client.guard("PATCH", "/v1/apps/APP", body)


def test_a_refused_write_names_apples_error_code_and_pointer_never_its_detail(
    served: Path,
) -> None:
    plan = asc_plan.build_plan(served)

    class Refusing(LiveDraft):
        def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
            if method == "PATCH" and "ageRatingDeclarations" in path:
                error = {
                    "status": "409",
                    "code": "ENTITY_ERROR.ATTRIBUTE.UNKNOWN",
                    "detail": "a sentence that may quote a value",
                    "source": {"pointer": "/data/attributes/ageRatingOverrideV2"},
                }
                return 409, {"errors": [error]}
            return super().request(method, path, body)

    with pytest.raises(asc_client.ApplyError) as refused:
        asc_client.apply_plan(plan, Refusing(plan), app_id="APP", log=lambda _line: None)
    message = str(refused.value)
    assert "ENTITY_ERROR.ATTRIBUTE.UNKNOWN" in message
    assert "/data/attributes/ageRatingOverrideV2" in message
    assert "may quote a value" not in message


def test_a_language_added_to_the_app_info_is_written_into_its_new_version_localization(
    served: Path,
) -> None:
    """Live run of 31 Oct 2026: App Store Connect creates a version localization when a
    language joins the app info, so a POST for it answered 409 DUPLICATE. The writer
    reads a version's localizations again just before writing one, and PATCHes it."""
    plan = asc_plan.build_plan(served)

    class AddsVersionLocale(LiveDraft):
        def __init__(self, plan: asc_plan.Plan) -> None:
            super().__init__(plan)
            self.version_locales = ["en-US"]

        def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
            base = path.split("?", 1)[0]
            if method == "POST" and base == "/v1/appInfoLocalizations":
                self.version_locales.append(body["data"]["attributes"]["locale"])
            if method == "POST" and base == "/v1/appStoreVersionLocalizations":
                self.calls.append((method, path))
                return 409, {"errors": [{"code": "ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE"}]}
            if method == "GET" and base == "/v1/appInfos/info-1/appInfoLocalizations":
                self.calls.append((method, path))
                return 200, {"data": [{"id": "ail-en-US", "attributes": {"locale": "en-US"}}]}
            if method == "GET" and base == "/v1/appStoreVersions/v-1/appStoreVersionLocalizations":
                self.calls.append((method, path))
                rows = [
                    {"id": f"avl-{loc}", "attributes": {"locale": loc}}
                    for loc in self.version_locales
                ]
                return 200, {"data": rows}
            return super().request(method, path, body)

    live = AddsVersionLocale(plan)
    asc_client.apply_plan(plan, live, app_id="APP", log=lambda _line: None)
    writes = [(m, p) for m, p in live.calls if m != "GET"]
    assert ("POST", "/v1/appInfoLocalizations") in writes
    assert ("PATCH", "/v1/appStoreVersionLocalizations/avl-tr") in writes
    assert ("POST", "/v1/appStoreVersionLocalizations") not in writes
