"""Which languages have a signed PolicyGuard lexicon. Exactly one (INT-298).

**``tr`` and nothing else.** That is the deliverable, not a stub. Which
languages this product supports is a product decision (HUMAN_BLOCKERS
**HB-O5**); what their clinical text says, and who signs it, is a clinical one
(**HB-C19**, addressed to the physician of record, whose ``blocks`` column
reads *"Every locale except ``tr`` running an intake"*). Adding a module here
would answer both on their owners' behalf. CLAUDE.md names the shape for
exactly this: *build the mechanism, wire the gate, make it fail closed, leave
the content empty.*

There is **no second registry** in this file. INT-296's
``intake_platform.locale`` decides which languages a clinician has signed for;
this table only records which of them a lexicon has actually been written for,
and :func:`~intake_voice_runtime.talker.guard_lexicon.compile_guard_lexicon`
refuses any document the locale registry does not vouch for. Both must hold: a
lexicon without a registration is unusable, and a registration without a
lexicon gets no guard.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from intake_platform.locale import DEFAULT_LOCALE, safe_code

from intake_voice_runtime.talker.guard_lexicon import (
    GuardLexicon,
    LocaleHasNoSignedLexicon,
    SignedGuardLexicon,
    compile_guard_lexicon,
)
from intake_voice_runtime.talker.guard_lexicons.tr import TURKISH_GUARD_LEXICON

__all__ = [
    "GUARD_LEXICONS",
    "guard_lexicon_for",
    "registered_guard_locales",
]

#: **The table.** One entry, deliberately. A second means HB-O5 has named the
#: language and HB-C19 has named a clinician who reads it and has signed its
#: clinical text — two different humans, neither of them an agent.
GUARD_LEXICONS: Mapping[str, GuardLexicon] = MappingProxyType(
    {DEFAULT_LOCALE: TURKISH_GUARD_LEXICON}
)


def _the_table_files_every_lexicon_under_its_own_language() -> None:
    """Checked at import, so a mis-filed lexicon fails the build.

    Found by perturbation while building INT-298 and worth stating: without
    this, filing the Turkish document under ``ar`` produced a *compiling*
    Arabic guard running the Turkish arms — the exact defect this issue
    exists to remove, wearing a valid sign-off, because every other check
    reads the document's own locale and the document was honest.
    """
    misfiled = sorted(
        f"{safe_code(key)}->{safe_code(document.locale)}"
        for key, document in GUARD_LEXICONS.items()
        if key != document.locale
    )
    if misfiled:
        raise LocaleHasNoSignedLexicon(
            "a guard lexicon is filed under a language it was not written for, which "
            "is a guard for that language with somebody else's vocabulary: "
            f"{misfiled}"
        )


_the_table_files_every_lexicon_under_its_own_language()


def registered_guard_locales() -> tuple[str, ...]:
    """Every language a guard can be built for, in table order."""
    return tuple(GUARD_LEXICONS)


def guard_lexicon_for(locale: str) -> SignedGuardLexicon:
    """The signed lexicon for ``locale``, or a refusal that echoes nothing.

    A locale with no lexicon is refused here rather than given empty arms,
    because empty arms would return a clean verdict on every sentence and a
    clean verdict is read downstream as *checked*.
    """
    if locale not in GUARD_LEXICONS:
        raise LocaleHasNoSignedLexicon(
            f"no PolicyGuard lexicon is written for locale {safe_code(locale)}; this "
            f"build guards {', '.join(registered_guard_locales())}. Invariant 2's "
            "vocabulary is Turkish and transfers to no other language, so a guard "
            "for another one would report clean on anything (HUMAN_BLOCKERS HB-C19 "
            "names the clinician who would have to sign one; HB-O5 names the language)"
        )
    return compile_guard_lexicon(GUARD_LEXICONS[locale])
