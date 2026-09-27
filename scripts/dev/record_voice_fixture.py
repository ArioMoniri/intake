"""Record the responses the admin-web Voice page renders (INT-182).

``apps/admin-web/e2e/voice.spec.ts`` drives the page's server-side loader and
renders the page. As with ``record_ops_fixture.py`` and its siblings, the
``/admin/voice`` body is produced by the shipped composite
(``intake_api.admin.voice_console.build_voice_console``), never hand-written
in TypeScript — a hand-kept copy keeps passing on the day the composite
changes. ``tests/admin/test_voice_console.py`` holds the committed files equal
to :func:`record`, so a drift fails there.

The inputs, all synthetic and all named here:

- **Prometheus** — the constructed answers in
  ``tests/fixtures/voice/prometheus_responses.json`` (no Prometheus runs on
  this host; container runtimes are CI-only). Its two latency answers are
  empty on purpose: nothing emits ``voice.round_trip_ms`` yet, so the recorded
  page shows that tile unknown rather than a number nobody measured.
- **The control store** — the shipped ``RedisVoiceControlStore`` over an
  in-memory Redis server, seeded with three synthetic tenants: one with the
  kill switch engaged, one on voice, one typed with a voice canary.
- **The four-eyes service** — one pending default-profile switch.

Run: ``uv run python scripts/dev/record_voice_fixture.py`` (also ``make
admin-fixtures``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import httpx
from intake_api.admin.ops_prom import PromClient
from intake_api.admin.voice_console import VOICE_QUERIES, build_voice_console
from intake_platform.admin.actions import VOICE_PROFILE_SWITCH
from intake_platform.admin.flag_governance import FlagChangeReason, build_flag_change_justification
from intake_platform.admin.four_eyes import ActorBlock, PendingAction, PendingActionState
from intake_platform.admin.roles import AdminRole
from intake_platform.voice_control import RedisVoiceControlStore, TenantVoiceControl

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
PROM_ANSWERS = REPO / "tests" / "fixtures" / "voice" / "prometheus_responses.json"
#: The instant the recorded Prometheus answers were taken at (INT-351's).
RECORDED_AT = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)

SEEDED: tuple[dict[str, Any], ...] = (
    {
        "tenant_id": "tenant-a",
        "revision": 3,
        "kill_switch": True,
        "default_profile": "residency_tr",
        "changed_at": "2026-09-26T15:42:00+00:00",
        "changed_by": "kc-sub-sre-oncall-1",
        "last_change": "kill_switch_engage",
    },
    {
        "tenant_id": "tenant-b",
        "revision": 2,
        "default_profile": "residency_tr",
        "changed_at": "2026-09-25T09:10:00+00:00",
        "changed_by": "kc-sub-clinical-lead-1",
        "approved_by": "kc-sub-qms-owner-1",
        "last_change": "default_profile",
    },
    {
        "tenant_id": "tenant-c",
        "revision": 1,
        "default_profile": "typed",
        "canary_profile": "residency_tr",
        "canary_weight": 10,
        "changed_at": "2026-09-26T08:00:00+00:00",
        "changed_by": "kc-sub-platform-owner-1",
        "approved_by": "kc-sub-clinical-lead-2",
        "last_change": "canary",
    },
)


def recorded_prometheus() -> PromClient:
    answers: dict[str, Any] = json.loads(PROM_ANSWERS.read_text(encoding="utf-8"))
    by_expr = {expr: query_id for query_id, expr in VOICE_QUERIES.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers[by_expr[request.url.params["query"]]])

    return PromClient(base_url="http://prometheus.recorded", transport=httpx.MockTransport(handler))


def seeded_store() -> RedisVoiceControlStore:
    client = fakeredis.FakeRedis()
    store = RedisVoiceControlStore(client)
    for row in SEEDED:
        control = TenantVoiceControl.model_validate(row)
        # a recorded state, not a history: one record at the recorded revision
        client.set(store.key(control.tenant_id), control.model_dump_json())
    return store


def seeded_pending() -> tuple[PendingAction, ...]:
    created = RECORDED_AT - timedelta(minutes=4)
    return (
        PendingAction(
            id="01jbq0voicerecordedprofile01",
            action=VOICE_PROFILE_SWITCH,
            actor=ActorBlock(
                subject="kc-sub-clinical-lead-1",
                role=AdminRole.CLINICAL_LEAD,
                org="org:intake",
                authenticator_aaguid="aaguid-recorded-1",
                credential_id="cred-recorded-1",
                session_id="sid-recorded-1",
            ),
            target_ref="voice:tenant-d",
            justification=build_flag_change_justification(
                reason_class=FlagChangeReason.ROLLOUT_EXPANSION,
                free_text="Recorded request: pilot clinic dry run signed off.",
            ),
            evidence={
                "tenant": "tenant-d",
                "base_revision": "0",
                "control": "default_profile",
                "profile": "residency_tr",
            },
            created_at=created,
            expires_at=created + timedelta(minutes=15),
            state=PendingActionState.PENDING,
            approver=None,
            assertion_id=None,
        ),
    )


def record(*, configured: bool) -> dict[str, Any]:
    """The composite over the recorded inputs, or over none at all."""
    if configured:
        return build_voice_console(
            prom=recorded_prometheus(),
            controls=seeded_store(),
            pending=seeded_pending(),
            now=RECORDED_AT,
        )
    return build_voice_console(prom=None, controls=None, pending=(), now=RECORDED_AT)


def _write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def main() -> int:
    _write("voice.payload.json", record(configured=True))
    _write("voice.unconfigured.payload.json", record(configured=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
