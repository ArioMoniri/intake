"""INT-561 — every registry component's licence is verified from its raw LICENSE.

Acceptance (docs/backlog/issues.yaml INT-561, GitHub #949):

- a licence-auditor pass fetches each component's raw LICENSE (pinned revision
  or commit) and records the URL, the sha256 of the blob, the SPDX id, a
  commercial-use verdict and the UTC instant of the fetch in the registry;
- a component whose raw licence cannot be found, or is not commercially
  usable, is marked so and never shown as verified;
- tests pin every registry row to a recorded verification; a row without one
  fails.

CLAUDE.md invariant 19: a licence is read from the raw LICENSE blob, never from
a badge, a model-card tag or a package classifier. The admin page's
"Lisans doğrulandı" column renders ``licence_verified_at``; these tests hold
that a date there always means "read, hashed, commercially usable".
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from intake_api.admin.ops_console import build_ops_console
from intake_probes.console import CellSeverity, models_module
from intake_probes.registry import CommercialUse, Registry, RegistryEntry, load_registry
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
EVIDENCE_PATH = REPO / "docs" / "evidence" / "INT-561.md"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)

#: a raw blob at a full 40-hex revision: GitHub raw or a Hugging Face `raw/`
_PINNED_RAW_URL = re.compile(
    r"^https://(?:raw\.githubusercontent\.com/[^/\s]+/[^/\s]+/[0-9a-f]{40}/"
    r"|huggingface\.co/(?:datasets/)?[^/\s]+/[^/\s]+/raw/[0-9a-f]{40}/)\S+$"
)
_READ = {CommercialUse.YES, CommercialUse.CONDITIONAL, CommercialUse.NO}
_USABLE = {CommercialUse.YES, CommercialUse.CONDITIONAL}


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "component": "sample",
        "self_hostable": True,
        "self_hosted_now": True,
        "host": "dev compose 127.0.0.1:5432",
        "license": "Apache-2.0",
        "probe": "http_health",
        "budget_ms": 500,
        "fallback": "none",
        "phi_path": False,
    }
    base.update(overrides)
    return base


#: a complete record for a blob that was read and permits commercial use;
#: the near-miss tests remove or bend one key at a time
_VERIFIED: dict[str, object] = {
    "licence_verified_at": "2026-10-16",
    "licence_checked_at": "2026-10-16T23:11:04Z",
    "licence_blob_url": ("https://raw.githubusercontent.com/example/repo/" + "c" * 40 + "/LICENSE"),
    "licence_blob_sha256": "d" * 64,
    "licence_spdx": "Apache-2.0",
    "licence_commercial_use": "yes",
}

_NOT_FOUND: dict[str, object] = {
    "licence_checked_at": "2026-10-16T23:11:10Z",
    "licence_spdx": "NOASSERTION",
    "licence_commercial_use": "blob_not_found",
    "licence_note": "the weights repo carries no LICENSE at the pinned revision (404)",
}


def _entry(**record: object) -> RegistryEntry:
    return RegistryEntry.model_validate(_row(**record))


def _without(record: dict[str, object], *keys: str) -> dict[str, object]:
    return {k: v for k, v in record.items() if k not in keys}


def _registry() -> Registry:
    return load_registry(REGISTRY_PATH)


def _evidence_rows() -> dict[str, dict[str, str]]:
    """The verification table in docs/evidence/INT-561.md, keyed by component.

    Columns: component · verdict · SPDX · blob URL · sha256 · fetched (UTC).
    """
    rows: dict[str, dict[str, str]] = {}
    for line in EVIDENCE_PATH.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not re.fullmatch(r"`[a-z0-9][a-z0-9._-]*`", cells[0]):
            continue
        component, verdict, spdx, url, sha, fetched = (c.strip("`") for c in cells)
        rows[component] = {
            "verdict": verdict,
            "spdx": spdx,
            "url": url,
            "sha256": sha,
            "fetched": fetched,
        }
    return rows


# --- the shipped registry: every row is pinned to a recorded verification ----------


class TestEveryShippedRowCarriesARecord:
    def test_every_row_has_a_verdict_an_spdx_id_and_a_fetch_instant(self) -> None:
        missing = [
            e.component
            for e in _registry()
            if e.licence_commercial_use is None
            or e.licence_spdx is None
            or e.licence_checked_at is None
        ]
        assert missing == [], f"rows with no licence verification record: {missing}"

    def test_every_read_blob_is_a_raw_url_at_a_full_revision_with_its_sha256(self) -> None:
        for e in _registry():
            if e.licence_commercial_use not in _READ:
                continue
            assert e.licence_blob_url is not None, e.component
            assert _PINNED_RAW_URL.fullmatch(e.licence_blob_url), (
                f"{e.component}: {e.licence_blob_url} is not a raw blob at a 40-hex revision"
            )
            assert e.licence_blob_sha256 is not None, e.component

    def test_a_date_in_the_verified_column_means_read_and_usable(self) -> None:
        for e in _registry():
            if e.licence_commercial_use in _USABLE:
                assert e.licence_verified_at is not None, e.component
            else:
                assert e.licence_verified_at is None, (
                    f"{e.component} is {e.licence_commercial_use} and must never read as verified"
                )

    def test_the_conditional_rows_state_their_condition(self) -> None:
        for e in _registry():
            if e.licence_commercial_use is CommercialUse.CONDITIONAL:
                assert e.licence_condition, e.component

    def test_every_record_matches_the_evidence_table(self) -> None:
        table = _evidence_rows()
        for e in _registry():
            assert e.component in table, f"{e.component} has no row in {EVIDENCE_PATH.name}"
            row = table[e.component]
            assert e.licence_commercial_use is not None
            assert row["verdict"] == e.licence_commercial_use.value, e.component
            assert row["spdx"] == e.licence_spdx, e.component
            assert e.licence_checked_at is not None
            assert row["fetched"] == e.licence_checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"), (
                e.component
            )
            if e.licence_commercial_use in _READ:
                assert row["url"] == e.licence_blob_url, e.component
                assert row["sha256"] == e.licence_blob_sha256, e.component
            else:
                assert row["sha256"] == "—", e.component

    def test_the_two_blobs_that_were_hashed_without_their_trailing_newline_are_corrected(
        self,
    ) -> None:
        """INT-203 recorded sha256 of each MIT text with the final newline
        stripped, so an auditor re-reading the same bytes could not reproduce
        it. The re-fetch on 2026-10-16 hashed the bytes as served."""
        registry = _registry()
        assert registry.get("edge-ingress").licence_blob_sha256 == (
            "c33e29340498ccde22ba0ab9537d6eb0aa3a2eae0dda61bb6df31df6a032fa5b"
        )
        assert registry.get("edge-crowdsec").licence_blob_sha256 == (
            "198fa694dee3f87684bd26b9ae5227e07f016cc7a3ac187d0036afaf8d08d2da"
        )

    def test_the_rows_with_no_licence_blob_say_so_and_stay_unverified(self) -> None:
        registry = _registry()
        for name in ("whisper-tr-medical", "deid-tr-ner-v1"):
            row = registry.get(name)
            assert row.licence_commercial_use is CommercialUse.BLOB_NOT_FOUND, name
            assert row.licence_verified_at is None, name
            assert row.license.upper().startswith("UNVERIFIED"), name


# --- the record's shape: near misses ---------------------------------------------


class TestTheRecordShape:
    @pytest.mark.parametrize(
        "record",
        [
            _VERIFIED,
            {
                **_VERIFIED,
                "licence_commercial_use": "conditional",
                "licence_condition": "internal self-hosting only, never offered as a service",
            },
            {**_without(_VERIFIED, "licence_verified_at"), "licence_commercial_use": "no"},
            _NOT_FOUND,
        ],
        ids=["yes", "conditional", "no", "blob_not_found"],
    )
    def test_a_complete_record_is_accepted(self, record: dict[str, object]) -> None:
        entry = _entry(**record)
        assert entry.licence_commercial_use is not None

    @pytest.mark.parametrize("missing", ["licence_blob_sha256", "licence_blob_url"])
    def test_a_read_blob_without_its_sha256_or_url_is_refused(self, missing: str) -> None:
        with pytest.raises(ValidationError, match=missing):
            _entry(**_without(_VERIFIED, missing))

    @pytest.mark.parametrize("missing", ["licence_blob_sha256", "licence_blob_url"])
    def test_a_non_commercial_blob_without_its_sha256_or_url_is_refused(self, missing: str) -> None:
        record = {**_without(_VERIFIED, "licence_verified_at"), "licence_commercial_use": "no"}
        with pytest.raises(ValidationError, match=missing):
            _entry(**_without(record, missing))

    def test_a_usable_record_without_a_verified_date_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="licence_verified_at"):
            _entry(**_without(_VERIFIED, "licence_verified_at"))

    @pytest.mark.parametrize("verdict", ["no", "blob_not_found"])
    def test_a_licence_that_is_not_usable_can_never_carry_a_verified_date(
        self, verdict: str
    ) -> None:
        base = _VERIFIED if verdict == "no" else {**_NOT_FOUND, "licence_verified_at": "2026-10-16"}
        with pytest.raises(ValidationError, match="must never carry licence_verified_at"):
            _entry(**{**base, "licence_commercial_use": verdict})

    def test_a_verified_record_under_an_unverified_licence_line_is_refused(self) -> None:
        """The line and the record must agree: a row cannot show a date in
        the verified column while its licence line still says UNVERIFIED."""
        with pytest.raises(ValidationError, match="must agree"):
            _entry(**{**_VERIFIED, "license": "UNVERIFIED — declared Apache-2.0"})

    def test_a_conditional_verdict_without_its_condition_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="licence_condition"):
            _entry(**{**_VERIFIED, "licence_commercial_use": "conditional"})

    def test_a_condition_on_an_unconditional_verdict_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="licence_condition"):
            _entry(**{**_VERIFIED, "licence_condition": "attribution"})

    def test_a_not_found_record_cannot_claim_a_hash(self) -> None:
        with pytest.raises(ValidationError, match="licence_blob_sha256"):
            _entry(**{**_NOT_FOUND, "licence_blob_sha256": "d" * 64})

    def test_a_not_found_record_must_say_where_it_looked(self) -> None:
        with pytest.raises(ValidationError, match="licence_note"):
            _entry(**_without(_NOT_FOUND, "licence_note"))

    def test_a_not_found_record_asserts_no_licence_id(self) -> None:
        with pytest.raises(ValidationError, match="NOASSERTION"):
            _entry(**{**_NOT_FOUND, "licence_spdx": "Apache-2.0"})

    def test_a_read_blob_cannot_be_noassertion(self) -> None:
        with pytest.raises(ValidationError, match="NOASSERTION"):
            _entry(**{**_VERIFIED, "licence_spdx": "NOASSERTION"})

    @pytest.mark.parametrize("checked_at", ["2026-10-16T23:11:04", "2026-10-17T02:11:04+03:00"])
    def test_the_fetch_instant_is_utc(self, checked_at: str) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            _entry(**{**_VERIFIED, "licence_checked_at": checked_at})

    def test_a_verified_date_after_the_fetch_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="licence_checked_at"):
            _entry(**{**_VERIFIED, "licence_verified_at": "2026-10-17"})

    @pytest.mark.parametrize(
        "key", ["licence_spdx", "licence_checked_at", "licence_commercial_use"]
    )
    def test_a_partial_record_is_refused(self, key: str) -> None:
        with pytest.raises(ValidationError, match=key):
            _entry(**_without(_VERIFIED, key))

    def test_a_bare_spdx_claim_with_no_record_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="licence_commercial_use"):
            _entry(licence_spdx="Apache-2.0")

    @pytest.mark.parametrize("spdx", ["apache 2", "MIT, Apache-2.0", ""])
    def test_the_licence_id_is_an_spdx_expression(self, spdx: str) -> None:
        with pytest.raises(ValidationError):
            _entry(**{**_VERIFIED, "licence_spdx": spdx})


# --- what the console and the admin page show -----------------------------------


def _module_row(**record: object) -> Any:
    registry = Registry.model_validate({"components": [_row(**record)]})
    return models_module(registry, {}).rows[0]


class TestTheConsoleMarksIt:
    def test_a_non_commercial_licence_is_marked_and_never_dated(self) -> None:
        row = _module_row(
            **{**_without(_VERIFIED, "licence_verified_at"), "licence_commercial_use": "no"}
        )
        assert row.licence_verified_at is None
        assert [f.code for f in row.findings if f.code.startswith("licence_")] == [
            "licence_not_commercially_usable"
        ]
        assert row.severity is not CellSeverity.OK

    def test_a_missing_blob_is_marked_not_verified(self) -> None:
        row = _module_row(**_NOT_FOUND)
        assert row.licence_verified_at is None
        assert [f.code for f in row.findings if f.code.startswith("licence_")] == [
            "licence_not_verified_from_blob"
        ]

    @pytest.mark.parametrize("verdict", ["yes", "conditional"])
    def test_a_usable_licence_carries_no_licence_finding(self, verdict: str) -> None:
        record = {**_VERIFIED, "licence_commercial_use": verdict}
        if verdict == "conditional":
            record["licence_condition"] = "used only with LiveKit Agents"
        row = _module_row(**record)
        assert row.licence_verified_at == date(2026, 10, 16)
        assert not [f for f in row.findings if f.code.startswith("licence_")]

    def test_the_admin_page_column_reads_the_records(self) -> None:
        """The ops tile behind the page's "Lisans doğrulandı" column, built
        from the committed registry: a date exactly where the record says the
        blob was read and is usable, and nothing anywhere else."""
        registry = _registry()
        payload = build_ops_console(
            prom=None, models=models_module(registry, {}), results={}, now=NOW
        )
        shown = {
            r["component"]: r["licence_verified_at"] for r in payload["tiles"]["models"]["rows"]
        }
        for e in registry:
            if e.licence_commercial_use in _USABLE:
                assert e.licence_verified_at is not None
                assert shown[e.component] == e.licence_verified_at.isoformat(), e.component
            else:
                assert shown[e.component] is None, e.component
