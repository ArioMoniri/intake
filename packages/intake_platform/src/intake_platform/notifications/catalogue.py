"""INT-141 — the closed catalogue of notification templates.

**Every notification body in this product is a constant.** There is no
interpolation, no format string, no ``{}`` and no argument that could carry a
patient's data into one: :func:`render` takes a kind and a locale, both closed
enums, and returns committed text. That is what makes content-freedom a
property of the type system rather than a promise in a review comment — an
appointment reminder that names the department is a disclosure to whoever is
standing behind the patient when the lock screen lights up, and the only
reliable way to keep the department out is to have no channel through which it
could arrive.

Two consequences worth stating, because they read as limitations and are the
design:

- **Timing lives in the template, not in the body.** "Tomorrow" and "coming
  up" are different templates rather than one template and a rendered
  interval, so the choice among them depends on the reminder kind alone and
  never on anything clinical.
- **The deep link is a destination, not a record.** ``DeepLinkRoute`` is a
  closed set of app screens with no identifier in it; a link carrying a visit
  id would put a linkable reference on a lock screen (files/10 §4: no PHI in
  push notifications or deep links).

:data:`CORPUS_VOCABULARY` is the union of every word in this file's committed
copy. ``intake_platform.notifications.contentfree`` proves a rendered payload
draws only on it — so any interpolated value at all, clinical or not, is a
violation the build catches.

Register: `siz` throughout, ≤ B1, no clinical vocabulary and no word that
would tell a bystander what the app is for beyond its own name (00 §2;
CLAUDE.md clinical content rules). Turkish is the source of truth; English
mirrors it.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, final

from intake_platform.notifications.folding import tokens

__all__ = [
    "CORPUS_VOCABULARY",
    "TEMPLATES",
    "Channel",
    "DeepLinkRoute",
    "Locale",
    "MessageClass",
    "RenderedMessage",
    "ReminderKind",
    "Template",
    "render",
    "template_for",
]


class MessageClass(enum.StrEnum):
    """files/06 §1 row 6563-İYS: appointment and service messages are
    non-commercial; **any** marketing message needs an İYS-registered
    consent. The two are different classes rather than a boolean on one,
    because the sealing function for each takes different arguments — see
    ``intake_platform.notifications.iys``."""

    TRANSACTIONAL = "transactional"
    COMMERCIAL = "commercial"


class Channel(enum.StrEnum):
    PUSH = "push"
    SMS = "sms"


class Locale(enum.StrEnum):
    TR = "tr"
    EN = "en"


class DeepLinkRoute(enum.StrEnum):
    """Where tapping the notification lands. A closed set of screens, never
    a record reference: ``/visits/<uuid>`` on a lock screen is a linkable
    identifier, and "Bugün" already shows the next visit to the person who
    unlocked the phone."""

    APP_ROOT = "app_root"
    TODAY = "today"


class ReminderKind(enum.StrEnum):
    """The transactional reminders this product sends. There is deliberately
    no commercial member: the dispatcher's only entry point takes this type,
    so no argument exists that could carry a campaign through it."""

    VISIT_PREPARE = "visit_prepare"
    VISIT_SOON = "visit_soon"
    INTAKE_RESUME = "intake_resume"
    NOTE_READY = "note_ready"


@final
@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """One notification, fully resolved. Nothing here was interpolated."""

    template_key: str
    locale: Locale
    route: DeepLinkRoute
    title: str
    body: str

    def with_body(self, body: str) -> RenderedMessage:
        """Replace the body — for negative controls that must be caught by
        the content-freedom assertion, and for nothing else."""
        return replace(self, body=body)


@final
@dataclass(frozen=True, slots=True)
class Template:
    key: str
    message_class: MessageClass
    route: DeepLinkRoute
    title: Mapping[Locale, str]
    body: Mapping[Locale, str]

    def render(self, locale: Locale) -> RenderedMessage:
        return RenderedMessage(
            template_key=self.key,
            locale=locale,
            route=self.route,
            title=self.title[locale],
            body=self.body[locale],
        )


def _template(
    kind: ReminderKind, route: DeepLinkRoute, title: str, body_tr: str, body_en: str
) -> Template:
    return Template(
        key=kind.value,
        # Every template built here is transactional by construction: this
        # helper takes a ReminderKind, and no commercial kind exists.
        message_class=MessageClass.TRANSACTIONAL,
        route=route,
        title={Locale.TR: title, Locale.EN: title},
        body={Locale.TR: body_tr, Locale.EN: body_en},
    )


#: The app's own name is the whole title. A subject line that said anything
#: else would be the first place a symptom crept back in.
_TITLE: Final = "Vizite"

TEMPLATES: Final[Mapping[ReminderKind, Template]] = MappingProxyType(
    {
        ReminderKind.VISIT_PREPARE: _template(
            ReminderKind.VISIT_PREPARE,
            DeepLinkRoute.TODAY,
            _TITLE,
            "Yarınki viziteniz için hazırlığınızı tamamlayabilirsiniz. "
            "Uygulamayı açın ve kaldığınız yerden devam edin.",
            "You can finish getting ready for tomorrow's visit. "
            "Open the app and carry on where you left off.",
        ),
        ReminderKind.VISIT_SOON: _template(
            ReminderKind.VISIT_SOON,
            DeepLinkRoute.TODAY,
            _TITLE,
            "Viziteniz yaklaşıyor. Hazırlığınızı uygulamada tamamlayabilirsiniz.",
            "Your visit is coming up. You can finish getting ready in the app.",
        ),
        ReminderKind.INTAKE_RESUME: _template(
            ReminderKind.INTAKE_RESUME,
            DeepLinkRoute.TODAY,
            _TITLE,
            "Yarım kalan bir hazırlığınız var. Kaldığınız yerden devam edebilirsiniz.",
            "You have an unfinished preparation. You can carry on where you left off.",
        ),
        ReminderKind.NOTE_READY: _template(
            ReminderKind.NOTE_READY,
            DeepLinkRoute.APP_ROOT,
            _TITLE,
            "Hazırlığınız tamamlandı. Uygulamada gözden geçirebilir ve gönderebilirsiniz.",
            "Your preparation is ready. You can review it in the app and send it.",
        ),
    }
)


def _corpus() -> frozenset[str]:
    words: set[str] = set()
    for template in TEMPLATES.values():
        for mapping in (template.title, template.body):
            for text in mapping.values():
                words.update(tokens(text))
    return frozenset(words)


#: Every word the committed copy uses, folded. A rendered payload whose
#: vocabulary is a subset of this cannot be carrying anything patient-specific
#: — that is the whole content-freedom argument, and it is checkable.
CORPUS_VOCABULARY: Final[frozenset[str]] = _corpus()


def template_for(kind: ReminderKind) -> Template:
    """Total over the enum: adding a kind without copy fails at import."""
    return TEMPLATES[kind]


def render(kind: ReminderKind, locale: Locale) -> RenderedMessage:
    return template_for(kind).render(locale)
