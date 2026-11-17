"""One tick of the 60-day auto-disable (INT-366; files/08 §2.4; inv. 4, 6).

files/08 §2.4: "60-day auto-disable on no login." A tick reads every staff
account from Keycloak, and each enabled one whose last login — or, if it never
logged in, whose creation — is sixty days old or more is offboarded through
the same pipeline a person uses (:func:`intake_platform.admin.access.offboarding.offboard`):
Keycloak account disabled, sessions ended, OpenBao identity disabled and its
tokens revoked, every other console system listed for confirmation. Every step
is on the audit chain under this job's own actor id and the ``dormant_60d``
reason.

**It refuses before it disables anyone** when the realm does not keep sixty
days of LOGIN events. Keycloak stores no last-login field; the login history
*is* the events store, and an account whose last login has expired out of it
would otherwise look exactly like one that never logged in — and the job
would disable the whole realm. A tick that cannot tell is a refusal, never a
clean run.

Idempotent: a disabled account is not dormant, so running the job again the
same day finds nothing new.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from intake_platform.admin.access import IdentityWiring, LoginHistoryUnavailable
from intake_platform.admin.access.offboarding import (
    DORMANT_AFTER_DAYS,
    Offboarding,
    OffboardingReason,
    StepOutcome,
    dormant_users,
    offboard,
)
from intake_platform.admin.audit import AdminAuditSink

__all__ = ["HYGIENE_ACTOR", "HygieneReport", "run_auto_disable"]

#: The job's audit actor. A service account never holds a console role
#: (files/08 §2.4); this id names the job on the chain and nothing more.
HYGIENE_ACTOR: Final = "svc:access-hygiene"


@dataclass(frozen=True)
class HygieneReport:
    login_history_days: float
    staff_accounts: int
    #: Subjects found dormant — disabled, or in a dry run, that would be.
    disabled: tuple[str, ...]
    offboardings: tuple[Offboarding, ...]
    dry_run: bool

    @property
    def ok(self) -> bool:
        """No step failed. Manual steps pending confirmation are expected."""
        return all(
            step.outcome is not StepOutcome.FAILED
            for result in self.offboardings
            for step in result.steps
        )


async def run_auto_disable(
    identity: IdentityWiring,
    sink: AdminAuditSink | None,
    *,
    now: datetime,
    dry_run: bool = False,
) -> HygieneReport:
    """Offboard every staff account with no login for sixty days at ``now``."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be tz-aware; a naive instant is not an instant")
    kept = await asyncio.to_thread(identity.directory.login_history_days)
    if kept < DORMANT_AFTER_DAYS:
        raise LoginHistoryUnavailable(
            "the realm keeps fewer days of LOGIN events than the dormancy window"
        )
    users = await asyncio.to_thread(identity.directory.staff_users)
    dormant = tuple(user.subject for user in dormant_users(users, now=now))
    if dry_run:
        return HygieneReport(kept, len(users), dormant, (), dry_run=True)
    if sink is None:
        raise ValueError("a run that disables accounts needs the audit chain")
    results: list[Offboarding] = []
    for subject in dormant:
        results.append(
            await offboard(
                subject=subject,
                reason=OffboardingReason.DORMANT,
                actor=HYGIENE_ACTOR,
                directory=identity.directory,
                leases=identity.leases,
                systems=identity.systems,
                adapters=identity.adapters,
                sink=sink,
                trigger="dormant",
            )
        )
    return HygieneReport(kept, len(users), dormant, tuple(results), dry_run=False)
