"""INT-576 — the structure of a Netgsm answer, and nothing in it.

On 28 Oct 2026 Netgsm answered the owner's real send with an HTTP 200 the
INT-528 parser could not read, and the SMS arrived anyway. Netgsm's own
sources name the success body's job id differently (INT-576 evidence), so the
owner has an opt-in diagnostic, ``netgsm_test_otp.sh --shape``, that prints
what the answer looked like. :func:`answer_shape` is all it prints.

Structure only (invariant 6):

- the media type of ``Content-Type``, without parameters;
- the kind of body: empty, a JSON object, other JSON, markup or text;
- the top-level JSON keys, each with its value's JSON type, or the markup's
  tag names in order of first appearance, at most :data:`MAX_NAMES`;
- the vendor's code, only when it is the documented one to three digits;
- the body's length in bytes.

Never a value: not the number, not the code, not the job id, not the body. A
key or tag is printed only when it is letters and underscores (otherwise
``?``), so no digit string can ride a name, and the code is at most three
digits, so it cannot be a six-digit OTP code or a phone number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx

__all__ = ["MAX_NAMES", "AnswerKind", "AnswerShape", "answer_shape"]

#: How many keys or tags the shape names.
MAX_NAMES: Final = 12
#: How much of a non-JSON body is scanned for tags or a leading code.
_SCAN_BYTES: Final = 4096
_NAME = re.compile(r"[A-Za-z_]{1,32}")
_MEDIA_TYPE = re.compile(r"[a-z]{1,32}/[a-z0-9.+-]{1,64}")
_CODE = re.compile(r"[0-9]{1,3}")
#: an opening tag's name: not a closing tag, a declaration or an instruction
_TAG = re.compile(r"<([^\s/>!?][^\s/>]*)")
_MARKUP_CODE = re.compile(r"<code>\s*([0-9]{1,3})\s*</code>")
_TEXT_CODE = re.compile(r"\s*([0-9]{1,3})(?:\s|\Z)")
_NOT_JSON: Final = object()


class AnswerKind(StrEnum):
    EMPTY = "empty"
    JSON_OBJECT = "json-object"
    JSON_OTHER = "json-other"
    MARKUP = "markup"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class AnswerShape:
    """What a Netgsm answer looked like, built so that it cannot hold a value."""

    content_type: str
    kind: AnswerKind
    names: tuple[str, ...]
    code: str
    length: int

    def render(self) -> str:
        names = ",".join(self.names) if self.names else "-"
        return (
            f"content_type={self.content_type} kind={self.kind} keys={names} "
            f"code={self.code} length={self.length}"
        )


def _name(raw: str) -> str:
    return raw if _NAME.fullmatch(raw) else "?"


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def _media_type(response: httpx.Response) -> str:
    header = response.headers.get("content-type")
    if header is None:
        return "-"
    media = header.split(";", 1)[0].strip().lower()
    return media if _MEDIA_TYPE.fullmatch(media) else "?"


def _decoded(content: bytes) -> object:
    try:
        return json.loads(content)
    except (ValueError, RecursionError):
        return _NOT_JSON


def _json_code(body: dict[str, object]) -> str:
    raw = body.get("code")
    if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 999:
        return str(raw)
    return raw if isinstance(raw, str) and _CODE.fullmatch(raw) else "-"


def _markup_names(text: str) -> tuple[str, ...]:
    names: list[str] = []
    for match in _TAG.finditer(text):
        name = _name(match.group(1))
        if name not in names:
            names.append(name)
        if len(names) == MAX_NAMES:
            break
    return tuple(names)


def answer_shape(response: httpx.Response) -> AnswerShape:
    """The structure of ``response``, never a value from it."""
    content = response.content
    media, length = _media_type(response), len(content)
    if not content.strip():
        return AnswerShape(media, AnswerKind.EMPTY, (), "-", length)
    decoded = _decoded(content)
    if isinstance(decoded, dict):
        pairs = list(decoded.items())[:MAX_NAMES]
        names = tuple(f"{_name(str(key))}:{_json_type(value)}" for key, value in pairs)
        return AnswerShape(media, AnswerKind.JSON_OBJECT, names, _json_code(decoded), length)
    if decoded is not _NOT_JSON:
        return AnswerShape(media, AnswerKind.JSON_OTHER, (), "-", length)
    text = content[:_SCAN_BYTES].decode("utf-8", errors="replace")
    if text.lstrip().startswith("<"):
        code = _MARKUP_CODE.search(text)
        return AnswerShape(
            media, AnswerKind.MARKUP, _markup_names(text), code.group(1) if code else "-", length
        )
    code = _TEXT_CODE.match(text)
    return AnswerShape(media, AnswerKind.TEXT, (), code.group(1) if code else "-", length)
