"""Clip audio: RIFF in, silence trimmed, Ogg/Opus out (INT-060).

**These bytes are agent speech, not patient audio, and the distinction is the
whole reason this module is allowed to exist.** CLAUDE.md invariant 3 governs
*patient* audio: raw microphone audio is never written to disk, a database, an
object store or a log, and its in-memory buffers are mlocked and zeroed. A
protocol clip is the opposite kind of artefact — the agent's own synthesised
voice reading a scripted Turkish string that is already committed to this
repository in plain text, produced at build time, on a build host, with no
session and no patient anywhere near it (files/03 §4.6 invariant 9: "clips in
MinIO are synthetic agent speech, never patient audio"). There is no capture
path here, no microphone, no session id; the only input is a compiled manifest
string. **Do not reach for this module to persist anything that came out of a
patient's mouth — it is a cache of scripts, not a recording store.**

Three decisions worth keeping:

1. **The trim happens here, at build time.** INT-240 measured one-word RED
   imperatives coming back from the TTS lane wrapped in ~1.2 s of silence at
   each end. Under CLAUDE.md invariant 21 the RED script is pre-positioned on
   the device and fired over the data channel, so there is no runtime moment
   in which that padding could be shaved — the clip is played as stored. Build
   time is therefore the only correct place, and the residual lead/trail is
   measured on the *encoded and decoded* clip rather than on an intermediate
   buffer, because the encoded clip is what the patient hears.
2. **No word is ever trimmed** (CLAUDE.md invariant 10). The cut is taken at a
   deliberately low floor and then backed off by a pad on each side, so the
   onset consonant and the release survive. Nothing between the first and the
   last above-floor sample is touched.
3. **Nothing is repaired silently.** A sample rate Opus does not take, more
   than one channel, or an entirely silent synthesis is a typed refusal — the
   build stops, which is where files/03 §4.9.4 says a TTS failure belongs.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from typing import Final

import numpy as np
import soundfile
from numpy.typing import NDArray

from voice_clips.errors import ClipCacheError

__all__ = [
    "LEAD_PAD_MS",
    "MAX_LEAD_SILENCE_MS",
    "MAX_TRAIL_SILENCE_MS",
    "OPUS_SAMPLE_RATES_HZ",
    "SILENCE_FLOOR_DBFS",
    "TRAIL_PAD_MS",
    "ClipAudioError",
    "ClipSilenceBoundError",
    "EncodedClip",
    "MalformedWavError",
    "MultiChannelClipError",
    "Pcm",
    "SilentClipError",
    "SynthesisedSpeech",
    "UnsupportedSampleRateError",
    "decode_opus",
    "encode_clip",
    "silence_edges_ms",
    "trim_silence",
    "wav_bytes",
    "wav_to_speech",
]

#: The input rates Opus itself accepts. Anything else means the endpoint is
#: not one of the pinned models (files/03 §4.9.1 rows 10-12), and a build that
#: quietly resampled it would hide that rather than surface it.
OPUS_SAMPLE_RATES_HZ: Final[tuple[int, ...]] = (8000, 12000, 16000, 24000, 48000)

#: Everything quieter than this counts as silence. Low on purpose: a high
#: floor would eat a breathy word onset, and eating a word is invariant 10.
SILENCE_FLOOR_DBFS: Final = -50.0

#: How much silence is kept in front of and behind the speech after the cut,
#: so the attack and the release are never clipped.
LEAD_PAD_MS: Final = 20
TRAIL_PAD_MS: Final = 40

#: What the stored clip is allowed to still carry. Asserted on the decoded
#: clip by :func:`encode_clip` and pinned by tests/voice.
MAX_LEAD_SILENCE_MS: Final = 40
MAX_TRAIL_SILENCE_MS: Final = 60

_FULL_SCALE: Final = 32767.0
_CONTAINER_FORMAT: Final = "OGG"
_CODEC_SUBTYPE: Final = "OPUS"
_SAMPLE_DTYPE: Final = "int16"
_WAV_HEADER_LEN: Final = 12
_PCM_FORMAT_TAG: Final = 1
_BITS_PER_SAMPLE: Final = 16


class ClipAudioError(ClipCacheError):
    """Base for every refusal on the clip audio path."""


class MalformedWavError(ClipAudioError):
    """A synthesis response was not a 16-bit PCM RIFF/WAVE body."""


class UnsupportedSampleRateError(ClipAudioError):
    """A rate Opus does not take. Refused rather than resampled."""


class MultiChannelClipError(ClipAudioError):
    """Agent speech is mono; more than one channel means the wrong endpoint."""


class SilentClipError(ClipAudioError):
    """A synthesis carried no speech at all — a clip nobody could hear."""


class ClipSilenceBoundError(ClipAudioError):
    """The stored clip still carries more dead air than the bounds allow."""


@dataclass(frozen=True)
class SynthesisedSpeech:
    """One TTS response as the gateway hands it over: interleaved 16-bit LE."""

    pcm_s16le: bytes
    sample_rate_hz: int
    channels: int

    @property
    def samples(self) -> NDArray[np.int16]:
        return np.frombuffer(self.pcm_s16le, dtype="<i2")


@dataclass(frozen=True)
class Pcm:
    """Mono 16-bit samples at a known rate."""

    samples: NDArray[np.int16]
    sample_rate_hz: int

    @property
    def duration_ms(self) -> float:
        return 1000.0 * self.samples.size / self.sample_rate_hz


@dataclass(frozen=True)
class EncodedClip:
    """What goes into the object store, plus what the build report states."""

    data: bytes
    sample_rate_hz: int
    duration_ms: float
    lead_silence_ms: float
    trail_silence_ms: float


def _floor_amplitude() -> float:
    return _FULL_SCALE * 10 ** (SILENCE_FLOOR_DBFS / 20)


def _above_floor(samples: NDArray[np.int16]) -> NDArray[np.int64]:
    loud: NDArray[np.int64] = np.flatnonzero(
        np.abs(samples.astype(np.float64)) > _floor_amplitude()
    )
    return loud


def wav_to_speech(body: bytes) -> SynthesisedSpeech:
    """Parse a canonical RIFF/WAVE body into raw PCM.

    Deliberately hand-rolled and deliberately narrow: it accepts exactly the
    shape the pinned TTS servers emit (PCM format tag, 16 bits per sample) and
    refuses everything else. A general audio-file reader on this path would be
    a general audio-file *writer* one refactor later, which is the surface
    invariant 3 keeps closed.
    """
    if len(body) < _WAV_HEADER_LEN or body[0:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise MalformedWavError(f"synthesis response is not a RIFF/WAVE body ({len(body)} bytes)")
    offset = _WAV_HEADER_LEN
    declared: tuple[int, int, int, int] | None = None
    while offset + 8 <= len(body):
        chunk_id = body[offset : offset + 4]
        (size,) = struct.unpack_from("<I", body, offset + 4)
        payload = body[offset + 8 : offset + 8 + size]
        if chunk_id == b"fmt " and size >= 16:
            tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", payload, 0)
            declared = (tag, channels, rate, bits)
        elif chunk_id == b"data" and declared is not None:
            tag, channels, rate, bits = declared
            if tag != _PCM_FORMAT_TAG or bits != _BITS_PER_SAMPLE:
                raise MalformedWavError(
                    f"only 16-bit PCM is accepted (format tag {tag}, {bits} bits)"
                )
            return SynthesisedSpeech(pcm_s16le=payload, sample_rate_hz=rate, channels=channels)
        offset += 8 + size + (size % 2)
    raise MalformedWavError("RIFF/WAVE body carries no fmt+data pair")


def wav_bytes(speech: SynthesisedSpeech) -> bytes:
    """Frame raw signed 16-bit LE PCM as a canonical RIFF/WAVE body.

    The inverse of :func:`wav_to_speech`, and the one sanctioned place agent
    speech is wrapped into a WAV — for a caller that needs a playable container
    rather than the Ogg/Opus :func:`encode_clip` produces (the ADR-028
    on-demand dev route, which hands the byte stream to expo-av). Like
    everything in this module the bytes are agent speech, a scripted clip and
    never patient audio (invariant 3); the module docstring above is the whole
    argument for why that distinction holds and why this framing belongs here
    and not ad hoc in a service. It is header assembly only — no file is
    opened, no audio library is called and the constants are RIFF's own (36 =
    the header bytes after the RIFF size field; 16-byte PCM ``fmt `` chunk;
    format tag 1 = PCM; 16 bits per sample), so it carries no allow-listed
    dependency and the numeral/consent guarantees the caller made upstream are
    the only ones that matter here.
    """
    pcm = speech.pcm_s16le
    rate = int(speech.sample_rate_hz)
    channels = int(speech.channels)
    byte_rate = rate * channels * 2
    block_align = channels * 2
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, block_align, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def silence_edges_ms(pcm: Pcm) -> tuple[float, float]:
    """Leading and trailing dead air, in milliseconds."""
    above = _above_floor(pcm.samples)
    if above.size == 0:
        return pcm.duration_ms, pcm.duration_ms
    per_sample_ms = 1000.0 / pcm.sample_rate_hz
    lead = int(above[0]) * per_sample_ms
    trail = (pcm.samples.size - 1 - int(above[-1])) * per_sample_ms
    return lead, trail


def trim_silence(speech: SynthesisedSpeech) -> Pcm:
    """Cut the dead air at both ends, keeping a pad so no word is clipped."""
    samples = speech.samples
    above = _above_floor(samples)
    if above.size == 0:
        raise SilentClipError(
            f"synthesis carried no sample above {SILENCE_FLOOR_DBFS} dBFS — "
            "an inaudible clip is a turn the patient never hears"
        )
    rate = speech.sample_rate_hz
    start = max(0, int(above[0]) - round(LEAD_PAD_MS * rate / 1000))
    end = min(samples.size, int(above[-1]) + 1 + round(TRAIL_PAD_MS * rate / 1000))
    return Pcm(samples=samples[start:end], sample_rate_hz=rate)


def _write_ogg_opus(pcm: Pcm) -> bytes:
    buffer = io.BytesIO()
    soundfile.write(
        buffer,
        pcm.samples,
        pcm.sample_rate_hz,
        format=_CONTAINER_FORMAT,
        subtype=_CODEC_SUBTYPE,
    )
    return buffer.getvalue()


def decode_opus(data: bytes) -> Pcm:
    """Decode a stored clip back to mono PCM — the builder's own read-back."""
    decoded, rate = soundfile.read(io.BytesIO(data), dtype=_SAMPLE_DTYPE)
    samples: NDArray[np.int16] = np.asarray(decoded, dtype=np.int16).reshape(-1)
    return Pcm(samples=samples, sample_rate_hz=int(rate))


def encode_clip(
    speech: SynthesisedSpeech,
    *,
    max_lead_ms: float = MAX_LEAD_SILENCE_MS,
    max_trail_ms: float = MAX_TRAIL_SILENCE_MS,
) -> EncodedClip:
    """Trim, encode to Ogg/Opus, and read the result back to prove the bounds.

    The read-back is not ceremony. Encoder priming and container granule
    handling both add samples in front of the audio, so the only honest place
    to measure the lead the patient will hear is the decoded stored clip. The
    bounds are parameters solely so a test can prove the guard fires; the
    defaults are the pinned constants and nothing in the builder passes others.
    """
    if speech.channels != 1:
        raise MultiChannelClipError(
            f"agent speech is mono; the endpoint returned {speech.channels} channels"
        )
    if speech.sample_rate_hz not in OPUS_SAMPLE_RATES_HZ:
        raise UnsupportedSampleRateError(
            f"{speech.sample_rate_hz} Hz is not an Opus input rate "
            f"({', '.join(str(rate) for rate in OPUS_SAMPLE_RATES_HZ)}) — refused "
            "rather than resampled, because the wrong rate means the wrong endpoint"
        )
    data = _write_ogg_opus(trim_silence(speech))
    decoded = decode_opus(data)
    lead, trail = silence_edges_ms(decoded)
    if lead > max_lead_ms or trail > max_trail_ms:
        raise ClipSilenceBoundError(
            f"stored clip still carries {lead:.1f} ms lead / {trail:.1f} ms trail "
            f"(bounds {max_lead_ms} / {max_trail_ms} ms)"
        )
    return EncodedClip(
        data=data,
        sample_rate_hz=decoded.sample_rate_hz,
        duration_ms=decoded.duration_ms,
        lead_silence_ms=lead,
        trail_silence_ms=trail,
    )
