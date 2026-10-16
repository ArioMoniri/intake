"""INT-490 — what the research and improvement analytics may show (LD-06).

The closed vocabulary of the admin panel's Analytics page: the period grain,
the dimension keys, the views and the value each partition may take. Nothing
here is derived from data, so nothing here can carry a value a patient typed.

**One grain, fixed buckets.** LD-06 ``admin_analytics.conditions.across_views``
asks for "fixed, non-overlapping period buckets". The bucket is the ISO week in
UTC (Monday 00:00 to the next Monday), the unit INT-171's views and Loop 2
already reason in (files/09 §4 runs Loop 2 weekly), and the only one: a second
grain over the same population would make a month minus its visible weeks a
way to recover a withheld week. Only CLOSED weeks are served, so a figure for a
week never changes because the week is still filling.

**Every view is a partition.** Each view splits one population into exclusive
cells over a closed domain, and every figure the panel draws is a count of one
cell or a sum of cells of the same view (a cumulative funnel, a share). So the
cells LD-06 counts — "every combination of dimensions the panel can show" — are
exactly the declared cells, and a drop-off is never a number the gate did not
see.

**Dimension keys are a closed list with a refusal rule** (invariant 6), the
same shape as the INT-481 metric-label scan: a key that names a person, a
session or a device, carries free text, or is identifier-shaped is refused.

sec_row: `observability-pipeline`.  legal: LD-06 (KVKK m.28(1)(b); Yönetmelik m.10).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

from intake_platform.locale.registry import LOCALE_REGISTRY

__all__ = [
    "ALLOWED_DIMENSION_KEYS",
    "FAMILY_VIEW_KINDS",
    "QUESTION_VIEW_KINDS",
    "VIEW_SPECS",
    "AnswerTimeBand",
    "AsrBand",
    "InputMode",
    "Period",
    "PeriodRefused",
    "Platform",
    "QuestionOutcome",
    "RepeatBand",
    "Stage",
    "TriageBucket",
    "ViewKind",
    "ViewSpec",
    "dimension_key_problem",
]


class Stage(enum.StrEnum):
    """The furthest funnel stage a person reached in the week (exclusive)."""

    #: a visit was opened for them and nothing more happened in the week
    INVITED = "invited"
    #: the intake began (a start instant, a document, or a note) but no note
    STARTED = "started"
    #: the intake produced a note the patient has not sent
    FINISHED = "finished"
    #: the patient sent the note (a share exists)
    SHARED = "shared"


class TriageBucket(enum.StrEnum):
    """The rules-engine level of a finished intake (invariant 1), or none."""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    #: no rules-engine determination is on record for the intake
    NOT_EVALUATED = "not_evaluated"


class Platform(enum.StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class QuestionOutcome(enum.StrEnum):
    ANSWERED = "answered"
    SKIPPED = "skipped"
    #: the session ended while the question was open
    ABANDONED = "abandoned"


class InputMode(enum.StrEnum):
    TYPED = "typed"
    VOICE = "voice"


class RepeatBand(enum.StrEnum):
    """Repeat-or-clarify requests while the question was open."""

    NONE = "none"
    ONE_OR_MORE = "one_or_more"


class AnswerTimeBand(enum.StrEnum):
    """Time from the question being asked to the answer, as a band.

    Bands, never a mean: a mean is a sum divided by a count, and a sum can be
    differenced across views like any count can — but the auditor in
    :mod:`intake_platform.analytics.research.audit` only reasons about counts.
    """

    UNDER_10S = "under_10s"
    S10_TO_30 = "10s_to_30s"
    S30_TO_60 = "30s_to_60s"
    OVER_60S = "over_60s"


class AsrBand(enum.StrEnum):
    """A measured speech-recognition quality band for one voice answer — a
    measurement of that recording, never a property of the product (inv. 20)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ViewKind(enum.StrEnum):
    FUNNEL = "funnel"
    TRIAGE = "triage"
    LOCALE = "locale"
    PLATFORM = "platform"
    QUESTION_OUTCOME = "question_outcome"
    QUESTION_MODE = "question_mode"
    QUESTION_REPEAT = "question_repeat"
    QUESTION_TIME = "question_time"
    QUESTION_ASR = "question_asr"


@dataclass(frozen=True)
class ViewSpec:
    """One kind of view: which population it splits, and by what."""

    kind: ViewKind
    #: ``family`` — one per protocol version; ``question`` — one per question
    #: of a protocol version
    scope: str
    #: the dimension key the cells are told apart by
    partition: str
    domain: tuple[str, ...]
    #: lower is kept first when the cross-view check must withhold a view
    priority: int


def _values(kind: type[enum.StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in kind)


VIEW_SPECS: Final[dict[ViewKind, ViewSpec]] = {
    spec.kind: spec
    for spec in (
        ViewSpec(ViewKind.FUNNEL, "family", "stage", _values(Stage), 0),
        ViewSpec(ViewKind.TRIAGE, "family", "triage_level", _values(TriageBucket), 1),
        ViewSpec(ViewKind.LOCALE, "family", "locale", tuple(sorted(LOCALE_REGISTRY)), 2),
        ViewSpec(ViewKind.PLATFORM, "family", "platform", _values(Platform), 3),
        ViewSpec(ViewKind.QUESTION_OUTCOME, "question", "outcome", _values(QuestionOutcome), 4),
        ViewSpec(ViewKind.QUESTION_MODE, "question", "input_mode", _values(InputMode), 5),
        ViewSpec(ViewKind.QUESTION_REPEAT, "question", "repeat_band", _values(RepeatBand), 6),
        ViewSpec(ViewKind.QUESTION_TIME, "question", "time_band", _values(AnswerTimeBand), 7),
        ViewSpec(ViewKind.QUESTION_ASR, "question", "asr_band", _values(AsrBand), 8),
    )
}

FAMILY_VIEW_KINDS: Final = frozenset(k for k, s in VIEW_SPECS.items() if s.scope == "family")
QUESTION_VIEW_KINDS: Final = frozenset(k for k, s in VIEW_SPECS.items() if s.scope == "question")

#: Every key a released view may carry. Closed: a new key is a reviewed edit
#: here, and :func:`dimension_key_problem` must pass on it.
ALLOWED_DIMENSION_KEYS: Final = frozenset(
    {"period", "protocol", "protocol_version", "question"}
    | {spec.partition for spec in VIEW_SPECS.values()}
)

_PERSON_SEGMENTS: Final = frozenset(
    {
        "account",
        "actor",
        "address",
        "birth",
        "client",
        "device",
        "dob",
        "email",
        "ip",
        "msisdn",
        "name",
        "national",
        "patient",
        "person",
        "phone",
        "session",
        "tckn",
        "tenant",
        "transcript",
        "user",
        "utterance",
    }
)
_FREE_TEXT_TAILS: Final = frozenset(
    {"body", "comment", "content", "message", "note", "payload", "raw", "text", "value"}
)
_IDENTIFIER_TAILS: Final = frozenset(
    {"fingerprint", "hash", "id", "ids", "key", "number", "sha", "sub", "token", "uuid"}
)
_KEY_SHAPE: Final = re.compile(r"^[a-z][a-z0-9_]*$")


def dimension_key_problem(key: str) -> str | None:
    """Why ``key`` may not be a dimension of a released view, or ``None``.

    ``tenant`` is refused as a segment here although the INT-481 metric-label
    list reviews it: a clinic is never a dimension of this release (LD-06
    names tenant among the dimensions that make a cell; the panel has none).
    """
    if _KEY_SHAPE.match(key) is None:
        return f"{key!r} is not a lower-case snake_case key"
    segments = key.split("_")
    person = sorted(set(segments) & _PERSON_SEGMENTS)
    if person:
        return f"{key!r} names a person, a session, a device or a clinic ({', '.join(person)})"
    if segments[-1] in _FREE_TEXT_TAILS:
        return f"{key!r} carries free text ({segments[-1]})"
    if segments[-1] in _IDENTIFIER_TAILS:
        return f"{key!r} is identifier-shaped ({segments[-1]})"
    return None


class PeriodRefused(ValueError):
    """A period id that is not an ISO week, or a week that has not closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_PERIOD_SHAPE: Final = re.compile(r"^(\d{4})-W(\d{2})$")


@dataclass(frozen=True, order=True)
class Period:
    """One ISO week, UTC. The only bucket the release is cut into."""

    year: int
    week: int

    def __post_init__(self) -> None:
        try:
            date.fromisocalendar(self.year, self.week, 1)
        except ValueError:
            raise PeriodRefused("period_malformed") from None

    @classmethod
    def parse(cls, text: str) -> Period:
        match = _PERIOD_SHAPE.fullmatch(text)
        if match is None:
            raise PeriodRefused("period_malformed")
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def containing(cls, instant: datetime) -> Period:
        if instant.tzinfo is None:
            raise ValueError("a period is located from an aware instant")
        year, week, _ = instant.astimezone(UTC).isocalendar()
        return cls(year, week)

    @classmethod
    def latest_closed(cls, now: datetime) -> Period:
        return cls.containing(now).previous

    @property
    def id(self) -> str:
        return f"{self.year:04d}-W{self.week:02d}"

    @property
    def start(self) -> datetime:
        day = date.fromisocalendar(self.year, self.week, 1)
        return datetime(day.year, day.month, day.day, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(days=7)

    @property
    def previous(self) -> Period:
        return Period.containing(self.start - timedelta(days=1))

    @property
    def following(self) -> Period:
        return Period.containing(self.end)

    def is_closed(self, now: datetime) -> bool:
        return self.end <= now

    def require_closed(self, now: datetime) -> Period:
        """The period, or :class:`PeriodRefused` when it has not ended: a week
        still filling is a figure that changes between two reads, and the
        difference is a person."""
        if not self.is_closed(now):
            raise PeriodRefused("period_not_closed")
        return self
