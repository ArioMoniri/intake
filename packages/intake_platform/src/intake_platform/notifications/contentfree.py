"""INT-141 — proving a notification carries nothing about the patient.

Two scans, because they answer two different questions and each is weak
alone.

**Vocabulary closure** (:func:`outside_vocabulary`, :func:`assert_content_free`)
is the strong one: every token of a rendered payload must already appear in
the committed template corpus. It needs no list of forbidden words, so it
catches the symptom nobody thought of, the clinician's surname, the document
title and the appointment time alike — anything interpolated is, by
definition, a word the corpus does not have. This is the check that runs on
the way out of the dispatcher.

**Distinctive-term leakage** (:func:`leaked_terms`) is the one that can be
pointed at a specific patient's data — the branch label on her visit, the
value in her slot — and asked "does this text disclose her?". The subtlety
that makes it worth writing carefully: a branch label routinely shares a
word with generic copy. "Kadın Hastalıkları **ve** Doğum" shares "ve" with
every sentence in the catalogue. A scan that reports that shared word fires
on every message for every patient and is switched off within a week; a scan
that only looks for the whole phrase misses "Kadın" standing alone. So a
term leaks when the **whole phrase** appears, or when any of its tokens that
are **not already in the generic corpus** appears. A word that is in the copy
for everybody tells a reader nothing about anybody.

Invariant 6 rides along: a :class:`ContentLeak` names the template and how
many tokens escaped, never the tokens themselves. An exception message is a
log line, and a leak detector that logs the leak is not a detector.
"""

from __future__ import annotations

from collections.abc import Iterable

from intake_platform.notifications.catalogue import CORPUS_VOCABULARY, RenderedMessage
from intake_platform.notifications.folding import fold, tokens

__all__ = [
    "ContentLeak",
    "assert_content_free",
    "leaked_terms",
    "outside_vocabulary",
]


class ContentLeak(Exception):
    """A payload carried a word the committed corpus does not have."""


def outside_vocabulary(text: str, vocabulary: frozenset[str]) -> tuple[str, ...]:
    """Tokens of ``text`` absent from ``vocabulary``, first occurrence order,
    deduplicated."""
    seen: set[str] = set()
    offenders: list[str] = []
    for token in tokens(text):
        if token in vocabulary or token in seen:
            continue
        seen.add(token)
        offenders.append(token)
    return tuple(offenders)


def leaked_terms(
    text: str,
    terms: Iterable[str],
    *,
    vocabulary: frozenset[str] = CORPUS_VOCABULARY,
) -> tuple[str, ...]:
    """Which of ``terms`` this text discloses (see the module docstring for
    why "discloses" is not "contains a shared word")."""
    folded_text = fold(text)
    present = set(tokens(text))
    leaked: list[str] = []
    for term in terms:
        if fold(term) in folded_text:
            leaked.append(term)
            continue
        distinctive = [token for token in tokens(term) if token not in vocabulary]
        if any(token in present for token in distinctive):
            leaked.append(term)
    return tuple(leaked)


def assert_content_free(message: RenderedMessage) -> None:
    """The gate the dispatcher runs on every payload before a transport sees
    it. A template that grows an interpolation slot fails here, not in review.
    """
    offenders = len(outside_vocabulary(message.title, CORPUS_VOCABULARY)) + len(
        outside_vocabulary(message.body, CORPUS_VOCABULARY)
    )
    if offenders:
        # counts and the template key only — the offending words are, by
        # hypothesis, the patient's data (invariant 6)
        raise ContentLeak(
            f"template {message.template_key!r} ({message.locale.value}) rendered "
            f"{offenders} token(s) outside the committed corpus; a notification "
            f"body must be constant text, never an interpolation"
        )
