"""INT-253 — the localization completeness gate.

The backlog names this file (``tests: [tests/release/test_i18n_complete.py]``)
and its acceptance is two clauses: *"i18n lint fails on missing keys; clinical
tr reviewed flag enforced"*. The issue title fixes the shipped set —
*"tr 100 percent, en 100 percent; ar planned P3 with RTL audit"* — so Arabic is
**not** delivered here; what is delivered is a gate that refuses to let an
``ar`` catalogue appear without the RTL audit that plan requires.

Why a Python test over TypeScript source, when a vitest suite already sits next
to the catalogues: ``apps/mobile/src/lib/i18n.test.ts`` can only assert things
about the two objects it imports — parity, non-emptiness, casing. Three of the
four completeness properties are properties of the *tree*, not of the objects:

  * a key defined and never used is invisible to anything that only imports the
    catalogue;
  * a user-visible string hardcoded in a screen is, by construction, not in the
    catalogue at all;
  * the ``[REVIEW]`` marker lives in a source comment, which no import sees.

So the gate reads the source. It is the same shape as
``tests/mobile/test_crash_scrub.py``: recover a property mechanically from the
tree, and record the exceptions here where widening them is visible in review.

**What this gate fixes versus what it flags.** Mechanical drift — a missing
mirror, an orphan, a hardcoded string — is fixed in the same change and the
gate then holds the tree at zero. Register and readability findings are
*recorded*, not rewritten: changing thirty-four patient-facing Turkish strings
from the short imperative to the doubled-polite one is a copy decision for the
owner of files/00 §2, not a lint autofix, and a half-applied register reads
worse than a consistent one. The recorded inventories below are therefore the
flag list. They are asserted by exact equality, so a new violation fails the
build and a fixed one has to be struck from the record — the same "may only
shrink" discipline ``scripts/ci/no_placeholders_allow.txt`` carries.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from intake_platform.locale import (
    DEFAULT_LOCALE,
    check_catalogue_completeness,
    enabled_locales,
    offerable_app_locales,
    offerable_intake_locales,
    registration,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicons.tr import B1_MAX_WORDS_PER_SENTENCE
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    Violation,
    policy_guard_for,
)

REPO = Path(__file__).resolve().parents[2]
MOBILE = REPO / "apps" / "mobile" / "src"
I18N = MOBILE / "lib" / "i18n"

#: The shipped set. files/00 §2 makes Turkish the source of truth and English
#: its mirror; INT-253's title plans `ar` for P3 *behind an RTL audit*, so a
#: third catalogue appearing here is a gate failure until that audit exists.
SHIPPED_LOCALES = ("tr", "en")
PLANNED_LOCALES = ("ar",)

#: Scripted protocol questions, red-flag scripts and instrument items are spoken
#: verbatim (invariant 10). This gate reads them for parity and never for
#: register or readability — a paraphrase there is a defect, not a fix.
SCRIPTED_PREFIXES = ("intake.q.", "intake.opt.", "intake.hpi.")

# --- the recorded inventories --------------------------------------------------------

#: Patient-facing clinical or legal sentences. tr.ts's own header declares the
#: convention — *"marked [REVIEW] — they ship to production only from
#: docs/legal/strings.yaml with clinician/counsel sign-off (invariant 18); here
#: they gate the dev shell"*. Enforcing it means two things: the marked set is
#: exactly this set (no clinical line loses its flag, no ordinary line gains
#: one), and **en carries the same marks**, because a reviewer reading only the
#: English catalogue must see the same three lines called out.
REVIEW_FLAGGED_KEYS = frozenset(
    {
        "app.disclaimer",
        "review.provenance",
        "review.healthProvenance",
    }
)

#: Keys no screen renders that are nonetheless **required by a landed issue's
#: acceptance test** — here ``apps/mobile/e2e/voice.spec.ts``, which asserts
#: INT-103's mic-permission and session-state copy exists in both catalogues
#: and says why-before-prompt as the stores require.
#:
#: They are the one honest exception to "delete an orphan". Deleting them would
#: un-deliver an accepted issue, and the defect they expose is not a
#: localization defect at all: ``lib/livekit/session.ts`` really does enter
#: ``connecting``, ``reconnecting``, ``backgrounded`` and ``interrupted``, and
#: no surface tells the patient about any of them. A patient whose voice visit
#: drops sees nothing. Same for the pre-permission primer: the copy that the
#: store rules ask for exists and nothing shows it.
#:
#: Flagged for the mobile owner as a product gap, not fixed here — building two
#: surfaces is not this issue's scope. Wire them and strike them from this set.
UNWIRED_ACCEPTANCE_KEYS = frozenset(
    {
        "voice.mic.why",
        "voice.mic.cta",
        "voice.mic.settingsHint",
        "voice.session.connecting",
        "voice.session.reconnecting",
        "voice.session.paused",
        "voice.session.interrupted",
        "voice.session.weakLink",
        "voice.session.ended",
    }
)

#: Modules that legitimately hold user-visible text outside the catalogue, each
#: with the reason it is not a localization defect. Nothing else may.
HARDCODED_EXEMPT = {
    "lib/taxonomy/branches.ts": (
        "`nameTr` is the taxonomy's own `name_tr`, projected verbatim from "
        "packages/protocols/taxonomy/branches.yaml and pinned field-for-field by "
        "branches.test.ts. Copying it into the catalogue would create a second "
        "source of truth for a name the served feed also sends."
    ),
    "lib/dev/accounts.ts": (
        "Synthetic demo accounts behind `__DEV__`, compiled out of release "
        "builds. Fixture data, not product copy."
    ),
    "lib/taxonomy/mhrsSms.ts": (
        "A Turkish character class inside the MHRS-message parser's regex. It "
        "is matched against text the patient pastes and is never rendered."
    ),
    "lib/taxonomy/turkishDates.ts": (
        "INT-400: the twelve Turkish month names and the I/İ fold of the "
        "server's `turkish_dates.TURKISH_MONTHS` and `fold_tr`, ported so the "
        "device reads a pasted date by the server's rule. They are matched "
        "against what a message printed and are never rendered. The server "
        "module creates no tr key for the same table, for the same reason."
    ),
}

#: Instructional prose and form labels carrying the SHORT imperative (`-in`)
#: where files/00 §2 asks for the doubled-polite one (`-iniz`): *"siz
#: throughout, -in for short in-flow buttons, -iniz for instructional prose and
#: form labels"*. tr.ts's header claims this split; the catalogue does not
#: implement it — every imperative in it is short-form, including the thirty-four
#: below, and there is not one `-iniz` verb in the file.
#:
#: Flagged, not rewritten. Owner: the files/00 §2 copy owner via the
#: clinical-reviewer subagent. Two things make this a decision rather than a
#: fix: the nineteen `a11y.*Hint` strings are what VoiceOver speaks, where
#: brevity is itself an accessibility property, and a partial application would
#: leave the app switching register between screens.
PROSE_REGISTER_FINDINGS = frozenset(
    {
        # INT-246: __DEV__-only diagnostic copy, never patient-facing.
        # Same short-imperative class as the entries below — INT-248 fixed
        # the PolicyGuard patterns, not the separate -iniz prose rule, so
        # this one legitimately still stands.
        "devVoice.hint",
        "a11y.backHint",
        "a11y.closeHint",
        # INT-247: same class as the 34 above — short imperative in
        # instructional prose, consistent with the catalogue while the -iniz
        # question is one decision for the copy owner.
        "a11y.carried.hint",
        "a11y.companion.ackHint",
        "a11y.companion.roleHint",
        "a11y.companion.speakerHint",
        "a11y.companion.thirdPartyHint",
        "a11y.confirmHint",
        "a11y.consent.rowHint",
        "a11y.consent.switchHint",
        "a11y.dialogue.bargeInHint",
        "a11y.dialogue.exitHint",
        "a11y.dialogue.sectionsHint",
        "a11y.dialogue.stopHint",
        "a11y.notifications.quietHint",
        "a11y.notifications.switchHint",
        "a11y.openHint",
        "a11y.selectHint",
        "a11y.shareHint",
        "a11y.typedHint",
        "auth.otp.body",
        "auth.phone.hint",
        "companion.speaker.footer",
        "consent.entry.sub",
        "consent.stale.body",
        "dialogue.entryBody",
        "dialogue.listeningHint",
        "dialogue.speakingHint",
        "records.needVisit.body",
        "records.offline.body",
        "review.intro",
        "visits.new.dateHint",
        "visits.new.hint",
        "visits.new.smsHint",
        "wellbeing.intro",
        # INT-143 (kiosk mode) and INT-311 (Doctor Link issue sheet): the same
        # short-imperative class as the entries above ("girin", "yazın"),
        # merged while CI was billing-blocked and recorded by INT-346 rather
        # than rewritten — a lone `-iniz` would trip the opposite gate and split
        # the register mid-screen. Awaiting clinical-reviewer register decision.
        "kiosk.exit.body",
        "kiosk.lock.body",
        "kiosk.pin.hint",
        "shares.issue.recipient.hint",
        # INT-370 (INT-354 slice S3, int-demo 148a7dbd): the visits-calendar
        # day hint, written before this gate existed, in the same "…için iki
        # kez dokunun." form as every sibling a11y hint above. Recorded, not
        # rewritten, for the same reason (build-source dea9bb8a recorded it
        # first). Awaiting clinical-reviewer register decision.
        "a11y.visits.dayHint",
    }
)

#: Sentences above the project's own B1 bound (``B1_MAX_WORDS_PER_SENTENCE``,
#: imported rather than restated so there is one number). Flagged, not
#: rewritten: this is the product's own description line and splitting it is a
#: copy decision.
#:
#: INT-588 struck the one entry, ``welcome.body``. It was not rewritten for
#: length: its "sesli ya da yazılı olarak" clause was false in a release build,
#: which has no voice, and removing it brought the sentence to 12 words.
B1_LENGTH_FINDINGS: frozenset[str] = frozenset()

#: What the canonical guard — the one invariant 2 names — says about the
#: catalogue. Every entry here is a **guard defect, not a copy defect**: the
#: catalogue sentence is correct and PolicyGuard mis-classifies it. They are
#: recorded because `services/**` is out of this issue's scope and because a
#: guard that drops "Devam edin" is a live problem for the Talker, not a
#: cosmetic one. Owner: services/voice-runtime, via the runtime-reviewer.
#:
#: Read as (violation class, key):
#:   register  — ``_SEN`` matches ``\w+(?:din|sın|sin)\b``, which is the polite
#:               imperative ``edin``/``gidin`` and the third-person optative
#:               ``ulaşsın``/``eklensin``, not second-person singular.
#:   treatment — ``bırakın``/``kullanın`` anchored to the clinical sense, here
#:               used of a date field, an app version and the service itself.
#:   diagnosis — ``\btanı\s+koy`` matches the *negated* disclaimer
#:               "Önvizit tanı koymaz", which is the sentence that exists to deny
#:               diagnosis.
#:   multi_question — one question whose subject is set off by a comma.
#:   jargon    — the length arm of the same check; see B1_LENGTH_FINDINGS.
POLICYGUARD_FINDINGS: frozenset[tuple[str, str]] = frozenset()
# INT-588 struck the last pair, ("jargon", "welcome.body"): the survivor of
# INT-248 that INT-253's B1 audit had also flagged (17 words against a 15-word
# bound). Its voice clause was false in a release build, and without it the
# sentence is 12 words, so the length arm no longer fires.
# INT-248 emptied this. All 22 recorded pairs were guard false positives, and
# fixing the guard's Turkish morphology resolved every one — including
# ("diagnosis", "app.disclaimer"), which was the sentence that exists to
# SATISFY invariant 2 being reported as a diagnosis claim. The set may only
# shrink, so a new pair now means clinical language really did enter patient
# copy.

# --- parsing -------------------------------------------------------------------------

#: One catalogue entry. The catalogues wrap long values onto the following line,
#: so the value may start after the newline; nothing else about their shape is
#: assumed, and `test_the_parser_sees_every_entry` fails loudly if a future
#: value takes a form this does not read (a template literal, a concatenation).
_ENTRY = re.compile(r'^  "([^"]+)":\s*\n?\s*("(?:[^"\\]|\\.)*"),?\s*$', re.M)
_KEY_LINE = re.compile(r'^  "([^"]+)":', re.M)

#: Every string literal in a module, used to decide whether a key is referenced.
#: Keys reach `t()` directly and also travel as constants (`kickerKey=`, notice
#: maps, option tables), so the reference test asks the weaker, honest question:
#: does the key appear anywhere in the shipped tree?
_STRING_LITERAL = re.compile(r'"((?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+)"')

#: A `[REVIEW]` marker and the key it sits above.
_REVIEW_BLOCK = re.compile(r'^\s*//\s*\[REVIEW\][^\n]*\n\s*"([^"]+)":', re.M)


def _strip_comments(text: str) -> str:
    """Comments are prose about the code, not shipped strings."""
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|[^:])//.*$", r"\1", without_blocks)


def _catalogue(locale: str) -> dict[str, str]:
    text = (I18N / f"{locale}.ts").read_text(encoding="utf-8")
    return {m.group(1): json.loads(m.group(2)) for m in _ENTRY.finditer(text)}


def _catalogue_order(locale: str) -> list[str]:
    return _KEY_LINE.findall((I18N / f"{locale}.ts").read_text(encoding="utf-8"))


def _shipped_sources() -> list[Path]:
    """Every module the app ships: the catalogues and the colocated suites out."""
    return sorted(
        path
        for path in MOBILE.rglob("*.ts*")
        if ".test." not in path.name and I18N not in path.parents
    )


def _is_scripted(key: str) -> bool:
    return key.startswith(SCRIPTED_PREFIXES)


def _sentences(guard: PolicyGuard, value: str) -> tuple[str, ...]:
    return guard.sentences(value)


@pytest.fixture(scope="module")
def tr() -> dict[str, str]:
    return _catalogue("tr")


@pytest.fixture(scope="module")
def en() -> dict[str, str]:
    return _catalogue("en")


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


# --- the shipped set -------------------------------------------------------------------


#: Modules in ``lib/i18n/`` that are not catalogues. Named rather than
#: pattern-matched, so a new file has to be classified consciously: a third
#: catalogue must not be able to slip in by being called something else.
#:
#: ``locale`` is INT-296's registry and resolver — which locales this build may
#: OFFER, which is a different question from which catalogues exist. `en.ts`
#: existing is exactly the case that makes the distinction load-bearing: it is
#: the reviewer's mirror of the Turkish source of truth, and it is deliberately
#: NOT a registered session locale.
NON_CATALOGUE_MODULES: Final = frozenset({"index", "locale", "locale.test"})


def test_exactly_the_shipped_locales_have_a_catalogue() -> None:
    """`ar` is P3 *behind an RTL audit* (INT-253 title). A catalogue appearing
    without that audit would ship an untested bidi surface, so it fails here."""
    present = sorted(
        path.stem for path in I18N.glob("*.ts") if path.stem not in NON_CATALOGUE_MODULES
    )
    assert present == sorted(SHIPPED_LOCALES), (
        f"catalogues on disk: {present}. Adding {PLANNED_LOCALES} needs the RTL "
        "audit INT-253 plans for P3 — a mirrored catalogue is not the whole job."
    )
    index = (I18N / "index.ts").read_text(encoding="utf-8")
    assert 'availableLocales: readonly Locale[] = ["tr", "en"]' in index


def test_no_rtl_affordance_is_claimed_before_the_audit() -> None:
    """The other half of the same promise: nothing in the app may already
    behave as if a bidi locale were supported."""
    for path in _shipped_sources():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        for token in ("I18nManager", "forceRTL", "allowRTL", '"rtl"', "isRTL"):
            assert token not in code, (
                f"{path.relative_to(MOBILE)} reaches {token!r}: RTL support is "
                "planned for P3 with an audit, and a half-wired affordance is "
                "worse than none"
            )


def test_the_parser_sees_every_entry() -> None:
    """A value shape this file cannot read would silently drop keys from every
    assertion below, so the count is checked against the raw key lines."""
    for locale in SHIPPED_LOCALES:
        parsed = _catalogue(locale)
        lines = _catalogue_order(locale)
        assert len(parsed) == len(lines), (
            f"{locale}.ts: parsed {len(parsed)} of {len(lines)} entries — a value "
            "takes a form this gate does not read (a template literal or a "
            "concatenation). Add the shape to _ENTRY rather than to the catalogue."
        )
        assert len(set(lines)) == len(lines), f"{locale}.ts has a duplicate key"


# --- completeness ----------------------------------------------------------------------


def test_every_key_exists_in_both_catalogues(tr: dict[str, str], en: dict[str, str]) -> None:
    """Invariant 5: tr is the source of truth, and en mirrors it key-for-key."""
    missing_en = sorted(set(tr) - set(en))
    missing_tr = sorted(set(en) - set(tr))
    assert not missing_en, f"defined in tr, missing from en: {missing_en}"
    assert not missing_tr, (
        f"defined in en with no tr key: {missing_tr}. Turkish is the source of "
        "truth — an English-first string is the defect, not the missing mirror."
    )


def test_the_two_catalogues_keep_the_same_order(tr: dict[str, str]) -> None:
    """Not cosmetic. Five parallel branches appending their own block is exactly
    how a mirror silently stops being reviewable side by side."""
    assert _catalogue_order("en") == _catalogue_order("tr")


def test_no_value_is_empty(tr: dict[str, str], en: dict[str, str]) -> None:
    for key, value in tr.items():
        assert value.strip(), f"tr[{key}] is empty"
        assert en[key].strip(), f"en[{key}] is empty"


#: Keys whose two catalogues are IDENTICAL on purpose, each for a reason that
#: is a property of the value rather than of the translation:
#:
#: - ``app.name`` and ``a11y.speaker.agent`` are the product's own name;
#: - (INT-346) the ``lang.tr`` / ``lang.en`` endonym keys left with INT-301,
#:   which reads each language's endonym from the locale registry instead of
#:   a catalogue label; the orphaned keys were deleted, so their exemption goes;
#: - the SI unit symbols (INT-282) are locale-invariant by definition. BIPM
#:   fixes ``cm`` and ``kg`` as symbols, not abbreviations of a word, so a
#:   "translated" unit would be WRONG rather than merely different — and the
#:   symbol still lives in the catalogue because invariant 22 makes number and
#:   unit one atom, which needs the unit to have a key.
IDENTICAL_BY_NATURE: Final[frozenset[str]] = frozenset(
    {
        "app.name",
        "a11y.speaker.agent",
        "intake.unit.cm",
        "intake.unit.kg",
    }
)


def test_no_english_value_is_left_in_turkish(en: dict[str, str], tr: dict[str, str]) -> None:
    """An untranslated mirror is a missing key that happens to have a value.
    Product names, endonyms and SI unit symbols are the honest exceptions."""
    untranslated = {
        key for key, value in en.items() if value == tr[key] and key not in IDENTICAL_BY_NATURE
    }
    assert not untranslated, f"en still carries the Turkish string for: {sorted(untranslated)}"


def test_every_identical_by_nature_key_really_is_identical() -> None:
    """The exemption list may not rot into a place to hide a missing
    translation: a key that no longer needs the exemption loses it."""
    tr_catalogue, en_catalogue = _catalogue("tr"), _catalogue("en")
    for key in sorted(IDENTICAL_BY_NATURE):
        assert key in tr_catalogue, f"{key} is exempted but no longer exists"
        assert tr_catalogue[key] == en_catalogue[key], (
            f"{key} now differs between catalogues; drop its exemption"
        )


def _orphans(tr: dict[str, str]) -> set[str]:
    referenced: set[str] = set()
    for path in _shipped_sources():
        referenced |= set(_STRING_LITERAL.findall(path.read_text(encoding="utf-8")))
    return {key for key in tr if key not in referenced}


def test_every_key_is_referenced_by_shipped_code(tr: dict[str, str]) -> None:
    """A key nothing renders is dead weight that still has to be translated,
    reviewed and kept in register. The catalogue is what ships, not a backlog:
    copy for a screen that does not exist yet belongs in the branch that builds
    the screen, where git can hand it back.

    Only the *shipped* tree counts as a reference. A key held alive by its own
    test — the case ``UNWIRED_ACCEPTANCE_KEYS`` records — is still not rendered
    to anybody, and calling that "used" is how a missing screen stays missing."""
    orphans = sorted(_orphans(tr) - UNWIRED_ACCEPTANCE_KEYS)
    assert not orphans, (
        f"{len(orphans)} catalogue keys are never referenced: {orphans}. Wire the "
        "key to its screen or delete it — an unused string is not localized, it "
        "is just carried."
    )


def test_the_unwired_acceptance_keys_are_exactly_the_recorded_ones(tr: dict[str, str]) -> None:
    """The reserved set may only shrink, and every member has to still be both
    things it claims: unrendered, and required by an acceptance test."""
    assert _orphans(tr) & UNWIRED_ACCEPTANCE_KEYS == set(UNWIRED_ACCEPTANCE_KEYS), (
        "a reserved key is now rendered — strike it from UNWIRED_ACCEPTANCE_KEYS: "
        f"{sorted(set(UNWIRED_ACCEPTANCE_KEYS) - _orphans(tr))}"
    )
    assert UNWIRED_ACCEPTANCE_KEYS <= set(tr)
    # The claim is checked per family, not per key. `voice.session.*` is one
    # state machine's copy — connecting, reconnecting, paused, interrupted,
    # weak, ended — and the spec names three of the six. Reserving half a
    # family would leave the screen that eventually lands with three states to
    # write copy for and three to inherit, which is how registers diverge.
    # What the assertion has to prevent is the reservation outliving its
    # acceptance, and a family the spec no longer mentions at all does that.
    spec = (MOBILE.parent / "e2e" / "voice.spec.ts").read_text(encoding="utf-8")
    families = {key.rsplit(".", 1)[0] for key in UNWIRED_ACCEPTANCE_KEYS}
    unclaimed = sorted(family for family in families if f'"{family}.' not in spec)
    assert not unclaimed, (
        f"{unclaimed} are reserved as acceptance-bound but no longer appear in "
        "e2e/voice.spec.ts — nothing requires them now, so delete them"
    )


# --- the clinical review flag ------------------------------------------------------------


def test_the_clinical_review_flag_is_carried_by_both_catalogues() -> None:
    """The acceptance's second clause. tr.ts declares that patient-facing
    clinical and legal sentences are marked ``[REVIEW]``; a marker present only
    in Turkish tells a reviewer of the English catalogue nothing."""
    for locale in SHIPPED_LOCALES:
        text = (I18N / f"{locale}.ts").read_text(encoding="utf-8")
        marked = frozenset(_REVIEW_BLOCK.findall(text))
        assert marked == REVIEW_FLAGGED_KEYS, (
            f"{locale}.ts marks {sorted(marked)}; the recorded clinical set is "
            f"{sorted(REVIEW_FLAGGED_KEYS)}. Adding or removing a mark is a "
            "clinical/counsel decision (invariant 18) and is recorded here."
        )


def test_every_review_flagged_key_exists(tr: dict[str, str]) -> None:
    assert REVIEW_FLAGGED_KEYS <= set(tr)


# --- hardcoded strings -------------------------------------------------------------------

#: Props whose value a patient reads or a screen reader speaks. Both the JSX
#: form (`label="…"`) and the object form (`title: "…"`) — a notice table is
#: just as visible as an attribute.
#:
#: React Native's hint-text prop is spelled with a leading character class so
#: this line does not itself trip the no_placeholders gate, whose token list
#: contains that word. The class also catches a capitalised prop of the same
#: name on a wrapper component, so it costs nothing.
_VISIBLE_PROP = re.compile(
    r"\b(label|title|[pP]laceholder|accessibilityLabel|accessibilityHint|"
    r"accessibilityValue|footer|header|message)\s*[=:]\s*\{?\s*[\"']([^\"'\n]+)[\"']"
)
#: A JSX text node: characters between tags that are neither an expression nor
#: markup. Component text in this app is always `{t("…")}`, so any letter here
#: is copy that never reached the catalogue. The excluded characters keep a
#: comparison inside a conditional (`bookable.length > shown.length ? (`) from
#: reading as a text node; every real text node is plain prose.
_JSX_TEXT = re.compile(r">\s*([A-Za-zÇĞİÖŞÜçğıöşü][^<>{}\n?()=&|;\[\]]*?)\s*<")
#: The catch-all the first two miss: Turkish copy reaching the screen by some
#: route this gate does not model. A letter that exists only in Turkish is a
#: reliable marker — English identifiers, style tokens and route names have
#: none, so this fires on prose and on nothing else.
_TURKISH_LITERAL = re.compile(r"[\"']([^\"'\n]*[çğıöşüÇĞİÖŞÜ][^\"'\n]*)[\"']")


def _hardcoded(path: Path) -> Iterator[str]:
    code = _strip_comments(path.read_text(encoding="utf-8"))
    for match in _VISIBLE_PROP.finditer(code):
        yield f"{match.group(1)}={match.group(2)!r}"
    for match in _TURKISH_LITERAL.finditer(code):
        yield f"turkish literal {match.group(1)!r}"
    if path.suffix == ".tsx":
        for match in _JSX_TEXT.finditer(code):
            yield f"text node {match.group(1)!r}"


def test_no_user_visible_string_is_hardcoded_outside_the_catalogue() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _shipped_sources():
        relative = path.relative_to(MOBILE).as_posix()
        if relative in HARDCODED_EXEMPT:
            continue
        found = list(_hardcoded(path))
        if found:
            offenders[relative] = found
    assert not offenders, (
        f"user-visible strings outside the catalogue: {offenders}. Invariant 5 "
        "makes the tr catalogue the source of truth; a literal in a screen has "
        "no key, so it can never be mirrored, reviewed or kept in register."
    )


@pytest.mark.parametrize("relative", sorted(HARDCODED_EXEMPT))
def test_every_hardcoded_exemption_is_still_load_bearing(relative: str) -> None:
    """An exemption that no longer applies is a hole in the scan. Each one has
    to keep earning its place, so the list only shrinks."""
    path = MOBILE / relative
    assert path.exists(), f"{relative} is gone; drop its exemption"
    assert list(_hardcoded(path)), (
        f"{relative} no longer holds any user-visible literal; drop its exemption"
    )


# --- register ----------------------------------------------------------------------------

#: `sen` in its own right: the bare pronoun and its cases. The verb endings are
#: deliberately not matched here — `-sın/-din` are also the third-person
#: optative and the polite imperative, which is the very confusion recorded in
#: POLICYGUARD_FINDINGS. A gate that repeats that mistake would train people to
#: ignore it.
_SEN = re.compile(r"\b(?:sen|sana|seni|senin|sende|senden|seninle)\b", re.IGNORECASE)


def test_no_turkish_string_addresses_the_patient_as_sen(tr: dict[str, str]) -> None:
    """files/00 §2: *"`siz` to a 25-year-old costs mild stiffness; `sen` to a
    72-year-old costs the session"*. `sen` is reachable only by mirroring what
    the patient said, never from the catalogue."""
    offenders = {key: value for key, value in tr.items() if _SEN.search(value)}
    assert not offenders, f"`sen` register in patient copy: {offenders}"


#: Short-form polite imperatives the catalogue uses. The doubled-polite form is
#: this plus -iz/-ız/-uz/-üz (`edin` → `ediniz`).
_SHORT_IMPERATIVE = re.compile(
    r"\b(?:edin|girin|verin|deneyin|seçin|açın|kapatın|bırakın|yazın|dokunun|okuyun|"
    r"arayın|tutun|gidin|ekleyin|gönderin|onaylayın|düzenleyin|isteyin|yapın|bekleyin|"
    r"söyleyin|yanıtlayın|görün|başlayın|kullanın|paylaşın|konuşun|dinleyin|silin|"
    r"çıkın|dönün|geçin|kaydedin|yükleyin|indirin|yapıştırın|belirtin|durdurun|"
    r"tamamlayın|inceleyin)\b",
    re.IGNORECASE,
)
#: The catalogue's own naming convention for instructional prose and form
#: labels, which is what files/00 §2 binds `-iniz` to. `note` is deliberately
#: absent: `visit.reviewNote` is a button and `welcome.devNote` is prose, so the
#: segment does not discriminate.
_PROSE_KEY = re.compile(r"(?i)[a-z]*(?:body|hint|intro|info|footer|sub|why)$")


def _prose_register_offenders(tr: dict[str, str]) -> set[str]:
    return {
        key
        for key, value in tr.items()
        if not _is_scripted(key)
        and _PROSE_KEY.search(key.rsplit(".", 1)[-1])
        and _SHORT_IMPERATIVE.search(value)
    }


def test_the_prose_register_findings_are_exactly_the_recorded_ones(tr: dict[str, str]) -> None:
    """files/00 §2 splits the imperative by context: `-in` on short in-flow
    buttons, `-iniz` on instructional prose and form labels. tr.ts's header
    claims that split and the catalogue does not implement it anywhere.

    These are flagged, not rewritten — see PROSE_REGISTER_FINDINGS. What the
    gate holds is the boundary: a new prose string may not join them."""
    found = _prose_register_offenders(tr)
    assert found == set(PROSE_REGISTER_FINDINGS), (
        f"new prose-register findings: {sorted(found - PROSE_REGISTER_FINDINGS)}; "
        f"resolved: {sorted(PROSE_REGISTER_FINDINGS - found)}. New instructional "
        "prose uses `-iniz` (files/00 §2); the recorded set may only shrink."
    )


def test_no_short_in_flow_control_uses_the_doubled_polite_form(tr: dict[str, str]) -> None:
    """The other direction of the same rule, and the one with no recorded
    exceptions: a button never says `Ediniz`."""
    formal = re.compile(
        r"\b(?:"
        + "|".join(
            stem + suffix
            for stem, suffix in (
                ("ed", "iniz"),
                ("gir", "iniz"),
                ("ver", "iniz"),
                ("deney", "iniz"),
                ("seç", "iniz"),
                ("aç", "ınız"),
                ("yaz", "ınız"),
                ("okuy", "unuz"),
                ("dokun", "unuz"),
                ("gönder", "iniz"),
                ("ekley", "iniz"),
                ("tıkl", "ayınız"),
            )
        )
        + r")\b",
        re.IGNORECASE,
    )
    offenders = {key: value for key, value in tr.items() if formal.search(value)}
    assert not offenders, (
        f"doubled-polite imperative found: {offenders}. Until the register "
        "decision in PROSE_REGISTER_FINDINGS is taken, the catalogue is "
        "uniformly short-form; a lone `-iniz` is drift in the other direction."
    )


# --- mid-word truncation (00 §2, INT-260) ------------------------------------------------

#: The negation and privative suffixes files/00_STATE.md §2 names, verbatim:
#: "Never truncate mid-word in Turkish. Compile-time negation/privative
#: no-truncate list: -m(ı|i|u|ü)yor, -maz/-mez, -sız/-siz/-suz/-süz,
#: -madan/-meden. `word-break: break-all` banned app-wide."
#:
#: The hazard is not cosmetic and the row states it: `ağrımıyor` truncated to
#: `ağrım…` turns "it doesn't hurt" into "my pain" — the negation is carried by
#: the SUFFIX, so cutting the tail of a Turkish word can inverse a clinical
#: fact. The row also says the scan found exactly one such token, "which is
#: precisely why review will miss it and it must be a build gate". This is that
#: gate; it did not exist before INT-260.
_NO_TRUNCATE_SUFFIX = re.compile(
    r"(?:m[ıiuü]yor|maz|mez|s[ıiuü]z|madan|meden)\b",
    re.IGNORECASE,
)

#: Every prop or style that can cut a rendered string short. React Native has
#: no CSS, so `word-break` is not reachable at all; what IS reachable is
#: `numberOfLines` (with its implicit tail ellipsis), an explicit
#: `ellipsizeMode`/`lineBreakMode`, and `adjustsFontSizeToFit`, which shrinks
#: rather than cuts but is the same "make it fit by changing the words'
#: appearance" move and is banned by 02 §8.2's no-harder-clamping rule.
_TRUNCATION_AFFORDANCES = (
    "numberOfLines",
    "ellipsizeMode",
    "lineBreakMode",
    "adjustsFontSizeToFit",
    "word-break",
    "break-all",
)


def test_no_turkish_string_can_be_truncated_mid_word() -> None:
    """files/00 §2's ruling, enforced by ABSENCE.

    The app truncates nowhere, so no Turkish word can lose its negation suffix
    — and that is a much stronger guarantee than auditing each render site,
    because it cannot drift. A future screen that genuinely needs to shorten a
    string has to come past this test and say why in review; there is no
    correct way to ellipsize a Turkish clinical sentence, so the honest answers
    are a shorter string or more room."""
    offenders: dict[str, list[str]] = {}
    for path in _shipped_sources():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        hits = [token for token in _TRUNCATION_AFFORDANCES if token in code]
        if hits:
            offenders[path.relative_to(MOBILE).as_posix()] = hits
    assert not offenders, (
        f"truncation affordances reached: {offenders}. files/00 §2: 'Never "
        "truncate mid-word in Turkish' — `ağrımıyor` cut to `ağrım…` inverts "
        "the clinical fact. Give the string room or shorten the copy."
    )


def test_the_truncation_hazard_class_is_not_empty(tr: dict[str, str]) -> None:
    """The gate above is only worth anything while the catalogue actually holds
    words whose meaning lives in a suffix. This asserts the hazard is real, so
    a future refactor cannot quietly empty the class and make the ban vacuous —
    the same discipline `test_scripted_protocol_text_is_never_measured...`
    applies to its own exclusion."""
    at_risk = {key for key, value in tr.items() if _NO_TRUNCATE_SUFFIX.search(value)}
    assert at_risk, (
        "no negation or privative suffix appears anywhere in the catalogue; "
        "either the copy changed shape or the pattern stopped matching Turkish"
    )


# --- readability -------------------------------------------------------------------------


def test_the_b1_length_findings_are_exactly_the_recorded_ones(
    tr: dict[str, str], guard: PolicyGuard
) -> None:
    """B1 proxy, using the runtime's own bound so there is one number in the
    project. Scripted protocol text is excluded: invariant 10 makes it verbatim,
    so a long scripted question is a finding against the pack, never a rewrite
    here."""
    over: set[str] = set()
    for key, value in tr.items():
        if _is_scripted(key):
            continue
        for sentence in _sentences(guard, value):
            if len(sentence.split()) > B1_MAX_WORDS_PER_SENTENCE:
                over.add(key)
    assert over == set(B1_LENGTH_FINDINGS), (
        f"above the B1 bound of {B1_MAX_WORDS_PER_SENTENCE} words: "
        f"new {sorted(over - B1_LENGTH_FINDINGS)}, resolved "
        f"{sorted(B1_LENGTH_FINDINGS - over)}"
    )


def test_scripted_protocol_text_is_never_measured_for_register_or_length(
    tr: dict[str, str],
) -> None:
    """The exclusion has to be real, not incidental: this asserts the catalogue
    still holds scripted keys, so a future refactor cannot quietly empty the
    class and make the exclusion vacuous."""
    scripted = {key for key in tr if _is_scripted(key)}
    assert len(scripted) > 100, "the scripted class is empty; the exclusion is vacuous"
    assert not scripted & set(PROSE_REGISTER_FINDINGS)
    assert not scripted & set(B1_LENGTH_FINDINGS)


# --- the canonical guard -------------------------------------------------------------------


def _policyguard_findings(tr: dict[str, str], guard: PolicyGuard) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for key, value in tr.items():
        for sentence in _sentences(guard, value):
            violation: Violation
            for violation in guard.inspect_sentence(sentence):
                found.add((violation.violation_class.value, key))
    return found


def test_the_catalogue_through_policyguard_matches_the_record(
    tr: dict[str, str], guard: PolicyGuard
) -> None:
    """Invariant 2 says patient-facing text passes PolicyGuard. Nothing ran the
    mobile catalogue through it until now, and doing so is worth more as a
    cross-check on the guard than on the copy: every finding recorded in
    POLICYGUARD_FINDINGS is the guard mis-reading a correct sentence.

    Recording them here means the guard's lexicon and the catalogue cannot drift
    apart unnoticed — a genuine diagnosis or treatment sentence entering the
    copy shows up as a new pair, and a fix in `services/voice-runtime` shows up
    as a resolved one."""
    found = _policyguard_findings(tr, guard)
    assert found == set(POLICYGUARD_FINDINGS), (
        f"new PolicyGuard findings: {sorted(found - POLICYGUARD_FINDINGS)}; "
        f"resolved: {sorted(POLICYGUARD_FINDINGS - found)}. A new pair is either "
        "clinical language entering patient copy — fix the copy — or a guard "
        "false positive, which is recorded here with the reason."
    )


# --- INT-296: the gate generalises from `tr` to every ENABLED locale --------------------
#
# Invariant 5 is not weakened by any of this. The rule was *"`tr` must exist"*;
# it becomes *"`tr` must exist AND every locale this build actually offers must
# be complete against it"*. `tr` stays required, stays the source of truth and
# stays the default.
#
# The subject of the generalised lint is the REGISTRY, not the set of files on
# disk. That is the whole distinction INT-296 draws: a catalogue existing is not
# a language being offered. `en.ts` is INT-253's reviewer mirror and is not a
# registered session locale, so it is held to parity by the tests above and is
# absent from the chooser — which is the honest state while HB-O5 has not named
# a second language and HB-C19 has not signed one.


def _registry_catalogues() -> dict[str, dict[str, str]]:
    """Every ENABLED locale's real catalogue, keyed by code."""
    return {code: _catalogue(code) for code in enabled_locales()}


def test_turkish_is_registered_and_is_the_default() -> None:
    """Invariant 5, asserted against the registry rather than assumed."""
    assert DEFAULT_LOCALE == "tr"
    assert DEFAULT_LOCALE in enabled_locales()


def test_every_enabled_locale_has_a_catalogue_on_disk() -> None:
    """Enabling a locale with no catalogue must fail the build, not fail the
    patient at the first screen that has no string for them."""
    missing = [code for code in enabled_locales() if not (I18N / f"{code}.ts").is_file()]
    assert not missing, f"registered with no catalogue: {missing}"


def test_every_enabled_locale_is_complete_against_turkish() -> None:
    """The generalised lint itself, run over the real tree by the same resolver
    the app uses — so the gate and the runtime cannot disagree about what
    'complete' means."""
    complaints = check_catalogue_completeness(_registry_catalogues())
    assert not complaints, "enabled locales are not complete:\n" + "\n".join(complaints)


def test_the_registrys_completeness_claim_matches_the_tree() -> None:
    """Both directions. A locale that CLAIMS completeness and is not must fail
    the build; a locale that is complete and does not claim it is a chooser
    entry silently withheld, which is a defect of its own."""
    catalogues = _registry_catalogues()
    reference = _catalogue(DEFAULT_LOCALE)
    for code in enabled_locales():
        actually_complete = not check_catalogue_completeness(
            {DEFAULT_LOCALE: reference, code: catalogues[code]}
        )
        claimed = registration(code).ui_catalogue_complete
        assert claimed == actually_complete, (
            f"{code} claims ui_catalogue_complete={claimed} and the tree says {actually_complete}"
        )


def test_the_chooser_offers_no_locale_this_gate_has_not_cleared() -> None:
    """The join between the build property and the runtime one: nothing may be
    offerable that is not enabled, and an intake locale is strictly narrower
    than an app locale because it speaks red-flag scripts."""
    assert set(offerable_app_locales()) <= set(enabled_locales())
    assert set(offerable_intake_locales()) <= set(offerable_app_locales())


def test_the_registry_ships_holding_only_turkish() -> None:
    """The issue's own last acceptance line, pinned where a widening edit is
    visible: HB-O5 (owner) names which languages, HB-C19 (clinician) signs what
    they say, HB-L23 (counsel) settles what a translated legal text is, and
    HB-L24 settles the instrument licences. Enabling one here would answer all
    four."""
    assert enabled_locales() == ("tr",)
