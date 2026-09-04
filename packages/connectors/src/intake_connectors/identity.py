"""Matching a verified caller to a row in a hospital feed, and refusing when
the data cannot tell two people apart.

The design is forced by what the upstream feed actually contains rather than
by what an identity flow usually looks like. Three measured facts:

* **The TC Kimlik is missing more often than it is present** — ten of sixteen
  rows in the measured window carry ``null``. So the TC cannot be a second
  authentication factor: making it one would lock out the majority of
  patients, and calling it one would be a claim the data does not support.
* **A phone number is not unique.** One handset in the same window belongs to
  two different patients, which is ordinary in Türkiye. So the phone cannot be
  the sole key either.
* **The two sides spell the phone differently.** The feed writes twelve
  characters beginning ``905``; the app's phone screen produces ``05…``. Raw
  comparison matches nothing, and the failure is indistinguishable from "this
  patient has no appointment".

So: the OTP is the authentication, and the TC is a *disambiguator* consulted
only when the phone alone leaves more than one candidate. When it cannot
disambiguate — the wrong TC, no TC supplied, or candidates that all carry
``null`` — the answer is a refusal. Showing one patient another patient's
visit is a worse outcome than a login that did not work, and a refusal that
can be retried with a different TC is an oracle, so the terminal refusals
stay terminal.

Nothing in this module prints an identifier. :class:`IdentityCandidate` and
:class:`IdentityResolution` both render as ids and counts, because a
resolution is exactly the object a caller reaches for when a login failed and
they want to know why (invariant 6).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "IdentityCandidate",
    "IdentityOutcome",
    "IdentityResolution",
    "identifier_digest",
    "normalise_tr_msisdn",
    "resolve_identity",
    "tckn_is_valid",
]

#: How many hex characters of the sha256 a printed identifier shows. The same
#: number ``intake_platform.ci.phi`` uses, and pinned equal to it by a test:
#: two definitions of "safe to print" would drift, and the half that drifts is
#: always the one nobody runs against real data.
_DIGEST_CHARS = 16

#: Turkish mobiles, in every spelling that reaches either side of this match.
#: Identical in effect to ``intake_api.otp.normalise_tr_phone`` (pinned by a
#: test): a formatting difference must not fork a match any more than it may
#: fork a pseudonym or a rate bucket.
_TR_MOBILE = re.compile(r"^(?:\+90|90|0)?(5\d{9})$")
_STRIP = re.compile(r"[\s\-().]")

_TCKN = re.compile(r"^[1-9][0-9]{10}$")


def identifier_digest(value: str) -> str:
    """A stable, truncated fingerprint of an identifier, safe to print."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


def normalise_tr_msisdn(raw: str | None) -> str | None:
    """A Turkish mobile in any accepted spelling → ``+905`` plus nine digits.

    ``None`` when it is not one, which includes a landline: a feed row whose
    ``cell_phone`` is a fixed line can never be reached by a mobile login, and
    silently widening the pattern to accept it would make that row matchable
    by a number the OTP tier can never have verified.
    """
    if raw is None or len(raw) > 32:
        return None
    match = _TR_MOBILE.match(_STRIP.sub("", raw))
    if match is None:
        return None
    return f"+90{match.group(1)}"


def tckn_is_valid(raw: str | None) -> bool:
    """The published TC Kimlik check digits, computed rather than assumed.

    Eleven digits, never leading zero; the tenth digit is
    ``(7·odd − even) mod 10`` over the first nine and the eleventh is the sum
    of the first ten mod 10. This is arithmetic on a public format — it is not
    a claim that the number belongs to anybody, and it is not a lookup. Its
    only job here is to keep a mistyped or invented value from being used as a
    disambiguator, where it could only ever produce a wrong answer or a
    refusal.
    """
    if raw is None or _TCKN.match(raw) is None:
        return False
    digits = [int(character) for character in raw]
    odd = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even = digits[1] + digits[3] + digits[5] + digits[7]
    if (odd * 7 - even) % 10 != digits[9]:
        return False
    return sum(digits[:10]) % 10 == digits[10]


class IdentityOutcome(StrEnum):
    """What the feed was able to say about the caller.

    ``NEEDS_TCKN`` is the only recoverable one: it means a second question has
    an answer that would settle it. ``REFUSED_AMBIGUOUS`` means no answer
    would, or that the answer given was wrong — and it is terminal on purpose.
    """

    MATCHED = "matched"
    NO_MATCH = "no_match"
    NEEDS_TCKN = "needs_tckn"
    REFUSED_AMBIGUOUS = "refused_ambiguous"


@dataclass(frozen=True, repr=False)
class IdentityCandidate:
    """One feed row reduced to the three fields matching may look at.

    Names are deliberately absent. A name cannot disambiguate — the measured
    shared handset belongs to two people with the *same* surname — and a field
    that cannot decide anything is a field that can only leak.
    """

    patient_number: str
    msisdn: str | None
    tckn: str | None

    def __repr__(self) -> str:
        phone = "-" if self.msisdn is None else identifier_digest(self.msisdn)
        tckn = "-" if self.tckn is None else identifier_digest(self.tckn)
        return f"IdentityCandidate({self.patient_number}, msisdn={phone}, tckn={tckn})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class IdentityResolution:
    """The auditable outcome of one match — safe to log exactly as it is.

    Every field is an id, a count or a member of a closed vocabulary. There is
    no key a phone number, a TC Kimlik or a name could occupy even by
    accident, which is what makes this the object a failing login reports.
    """

    outcome: IdentityOutcome
    patient_number: str | None
    #: An id-shaped reason from the closed set below, never prose.
    reason: str
    #: How many feed rows the phone alone selected.
    candidate_count: int

    @property
    def matched(self) -> bool:
        return self.outcome is IdentityOutcome.MATCHED


def resolve_identity(
    candidates: Iterable[IdentityCandidate],
    *,
    phone: str,
    tckn: str | None = None,
) -> IdentityResolution:
    """Match a verified phone to at most one feed row.

    ``phone`` must already be canonical (``+905`` plus nine digits); passing anything
    else raises rather than quietly matching nothing, because "no appointment"
    and "your caller normalised the number wrongly" are the same observation
    from outside and only one of them is a bug worth finding.
    """
    if normalise_tr_msisdn(phone) != phone:
        raise ValueError("phone must already be normalised to E.164 (+90, then the ten-digit mobile)")

    matches: Sequence[IdentityCandidate] = [
        candidate for candidate in candidates if candidate.msisdn == phone
    ]
    count = len(matches)

    if count == 0:
        return IdentityResolution(IdentityOutcome.NO_MATCH, None, "no_phone_match", 0)
    if count == 1:
        # The TC is deliberately not consulted here. It is a disambiguator,
        # and there is nothing to disambiguate; treating it as a second factor
        # would refuse the ten-in-sixteen patients whose row carries none.
        return IdentityResolution(
            IdentityOutcome.MATCHED, matches[0].patient_number, "single_phone_match", 1
        )

    if not any(candidate.tckn for candidate in matches):
        # Asking for a TC that provably cannot separate these rows is a dead
        # end dressed as a prompt, so the refusal is immediate.
        return IdentityResolution(
            IdentityOutcome.REFUSED_AMBIGUOUS, None, "no_tckn_available", count
        )
    if tckn is None:
        return IdentityResolution(IdentityOutcome.NEEDS_TCKN, None, "tckn_required", count)
    if not tckn_is_valid(tckn):
        # Recoverable: the caller can type it again. The value is not echoed
        # and the outcome does not say which digit was wrong.
        return IdentityResolution(IdentityOutcome.NEEDS_TCKN, None, "tckn_invalid", count)

    narrowed = [candidate for candidate in matches if candidate.tckn == tckn]
    if len(narrowed) == 1:
        return IdentityResolution(
            IdentityOutcome.MATCHED, narrowed[0].patient_number, "tckn_disambiguated", count
        )
    reason = "tckn_ambiguous" if narrowed else "tckn_no_match"
    return IdentityResolution(IdentityOutcome.REFUSED_AMBIGUOUS, None, reason, count)
