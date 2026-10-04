"""INT-483 / ADR-040 — whom a question is addressed to, and what a proxy hears.

Owner decision D24, answer 1Y (3 Oct 2026): in a proxy session — a parent or
carer answering for the patient — every self-addressed question is reworded
for the patient ("Çocuğunuz…") or skipped, and the child and carer paths stay
closed until that mechanism exists. This module is the DSL half of the
mechanism. The compiler half is :mod:`protocols.compile.proxy_path`, the
runtime half is the engine's ``addressing``.

Three facts, each a type rather than a convention:

* :class:`Addressee` — whom the slot's own text speaks to. ``patient`` is the
  default and the fail-closed reading: a slot that says nothing about its
  addressee is treated as speaking to the patient in the second person, which
  is what every slot authored before ADR-040 does ("Şikâyetiniz ne zaman
  başladı?"). ``speaker`` is for the few questions that are about whoever
  holds the device — who they are answering for, whether they confirm what is
  on the screen — and read correctly in either session.
* :class:`ProxyAddressing` — what a ``patient``-addressed slot does in a proxy
  session: either it is **reworded**, carrying its own verbatim ``ask_tr``
  (and a ``follow_up_tr`` / ``confirm_tr`` for every one the self form
  speaks), or it is **skipped** (``skip: true``). Exactly one of the two.
* :class:`Addressing` — which of the two a resolved document was built for.

The text a proxy hears is pack text, spoken verbatim from the clip cache or
TTS like any other scripted question (CLAUDE.md invariant 10). There is no
runtime rewording, no pronoun substitution and no template: a sentence about
"çocuğunuz" is a different sentence, written and reviewed as one.

What this module does NOT decide, and why the packs carry no proxy content:
which item is reworded and which is skipped, and every proxy sentence, are
clinical decisions (owner decision D18), recorded in a clinical decision record
before they enter a pack. Until then the compiler refuses the proxy path for
every pack, which is the closed state D24 asks for.
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

from protocols.locale_text import LocaleText

__all__ = [
    "RED_FLAG_PROBE_SECTION",
    "SUBJECT_ROLE_REF",
    "Addressee",
    "Addressing",
    "ProxyAddressing",
    "proxy_text_mismatches",
]

#: The base pack's identity slot (files/04 §1 row 1, ``subject_role``): the
#: in-session answer that says whether the speaker is the patient. CD-01 names
#: it as the selector of the proxy form. A red-flag probe gated on it is a probe
#: that a proxy session can skip, which ADR-040 forbids (invariant 7).
SUBJECT_ROLE_REF = "identity_check.subject_role"

#: files/04 §1 row 4: the section holding one layperson-answerable probe per
#: red-flag family of files/04 §3. Every slot in it is a red-flag probe whether
#: or not a signed rule reads it yet, because the families' triggers are
#: unsigned (HB-C1) and a probe must not become skippable in the gap between.
RED_FLAG_PROBE_SECTION = "red_flags"


class Addressee(enum.StrEnum):
    """Whom a slot's authored text speaks to (ADR-040)."""

    #: The patient, in the second person. The default: silence is read as
    #: self-addressed, so a slot nobody classified needs proxy handling.
    PATIENT = "patient"
    #: Whoever holds the device, in either session. Never a red-flag probe:
    #: the speaker's own answer must not fill the patient's rule slot.
    SPEAKER = "speaker"


class Addressing(enum.StrEnum):
    """Which session a resolved document speaks to (ADR-040).

    Selected by the session's subject role: the patient answering for
    themselves is ``self``; a parent, guardian or carer answering for the
    patient is ``proxy``. INT-133's ``assisted_self_report`` (the patient's
    own words on a relative's device) is ``self``, because the patient is the
    one answering.
    """

    SELF = "self"
    PROXY = "proxy"


class ProxyAddressing(FrozenModel):
    """What a patient-addressed slot does in a proxy session: reworded or
    skipped, never both and never neither (ADR-040)."""

    skip: bool = Field(
        default=False,
        description="Not asked in a proxy session. The slot records NOT_ASKED_PROXY, "
        "never an answer, and the clinician note shows it as not asked (proxy). "
        "Refused by the compiler on a red-flag probe (CLAUDE.md invariant 7).",
    )
    ask_tr: LocaleText | None = Field(
        default=None,
        description="The question as put to the proxy, about the patient, per locale; "
        "spoken verbatim (CLAUDE.md invariant 10).",
    )
    confirm_tr: LocaleText | None = Field(
        default=None,
        description="The proxy form of the slot's confirm_tr. Required exactly when the "
        "self form carries one.",
    )
    follow_up_tr: LocaleText | None = Field(
        default=None,
        description="The proxy form of the slot's follow_up_tr. Required exactly when the "
        "self form carries one.",
    )

    @model_validator(mode="after")
    def _reworded_or_skipped(self) -> ProxyAddressing:
        texts = (self.ask_tr, self.confirm_tr, self.follow_up_tr)
        if self.skip and any(text is not None for text in texts):
            raise ValueError(
                "a proxy block is reworded OR skipped, never both: a skipped slot is "
                "not spoken, so proxy text on it is text nobody hears (ADR-040)"
            )
        if not self.skip and self.ask_tr is None:
            raise ValueError(
                "a proxy block that does not skip must carry its own ask_tr — there is "
                "no runtime rewording of the self-addressed text (ADR-040; CLAUDE.md "
                "invariant 10)"
            )
        return self


def proxy_text_mismatches(
    proxy: ProxyAddressing,
    *,
    ask_tr: object | None,
    confirm_tr: object | None,
    follow_up_tr: object | None,
) -> tuple[str, ...]:
    """The spoken fields where a rewording and its self form disagree.

    Every text the self form can speak has a proxy counterpart, so nothing
    self-addressed is ever spoken in a proxy session — a follow-up or confirm
    in the second person after a reworded question is the same defect one turn
    later. A proxy field with no self counterpart is refused too: it would be
    text the runtime never reaches — which is also why a slot with no question
    of its own cannot be reworded into one. A skipped slot speaks nothing and
    has no mismatch.
    """
    if proxy.skip:
        return ()
    gaps: list[str] = []
    if ask_tr is None:
        gaps.append("ask_tr")
    for name, self_form, proxy_form in (
        ("confirm_tr", confirm_tr, proxy.confirm_tr),
        ("follow_up_tr", follow_up_tr, proxy.follow_up_tr),
    ):
        if (self_form is None) != (proxy_form is None):
            gaps.append(name)
    return tuple(gaps)
