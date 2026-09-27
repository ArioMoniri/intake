"""The Acıbadem appointments read adapter, and the login it feeds.

The upstream ships no response schema, so this module is written against a
*measured* one. Two endpoints, both authenticated by an ``x-api-key`` header
that also gates ``/health``:

``GET /api/v1/appointments/upcoming``
    ``{date_range: {from, to}, count, data: [...]}`` where each row is exactly
    ``{patient_number, patient_name, patient_surname, cell_phone,
    tckimlik_no}``. It is a *directory* for a short window, not a schedule.

``GET /api/v1/patients/{patient_number}/appointments``
    ``{patient_number, count, data: [...]}`` where each row adds ``app_date``
    (``DD-MM-YYYY``), ``start_time``, ``unplanned_app``, ``doctor_id``,
    ``facility_name``, ``specialty_name`` and ``randevu_saati`` (``HH:MM``).
    Measured behaviour worth writing down because it is not obvious: this
    endpoint returns the patient's **entire history**, not the upcoming
    window — the measured feed reaches back to 2021 — so an "upcoming visit"
    is something this side filters for. An unknown number answers ``200`` with
    an empty list rather than an error, and a non-numeric one answers ``422``.

Three fields need care and get it:

* **``randevu_saati`` is the time of record.** ``start_time`` is a
  five-minute slot index from midnight (``108`` → ``09:00``), except where it
  is a sentinel: the measured feed contains ``300``, which would decode to
  ``25:00``, on a row whose real time is ``13:05``. Nothing here derives a
  time from the integer; it is carried as the opaque number it is.
* **``patient_number`` is an identifier, not a quantity** (invariant 22). It
  stays a string end to end — one measured row of sixteen is letters and a
  full stop — and never acquires a thousands separator or a spoken form.
* **``unplanned_app`` is mislabelled upstream.** It holds a ``HH:MM`` string
  or ``null``, not a flag. It is carried verbatim and used for nothing.

Every model here redacts itself. This feed is the densest concentration of
identifiers in the system — names, mobile numbers and TC Kimlik numbers in one
row — and the default dataclass/pydantic representation would put all three
into any traceback that touched a parse (invariant 6). For the same reason
:class:`AcibademUpstreamError` carries a code from a closed set and never a
response body: an upstream's error prose is the single most likely place for a
patient's name to arrive back at us.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from intake_platform.egress import TransferLog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from intake_connectors.credentials import CredentialResolver, require_keys
from intake_connectors.identity import (
    IdentityCandidate,
    IdentityOutcome,
    IdentityResolution,
    normalise_tr_msisdn,
)
from intake_connectors.sender import ConsentGate
from intake_connectors.sources import ClinicalSource, lan_source_client

__all__ = [
    "ADAPTER_ID",
    "API_KEY_HEADER",
    "UPCOMING_PATH",
    "AcibademAppointmentsClient",
    "AcibademLogin",
    "AcibademUpstreamError",
    "Appointment",
    "LoginResult",
    "UpcomingPatient",
    "patient_appointments_path",
]

ADAPTER_ID = "acibadem-appointments"
API_KEY_HEADER = "x-api-key"
UPCOMING_PATH = "/api/v1/appointments/upcoming"

#: What may occupy the ``{patient_number}`` segment. Narrow enough that no
#: value can reshape the path — no slash, no dot-dot, no query, no fragment,
#: no whitespace — and wide enough for the one measured row whose number is
#: letters and a trailing full stop.
_PATIENT_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]{0,31}$")

_TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")

#: The closed failure vocabulary. Every member is something a caller can act
#: on differently, and none of them is quoted from the upstream.
_STATUS_CODES: dict[int, str] = {
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    422: "unprocessable",
}


class AcibademUpstreamError(Exception):
    """The upstream did not answer usefully, said as a code and nothing more."""

    def __init__(self, code: str) -> None:
        super().__init__(f"acibadem upstream: {code}")
        self.code = code


def patient_appointments_path(patient_number: str) -> str:
    """The per-patient path for one number, or a refusal.

    Refusing here rather than escaping is deliberate: an escaped ``..`` still
    reaches a server that may normalise it, and there is no legitimate patient
    number this rejects — the measured feed's whole domain passes.
    """
    if _PATIENT_NUMBER.match(patient_number) is None:
        raise ValueError(
            "a patient number is an identifier: letters, digits, '.', '-' and '_' "
            "only, 1-32 characters — anything else could reshape the request path"
        )
    if ".." in patient_number:
        raise ValueError("a patient number must not traverse ('..')")
    return f"/api/v1/patients/{patient_number}/appointments"


def _redacted_repr(name: str, patient_number: str, extra: str = "") -> str:
    return f"{name}({patient_number}{extra})"


class UpcomingPatient(BaseModel):
    """One row of the upcoming directory. Identifiers in, nothing printed out."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    patient_number: str = Field(min_length=1, max_length=32)
    patient_name: str = Field(max_length=128)
    patient_surname: str = Field(max_length=128)
    cell_phone: str | None = Field(default=None, max_length=32)
    tckimlik_no: str | None = Field(default=None, max_length=16)

    @field_validator("patient_number")
    @classmethod
    def _addressable(cls, value: str) -> str:
        patient_appointments_path(value)
        return value

    @property
    def msisdn(self) -> str | None:
        """The row's phone in the one canonical spelling both sides share."""
        return normalise_tr_msisdn(self.cell_phone)

    def as_candidate(self) -> IdentityCandidate:
        return IdentityCandidate(
            patient_number=self.patient_number, msisdn=self.msisdn, tckn=self.tckimlik_no or None
        )

    def __repr__(self) -> str:
        return _redacted_repr("UpcomingPatient", self.patient_number)

    def __str__(self) -> str:
        return self.__repr__()


class Appointment(BaseModel):
    """One appointment row from the per-patient endpoint."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    patient_number: str = Field(min_length=1, max_length=32)
    patient_name: str = Field(max_length=128)
    patient_surname: str = Field(max_length=128)
    cell_phone: str | None = Field(default=None, max_length=32)
    tckimlik_no: str | None = Field(default=None, max_length=16)
    #: ``DD-MM-YYYY`` upstream; a real date here, so nothing downstream has to
    #: guess which of the first two components is the month.
    app_date: dt.date
    #: ``HH:MM`` upstream, and the field of record for when the visit is.
    randevu_saati: dt.time
    #: A five-minute slot index with at least one sentinel value in the
    #: measured feed. Carried, never decoded.
    start_time: int
    #: Mislabelled upstream: a ``HH:MM`` string or null, not a flag.
    unplanned_app: str | None = Field(default=None, max_length=16)
    doctor_id: int | None = None
    facility_name: str = Field(max_length=128)
    specialty_name: str = Field(max_length=128)

    @field_validator("patient_number")
    @classmethod
    def _addressable(cls, value: str) -> str:
        patient_appointments_path(value)
        return value

    @field_validator("app_date", mode="before")
    @classmethod
    def _turkish_date(cls, value: Any) -> Any:
        if isinstance(value, str):
            return dt.datetime.strptime(value, "%d-%m-%Y").date()
        return value

    @field_validator("randevu_saati", mode="before")
    @classmethod
    def _clock_time(cls, value: Any) -> Any:
        if isinstance(value, str):
            if _TIME.match(value) is None:
                raise ValueError("randevu_saati must be HH:MM")
            hour, minute = value.split(":")
            return dt.time(int(hour), int(minute))
        return value

    @property
    def appointment_date(self) -> dt.date:
        return self.app_date

    @property
    def appointment_time(self) -> dt.time:
        return self.randevu_saati

    def __repr__(self) -> str:
        return _redacted_repr("Appointment", self.patient_number, f", {self.app_date.isoformat()}")

    def __str__(self) -> str:
        return self.__repr__()


class AcibademAppointmentsClient:
    """One source row, one credential, two endpoints, no response body in an error."""

    def __init__(
        self,
        *,
        source: ClinicalSource,
        credentials: CredentialResolver,
        transport: httpx.BaseTransport | None = None,
        transfer_log: TransferLog | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        if source.adapter_id != ADAPTER_ID:
            raise ValueError(
                f"this client serves {ADAPTER_ID!r} rows; {source.adapter_id!r} names a "
                "different adapter and would send this credential somewhere else"
            )
        self._source = source
        self._credentials = credentials
        self._transport = transport
        self._transfer_log = transfer_log
        self._timeout = timeout

    @property
    def source(self) -> ClinicalSource:
        return self._source

    def upcoming(self) -> tuple[UpcomingPatient, ...]:
        """The directory for the upstream's own window."""
        payload = self._get(UPCOMING_PATH)
        return tuple(self._parse(UpcomingPatient, payload))

    def appointments_for(self, patient_number: str) -> tuple[Appointment, ...]:
        """Every appointment the upstream holds for one number, history included.

        Rows carrying a different ``patient_number`` are dropped rather than
        trusted: the upstream selects them, and "the receiver filtered
        correctly" is not a property this side can assert on the receiver's
        behalf.
        """
        payload = self._get(patient_appointments_path(patient_number))
        return tuple(
            row for row in self._parse(Appointment, payload) if row.patient_number == patient_number
        )

    # --- internals ---------------------------------------------------------

    def _api_key(self) -> str:
        (key,) = require_keys(self._credentials.read(self._source.credential_ref), "api_key")
        return key

    def _get(self, path: str) -> Any:
        headers = {API_KEY_HEADER: self._api_key(), "Accept": "application/json"}
        client = lan_source_client(
            self._source, self._transport, self._transfer_log, timeout=self._timeout
        )
        try:
            response = client.get(self._source.url(path), headers=headers)
        finally:
            client.close()
        if response.status_code != 200:
            raise AcibademUpstreamError(_STATUS_CODES.get(response.status_code, "upstream_error"))
        try:
            return response.json()
        except ValueError:
            raise AcibademUpstreamError("malformed") from None

    @staticmethod
    def _parse(model: type[BaseModel], payload: Any) -> list[Any]:
        if not isinstance(payload, dict):
            raise AcibademUpstreamError("malformed")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise AcibademUpstreamError("malformed")
        parsed: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                raise AcibademUpstreamError("malformed")
            try:
                parsed.append(model.model_validate(row))
            except Exception:  # noqa: BLE001 - the cause quotes the row it failed on
                raise AcibademUpstreamError("malformed") from None
        return parsed


@dataclass(frozen=True)
class LoginResult:
    """What one sign-in attempt concluded, and what it may show.

    Safe to log whole: ``outcome`` and ``reason`` are closed vocabularies,
    ``patient_number`` is an identifier, and ``appointments`` render as ids and
    dates. The phone and the TC the caller supplied are deliberately absent —
    a failed login is exactly where an identifier gets echoed back into a log.
    """

    outcome: IdentityOutcome
    patient_number: str | None
    reason: str
    appointments: tuple[Appointment, ...] = field(default=())

    @property
    def matched(self) -> bool:
        return self.outcome is IdentityOutcome.MATCHED


class AcibademLogin:
    """Phone-first sign-in over the appointments feed, behind the consent gate.

    The OTP is the authentication; this runs *after* it, on a phone the OTP
    tier has already verified. What is left to decide is which hospital record
    that verified phone belongs to, and whether it may be read at all.

    ``consent`` has no default, exactly as :class:`~intake_connectors.sender.
    ConnectorSender`'s does: a caller cannot express an unconsented read. It is
    asked *before* the first request leaves, because invariant 4 gates the
    read and not the answer — fetching and then discarding would already have
    disclosed to the hospital which patient asked.
    """

    def __init__(self, *, client: AcibademAppointmentsClient, consent: ConsentGate) -> None:
        self._client = client
        self._consent = consent

    def sign_in(
        self,
        *,
        tenant_id: str,
        patient_ref: str,
        phone: str,
        tckn: str | None = None,
        today: dt.date,
    ) -> LoginResult:
        """Resolve a verified phone to one patient and their upcoming visits.

        ``today`` is passed rather than read from the clock so the boundary
        between "upcoming" and "past" is a decision the caller owns and a test
        can pin.
        """
        verdict = self._consent(
            tenant_id=tenant_id, patient_ref=patient_ref, scope=self._client.source.consent_scope
        )
        if not verdict.allowed:
            return LoginResult(IdentityOutcome.NO_MATCH, None, f"consent_{verdict.reason}")

        normalised = normalise_tr_msisdn(phone)
        if normalised is None:
            # Nothing leaves the process for a number the OTP tier could not
            # have verified in the first place.
            return LoginResult(IdentityOutcome.NO_MATCH, None, "phone_not_normalisable")

        resolution = self._resolve(normalised, tckn)
        if not resolution.matched or resolution.patient_number is None:
            return LoginResult(resolution.outcome, None, resolution.reason)

        upcoming = self._upcoming_for(resolution.patient_number, today)
        return LoginResult(
            IdentityOutcome.MATCHED, resolution.patient_number, resolution.reason, upcoming
        )

    def _resolve(self, phone: str, tckn: str | None) -> IdentityResolution:
        from intake_connectors.identity import resolve_identity

        candidates: Iterable[IdentityCandidate] = (
            row.as_candidate() for row in self._client.upcoming()
        )
        return resolve_identity(candidates, phone=phone, tckn=tckn)

    def _upcoming_for(self, patient_number: str, today: dt.date) -> tuple[Appointment, ...]:
        rows: Sequence[Appointment] = self._client.appointments_for(patient_number)
        upcoming = [row for row in rows if row.app_date >= today]
        upcoming.sort(key=lambda row: (row.app_date, row.randevu_saati))
        return tuple(upcoming)
