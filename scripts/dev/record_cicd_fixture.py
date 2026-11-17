"""Record the responses the admin-web CI/CD page renders (INT-187).

``apps/admin-web/e2e/cicd.spec.ts`` drives the page's server-side loader and
renders the page. As with ``record_voice_fixture.py`` and its siblings, the
``/admin/cicd`` body is produced by the shipped composite
(``intake_api.admin.cicd_console.build_cicd_console``), never hand-written in
TypeScript. ``tests/admin/test_cicd_console.py`` holds the committed files equal
to :func:`record`, so a drift fails there.

The inputs, all named here:

- **GitHub** — the real API answers recorded from ``ArioMoniri/intake`` on
  27 Sep 2026 under ``tests/fixtures/ops/github_cicd_*.json`` (see
  ``tests/observability/test_ops_cicd.py``), served to the shipped ops
  collector (``intake_probes.ops_cicd.GithubCicdSource`` inside
  ``OpsCollector``) through an ``httpx.MockTransport``. No network.
- **Prometheus** — the collector's own exposition after one collection,
  answered back for each :data:`~intake_api.admin.cicd_console.CICD_QUERIES`
  expression (every query is ``max by (<all labels>) (<family>)``, so the
  answer is the family's samples). No Prometheus runs on this host; the chain
  GitHub → collector → exposition → composite is the shipped one end to end.
  The SLO queries answer empty: nothing emits those SLIs here, so the error
  budget reads *unmeasured*, never within budget.
- **The freeze store** — the shipped ``RedisReleaseFreezeStore`` over an
  in-memory Redis, seeded with one freeze engaged by an ``sre_oncall``.
- **The four-eyes service** — one pending lift requested by ``platform_admin``.
- **``/version``** — a synthetic stamp: the recorded ``main`` head, the
  recording instant, and the sha256 of a fixed label standing in for an SBOM.
  The unconfigured recording carries ``dev`` in all three, which is what an
  unstamped build serves.

Run: ``uv run python scripts/dev/record_cicd_fixture.py`` (also ``make
admin-fixtures``).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import httpx
from intake_api.admin.cicd_console import CICD_QUERIES, build_cicd_console
from intake_api.admin.ops_prom import PromClient
from intake_api.admin.reliability_console import load_slo_files
from intake_platform.admin.actions import DEPLOY_FREEZE_LIFT
from intake_platform.admin.flag_governance import FlagChangeReason, build_flag_change_justification
from intake_platform.admin.four_eyes import ActorBlock, PendingAction, PendingActionState
from intake_platform.admin.roles import AdminRole
from intake_platform.health import VersionInfo
from intake_platform.release_freeze import (
    DeployFreeze,
    DeployFreezeChange,
    RedisReleaseFreezeStore,
)
from intake_probes.ops_cicd import GithubCicdSource
from intake_probes.ops_collector import OpsCollector
from prometheus_client import REGISTRY, generate_latest
from prometheus_client.parser import text_string_to_metric_families

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
GITHUB = REPO / "tests" / "fixtures" / "ops"
SLO_DIR = REPO / "docs" / "slo"
RECORDED_REPO = "ArioMoniri/intake"
#: Just after the GitHub answers were recorded (27 Sep 2026, ~05:55 UTC).
RECORDED_AT = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
_QUERY = re.compile(r"^max by \(([a-z_, ]+)\) \(([a-z_]+)\)$")


def _load(name: str) -> Any:
    return json.loads((GITHUB / f"github_cicd_{name}.json").read_text(encoding="utf-8"))


def recorded_github() -> httpx.MockTransport:
    """The recorded API answers, routed by path. Anything else is a 404."""
    base = f"/repos/{RECORDED_REPO}"
    jobs: dict[str, Any] = _load("jobs")
    checks: dict[str, Any] = _load("check_runs")
    fixed = {
        f"{base}/actions/runs": _load("runs_main"),
        f"{base}/branches/main": _load("branch_main"),
        f"{base}/rules/branches/main": _load("rules_main"),
        f"{base}/pulls": _load("pulls_open"),
        f"{base}/releases": _load("releases"),
        f"{base}/tags": _load("tags"),
        f"{base}/actions/workflows/security.yml/runs": _load("security_tag_runs"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in fixed:
            return httpx.Response(200, json=fixed[path])
        job = re.fullmatch(rf"{base}/actions/runs/(\d+)/jobs", path)
        if job and job.group(1) in jobs:
            return httpx.Response(200, json=jobs[job.group(1)])
        check = re.fullmatch(rf"{base}/commits/([0-9a-f]{{40}})/check-runs", path)
        if check and check.group(1) in checks:
            return httpx.Response(200, json=checks[check.group(1)])
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def collected_exposition() -> dict[str, list[tuple[dict[str, str], float]]]:
    """One collection by the shipped collector over the recorded answers,
    read back from its own exposition, family by family."""
    source = GithubCicdSource(
        repo=RECORDED_REPO, token=lambda: "recorded", transport=recorded_github()
    )
    outcome = OpsCollector(cicd=source).collect_once()
    if outcome["cicd"] != "ok":
        raise SystemExit(f"the recorded collection failed: {outcome['cicd']}")
    families: dict[str, list[tuple[dict[str, str], float]]] = {}
    for family in text_string_to_metric_families(generate_latest(REGISTRY).decode("utf-8")):
        for sample in family.samples:
            families.setdefault(sample.name, []).append((dict(sample.labels), sample.value))
    return families


def recorded_prometheus() -> PromClient:
    families = collected_exposition()
    by_expr = {expr: query_id for query_id, expr in CICD_QUERIES.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        expr = request.url.params["query"]
        result: list[dict[str, Any]] = []
        match = _QUERY.fullmatch(expr) if expr in by_expr else None
        if match is not None:
            wanted = {name.strip() for name in match.group(1).split(",")}
            for labels, value in families.get(match.group(2), []):
                if set(labels) == wanted:
                    result.append(
                        {"metric": labels, "value": [RECORDED_AT.timestamp(), repr(value)]}
                    )
        body = {"status": "success", "data": {"resultType": "vector", "result": result}}
        return httpx.Response(200, json=body)

    return PromClient(base_url="http://prometheus.recorded", transport=httpx.MockTransport(handler))


def seeded_store() -> RedisReleaseFreezeStore:
    store = RedisReleaseFreezeStore(fakeredis.FakeRedis())
    store.write(
        DeployFreeze(
            engaged=True,
            revision=1,
            changed_at=RECORDED_AT - timedelta(minutes=20),
            changed_by="kc-sub-sre-oncall",
            last_change=DeployFreezeChange.ENGAGE,
            reason_class=FlagChangeReason.INCIDENT_MITIGATION.value,
        ),
        expected_revision=0,
    )
    return store


def seeded_pending() -> tuple[PendingAction, ...]:
    created = RECORDED_AT - timedelta(minutes=4)
    return (
        PendingAction(
            id="01jbq0cicdrecordedlift00001",
            action=DEPLOY_FREEZE_LIFT,
            actor=ActorBlock(
                subject="kc-sub-platform-admin",
                role=AdminRole.PLATFORM_ADMIN,
                org="org:intake",
                authenticator_aaguid="aaguid-recorded-1",
                credential_id="cred-recorded-1",
                session_id="sid-recorded-1",
            ),
            target_ref="release:deploy-freeze",
            justification=build_flag_change_justification(
                reason_class=FlagChangeReason.INCIDENT_MITIGATION,
                free_text="Recorded request: the api fix is verified on staging.",
            ),
            evidence={"control": "freeze_lift", "base_revision": "1"},
            created_at=created,
            expires_at=created + timedelta(minutes=15),
            state=PendingActionState.PENDING,
            approver=None,
            assertion_id=None,
        ),
    )


def _stamped() -> VersionInfo:
    head = str(_load("branch_main")["commit"]["sha"])
    digest = hashlib.sha256(b"recorded-sbom:" + head.encode("ascii")).hexdigest()
    return VersionInfo(
        git_sha=head,
        built_at=RECORDED_AT.strftime("%Y-%m-%dT%H:%M:%SZ"),
        sbom_digest=f"sha256:{digest}",
    )


def record(*, configured: bool) -> dict[str, Any]:
    """The composite over the recorded inputs, or over none at all."""
    if configured:
        return build_cicd_console(
            prom=recorded_prometheus(),
            slo_files=load_slo_files(SLO_DIR),
            freeze_store=seeded_store(),
            pending=seeded_pending(),
            version=_stamped(),
            environment="staging",
            now=RECORDED_AT,
        )
    return build_cicd_console(
        prom=None,
        slo_files=load_slo_files(SLO_DIR),
        freeze_store=None,
        pending=(),
        version=VersionInfo(git_sha="dev", built_at="dev", sbom_digest="dev"),
        environment="dev",
        now=RECORDED_AT,
    )


def _write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def main() -> int:
    _write("cicd.payload.json", record(configured=True))
    _write("cicd.unconfigured.payload.json", record(configured=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
