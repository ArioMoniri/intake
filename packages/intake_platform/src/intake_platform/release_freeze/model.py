"""The deploy-freeze record (INT-187; files/08 §3 "CI/CD & releases", §8.2).

One record per deployment — the Redis the deployment's own API writes and its
own deploy path reads — holding whether deploys are frozen, who changed that
last, and who approved it when a second key was required.

**Asymmetric by construction** (files/08 §8.2). Freezing is the safe
direction: tier 1, one eligible key, no approver. Lifting is the direction
that lets changes reach patients again: tier 2, a distinct second human. The
record makes the asymmetry checkable after the fact — an engage never carries
an approver and a lift always does — and refuses any record that says
otherwise, so a hand-written key in Redis cannot claim a lift nobody approved.

**Never written means not frozen.** A deployment that has never frozen has no
record, and that is the normal state rather than a failure: absent a freeze,
deploys proceed. What is *not* the normal state — a record that is not JSON,
fails this model, or cannot be read — is a refusal in the store, and the deploy
path refuses on it (:mod:`.verdict`).

**Ids only** (invariant 6). Closed enumerations, an integer, a timestamp, two
staff subjects and a closed reason class. The change reason's free text never
enters the record; the four-eyes brief and the audit chain own it. Validation
errors hide their input (files/08 §0c F12).
"""

from __future__ import annotations

import enum
import re
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["DeployFreeze", "DeployFreezeChange"]

#: The staff-subject shape the console principal already enforces.
_SUBJECT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")
#: A closed reason class is a code, never prose.
_REASON_CLASS: Final = re.compile(r"^[a-z][a-z_]{0,63}$")


class DeployFreezeChange(enum.StrEnum):
    """Which way the freeze moved last — and the ``control`` label's domain."""

    ENGAGE = "freeze_engage"
    LIFT = "freeze_lift"


class DeployFreeze(BaseModel):
    """The deployment's freeze. Immutable; a change is a new revision."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    engaged: bool = False
    #: 0 is "never written". Every write moves it by exactly one, which is what
    #: a lift approval binds to (the approver approves the revision the brief
    #: showed them).
    revision: int = Field(default=0, ge=0, strict=True)
    changed_at: datetime | None = None
    changed_by: str | None = None
    approved_by: str | None = None
    last_change: DeployFreezeChange | None = None
    #: The INT-188 change-reason category the last change was filed under.
    reason_class: str | None = None

    @field_validator("changed_by", "approved_by")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        if value is not None and not _SUBJECT.fullmatch(value):
            raise ValueError("a staff subject is id-shaped")
        return value

    @field_validator("reason_class")
    @classmethod
    def _reason_class(cls, value: str | None) -> str | None:
        if value is not None and not _REASON_CLASS.fullmatch(value):
            raise ValueError("a reason class is a closed code")
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.revision == 0:
            written = (
                self.engaged,
                self.changed_at,
                self.changed_by,
                self.approved_by,
                self.last_change,
                self.reason_class,
            )
            if any(value not in (None, False) for value in written):
                raise ValueError("a record never written claims no state and no author")
            return self
        if None in (self.changed_at, self.changed_by, self.last_change, self.reason_class):
            raise ValueError("a written freeze names when, who, which way and why")
        if self.engaged is not (self.last_change is DeployFreezeChange.ENGAGE):
            raise ValueError("engaged exactly when the last change was an engage")
        if (self.approved_by is not None) is not (self.last_change is DeployFreezeChange.LIFT):
            raise ValueError("a lift always has a second key and an engage never does")
        return self

    @classmethod
    def unconfigured(cls) -> DeployFreeze:
        """What a deployment that never froze reads as: not frozen."""
        return cls()

    @property
    def configured(self) -> bool:
        return self.revision > 0
