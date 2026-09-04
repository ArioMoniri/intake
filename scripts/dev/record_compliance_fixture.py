"""Record apps/admin-web/e2e/fixtures/compliance.payload.json from the API.

INT-189. The admin-web compliance module renders the five `/admin/compliance/*`
bodies; this records them into one composite fixture so the vitest spec asserts
against what the API actually serves rather than a hand mock. Re-run when the
served shape changes: `python scripts/dev/record_compliance_fixture.py`.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from admin_harness import bearer, build_admin_harness
from intake_platform.egress import DataClass, EgressPurpose, TransferRecord

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "compliance.payload.json"


def _feed() -> tuple[TransferRecord, ...]:
    return (
        TransferRecord(
            ts=datetime(2026, 9, 1, 9, tzinfo=UTC),
            host="pypi.org",
            port=443,
            purpose=EgressPurpose.PACKAGE_REGISTRY,
            data_class=DataClass.NON_PERSONAL,
            bytes_out=2048,
            decision="allow",
            reason="ok",
            tier="dev",
        ),
        TransferRecord(
            ts=datetime(2026, 9, 2, 11, tzinfo=UTC),
            host="github.com",
            port=443,
            purpose=EgressPurpose.SOURCE_CONTROL,
            data_class=DataClass.NON_PERSONAL,
            bytes_out=8192,
            decision="allow",
            reason="ok",
            tier="dev",
        ),
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        harness_iter = build_admin_harness(Path(tmp))
        harness = next(harness_iter)
        try:
            harness.client.app.state.api.transfer_feed = _feed()  # type: ignore[attr-defined]
            headers = bearer("auditor")
            payload = {
                "vendor_register": harness.client.get(
                    "/admin/compliance/vendor-register", headers=headers
                ).json(),
                "consents": harness.client.get(
                    "/admin/compliance/consents", headers=headers
                ).json(),
                "audit_search": harness.client.get(
                    "/admin/compliance/audit-search", headers=headers
                ).json(),
                "dsar": harness.client.get("/admin/compliance/dsar", headers=headers).json(),
                "evidence": harness.client.get(
                    "/admin/compliance/evidence-export", headers=headers
                ).json(),
            }
        finally:
            harness_iter.close()
    FIXTURE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(REPO)}")


if __name__ == "__main__":
    main()
