"""The clip catalogue — the compiler's manifest, read at the microphone end.

files/03 §4.2: *"Every ``ask_tr`` / ``confirm_tr`` / ``action_tr`` string in a
compiled protocol is pre-synthesised per voice at ``protocols compile --voice
<id>`` into Opus clips stored in MinIO and keyed by ``sha256(text_tr,
voice_id)``. ``protocol_next`` returns ``clip_id``; the Talker plays it instead
of calling TTS."*

The artefact consumed here is the compiler's own output (e),
``packages/protocols/dist/<pack>/clips.<voice>.json``, and :func:`clip_id_for`
recomputes the key with the same construction
``protocols.compile.emit_clips`` used to write it. The two sides therefore
agree by derivation rather than by convention — a drift in either would show
up as a cache miss on every clip, which is loud.

The **bytes** behind a ``clip_id`` come from :class:`ports.ClipStore`, whose
production implementation is ``packages/voice-clips`` (INT-060). That package
is not on this branch, so the service wires the port fail-closed and
``/readyz`` says so; see :mod:`intake_voice_runtime.app`.

Invariant 22 is enforced at load, not at speak time: a manifest entry carrying
a digit means the compiler's Turkish expansion did not run (or a manifest was
hand-edited), and the honest response is to refuse the whole catalogue rather
than to discover it one clip into a session.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

from clinical_schemas.common import FrozenModel
from protocols.dsl import clip_text_hash
from pydantic import Field

from intake_voice_runtime.talker.speech import NumeralOnTtsPathError, assert_no_numeral

__all__ = ["ClipCatalogue", "ClipNotCachedError", "ClipRef", "clip_id_for"]


class ClipNotCachedError(LookupError):
    """No clip exists for this text in this voice — a miss, never a guess."""


def clip_id_for(text_tr: str, voice_id: str) -> str:
    """``clip.<voice>.<sha256(text, voice)>`` — the compiler's own construction
    (``protocols.compile.emit_clips._clip_id``; files/03 §4.9.1 row 10)."""
    digest = hashlib.sha256(f"{text_tr}\x00{voice_id}".encode()).hexdigest()
    return f"clip.{voice_id}.{digest}"


class ClipRef(FrozenModel):
    """One manifest row, as the Talker needs it."""

    text_hash: str = Field(min_length=64, max_length=64)
    clip_id: str = Field(min_length=1)
    text_tr: str = Field(min_length=1)
    scripted: bool = Field(description="Paraphrase is never permitted here (invariant 10).")


class ClipCatalogue:
    """Text → clip, for exactly one voice."""

    def __init__(
        self,
        *,
        voice: str,
        resolved_protocol_hash: str,
        refs: dict[str, ClipRef],
    ) -> None:
        self.voice = voice
        self.resolved_protocol_hash = resolved_protocol_hash
        self._refs = refs

    def __len__(self) -> int:
        return len(self._refs)

    @classmethod
    def empty(cls, voice: str) -> ClipCatalogue:
        """A catalogue with no clips: every turn falls through to TTS, still
        verbatim. This is the state of a session whose pack has not been
        pre-synthesised (``make clips`` belongs to INT-060)."""
        return cls(voice=voice, resolved_protocol_hash="", refs={})

    @classmethod
    def load(cls, path: Path) -> ClipCatalogue:
        """Read one ``clips.<voice>.json`` emitted by ``protocols compile``."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        voice = str(payload["voice"])
        refs: dict[str, ClipRef] = {}
        for entry in payload["entries"]:
            if entry["voice"] != voice:
                raise ValueError(
                    f"clip manifest for voice {voice!r} carries an entry for "
                    f"{entry['voice']!r}: a clip is keyed by (text, voice) and a "
                    "mixed manifest would serve another voice's audio"
                )
            text_tr = str(entry["text_tr"])
            try:
                assert_no_numeral(text_tr)
            except NumeralOnTtsPathError as err:
                raise NumeralOnTtsPathError(
                    f"clip manifest {path.name} carries an unexpanded numeral — the "
                    f"compiler's Turkish expansion did not run (invariant 22): {err}"
                ) from err
            ref = ClipRef(
                text_hash=str(entry["text_hash"]),
                clip_id=str(entry["clip_id"]),
                text_tr=text_tr,
                scripted=bool(entry["scripted"]),
            )
            refs[ref.text_hash] = ref
        return cls(
            voice=voice,
            resolved_protocol_hash=str(payload["resolved_protocol_hash"]),
            refs=refs,
        )

    def get(self, text_tr: str) -> ClipRef | None:
        """The cached clip for this exact Turkish, or ``None``.

        Keyed on the NFC form, so the same *visible* Turkish always hits the
        same clip — ``protocols.dsl.clip_text_hash`` normalises identically.
        """
        return self._refs.get(clip_text_hash(unicodedata.normalize("NFC", text_tr)))

    def resolve(self, text_tr: str) -> ClipRef:
        ref = self.get(text_tr)
        if ref is None:
            raise ClipNotCachedError(
                f"no clip for this text in voice {self.voice!r}; the turn falls "
                "through to verbatim TTS"
            )
        return ref
