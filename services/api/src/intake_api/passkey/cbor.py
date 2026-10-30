"""Strict CBOR for passkey objects (INT-582): one item, definite lengths, no
duplicate keys, bounded depth — and no semantic tag anywhere.

cbor2 decodes the tags it knows (an epoch date, a bignum, a URI, embedded
CBOR) into Python values without saying so, so a check by type after decoding
cannot see them. :func:`refuse_tags` walks the item's headers first and
refuses major type 6 wherever it sits; WebAuthn's attestation object, COSE
key and extensions map never carry one. Every refusal is the caller's
``malformed`` (raised as :class:`CborShapeError`).
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

import cbor2

__all__ = ["CborShapeError", "decode_map", "decode_one", "refuse_tags"]

MAX_DEPTH = 8
_TAG = 6


class CborShapeError(ValueError):
    """The bytes are not one strict, tag-free CBOR item."""


def _argument(data: bytes, offset: int) -> tuple[int, int, int]:
    """(major type, argument, offset after the header) of the item at ``offset``."""
    if offset >= len(data):
        raise CborShapeError("truncated")
    initial = data[offset]
    major, info = initial >> 5, initial & 0x1F
    if info < 24:
        return major, info, offset + 1
    widths = {24: 1, 25: 2, 26: 4, 27: 8}
    if info not in widths:  # 28-30 reserved, 31 indefinite
        raise CborShapeError("indefinite or reserved length")
    end = offset + 1 + widths[info]
    if end > len(data):
        raise CborShapeError("truncated")
    return major, int.from_bytes(data[offset + 1 : end], "big"), end


def _walk(data: bytes, offset: int, depth: int) -> int:
    if depth > MAX_DEPTH:
        raise CborShapeError("too deep")
    major, argument, offset = _argument(data, offset)
    if major == _TAG:
        raise CborShapeError("semantic tag")
    if major in (2, 3):  # byte and text strings
        offset += argument
        if offset > len(data):
            raise CborShapeError("truncated")
        return offset
    if major in (4, 5):  # arrays and maps
        for _ in range(argument * (2 if major == 5 else 1)):
            offset = _walk(data, offset, depth + 1)
        return offset
    return offset  # integers, simple values and floats carry no children


def refuse_tags(data: bytes) -> int:
    """Walk one CBOR item from the start of ``data``; return its length."""
    return _walk(data, 0, 0)


def decode_one(data: bytes) -> tuple[Any, int]:
    """One tag-free CBOR item and how many bytes it used."""
    used = refuse_tags(data)
    stream = io.BytesIO(data[:used])
    try:
        value = cbor2.CBORDecoder(
            stream,
            read_size=1,
            max_depth=MAX_DEPTH,
            allow_indefinite=False,
            allow_duplicate_keys=False,
        ).decode()
    except (cbor2.CBORError, ValueError, EOFError, RecursionError) as exc:
        raise CborShapeError("undecodable") from exc
    if stream.tell() != used:
        raise CborShapeError("length disagreement")
    return value, used


def decode_map(data: bytes) -> Mapping[Any, Any]:
    """Exactly one tag-free CBOR map and nothing after it."""
    value, used = decode_one(data)
    if used != len(data) or not isinstance(value, dict):
        raise CborShapeError("not exactly one map")
    return value
