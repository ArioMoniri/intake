"""INT-308 — the carrier/geo sanity check on the OTP request path.

files/10 §2 has always named *"carrier/geo sanity checks against SMS pumping"*
in the same sentence as the request budgets. INT-263 found that no code
honoured it and marked it named-but-unbuilt rather than letting the sentence
read as coverage. This module is the control; ``infra/security/msisdn_allocation.yaml``
is its authority, and that authority is empty.

**The two halves are in very different states, and conflating them is how a
spec starts lying again.**

*Geo* is enforced today and was before this module existed:
:func:`intake_api.otp.normalise_tr_phone` admits a Turkish mobile and nothing
else, so a premium or high-payout international range never reaches the
delivery adapter at all. That is the single most load-bearing anti-pumping
property this system has, it is a consequence of being a Turkish-only product,
and INT-308's contribution to it is a test that pins it rather than any new
code.

*Carrier* is wired and inert. The check derives the operator prefix of an
already-normalised ``+90`` number in memory and asks the authority whether that
prefix has been allocated to a mobile operator. The shipped authority declares
zero prefixes, so it answers "I cannot say" and every request is admitted. The
prefixes are a published BTK fact nobody here has read from the publication,
and writing them from memory is the invented value HUMAN_BLOCKERS rule 1
forbids — in the expensive direction, because a prefix wrongly recorded as
unallocated refuses every real subscriber behind it with a 422 that reads like
a typo. The ask is in ``docs/backlog/blockers.md``.

**The asymmetry is the whole design.** A lookup that cannot be made ADMITS; only
a positive signal REFUSES. Concretely: no authority, an unreadable table, an
authority that raises, an authority that times out, a prefix the authority has
no opinion about — all admit. The one refusal is a prefix positively absent
from a list that declares itself complete. A carrier check that failed closed
would lock a patient out of their own intake the first time a lookup timed out,
which is a worse failure than the cost it was meant to save.

**Nothing is persisted.** The prefix lives for the length of one request and is
discarded: it reaches no Redis key, no log line, no metric label and no audit
row (CLAUDE.md invariant 6). A carrier or country derivation is a fact about a
person, so the way not to owe it an inventory annotation is not to keep it.

**What is deliberately NOT here.** A live per-number lookup (HLR, number
portability) answers a stronger question, needs a contracted vendor, and sends
the patient's own number to a third party — a lawful-basis decision and a
licence question (CLAUDE.md invariant 19), not a configuration change. The
:class:`MsisdnAuthority` seam is deliberately narrower than that: it is handed a
country code and an operator prefix, never the subscriber number, so a vendor
that needs the whole MSISDN cannot be dropped in behind it without the
conversation that costs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

# pyyaml arrives with intake-platform, which is a direct dependency of this
# service (same route as intake_voice_runtime.adapters.pins).
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = [
    "CARRIER_GEO_ASK",
    "MSISDN_ALLOCATION_PATH",
    "AllocationSource",
    "AllocationTable",
    "AllocationTableAuthority",
    "CarrierGeoCheck",
    "CarrierGeoConfigError",
    "CarrierGeoOutcome",
    "CarrierGeoVerdict",
    "MsisdnAuthority",
    "carrier_geo_from_path",
    "load_allocation_table",
    "split_e164",
]

logger = logging.getLogger("intake_api.carrier_geo")

#: The committed authority, relative to the repo root (the taxonomy_path idiom).
MSISDN_ALLOCATION_PATH = Path("infra/security/msisdn_allocation.yaml")

CARRIER_GEO_ASK = (
    "infra/security/msisdn_allocation.yaml declares no allocated operator prefixes, so the "
    "carrier half of files/10 §2's SMS-pumping control admits every request and only the "
    "request budgets and the Turkish-mobile-only normalisation stand against pumping. Which "
    "5XX prefixes the BTK has allocated is a published fact nobody here has read from the "
    "publication, and a prefix wrongly recorded as unallocated refuses every real subscriber "
    "behind it. The ask is recorded in docs/backlog/blockers.md; its HUMAN_BLOCKERS row id is "
    "allocated by the coordinator."
)

#: The only numbering plan ``normalise_tr_phone`` admits. Written as a constant
#: rather than a slice index so that adding a second country is a decision about
#: that country's plan, not an off-by-one.
TR_COUNTRY_CODE = "90"
TR_NATIONAL_DIGITS = 10
TR_OPERATOR_PREFIX_LEN = 3


class CarrierGeoConfigError(Exception):
    """The allocation table could not be read or does not validate.

    Raised by :func:`load_allocation_table` and caught by
    :func:`carrier_geo_from_path`, which admits and says so — the config error
    is a lookup that cannot be made, and those admit.
    """


class CarrierGeoOutcome(StrEnum):
    ADMIT = "admit"
    REFUSE = "refuse"
    UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class CarrierGeoVerdict:
    """The check's answer. ``reason`` is a static code from a closed set —
    never a prefix, a carrier name, a country or anything from the number
    (invariant 6), so it is safe to log and safe to put in a test name."""

    outcome: CarrierGeoOutcome
    reason: str

    @property
    def refuses(self) -> bool:
        return self.outcome is CarrierGeoOutcome.REFUSE


class MsisdnAuthority(Protocol):
    """Whether a numbering-plan prefix has been allocated to a mobile operator.

    Three answers and a fourth by exception, and the caller's asymmetry rests
    on the distinction between the first two:

    * ``True``  — allocated. Admit.
    * ``False`` — POSITIVELY not allocated. This is the only refusal.
    * ``None``  — this authority has no opinion about that prefix. Admit.
    * raising   — a lookup failure, including a timeout. Admit.

    The subscriber number is never passed: an authority that needs it is a
    different control with its own lawful-basis question.
    """

    def allocated(self, *, country_code: str, operator_prefix: str) -> bool | None: ...


class AllocationSource(BaseModel):
    """Where the prefixes were read from, in the shape a red-flag rule's
    ``source`` block carries and for the same reason: a list nobody can re-read
    is a list somebody typed from memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority: str = Field(min_length=1)
    document: str = Field(min_length=1)
    published_on: str = Field(min_length=1)
    url: str = Field(min_length=1)
    retrieved_on: str = Field(min_length=1)


class AllocationTable(BaseModel):
    """``infra/security/msisdn_allocation.yaml``, validated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    country_code: str = Field(pattern=r"^[1-9][0-9]{0,2}$")
    #: Whether ``allocated_prefixes`` is the COMPLETE set for that plan. This
    #: one boolean is the entire difference between "absent, therefore
    #: positively unallocated, therefore refuse" and "absent, therefore
    #: unknown, therefore admit".
    exhaustive: bool
    allocated_prefixes: tuple[str, ...] = ()
    source: AllocationSource | None = None

    @model_validator(mode="after")
    def _prefixes_need_a_source(self) -> AllocationTable:
        if self.allocated_prefixes and self.source is None:
            raise ValueError(
                "allocated_prefixes without a source: which prefixes an authority has "
                "allocated is a published fact, and a list with nothing to re-read it "
                "against is the invented value HUMAN_BLOCKERS rule 1 forbids"
            )
        if len(set(self.allocated_prefixes)) != len(self.allocated_prefixes):
            raise ValueError("allocated_prefixes contains a duplicate")
        for prefix in self.allocated_prefixes:
            if not prefix.isdigit():
                raise ValueError(f"allocated prefix {prefix!r} is not a run of digits")
        return self

    @property
    def can_refuse(self) -> bool:
        """True only when this table is able to produce a positive signal at
        all. False is the shipping state and it is visible on purpose."""
        return self.exhaustive and bool(self.allocated_prefixes)


@dataclass(frozen=True, slots=True)
class AllocationTableAuthority:
    """The file-backed authority. No network, no vendor, no transfer."""

    table: AllocationTable

    def allocated(self, *, country_code: str, operator_prefix: str) -> bool | None:
        if country_code != self.table.country_code:
            return None
        if operator_prefix in self.table.allocated_prefixes:
            return True
        # Absent. Only a table that declares itself complete may turn that into
        # a positive "not allocated"; a partial list has no opinion.
        return False if self.table.can_refuse else None

    @property
    def can_refuse(self) -> bool:
        return self.table.can_refuse


def split_e164(phone_e164: str) -> tuple[str, str] | None:
    """``+905321114455`` → ``("90", "532")``; ``None`` when it is not a number
    of the one plan this check understands.

    ``None`` admits. The OTP path has already refused everything that is not a
    Turkish mobile, so reaching ``None`` here means the two definitions have
    drifted apart — and the safe direction when they have is to say nothing
    rather than to refuse on a parse this module got wrong.
    """
    prefix = f"+{TR_COUNTRY_CODE}"
    if not phone_e164.startswith(prefix):
        return None
    national = phone_e164[len(prefix) :]
    if len(national) != TR_NATIONAL_DIGITS or not national.isdigit():
        return None
    return TR_COUNTRY_CODE, national[:TR_OPERATOR_PREFIX_LEN]


@dataclass(frozen=True, slots=True)
class CarrierGeoCheck:
    """The control, as it sits on the OTP request path.

    Constructed with no authority by default, which admits everything — the
    correct state for any wiring that has not been given one, and the reason
    every existing test in the suite keeps passing unchanged.
    """

    authority: MsisdnAuthority | None = None

    def evaluate(self, phone_e164: str) -> CarrierGeoVerdict:
        split = split_e164(phone_e164)
        if split is None:
            return CarrierGeoVerdict(CarrierGeoOutcome.UNCHECKED, "unparsed_numbering_plan")
        if self.authority is None:
            return CarrierGeoVerdict(CarrierGeoOutcome.UNCHECKED, "no_authority")
        country_code, operator_prefix = split
        try:
            answer = self.authority.allocated(
                country_code=country_code, operator_prefix=operator_prefix
            )
        except Exception:  # noqa: BLE001 — fail OPEN is the requirement
            # Deliberately no exception detail and no `logger.exception`: the
            # traceback of a vendor client is the one place a subscriber number
            # would plausibly appear in a log (invariant 6). A timeout, a DNS
            # failure and a bug are all the same thing here — a lookup that did
            # not happen — and all of them admit.
            logger.info("carrier/geo lookup failed; admitting (fail open)")
            return CarrierGeoVerdict(CarrierGeoOutcome.UNCHECKED, "lookup_failed")
        if answer is None:
            return CarrierGeoVerdict(CarrierGeoOutcome.UNCHECKED, "authority_has_no_answer")
        if answer:
            return CarrierGeoVerdict(CarrierGeoOutcome.ADMIT, "prefix_allocated")
        return CarrierGeoVerdict(CarrierGeoOutcome.REFUSE, "prefix_not_allocated")


def load_allocation_table(path: Path) -> AllocationTable:
    """Load and validate the committed authority, or raise."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise CarrierGeoConfigError(f"{path}: unreadable allocation table: {err}") from err
    if raw is None:
        raw = {}
    try:
        return AllocationTable.model_validate(raw)
    except ValidationError as err:
        raise CarrierGeoConfigError(f"{path}: {err}") from err


def carrier_geo_from_path(path: Path) -> CarrierGeoCheck:
    """Wire the check from the committed table, admitting if it cannot be read.

    The log line is the visible surface of the shipping state: an operator who
    greps for it learns whether the carrier half can refuse anything at all,
    without reading this file. It carries a path and two booleans and nothing
    from any request.
    """
    try:
        table = load_allocation_table(path)
    except CarrierGeoConfigError as err:
        logger.warning("carrier/geo authority unusable (%s); admitting every request", err)
        return CarrierGeoCheck()
    authority = AllocationTableAuthority(table)
    if authority.can_refuse:
        logger.info(
            "carrier/geo authority loaded from %s: %d allocated prefixes, exhaustive",
            path,
            len(table.allocated_prefixes),
        )
    else:
        logger.info(
            "carrier/geo authority loaded from %s and cannot refuse. %s", path, CARRIER_GEO_ASK
        )
    return CarrierGeoCheck(authority=authority)
