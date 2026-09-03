"""INT-299 — what a *translated* answer is, and what it must carry.

The clinician reads Turkish. The patient may not have spoken it. Printing the
clinician's phrase for a direct patient statement — ``hasta beyanı`` — over a
machine translation attributes to the patient a sentence they did not say.
That is the defect this module exists to make unrepresentable, and it takes
three values to do it.

**The original is the record; the rendering is the convenience.**
:class:`TranslatedText` carries the patient's own words verbatim and the
locale they were spoken in. It rides on the fact, beside the rendering the
note prints, so a surface that shows the translation is already holding the
original. A design where the original is recoverable only by re-running the
translator has lost it: a translator is a version, a revision and a set of
weights, and none of those is guaranteed to still exist when somebody asks
what the patient actually said.

**The translator is identified the way a model is.** files/03 §4.9.4 addresses
a model as ``model_id@revision`` and CLAUDE.md invariant 19 requires the
weights pinned by ``sha256``. A translation is a model output on the clinical
record, so it carries the same three facts plus the name a human uses for it.
:class:`TranslatorIdentity` refuses to be built without them — it does not
default, and it does not accept a value that cannot be a sha256. Nothing here
invents a hash: the check is a *shape* check, and the absence of any real
identity is why :data:`TRANSLATOR_REGISTRY` is empty.

**No translator is chosen here and no locale is registered.** Which languages
this product speaks is HB-O5's; who signs their clinical text is HB-C19's;
what a translated legal text legally *is* is HB-L23's; whether an instrument
survives the language is HB-L24's; and what KVKK category a stored locale
falls into once there is more than one is HB-L25's. Five humans stand between
this seam and a second language, and invariant 19 governs which translator may
exist at all. So the registry ships empty and :func:`translator` raises. That
is CLAUDE.md's shape for an open blocker: build the mechanism, wire the gate,
make it fail closed, leave the content empty.

**Invariant 6 rides on every refusal.** A source locale is a shape-checked
code and is safe in a message, a metric label or a log line; the text it
labels is not, and no error raised here ever contains it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import KW_ONLY, dataclass
from types import MappingProxyType
from typing import Final

from intake_platform.locale import DEFAULT_LOCALE, safe_code

__all__ = [
    "TRANSLATOR_REGISTRY",
    "TranslatedText",
    "TranslatorIdentity",
    "TranslatorUnidentified",
    "translator",
]

#: A sha256 as it is written down: 64 lowercase hex digits. This is a shape,
#: not a value — the module records hashes, it never produces one.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TranslatorUnidentified(ValueError):
    """No identifiable translator stands behind a translated line.

    Raised rather than rendered: an unattributed machine sentence on a
    clinical record is a sentence nobody can be asked about.
    """


@dataclass(frozen=True, slots=True)
class TranslatorIdentity:
    """Which model produced a rendering, in the form a model is pinned in.

    Four fields, none optional. ``name`` is what a human calls it, and the
    other three are what an auditor needs to fetch the same artefact again:
    :attr:`pinned_id` is files/03 §4.9.4's ``model_id@revision`` and
    ``sha256`` is invariant 19's weight hash.
    """

    name: str
    _: KW_ONLY
    model_id: str
    revision: str
    sha256: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("model_id", self.model_id),
            ("revision", self.revision),
        ):
            if not value.strip():
                raise TranslatorUnidentified(
                    f"a translator needs a {field_name}: a rendering on a clinical record "
                    "whose producer nobody can name is an unattributed machine sentence"
                )
        if "@" in self.model_id:
            raise TranslatorUnidentified(
                "model_id must not carry its own revision — `model_id@revision` is "
                "assembled once, from two fields, so two different revisions cannot be "
                "written on one line"
            )
        if not _SHA256.match(self.sha256):
            raise TranslatorUnidentified(
                "a translator's weights are pinned by a sha256 (64 lowercase hex digits, "
                "CLAUDE.md invariant 19); a value that cannot be one is not recorded as "
                "one, and a plausible hash is never written to make this pass"
            )

    @property
    def pinned_id(self) -> str:
        """files/03 §4.9.4's form: ``model_id@revision``."""
        return f"{self.model_id}@{self.revision}"


@dataclass(frozen=True, slots=True)
class TranslatedText:
    """The patient's own words, the language they said them in, and who
    rendered them.

    The Turkish the clinician reads is **not** stored here. It is already on
    the fact, as the fact's own lines, so the pair sits together with nothing
    that can drift between them: this value is the half a renderer would
    otherwise lose.
    """

    original: str
    _: KW_ONLY
    source_locale: str
    translator: TranslatorIdentity

    def __post_init__(self) -> None:
        # Every message below names shapes and codes only. `original` is the
        # patient's own sentence (invariant 6) and never reaches a message.
        if not self.original.strip():
            raise ValueError(
                "a translated line must retain the original it was translated from; "
                "an empty original is a line with no way back to what the patient said"
            )
        code = safe_code(self.source_locale)
        if code != self.source_locale:
            raise ValueError(
                "a source locale is a BCP-47-shaped tag, so that it is safe as a metric "
                f"label and a log field (got {code})"
            )
        if self.source_locale == DEFAULT_LOCALE:
            raise ValueError(
                f"{DEFAULT_LOCALE!r} is the language the note is written in, so a line "
                f"from {DEFAULT_LOCALE!r} is not a translation; marking the patient's own "
                "Turkish as a machine rendering is this issue's defect pointing the other way"
            )


#: **The translator registry.** Empty, deliberately.
#:
#: Registering one means a model has been chosen, and invariant 19 governs
#: that choice: open weights, commercially usable, licence-verified from the
#: raw LICENSE blob with ``licence_verified_at``, and pinned by
#: ``model_id@revision + sha256`` in the self-hosting registry. It also means a
#: language has been chosen (HB-O5) and its clinical text signed (HB-C19).
#: None of that has happened, so this holds nothing and the lookup refuses.
TRANSLATOR_REGISTRY: Final[Mapping[str, TranslatorIdentity]] = MappingProxyType({})


def translator(name: str) -> TranslatorIdentity:
    """The registered translator called ``name``, or a refusal.

    The refusal is the artefact, exactly as it is for files/03 §4.9.1 row 1 in
    :mod:`intake_voice_runtime.adapters.pins`: writing a revision and a sha256
    for a model nobody has chosen, served nowhere and licence-verified nowhere
    would be an invented value.
    """
    identity = TRANSLATOR_REGISTRY.get(name)
    if identity is None:
        raise TranslatorUnidentified(
            "no translator is registered in this build, so no line may be rendered as a "
            "translation. Registering one is CLAUDE.md invariant 19's work — open "
            "weights, a licence verified from the raw LICENSE blob, and "
            "`model_id@revision` + sha256 in the self-hosting registry — after HB-O5 has "
            "named the language and HB-C19 has named a clinician who reads it"
        )
    return identity
