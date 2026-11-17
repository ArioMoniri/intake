"""Test harness for the INT-060 clip cache: synthetic audio and a fake store.

Two things live here so both clip test modules share one definition.

**Synthetic speech.** No recorded Turkish audio is committed anywhere in this
repository, and inventing one and calling it a recording would be a lie about
provenance. The tone built by :func:`speech_like` is explicitly synthetic: a
gated sine with a soft onset, wrapped in the 1.2 s of leading and trailing
silence INT-240 measured coming back from the FreyaTTS lane. That silence
shape is the thing under test, not the timbre.

**A fake object store, not a mock.** It keeps real bucket/object state so the
tests assert what ended up where rather than a call script — the same shape as
``tests/security/test_document_store.py`` and ``tests/api/api_harness.py``.
"""

from __future__ import annotations

import base64
import io
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE_HZ = 24000
SILENCE_PAD_S = 1.2


def silence(seconds: float, sample_rate_hz: int = SAMPLE_RATE_HZ) -> NDArray[np.int16]:
    return np.zeros(int(seconds * sample_rate_hz), dtype=np.int16)


def speech_like(
    seconds: float = 0.6,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
    hz: float = 220.0,
    onset_s: float = 0.02,
) -> NDArray[np.int16]:
    """A loud, gated tone standing in for one spoken word."""
    n = int(seconds * sample_rate_hz)
    t = np.arange(n, dtype=np.float64) / sample_rate_hz
    envelope = np.minimum(1.0, np.arange(n, dtype=np.float64) / max(1.0, onset_s * sample_rate_hz))
    return (0.3 * np.sin(2 * np.pi * hz * t) * envelope * 32767).astype(np.int16)


def padded_speech(
    lead_s: float = SILENCE_PAD_S,
    trail_s: float = SILENCE_PAD_S,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
) -> NDArray[np.int16]:
    """The INT-240 shape: one short utterance drowned in silence at both ends."""
    return np.concatenate(
        [
            silence(lead_s, sample_rate_hz),
            speech_like(sample_rate_hz=sample_rate_hz),
            silence(trail_s, sample_rate_hz),
        ]
    )


def riff_wave(samples: NDArray[np.int16], sample_rate_hz: int = SAMPLE_RATE_HZ) -> bytes:
    """A canonical 16-bit mono RIFF/WAVE body, as the dev TTS bridge returns."""
    return riff_wave_multichannel(samples, sample_rate_hz, channels=1)


def riff_wave_multichannel(samples: NDArray[np.int16], sample_rate_hz: int, channels: int) -> bytes:
    payload = samples.astype("<i2").tobytes()
    block_align = 2 * channels
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(payload),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate_hz,
        sample_rate_hz * block_align,
        block_align,
        16,
        b"data",
        len(payload),
    )
    return header + payload


def write_recording(
    root: Path,
    *,
    text_hash: str,
    voice_id: str,
    text_tr: str,
    body: bytes,
    delivery_profile: str | None = None,
) -> Path:
    """Write one recorded-response fixture the way the gateway reads it back.

    ``delivery_profile`` (INT-415) binds the take to the profile key it was
    made under; ``None`` writes a profile-free take, as a self-hosted lane with
    no delivery controls produces."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{text_hash}.json"
    recording: dict[str, str] = {
        "voice_id": voice_id,
        "text_tr": text_tr,
        "body_base64": base64.b64encode(body).decode("ascii"),
    }
    if delivery_profile is not None:
        recording["delivery_profile"] = delivery_profile
    path.write_text(
        json.dumps(
            recording,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class _Stat:
    def __init__(self, size: int) -> None:
        self.size = size


@dataclass
class FakeClipStorage:
    """In-memory S3: bucket -> key -> (payload, content_type).

    ``stat_error_code`` makes every HEAD fail with that S3 error code, so the
    "a storage failure is not a cache miss" branch can be exercised.
    """

    buckets: dict[str, dict[str, tuple[bytes, str]]] = field(default_factory=dict)
    make_bucket_calls: list[str] = field(default_factory=list)
    stat_error_code: str | None = None

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(
        self, bucket_name: str, location: str | None = None, object_lock: bool = False
    ) -> None:
        del location, object_lock
        self.make_bucket_calls.append(bucket_name)
        self.buckets.setdefault(bucket_name, {})

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        **kwargs: Any,
    ) -> object:
        del kwargs
        payload = data.read()
        assert len(payload) == length
        self.buckets.setdefault(bucket_name, {})[object_name] = (payload, content_type)
        return object()

    def stat_object(self, bucket_name: str, object_name: str) -> _Stat:
        from minio.error import S3Error

        if self.stat_error_code is not None:
            raise S3Error(
                code=self.stat_error_code,
                message="refused",
                resource=object_name,
                request_id="fake",
                host_id="fake",
                response=None,
                bucket_name=bucket_name,
                object_name=object_name,
            )
        try:
            payload, _ = self.buckets[bucket_name][object_name]
        except KeyError:
            raise S3Error(
                code="NoSuchKey",
                message="not found",
                resource=object_name,
                request_id="fake",
                host_id="fake",
                response=None,
                bucket_name=bucket_name,
                object_name=object_name,
            ) from None
        return _Stat(len(payload))

    def get_object(self, bucket_name: str, object_name: str) -> io.BytesIO:
        payload, _ = self.buckets[bucket_name][object_name]
        return io.BytesIO(payload)

    # --- assertions the tests reach for -------------------------------------------

    def objects(self, bucket_name: str) -> dict[str, tuple[bytes, str]]:
        return self.buckets.get(bucket_name, {})


@dataclass
class RecordingGateway:
    """Wraps a real gateway and records the exact text handed to it, and the
    delivery profile key each call was made under (INT-415)."""

    inner: Any
    calls: list[tuple[str, str]] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)

    def synthesise(self, *, text_tr: str, voice_id: str, profile: Any) -> Any:
        self.calls.append((text_tr, voice_id))
        self.profiles.append(profile.key)
        return self.inner.synthesise(text_tr=text_tr, voice_id=voice_id, profile=profile)
