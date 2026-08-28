"""Shared helpers for the legal-lane suites (INT-038) — uniquely named so
test modules import it directly (the api_harness precedent).

Consent-text fixtures are synthetic test copy only, never real consent
language: real texts are authored by humans into docs/legal (INT-210) and
this module exists precisely to keep that boundary testable.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR / "api") not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR / "api"))

from api_harness import ApiHarness, run  # noqa: E402 — needs the path shim above
from intake_api.db import tenant_session  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_api.state import ApiState  # noqa: E402
from intake_platform.consent import grant_consent, purpose_ids, text_filename  # noqa: E402

FIXTURE_VERSION = "2026-08-27.1"
FIXTURE_BODY_TR = (
    "Sentetik test fikstürü metni (INT-038). Gerçek rıza metni docs/legal "
    "altına INT-210 ile gelir; bu satırlar yalnızca hash bağlamayı test eder."
)

# The scopes the dev-tier API slice checks today (dev_fixture.DEV_CONSENT_SCOPES).
BOUND_SCOPES = ("core", "documents", "share:previsit_note")


def write_consent_text(
    root: Path, purpose: str, *, version: str = FIXTURE_VERSION, body: str = FIXTURE_BODY_TR
) -> Path:
    """One consent-text file in the loader's contract shape (front matter
    carrying ``consent_text_version``, then the shown copy)."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / text_filename(purpose)
    path.write_text(
        f"---\nconsent_text_version: {version}\n---\n{body}\n",
        encoding="utf-8",
    )
    return path


def write_all_consent_texts(root: Path, *, version: str = FIXTURE_VERSION) -> Path:
    for purpose in purpose_ids():
        write_consent_text(root, purpose, version=version)
    return root


def api_state(harness: ApiHarness) -> ApiState:
    state = harness.client.app.state.api  # type: ignore[attr-defined]
    assert isinstance(state, ApiState)
    return state


def grant_bound(
    harness: ApiHarness,
    *scopes: str,
    patient_id: uuid.UUID = DEV_PATIENT_ID,
    channel: str = "app",
) -> None:
    """Grant hash-bound consents through the real service path (catalog +
    audit chain), as the mobile UI will once INT-131/INT-210 land."""
    state = api_state(harness)

    async def _grant() -> None:
        async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
            for scope in scopes:
                await grant_consent(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    patient_id=patient_id,
                    scope=scope,
                    channel=channel,
                    evidence_ref=f"evidence:test/{scope.replace(':', '.')}",
                    catalog=state.consent_catalog,
                    audit=state.audit,
                    actor="dev-patient",
                )

    run(_grant())
