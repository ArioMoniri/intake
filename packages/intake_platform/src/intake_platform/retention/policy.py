"""Retention policy as code (INT-036; files/06 §3; KVKK-7, DEST-2017).

The policy file (``retention_policy.yaml``, packaged beside this module) is
the files/06 §3 retention matrix in machine-readable form: one class per
matrix row, each carrying its verbatim citation. This loader is the gate that
keeps three properties true no matter what the file says:

- **no audio retention class exists** — invariant 3 says raw audio is never
  persisted, so the strongest retention statement is that there is nothing to
  retain: a ``classes`` entry whose name matches an audio pattern is refused
  (:class:`AudioRetentionClassError`), and the ``raw_audio: never_written``
  row must be present (:class:`RawAudioRowMissingError`). This is the policy
  half of ``audio_no_write_guard`` (files/10 §9.1 inv. 27).
- **the audit chain and the destruction log are not destroyable** — a
  ``classes`` entry naming them is refused (:class:`ProtectedClassError`),
  and :class:`DestroyableClass` cannot express them, so no executor can be
  routed to them (type-level, files/10 §2 WORM).
- **no invented durations** — a class 06 §3 leaves without a duration is
  ``draft_needs_source`` with ``kind: unspecified``; the schema refuses a
  draft row carrying a number and a sourced row carrying none, and the
  planner refuses to schedule a draft row (fail closed).
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AudioRetentionClassError",
    "ClassStatus",
    "DestroyableClass",
    "DestructionLogSpec",
    "NonPersistedRow",
    "PeriodicDestructionSpec",
    "PolicyClass",
    "PolicyClassMismatchError",
    "ProtectedClassError",
    "ProtectedRow",
    "RawAudioRowMissingError",
    "RetentionKind",
    "RetentionPolicy",
    "RetentionPolicyError",
    "RetentionRule",
    "default_policy_path",
    "load_default_policy",
    "load_policy",
    "parse_policy",
]

#: Names that would make audio a retention class. Deliberately broad: a class
#: that merely sounds like it persists sound is refused and must be renamed
#: or, far more likely, must not exist (invariant 3).
_AUDIO_NAME = re.compile(r"audio|pcm|recording|waveform", re.IGNORECASE)

#: The classes no policy file may make destroyable, whatever it says.
PROTECTED_CLASS_NAMES = frozenset({"audit_chain", "audit_records", "destruction_log"})


class RetentionPolicyError(ValueError):
    """A policy file that must not load."""


class AudioRetentionClassError(RetentionPolicyError):
    """A retention class for audio — invariant 3 says there is nothing to retain."""


class ProtectedClassError(RetentionPolicyError):
    """A destroyable entry for the audit chain or the destruction log."""


class RawAudioRowMissingError(RetentionPolicyError):
    """The ``raw_audio: never_written`` row is the guard's positive half."""


class PolicyClassMismatchError(RetentionPolicyError):
    """Policy classes and :class:`DestroyableClass` drifted apart."""


class DestroyableClass(enum.StrEnum):
    """Every class this engine may ever destroy — and, by omission, the
    type-level statement that the audit chain, the destruction log and any
    audio store can never be destruction targets: an executor is routed by
    this enum, and the enum cannot name them."""

    CLINICAL_RECORD = "clinical_record"
    DOCTOR_LINK_TOKENS = "doctor_link_tokens"
    CONSENT_RECORDS_HOSPITAL_TENANT = "consent_records_hospital_tenant"
    CONSENT_RECORDS_CONSUMER_TENANT = "consent_records_consumer_tenant"
    TELEMETRY = "telemetry"
    TRAFFIC_LOGS_5651 = "traffic_logs_5651"
    SATISFACTION = "satisfaction"
    RESEARCH_EXTRACTS = "research_extracts"
    # INT-582 (legal B4): a passkey whose recovery cool-off has ended
    RECOVERED_PASSKEYS = "recovered_passkeys"


class RetentionKind(enum.StrEnum):
    LIFE_OF_RECORD = "life_of_record"
    EXPIRY = "expiry"
    YEARS = "years"
    WITH_ACCOUNT = "with_account"
    # INT-582: due when an event the inventory names has run its course — the
    # item carries the instant (expires_at); the class carries no number, the
    # code that defines the event does (a passkey recovery's cool-off)
    EVENT_CLOCK = "event_clock"
    UNSPECIFIED = "unspecified"


class ClassStatus(enum.StrEnum):
    SOURCED = "sourced"
    DRAFT_NEEDS_SOURCE = "draft_needs_source"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetentionRule(_Frozen):
    """The duration half of a class row. Numbers may exist exactly where the
    kind calls for them — a smuggled figure on a kind that takes none is as
    refused as a missing one."""

    kind: RetentionKind
    years: int | None = Field(default=None, ge=1)
    max_hours: int | None = Field(default=None, ge=1)
    hard_ceiling_years: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> RetentionRule:
        if self.kind is RetentionKind.YEARS:
            if self.years is None:
                raise ValueError("retention kind 'years' requires a years value (06 §3 row)")
            if self.hard_ceiling_years is not None and self.hard_ceiling_years < self.years:
                raise ValueError("hard_ceiling_years must be ≥ years")
        else:
            if self.years is not None or self.hard_ceiling_years is not None:
                raise ValueError(f"retention kind '{self.kind}' takes no years value")
        if self.kind is RetentionKind.EXPIRY:
            if self.max_hours is None:
                raise ValueError("retention kind 'expiry' requires max_hours (06 §3: ≤ 72 h)")
        elif self.max_hours is not None:
            raise ValueError(f"retention kind '{self.kind}' takes no max_hours value")
        return self


class PolicyClass(_Frozen):
    data_class: str
    basis: str
    retention: RetentionRule
    action: Literal["destroy", "crypto_shred", "anonymize"]
    destruction_path: Literal["periodic", "dsar_only"]
    dsar_erasable: bool
    status: ClassStatus
    source: str

    @model_validator(mode="after")
    def _draft_and_duration_are_exclusive(self) -> PolicyClass:
        unspecified = self.retention.kind is RetentionKind.UNSPECIFIED
        if self.status is ClassStatus.DRAFT_NEEDS_SOURCE:
            if not unspecified:
                raise ValueError(
                    f"class {self.data_class!r} is draft_needs_source but carries a "
                    "duration — a number on an unsourced row is an invented value "
                    "(CLAUDE.md: never invent a value)"
                )
            if self.dsar_erasable:
                raise ValueError(
                    f"class {self.data_class!r} is draft_needs_source and must fail "
                    "closed on every path, the DSAR path included"
                )
        elif unspecified:
            raise ValueError(
                f"class {self.data_class!r} is sourced yet its retention is "
                "unspecified — either cite the 06 §3 duration or mark the row "
                "draft_needs_source"
            )
        if (
            self.retention.kind is RetentionKind.LIFE_OF_RECORD
            and self.destruction_path != "dsar_only"
        ):
            raise ValueError(
                f"class {self.data_class!r}: life-of-record data is destroyed only "
                "via the targeted DSAR path (06 §3: patient-deletable)"
            )
        return self


class NonPersistedRow(_Frozen):
    data_class: str
    storage: Literal["never_written", "memory_only"]
    zeroing_triggers: tuple[str, ...] = ()
    source: str

    @model_validator(mode="after")
    def _triggers_match_storage(self) -> NonPersistedRow:
        if self.storage == "memory_only" and not self.zeroing_triggers:
            raise ValueError(
                f"{self.data_class!r} is memory_only and must name its zeroing "
                "triggers (06 §3 lane-window row)"
            )
        if self.storage == "never_written" and self.zeroing_triggers:
            raise ValueError(f"{self.data_class!r} is never written; nothing exists to zero")
        return self


class PeriodicDestructionSpec(_Frozen):
    # DEST-2017 (RG 30224): periodic destruction at intervals ≤ 6 months —
    # a longer interval is unlawful, so the schema caps it here.
    interval_months: int = Field(ge=1, le=6)
    legal: tuple[str, ...]


class DestructionLogSpec(_Frozen):
    # DEST-2017: destruction records kept ≥ 3 years — the schema floor.
    min_retention_years: int = Field(ge=3)
    carrier: Literal["audit_chain"]
    legal: tuple[str, ...]


class ProtectedRow(_Frozen):
    data_class: str
    reason: str
    retention_years: int | None = Field(default=None, ge=1)
    min_retention_years: int | None = Field(default=None, ge=1)


class RetentionPolicy(_Frozen):
    schema_version: Literal[1]
    source_document: str
    source_section: str
    periodic_destruction: PeriodicDestructionSpec
    destruction_log: DestructionLogSpec
    non_persisted: tuple[NonPersistedRow, ...]
    classes: tuple[PolicyClass, ...]
    protected: tuple[ProtectedRow, ...]

    def class_for(self, data_class: DestroyableClass) -> PolicyClass:
        for row in self.classes:
            if row.data_class == data_class.value:
                return row
        raise PolicyClassMismatchError(  # pragma: no cover — parse_policy pins the bijection
            f"no policy row for {data_class!r}"
        )


def parse_policy(raw: Mapping[str, Any]) -> RetentionPolicy:
    """Validate a policy document and run the three guards, in guard order:
    the audio guard first (it is the invariant), then the protected-class
    guard, then the policy↔type bijection."""
    policy = RetentionPolicy.model_validate(raw)
    for row in policy.classes:
        if _AUDIO_NAME.search(row.data_class):
            raise AudioRetentionClassError(
                f"{row.data_class!r} would make audio a retention class; invariant 3 "
                "says raw audio is never persisted, so there is nothing to retain "
                "and no row may exist (06 §3: 'Raw audio: never written')"
            )
    protected_names = PROTECTED_CLASS_NAMES | {row.data_class for row in policy.protected}
    for row in policy.classes:
        if row.data_class in protected_names:
            raise ProtectedClassError(
                f"{row.data_class!r} is not destroyable by this engine: an engine "
                "that can delete its own evidence is not producing evidence "
                "(DEST-2017 destruction records; files/10 §2 WORM audit)"
            )
    if not any(
        row.data_class == "raw_audio" and row.storage == "never_written"
        for row in policy.non_persisted
    ):
        raise RawAudioRowMissingError(
            "the policy must positively assert the 06 §3 'Raw audio: never written' "
            "row under non_persisted — its absence would silently drop the guard"
        )
    declared = {row.data_class for row in policy.classes}
    expected = {member.value for member in DestroyableClass}
    if declared != expected:
        raise PolicyClassMismatchError(
            "policy classes and DestroyableClass drifted apart: "
            f"missing {sorted(expected - declared)}, unexpected {sorted(declared - expected)}"
        )
    return policy


def default_policy_path() -> Path:
    """The packaged policy file, beside this module."""
    return Path(__file__).with_name("retention_policy.yaml")


def load_policy(path: Path) -> RetentionPolicy:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RetentionPolicyError(f"{path} is not a mapping document")
    return parse_policy(loaded)


@lru_cache(maxsize=1)
def load_default_policy() -> RetentionPolicy:
    """The shipped policy, parsed once — the models are frozen, so the cached
    instance is safe to share."""
    return load_policy(default_policy_path())
