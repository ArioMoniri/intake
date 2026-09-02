"""``acoustic`` is unreachable outside a registered clinical investigation.

CLAUDE.md invariant 11, second sentence: *"``acoustic`` is unreachable unless
{study_id, protocol_version, ICF_version, approval_date} all assert, and fails
closed on protocol amendment."* files/03 §4.7.4 states why in one line —
*"outside the investigation the module is genuinely unreachable, not merely
unrendered"* — and files/10 §9.1 catalogues it as invariant 23 against TCKAY
m.11, which makes an amendment a **fresh submission**.

**The ethics ids come from the registry INT-230 already built**
(:mod:`intake_platform.research.studies`), not from a second register declared
here. That registry is the single place a study becomes real: it enforces the
approval window with **no grace day** (files/10 §9 invariant 35), refuses an
unknown study, and holds the protocol version the approval was granted
against. This module adds the three checks the acoustic gate needs on top:
the assertion's ``protocol_version`` and ``approval_date`` must be the
registered ones, and its ``icf_version`` must be one the registry vouches for.

**Today the gate refuses every assertion, twice over, and both refusals are
the correct outcome:**

1. ``study_registry.yaml`` holds no study — HB-L1 (the qualifying site is not
   named, so no KAEK submission has been made) and HB-R1 (the ethics decision
   and its ids do not exist). :class:`UnknownStudyError` fires before anything
   else is read.
2. ``StudyRecord`` carries no ``icf_version``. files/08 §3 specifies
   ``ICF_version`` as a field of the study-registry record; INT-230's record
   omits it because a research *export* never needed it. So the ICF version an
   assertion carries is claimed rather than vouched for, and the gate refuses
   with :class:`IcfVersionUnrecordedError`. :func:`_recorded_icf_version` reads
   the field through the model's own field set, so the day the registry gains
   it the check starts comparing with no edit here — which is the honest shape
   for a value that belongs in someone else's module.

There is **no shadow mode** (files/03 §4.7.4) and no ``dev_only`` bypass: a
refused assertion means the lane is not built, not that its output is hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from intake_platform.research import STUDY_FIELD_SHAPE, StudyRecord, StudyRegistry

__all__ = [
    "AcousticAdmission",
    "AcousticAssertion",
    "ApprovalDateMismatchError",
    "IcfVersionUnrecordedError",
    "ProtocolAmendedError",
    "StudyAssertionRefused",
    "admit_acoustic",
]


class StudyAssertionRefused(ValueError):
    """The four values did not all assert. Subclasses name which one failed."""


class ProtocolAmendedError(StudyAssertionRefused):
    """The registered protocol version is not the asserted one.

    TCKAY m.11: an amendment is a fresh submission, so an assertion written
    against the previous protocol is not stale — it is unapproved.
    """


class ApprovalDateMismatchError(StudyAssertionRefused):
    """The asserted ``approval_date`` is not the registered one."""


class IcfVersionUnrecordedError(StudyAssertionRefused):
    """The registry cannot vouch for the asserted ICF version."""


@dataclass(frozen=True, slots=True)
class AcousticAssertion:
    """The four values invariant 11 requires. All required, none defaulted.

    A default here would be an assertion nobody made, which is the failure
    files/08 §3 describes: *"if they are config, then whoever edits the deploy
    config mints a clinical investigation"*.
    """

    study_id: str
    protocol_version: str
    icf_version: str
    approval_date: date

    def __post_init__(self) -> None:
        for field_name in ("study_id", "protocol_version", "icf_version"):
            value = getattr(self, field_name)
            if STUDY_FIELD_SHAPE.fullmatch(value) is None:
                # the refused value is never echoed (invariant 6)
                raise StudyAssertionRefused(
                    f"acoustic assertion field {field_name!r} must be id-shaped "
                    "([A-Za-z0-9._:-], ≤64)"
                )


@dataclass(frozen=True, slots=True)
class AcousticAdmission:
    """Proof that a registered investigation admits this session's M3 module.

    :func:`admit_acoustic` is the only thing that builds one from a registry,
    so the runtime cannot construct the acoustic lane from an assertion alone.
    """

    study_id: str
    protocol_version: str
    icf_version: str
    approval_date: date


def _recorded_icf_version(record: StudyRecord) -> str | None:
    """The ICF version the registry vouches for, or ``None`` when it holds none.

    Read through ``model_fields`` rather than assumed: files/08 §3 puts
    ``ICF_version`` on the study-registry record, INT-230's record does not
    carry it yet, and adding it is that registry's change to make. Until then
    this returns ``None`` and the gate refuses.
    """
    if "icf_version" not in type(record).model_fields:
        return None
    value = getattr(record, "icf_version", None)
    # A field of another type is not an ICF version either: the register has to
    # vouch for the string the assertion carries, not for something adjacent.
    return value if isinstance(value, str) else None


def admit_acoustic(
    assertion: AcousticAssertion, *, registry: StudyRegistry, on: date
) -> AcousticAdmission:
    """Resolve the assertion against the registry, or refuse naming which gate closed.

    :param on: keyword-only, no default. An approval window is only meaningful
        against a date, and a default would let a caller ask without saying
        when — the same rule :meth:`StudyRegistry.resolve` already applies.
    """
    record = registry.resolve(assertion.study_id, on=on)
    if assertion.approval_date != record.approval_date:
        raise ApprovalDateMismatchError(
            f"study {assertion.study_id!r} was approved on "
            f"{record.approval_date.isoformat()}; the assertion says otherwise"
        )
    if assertion.protocol_version != record.protocol_version:
        raise ProtocolAmendedError(
            f"study {assertion.study_id!r} is registered against protocol "
            f"{record.protocol_version!r}; TCKAY m.11 makes an amendment a fresh "
            "submission, so an assertion against another version is unapproved"
        )
    recorded_icf = _recorded_icf_version(record)
    if recorded_icf is None or recorded_icf != assertion.icf_version:
        raise IcfVersionUnrecordedError(
            f"the registry records no ICF version for study {assertion.study_id!r} that "
            "matches this assertion; an ICF version the register cannot vouch for is "
            "claimed, not asserted (files/08 §3)"
        )
    return AcousticAdmission(
        study_id=record.study_id,
        protocol_version=record.protocol_version,
        icf_version=recorded_icf,
        approval_date=record.approval_date,
    )
