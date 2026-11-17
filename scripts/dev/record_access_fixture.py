"""Record the bodies the admin-web access page renders (INT-366).

``apps/admin-web/e2e/access.spec.ts`` drives the page's server-side loader and
renders the page. As with ``record_voice_fixture.py`` and its siblings, the
``/admin/access/review`` body is produced by the shipped code — the Keycloak
adapter (``KeycloakAdminDirectory``), the review generator and the route's own
view (``intake_api.admin.access_console.review_view``) — never hand-written in
TypeScript. ``tests/admin/test_access_review.py`` holds the committed files
equal to :func:`record`, so a drift fails there.

The inputs, all synthetic and all named here:

- **Keycloak** — the recorded realm in
  ``tests/admin/fixtures/keycloak_admin_realm.json``, answered by the test
  suite's fake admin server at the recorded instant (no Keycloak runs here).
- **The audit chain** — rows built below: both console sections countersigned
  40 days before the instant, tenant-a's clinician section 120 days before (so
  it shows overdue), two console actions, and one offboarding whose three
  manual steps are still open (the departed clinical lead, whose account the
  recorded realm already shows disabled).

Run: ``uv run python scripts/dev/record_access_fixture.py`` (also ``make
admin-fixtures``).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
# the fake Keycloak server lives with the suite that owns it (mocks live in
# tests only); the adapter it answers is the production one
sys.path.insert(0, str(REPO / "tests" / "admin"))

from access_fakes import FakeKeycloak, committed_systems  # noqa: E402
from intake_api.admin.access_console import review_view  # noqa: E402
from intake_platform.admin.access.offboarding import offboardings_from  # noqa: E402
from intake_platform.admin.access.review import (  # noqa: E402
    SIGNED_ACTION,
    ReviewLedger,
    generate_review,
    last_console_actions,
    signed_resource_ref,
)
from intake_platform.audit import AuditEntry  # noqa: E402

#: The instant the realm fixture was recorded at.
RECORDED_AT = datetime(2026, 9, 27, tzinfo=UTC)
_OFFBOARDING = "9f3c2a1be4d54c7a8e6b0d1f2a3b4c5d"
_DIGEST = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def _row(seq: int, days_ago: float, actor: str, action: str, ref: str) -> AuditEntry:
    return AuditEntry(
        seq=seq,
        timestamp_utc=(RECORDED_AT - timedelta(days=days_ago)).isoformat(),
        actor=actor,
        action=action,
        resource_ref=ref,
        consent_scope_ref="basis:KVKK-12",
        prev_hash="0" * 64,
        entry_hash="0" * 64,
    )


def _chain(*, reviewed: bool) -> list[AuditEntry]:
    ref = f"offboarding:{_OFFBOARDING}:kc-sub-clinical-lead"
    rows = [
        _row(1, 3, "kc-sub-compliance-officer", "admin.whoami.read.success", "admin_action:a:b"),
        _row(2, 1, "kc-sub-platform-owner", "admin.models.read.success", "admin_action:c:d"),
        _row(
            3,
            120,
            "kc-sub-qms-owner",
            SIGNED_ACTION,
            signed_resource_ref("clinicians:tenant-a", _DIGEST),
        ),
        _row(4, 0.5, "kc-sub-compliance-officer", "admin.offboarding.opened.departure", ref),
    ]
    for offset, system in enumerate(("keycloak_account", "keycloak_sessions", "openbao_leases")):
        rows.append(
            _row(
                5 + offset,
                0.5,
                "kc-sub-compliance-officer",
                f"admin.offboarding.{system}.revoked",
                ref,
            )
        )
    for offset, system in enumerate(("grafana", "langfuse", "unleash")):
        rows.append(
            _row(
                8 + offset,
                0.5,
                "kc-sub-compliance-officer",
                f"admin.offboarding.{system}.manual_pending",
                ref,
            )
        )
    if reviewed:
        for offset, section in enumerate(("platform_owner", "console_roles")):
            rows.append(
                _row(
                    11 + offset,
                    40,
                    "kc-sub-qms-owner-ext",
                    SIGNED_ACTION,
                    signed_resource_ref(section, _DIGEST),
                )
            )
    return rows


def record(*, reviewed: bool) -> dict[str, Any]:
    users = FakeKeycloak(RECORDED_AT).directory().staff_users()
    entries = _chain(reviewed=reviewed)
    ledger = ReviewLedger(clock=lambda: RECORDED_AT)
    ledger.load(entries)
    review = generate_review(users, ledger, last_console_actions(entries), now=RECORDED_AT)
    pending = [
        item
        for item in offboardings_from(entries, committed_systems()).values()
        if not item.complete
    ]
    return review_view(review, pending)


FIXTURES = {
    "access.payload.json": {"reviewed": True},
    "access.lapsed.payload.json": {"reviewed": False},
}


def main() -> None:
    for name, kwargs in FIXTURES.items():
        body = record(**kwargs)
        (OUT / name).write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
