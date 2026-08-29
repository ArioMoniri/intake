"""INT-091 — the clip player: verbatim, digit-free, and write-free.

Three invariants meet on this path and each has its own section:

- **10** — scripted questions, red-flag action scripts and validated
  instruments are spoken verbatim from ``text_tr`` (clip cache or TTS);
  paraphrase only where the protocol sets ``allow_paraphrase: true``.
- **22** — no numeral reaches any TTS model. The compiler expands every digit
  (``protocols.compile.tr_orthography``), the clip manifest is keyed over the
  *expanded* text, and the Talker refuses to synthesise anything carrying a
  digit — which is what makes the compiler's guarantee load-bearing at
  runtime rather than merely upstream.
- **3** — raw audio is never written anywhere. The static half is
  tests/voice/test_audio_retention_guard.py, which already scans
  services/**; the runtime half is here: a whole turn runs with every
  filesystem write primitive armed to raise.

The clip manifest consumed is the compiler's own artefact
(``packages/protocols`` output (e), ``clips.<voice>.json``), so the two sides
agree on ``sha256(text_tr, voice_id)`` by construction rather than by
convention.
"""

from __future__ import annotations

import builtins
import json
import os
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from intake_voice_runtime.talker.clips import (
    ClipCatalogue,
    ClipNotCachedError,
    clip_id_for,
)
from intake_voice_runtime.talker.speech import (
    NumeralOnTtsPathError,
    ParaphraseNotPermittedError,
)
from protocols.dsl import clip_text_hash
from talker_harness import (
    FakeClock,
    RecordedClipStore,
    RecordingSynthesizer,
    build_session,
    scripted_step,
)

VOICE = "residency-tr-01"
ASK = "Ağrınız kaç gündür sürüyor?"
EXPANDED = "İki tane beş yüz miligram tablet aldınız mı?"


def _manifest(tmp_path: Path, *texts: str) -> Path:
    path = tmp_path / f"clips.{VOICE}.json"
    path.write_text(
        json.dumps(
            {
                "voice": VOICE,
                "pack_id": "specialty.dahiliye",
                "resolved_protocol_hash": "a" * 64,
                "entries": [
                    {
                        "text_hash": clip_text_hash(text),
                        "clip_id": clip_id_for(text, VOICE),
                        "voice": VOICE,
                        "text_tr": text,
                        "scripted": True,
                        "subject": f"slot.{index}",
                    }
                    for index, text in enumerate(texts)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


# --- the catalogue -------------------------------------------------------------------


def test_the_catalogue_loads_the_compilers_own_artefact(tmp_path: Path) -> None:
    catalogue = ClipCatalogue.load(_manifest(tmp_path, ASK, EXPANDED))
    assert catalogue.voice == VOICE
    assert catalogue.resolved_protocol_hash == "a" * 64
    assert len(catalogue) == 2


def test_a_clip_is_keyed_by_sha256_of_text_and_voice(tmp_path: Path) -> None:
    """files/03 §4.9.1 row 10 — and the compiler's emit_clips agrees."""
    catalogue = ClipCatalogue.load(_manifest(tmp_path, ASK))
    clip = catalogue.resolve(ASK)
    assert clip.text_hash == clip_text_hash(ASK)
    assert clip.clip_id == clip_id_for(ASK, VOICE)
    assert clip.clip_id.startswith(f"clip.{VOICE}.")


def test_the_same_visible_turkish_resolves_to_the_same_clip(tmp_path: Path) -> None:
    """NFC normalisation: a decomposed 'ğ' must not miss the cache."""
    catalogue = ClipCatalogue.load(_manifest(tmp_path, ASK))
    decomposed = unicodedata.normalize("NFD", ASK)
    assert decomposed != ASK, "the fixture must actually differ in code points"
    assert catalogue.resolve(decomposed).clip_id == catalogue.resolve(ASK).clip_id


def test_text_absent_from_the_manifest_is_a_miss_not_a_guess(tmp_path: Path) -> None:
    catalogue = ClipCatalogue.load(_manifest(tmp_path, ASK))
    with pytest.raises(ClipNotCachedError):
        catalogue.resolve("Başka bir soru?")
    assert catalogue.get("Başka bir soru?") is None


def test_a_manifest_for_another_voice_is_refused(tmp_path: Path) -> None:
    path = _manifest(tmp_path, ASK)
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["voice"] = "some-other-voice"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="voice"):
        ClipCatalogue.load(path)


# --- invariant 10: verbatim ------------------------------------------------------------


def test_a_scripted_step_is_spoken_from_the_clip_cache(tmp_path: Path) -> None:
    clock = FakeClock()
    store = RecordedClipStore()
    synthesizer = RecordingSynthesizer()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=ASK)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK)),
        clip_store=store,
        synthesizer=synthesizer,
    )
    outcome = clock.run(session.take_turn(None))

    assert outcome.spoken_text == ASK
    assert outcome.from_clip is True
    assert store.served == [clip_id_for(ASK, VOICE)]
    assert synthesizer.requests == [], "a cached clip must never reach TTS"


def test_a_scripted_step_with_no_clip_falls_back_to_verbatim_tts(tmp_path: Path) -> None:
    """Invariant 10 says 'clip cache or TTS' — the fallback is still verbatim."""
    clock = FakeClock()
    synthesizer = RecordingSynthesizer()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=ASK)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, EXPANDED)),
        synthesizer=synthesizer,
    )
    outcome = clock.run(session.take_turn(None))

    assert outcome.spoken_text == ASK
    assert outcome.from_clip is False
    assert synthesizer.requests == [ASK]


def test_paraphrasing_a_scripted_step_is_refused(tmp_path: Path) -> None:
    clock = FakeClock()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=ASK)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK)),
    )
    with pytest.raises(ParaphraseNotPermittedError, match="s1"):
        clock.run(session.speak_step(session.protocol_next(), paraphrase="Kaç gün oldu?"))


def test_a_paraphrase_ok_step_accepts_a_paraphrase(tmp_path: Path) -> None:
    from intake_voice_runtime.steps import Step, StepKind

    clock = FakeClock()
    step = Step(step_id="s2", kind=StepKind.PARAPHRASE_OK, text_tr="Başka bir şikâyetiniz var mı?")
    session = build_session(
        clock, steps=[step], catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK))
    )
    outcome = clock.run(
        session.speak_step(session.protocol_next(), paraphrase="Ekleyeceğiniz var mı?")
    )
    assert outcome.spoken_text == "Ekleyeceğiniz var mı?"


# --- invariant 22: no numeral on the TTS path --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Ağrınız 2 gündür mü sürüyor?",
        "500 mg aldınız mı?",
        "Tansiyonunuz 140/90 mıydı?",
        "٣ gün oldu mu?",
    ],
)
def test_the_talker_refuses_to_synthesise_text_carrying_a_digit(tmp_path: Path, text: str) -> None:
    clock = FakeClock()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=text)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK)),
    )
    with pytest.raises(NumeralOnTtsPathError):
        clock.run(session.take_turn(None))


def test_expanded_turkish_orthography_passes(tmp_path: Path) -> None:
    clock = FakeClock()
    synthesizer = RecordingSynthesizer()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=EXPANDED)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK)),
        synthesizer=synthesizer,
    )
    outcome = clock.run(session.take_turn(None))
    assert outcome.spoken_text == EXPANDED
    assert synthesizer.requests == [EXPANDED]


def test_a_manifest_entry_carrying_a_digit_is_refused_at_load(tmp_path: Path) -> None:
    """The compiler cannot emit one; if a hand-edited manifest ever does, the
    Talker refuses the whole catalogue rather than one clip at speak time."""
    with pytest.raises(NumeralOnTtsPathError):
        ClipCatalogue.load(_manifest(tmp_path, "500 mg aldınız mı?"))


# --- invariant 3: no write path from the audio path ---------------------------------------


def test_a_whole_turn_runs_without_a_single_filesystem_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalogue = ClipCatalogue.load(_manifest(tmp_path, ASK))  # load before arming
    clock = FakeClock()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=ASK)],
        catalogue=catalogue,
        clip_store=RecordedClipStore(),
    )

    real_open = builtins.open

    def refuse_writes(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if set(mode) & set("wxa+"):
            raise AssertionError(f"the audio path opened {file!r} for writing (invariant 3)")
        return real_open(file, mode, *args, **kwargs)

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the audio path wrote to disk (invariant 3)")

    monkeypatch.setattr(builtins, "open", refuse_writes)
    monkeypatch.setattr(Path, "write_bytes", refuse)
    monkeypatch.setattr(Path, "write_text", refuse)
    monkeypatch.setattr(os, "write", refuse)

    outcome = clock.run(session.take_turn("iki gündür ağrıyor"))
    assert outcome.spoken_text == ASK


def test_the_talker_package_has_no_inbound_audio_type() -> None:
    """The Talker's audio surface is outbound only: it consumes transcripts,
    never patient frames. Nothing here can hold raw patient audio, so there is
    nothing for a write path to reach (invariant 3; files/10 §3)."""
    import intake_voice_runtime.ports as ports

    inbound = [
        name
        for name in dir(ports)
        if any(token in name.lower() for token in ("microphone", "capture", "pcm", "inbound"))
    ]
    assert inbound == []


def test_no_clip_bytes_are_retained_after_the_turn(tmp_path: Path) -> None:
    clock = FakeClock()
    session = build_session(
        clock,
        steps=[scripted_step(text_tr=ASK)],
        catalogue=ClipCatalogue.load(_manifest(tmp_path, ASK)),
        clip_store=RecordedClipStore(),
    )
    clock.run(session.take_turn(None))
    assert session.retained_frames() == 0
