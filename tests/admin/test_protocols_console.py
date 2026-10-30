"""INT-565 — `GET /admin/protocols`, the Protocols module's console composite.

The console's view-model (apps/admin-web/src/protocols, INT-184) renders this
body; until this issue it existed only as a recorder. Held here: the matrix is
``protocols.taxonomy.coverage`` over the API's own taxonomy and pack tree and
never counts an L0 draft as coverage (invariant 13); the review queue is
proposal-only and carries Loop 2's vocabulary without the API importing it
(invariant 12); clips live under the one spoken profile; the route is a
console read behind the role matrix and the audit wrapper; and the committed
e2e fixture is this route's own builder (no hand-kept copy).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ADMIN_TOKEN, ApiHarness, build_harness
from intake_api.admin.protocols_console import protocols_payload
from intake_platform.admin.console_vocab import EVIDENCE_CHECK_NAMES, PROPOSAL_TARGET_NAMES
from protocols.cli import load_registry
from protocols.loader import PackRegistry
from protocols.taxonomy import load_taxonomy
from recorders import recorder

REPO = Path(__file__).resolve().parents[2]
PACKS = REPO / "packages" / "protocols"
TAXONOMY = PACKS / "taxonomy" / "branches.yaml"
FIXTURE = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "protocols.payload.json"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _read(harness: ApiHarness, role: str = "clinical_lead") -> Any:
    return harness.client.get("/admin/protocols", headers=bearer(role))


class TestTheRoute:
    def test_a_protocol_reviewer_reads_the_composite(self, harness: ApiHarness) -> None:
        response = _read(harness)
        assert response.status_code == 200
        body = response.json()
        taxonomy = load_taxonomy(TAXONOMY)
        coverage = body["coverage"]
        assert coverage["summary"]["total"] == len(taxonomy.branches) == len(coverage["rows"])
        assert coverage["taxonomy_source"] == "packages/protocols/taxonomy/branches.yaml"
        assert body["review_queue"]["allowed_targets"] == list(PROPOSAL_TARGET_NAMES)
        assert body["review_queue"]["unmet_check_names"] == list(EVIDENCE_CHECK_NAMES)
        assert body["review_queue"]["rows"] == []

    def test_no_l0_draft_is_counted_as_coverage(self, harness: ApiHarness) -> None:
        rows = _read(harness).json()["coverage"]["rows"]
        for row in rows:
            if row["status"] in ("DIRECT", "CLUSTER"):
                assert row["served_maturity"] not in (None, "L0"), row["branch_id"]
            else:
                assert row["served_pack_id"] is None, row["branch_id"]

    def test_clips_are_keyed_by_the_spoken_profile_only(self, harness: ApiHarness) -> None:
        voices = _read(harness).json()["clip_coverage"]["voices"]
        assert {voice["profile"] for voice in voices} == {"residency_tr"}
        for voice in voices:
            assert voice["missing"] == voice["required"] - voice["cached"]

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        assert _read(harness, role="tenant_admin").status_code == 403

    def test_no_token_is_refused(self, harness: ApiHarness) -> None:
        assert harness.client.get("/admin/protocols").status_code == 401

    def test_an_unloadable_taxonomy_fails_closed(self, tmp_path: Path) -> None:
        for harness in build_harness(
            tmp_path,
            token_patient=None,
            token_admin=ADMIN_TOKEN,
            admin=build_admin_wiring(),
            client_addr=("192.0.2.10", 51000),
            taxonomy_path=tmp_path / "no-taxonomy-here.yaml",
        ):
            response = _read(harness)
            assert response.status_code == 503
            assert response.json() == {"error": "taxonomy_unconfigured"}


class TestTheBuilder:
    def test_a_servable_pack_is_refused_rather_than_counted_as_zero_clips(self) -> None:
        # near miss to the shipped state: one L1 pack makes the clip zeros a
        # claim this composite cannot back, so it refuses to build
        registry = load_registry(PACKS)
        taxonomy = load_taxonomy(TAXONOMY)
        promoted = PackRegistry()
        for pack in registry:
            if pack.id == "specialty.kardiyoloji":
                pack = pack.model_copy(update={"maturity": type(pack.maturity)("L1")})
            promoted.add(pack)
        with pytest.raises(ValueError, match="clip manifest"):
            protocols_payload(
                registry=promoted, taxonomy=taxonomy, taxonomy_source="t", generated_at=NOW
            )

    def test_the_shipped_tree_builds(self) -> None:
        body = protocols_payload(
            registry=load_registry(PACKS),
            taxonomy=load_taxonomy(TAXONOMY),
            taxonomy_source="packages/protocols/taxonomy/branches.yaml",
            generated_at=NOW,
        )
        assert body["coverage"]["generated_at"] == "2026-10-30"
        assert body["clip_coverage"]["servable_pack_count"] == 0


class TestTheFixtureIsTheRoutesOwn:
    def test_the_committed_fixture_is_the_builder_over_the_committed_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(REPO)
        built = recorder("record_protocols_fixture").build_payload()
        committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for doc in (built, committed):
            doc["coverage"].pop("generated_at")
            doc["clip_coverage"].pop("generated_at")
        assert built == committed, "re-run scripts/dev/record_protocols_fixture.py"
