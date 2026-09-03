"""INT-296 — which languages this build may offer, and on what two conditions.

**The registry ships holding exactly ``tr``.** That is the deliverable, not a
stub. Which languages this product supports is a product and market decision
(HUMAN_BLOCKERS.md **HB-O5**); what they say clinically is HB-C19's; what a
translated consent text legally *is* is HB-L23's; and whether an instrument is
even the same instrument in another language is HB-L24's. Registering a second
locale here would be answering all four on their owners' behalf. CLAUDE.md
names the correct shape for exactly this situation: *build the mechanism, wire
the gate, make it fail closed, leave the content empty.*

**Invariant 5 is unchanged.** ``tr`` remains the source of truth and the
default. Everything below is additive: a locale that is absent, incomplete or
unsigned is simply not offered, and nothing anywhere falls back to Turkish
string by string.

**Two conditions, two fields — never one flag.**

``ui_catalogue_complete``
    Every key the Turkish catalogue defines exists in this locale's catalogue
    with a non-blank value. Verified against the real catalogues at build time
    by ``tests/release/test_i18n_complete.py``; the field is the *claim*, and a
    claim that disagrees with the tree fails the build in both directions.

``clinical_signoff``
    HB-C19's question, verbatim: *"who signs the clinical text for that
    language, and do they read it"*. A red-flag action script or an instrument
    item in a second language is **new clinical content**, not a translation of
    signed content.

A locale may satisfy the first and not the second. It then renders the app and
may **not** run an intake. Collapsing the two into one boolean is precisely how
a locale that can draw a settings screen quietly acquires permission to speak a
triage script, so they stay apart.

**What ``clinical_signoff`` is not.** It is not a second copy of a pack's own
``clinical_signoff`` block. That block — all six fields still null on
``base.life_threat`` — is HB-C1, and the protocol compiler's serve interlock is
its gate. This field says only that a *nominated clinician who reads this
language* exists. Both gates must hold; neither substitutes for the other, and
a locale being offerable never makes an unsigned pack servable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_CODE_PATTERN",
    "LOCALE_REGISTRY",
    "LocaleClinicalSignoff",
    "LocaleNotOffered",
    "LocaleRegistration",
    "enabled_locales",
    "offerable_app_locales",
    "offerable_intake_locales",
    "registration",
    "safe_code",
]

#: Invariant 5. Not a configurable value: the source of truth is not a setting.
DEFAULT_LOCALE = "tr"

#: A language tag is a *code*, never prose. The pattern is the boundary that
#: keeps a sentence a patient typed from ever being echoed into a log message
#: or a metric label (invariant 6).
LOCALE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?$")

#: What a refusal says instead of the value it refused.
REDACTED_CODE = "<not-a-locale-code>"


class LocaleNotOffered(ValueError):
    """A locale was asked for that this build does not offer.

    Carries no caller-supplied text: the message is assembled from the closed
    registry and a shape-checked code, never from whatever arrived.
    """


def safe_code(value: str) -> str:
    """The only way a locale string reaches a message, a label or a log line.

    A well-formed tag is short, closed and non-identifying, so it passes
    through. Anything else — a sentence, a phone number, a name — is replaced
    wholesale rather than truncated, because a truncated identifier is still
    an identifier (invariant 6).
    """
    if LOCALE_CODE_PATTERN.match(value):
        return value
    return REDACTED_CODE


@dataclass(frozen=True, slots=True)
class LocaleClinicalSignoff:
    """HB-C19's answer for one language.

    ``signer_reads_locale`` is not a formality. A signature from a clinician
    who cannot read the sentence they are signing is the machine-translation
    failure wearing a signature, so it is refused at construction: an unsigned
    locale is *unconstructible*, not merely unflagged.
    """

    #: Who signs the clinical text for this language.
    signer_role: str
    #: Do they read it? Anything but ``True`` is refused.
    signer_reads_locale: bool
    #: Where the nomination is recorded, so a reviewer can look it up.
    recorded_in: str

    def __post_init__(self) -> None:
        if not self.signer_role.strip():
            raise ValueError(
                "a clinical sign-off needs a named signing role (HB-C19); "
                "an unattributed signature is not one"
            )
        if not self.recorded_in.strip():
            raise ValueError(
                "a clinical sign-off needs a citation a reviewer can look up (HB-C19); "
                "a nomination nobody can find is a nomination nobody made"
            )
        if self.signer_reads_locale is not True:
            raise ValueError(
                "the signer must read the language they sign for (HB-C19): a red-flag "
                "action script the signer cannot read is machine translation with a "
                "signature on it"
            )


@dataclass(frozen=True, slots=True)
class LocaleRegistration:
    """One offerable language, and the two separate conditions it must meet."""

    #: The BCP-47-shaped tag. Shape-checked so it can safely be a metric label.
    code: str
    #: The language's own name for itself, a build-time constant. Never a
    #: string a patient supplied, which is what keeps invariant 6 true when
    #: this reaches a chooser.
    endonym: str
    #: Condition one — the UI catalogue is complete against ``tr``.
    ui_catalogue_complete: bool
    #: Condition two — HB-C19 is answered for this language, or ``None``.
    clinical_signoff: LocaleClinicalSignoff | None

    def __post_init__(self) -> None:
        if not LOCALE_CODE_PATTERN.match(self.code):
            raise LocaleNotOffered(
                "a locale code must be a BCP-47-shaped tag, so that it is safe as a "
                f"metric label and a log field (got {safe_code(self.code)})"
            )
        if not self.endonym.strip():
            raise ValueError(
                f"locale {self.code} has no endonym; a chooser cannot name a language "
                "the language does not name itself"
            )

    @property
    def offerable_for_app(self) -> bool:
        """May the app be *rendered* in this language."""
        return self.ui_catalogue_complete

    @property
    def offerable_for_intake(self) -> bool:
        """May an *intake* run in this language. Strictly narrower, and it has
        to be: an intake speaks red-flag scripts and instrument items."""
        return self.ui_catalogue_complete and self.clinical_signoff is not None


#: Turkish's own sign-off. Nothing here is invented: HB-C19's "blocks" column
#: reads *"Every locale except `tr` running an intake"*, which is the register
#: of record recording that Turkish's answer is already settled. The signer is
#: the physician of record the repo already names.
_TURKISH_SIGNOFF = LocaleClinicalSignoff(
    signer_role="physician of record",
    signer_reads_locale=True,
    recorded_in=(
        "HUMAN_BLOCKERS.md HB-C19 — its own 'blocks' column excepts `tr`; the pack-level "
        "signature is the separate, still-open HB-C1 and the compiler's serve interlock"
    ),
)

#: **The registry.** One entry, deliberately. Adding a second means HB-O5 has
#: named the language, HB-C19 has named a signing clinician who reads it,
#: HB-L23 has said what a translated legal text legally is, and HB-L24 has
#: settled the instrument licences and validations for it — four different
#: humans, none of them an agent.
LOCALE_REGISTRY: Mapping[str, LocaleRegistration] = MappingProxyType(
    {
        DEFAULT_LOCALE: LocaleRegistration(
            code=DEFAULT_LOCALE,
            endonym="Türkçe",
            ui_catalogue_complete=True,
            clinical_signoff=_TURKISH_SIGNOFF,
        )
    }
)


def enabled_locales() -> tuple[str, ...]:
    """Every registered locale, in registry order."""
    return tuple(LOCALE_REGISTRY)


def offerable_app_locales() -> tuple[str, ...]:
    """Locales the chooser may offer for *rendering the app*.

    An incomplete locale is absent from this list. It is never present-and-
    patched: a screen half in another language and half in Turkish reads as
    finished, which is worse than a screen that never offered the language.
    """
    return tuple(code for code, entry in LOCALE_REGISTRY.items() if entry.offerable_for_app)


def offerable_intake_locales() -> tuple[str, ...]:
    """Locales the chooser may offer for *running an intake*."""
    return tuple(code for code, entry in LOCALE_REGISTRY.items() if entry.offerable_for_intake)


def registration(code: str) -> LocaleRegistration:
    """The registration for ``code``, or a refusal that echoes nothing."""
    if code in LOCALE_REGISTRY:
        return LOCALE_REGISTRY[code]
    raise LocaleNotOffered(
        f"locale {safe_code(code)} is not registered; this build offers "
        f"{', '.join(enabled_locales())} (HB-O5 names the rest, HB-C19 signs them)"
    )
