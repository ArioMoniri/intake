"""INT-230 — the study registry: which research a study is, and until when.

files/06 §75 (ETİK row) states the contract in one line: *"All research
consented (`research`) or anonymised per KSVY-16; **ethics IDs recorded on
every export**."* An ethics id is not a string a caller may pass in; it is a
property of a **registered** study, and a study is registered only when every
field a regulator would ask for exists — the committee that decided, the
decision id, the dates it is valid between, the protocol version it was
approved against, the site, and the closed list of people the extract may go
to.

**No grace period.** files/10 §9 records the failure mode plainly: a stale
study assertion outliving its approval is the *default* outcome rather than
an attack (invariant 35). So :meth:`StudyRegistry.resolve` takes the date it
is being asked about and refuses on either side of the approval window — the
day after ``approval_valid_until`` refuses exactly as an unregistered study
does. TCKAY m.11 makes an amendment a fresh submission, which is why
``protocol_version`` is part of the record and lands in the register: an
extract can be tied to the protocol version that was approved when it was
taken.

**The shipped registry is empty, and that is the deliverable.** No study
exists: HB-L1 has not named the qualifying site, so no KAEK submission has
been made and no approval id has been issued. Nothing here invents one
(HUMAN_BLOCKERS.md rule 1), and the export gate therefore refuses every
request today (rule 2: build the mechanism, wire the gate, make it fail
closed, leave the content empty).
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "STUDY_FIELD_SHAPE",
    "StudyApprovalLapsedError",
    "StudyApprovalNotYetInForceError",
    "StudyRecord",
    "StudyRegistry",
    "StudyRegistryError",
    "StudyRegistryRefusal",
    "UnknownStudyError",
    "default_registry_path",
    "load_default_registry",
    "load_registry",
]

#: Registry fields are identifiers, never prose: a committee decision id, a
#: site id, a recipient id. Same conservative alphabet the audit chain and the
#: analytics gate use, so a registry value can travel into an audit ref and a
#: register row without a second shape rule to keep in step.
STUDY_FIELD_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


class StudyRegistryError(ValueError):
    """A registry document that must not load."""


class StudyRegistryRefusal(LookupError):
    """The registry declined to resolve a study. Subclasses name why."""


class UnknownStudyError(StudyRegistryRefusal):
    """No such study is registered. Today this is every study."""


class StudyApprovalNotYetInForceError(StudyRegistryRefusal):
    """The approval exists but its start date has not arrived."""


class StudyApprovalLapsedError(StudyRegistryRefusal):
    """The approval's validity ended. There is no grace day (invariant 35)."""


def _id_shaped(value: str, *, field: str) -> str:
    if STUDY_FIELD_SHAPE.fullmatch(value) is None:
        # The refused value is not echoed: registry documents are authored by
        # humans and a paste error is exactly how prose reaches a log (inv. 6).
        raise ValueError(f"study registry field {field!r} must be id-shaped ([A-Za-z0-9._:-], ≤64)")
    return value


class StudyRecord(BaseModel):
    """One registered study. Every field is required and none has a default:
    a study missing its ethics decision id is not a study with a blank field,
    it is not a registered study."""

    # hide_input_in_errors is not cosmetic: pydantic's default ValidationError
    # text carries `input_value=<the refused value>`, so a paste error in the
    # registry — a whole consent sentence typed into `site`, a patient
    # identifier into `study_id` — would reach a traceback and a log verbatim
    # (invariant 6). Our own validators are careful not to echo; without this
    # the wrapper undoes that care.
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    study_id: str
    site: str
    ethics_committee: str
    ethics_approval_id: str
    approval_date: date
    approval_valid_until: date
    protocol_version: str
    #: The closed list of parties an extract under this study may go to. An
    #: empty list would be an open-ended transfer, so the minimum is one.
    recipients: tuple[str, ...] = Field(min_length=1)

    @field_validator(
        "study_id",
        "site",
        "ethics_committee",
        "ethics_approval_id",
        "protocol_version",
        mode="after",
    )
    @classmethod
    def _fields_are_id_shaped(cls, value: str, info: Any) -> str:
        return _id_shaped(value, field=str(info.field_name))

    @field_validator("recipients", mode="after")
    @classmethod
    def _recipients_are_id_shaped(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for recipient in value:
            _id_shaped(recipient, field="recipients")
        return value

    @model_validator(mode="after")
    def _window_moves_forward(self) -> StudyRecord:
        if self.approval_valid_until < self.approval_date:
            raise ValueError("approval_valid_until must not precede approval_date")
        return self

    def approves(self, recipient: str) -> bool:
        return recipient in self.recipients


class StudyRegistry(BaseModel):
    """The closed set of studies an extract may be taken for."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    studies: tuple[StudyRecord, ...] = ()

    @model_validator(mode="after")
    def _ids_are_unique(self) -> StudyRegistry:
        ids = [study.study_id for study in self.studies]
        if len(ids) != len(set(ids)):
            raise ValueError("study_id must be unique within the registry")
        return self

    def resolve(self, study_id: str, *, on: date) -> StudyRecord:
        """The registered study, or a refusal naming which gate closed.

        :param on: keyword-only, no default — an approval window is only
            meaningful against a date, and a default would let a caller ask
            the question without stating when it is being asked.
        """
        for study in self.studies:
            if study.study_id != study_id:
                continue
            if on < study.approval_date:
                raise StudyApprovalNotYetInForceError(
                    f"study {study_id!r} is approved from {study.approval_date.isoformat()}"
                )
            if on > study.approval_valid_until:
                raise StudyApprovalLapsedError(
                    f"study {study_id!r} approval ended "
                    f"{study.approval_valid_until.isoformat()}; there is no grace period "
                    "(files/10 §9, invariant 35)"
                )
            return study
        raise UnknownStudyError(
            f"no study {study_id!r} in the registry; an ethics approval is recorded by a "
            "human into study_registry.yaml, never asserted by a caller"
        )


def default_registry_path() -> Path:
    """The packaged registry file, beside this module."""
    return Path(__file__).with_name("study_registry.yaml")


def load_registry(path: Path) -> StudyRegistry:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise StudyRegistryError(f"{path} is not a mapping document")
    return StudyRegistry.model_validate(loaded)


@lru_cache(maxsize=1)
def load_default_registry() -> StudyRegistry:
    """The shipped registry, parsed once — the models are frozen, so the
    cached instance is safe to share."""
    return load_registry(default_registry_path())
