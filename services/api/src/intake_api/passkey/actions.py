"""The actions a passkey step-up opens (INT-582).

D36 (owner, 28 Oct 2026) names four: issuing a Doctor Link, changing the
phone number, data export and data delete. Three more belong to the mechanism
itself and are not D36 actions: adding a passkey while one is active,
removing a passkey, and cancelling a recovery somebody started from the OTP
tier. Without them an attacker holding only the SMS (a SIM swap) could enrol
their own passkey beside the patient's (the security review's B1), remove the
patient's, or cancel its holder's objection, and walk through the four.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["D36_ACTIONS", "StepUpAction"]


class StepUpAction(StrEnum):
    DOCTOR_LINK_ISSUE = "doctor_link_issue"
    PHONE_CHANGE = "phone_change"
    DATA_EXPORT = "data_export"
    DATA_DELETE = "data_delete"
    PASSKEY_ADD = "passkey_add"
    PASSKEY_REMOVE = "passkey_remove"
    RECOVERY_CANCEL = "recovery_cancel"


D36_ACTIONS: frozenset[StepUpAction] = frozenset(
    {
        StepUpAction.DOCTOR_LINK_ISSUE,
        StepUpAction.PHONE_CHANGE,
        StepUpAction.DATA_EXPORT,
        StepUpAction.DATA_DELETE,
    }
)
