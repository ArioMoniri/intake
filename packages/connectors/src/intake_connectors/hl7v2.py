"""The HL7v2 ORU^R01 inbound channel (INT-162).

An ORU^R01 is how a Turkish HBYS/SBYS lab feeds a result back: MSH (the
envelope), OBR (the order) and one OBX per observation. This channel turns such
a message into :class:`~intake_connectors.inbound.InboundObservation` values
and does three things carefully, because a message from a hospital LAN is
untrusted input on the PHI path:

**A segment can never issue a command** (invariant 14). Parsing is a table
lookup on the segment name — ``OBX`` is read, every other name is inert text —
so there is no segment a sender could craft that dispatches code. The
delimiters are read from MSH-2 (the message's own declaration) rather than
assumed, and an escape sequence *inside* a value is decoded to the literal
character it stands for, never re-interpreted as structure.

**No value reaches a log** (invariant 6). A malformed message raises an error
that names a segment position and a reason and quotes nothing; the byte cap is
checked before the body is split, so an oversized message is refused without
ever being read into fields.

**Nothing becomes a number unbidden** (invariant 22). The observation value is
carried as the token the segment printed. The mapper alone decides whether that
token is an unambiguous decimal, and it does so with grouping disabled; this
channel does not convert, round or normalise it.
"""

from __future__ import annotations

from datetime import datetime

from clinical_schemas.records import RecordItemKind

from intake_connectors.inbound import (
    InboundMessage,
    InboundObservation,
    InboundParseError,
)

__all__ = ["Hl7v2OruChannel", "Hl7v2ParseError"]

#: A single message is bounded before it is parsed. An ORU with more than this
#: is not a result we ingest; the cap is checked on the raw bytes so an
#: oversized payload never reaches the field splitter.
_MAX_BYTES = 1024 * 1024

#: The message type this kit accepts. ORU^R01 is an unsolicited observation
#: result; anything else (an ADT admit, an ORM order) is a different message
#: with different semantics and is refused rather than parsed as if it were one.
_MESSAGE_TYPE = ("ORU", "R01")

#: Charsets a message may declare in MSH-18, mapped to a Python codec. Closed so
#: a codec name a sender chose never reaches ``bytes.decode`` — an attacker-named
#: codec is a code path we did not audit. ISO-8859-1 is the guaranteed fallback
#: because it never raises, so a feed that declares nothing is still decoded.
_CHARSETS = {
    "": "utf-8",
    "ASCII": "ascii",
    "UNICODE UTF-8": "utf-8",
    "8859/1": "iso-8859-1",
    "8859/9": "iso-8859-9",
}


class Hl7v2ParseError(InboundParseError):
    """A message is not a well-formed ORU^R01. Carries no value from it."""


def _decode(body: bytes) -> str:
    """Decode the message to text, honouring MSH-18 from a closed codec set.

    A first pass reads MSH-18 through ISO-8859-1 (which maps every byte and
    never raises); the declared codec then re-decodes the original bytes. A
    declared-or-default codec that raises falls back to ISO-8859-1 so parsing
    never crashes on an undeclared Turkish encoding — the bytes are preserved
    either way.
    """
    structural = body.decode("iso-8859-1")
    charset = ""
    first = structural.replace("\r\n", "\r").replace("\n", "\r").split("\r", 1)[0]
    if first.startswith("MSH") and len(first) > 3:
        fields = first.split(first[3])
        if len(fields) > 17:
            charset = fields[17].strip()
    codec = _CHARSETS.get(charset, "utf-8")
    try:
        return body.decode(codec)
    except (UnicodeDecodeError, LookupError):
        return body.decode("iso-8859-1")


def _segments(text: str) -> list[str]:
    normalised = text.replace("\r\n", "\r").replace("\n", "\r")
    return [segment for segment in normalised.split("\r") if segment]


def _decode_escapes(value: str, sep: str, comp: str, sub: str, rep: str, esc: str) -> str:
    """Turn the five standard HL7 escape sequences into their literal
    characters. Everything else passes through unchanged — an escape is decoded
    to a character, never acted on."""
    if esc not in value:
        return value
    for token, replacement in (
        (f"{esc}F{esc}", sep),
        (f"{esc}S{esc}", comp),
        (f"{esc}T{esc}", sub),
        (f"{esc}R{esc}", rep),
        (f"{esc}E{esc}", esc),
    ):
        value = value.replace(token, replacement)
    return value


def _parse_ts(token: str) -> datetime | None:
    """Parse an HL7 TS (``YYYYMMDD[HHMMSS[.frac]][±ZZZZ]``) to a naive local
    datetime, or ``None`` when it is not legible. Never raises: an unreadable
    timestamp is a missing field, not a failed ingest."""
    digits = token.strip()
    for cut in ("+", "-"):
        digits = digits.split(cut, 1)[0]
    digits = digits.split(".", 1)[0]
    if len(digits) < 8 or not digits.isdigit():
        return None
    try:
        year, month, day = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
        hour = int(digits[8:10]) if len(digits) >= 10 else 0
        minute = int(digits[10:12]) if len(digits) >= 12 else 0
        second = int(digits[12:14]) if len(digits) >= 14 else 0
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


class Hl7v2OruChannel:
    """Parse one HL7v2 ORU^R01 message into observations."""

    channel_id = "hl7v2-oru"

    def parse(self, message: InboundMessage) -> tuple[InboundObservation, ...]:
        if message.byte_count > _MAX_BYTES:
            raise Hl7v2ParseError(
                f"message exceeds {_MAX_BYTES} bytes and is refused before parsing"
            )
        segments = _segments(_decode(message.body))
        if not segments or not segments[0].startswith("MSH"):
            raise Hl7v2ParseError("an HL7v2 message begins with an MSH segment")

        sep, comp, sub, rep, esc = self._delimiters(segments[0])
        self._require_message_type(segments[0], sep, comp)

        observations: list[InboundObservation] = []
        for index, segment in enumerate(segments):
            fields = segment.split(sep)
            if fields[0] != "OBX":
                # Every non-OBX segment is inert. There is no name here that
                # dispatches anything (invariant 14) — MSH is already consumed,
                # and an unknown segment is text we do not read.
                continue
            observations.append(self._observation(fields, index, comp, sub, rep, esc, sep))
        return tuple(observations)

    @staticmethod
    def _delimiters(msh: str) -> tuple[str, str, str, str, str]:
        if len(msh) < 8:
            raise Hl7v2ParseError("the MSH segment is too short to declare its delimiters")
        sep = msh[3]
        encoding = msh[4:].split(sep, 1)[0]
        if len(encoding) < 4:
            raise Hl7v2ParseError("MSH-2 must declare four encoding characters")
        comp, rep, esc, sub = encoding[0], encoding[1], encoding[2], encoding[3]
        chosen = {sep, comp, rep, esc, sub}
        if len(chosen) != 5:
            raise Hl7v2ParseError("the field separator and encoding characters must be distinct")
        for character in chosen:
            if character.isalnum() or character.isspace():
                raise Hl7v2ParseError("a delimiter must be a non-alphanumeric character")
        return sep, comp, sub, rep, esc

    @staticmethod
    def _require_message_type(msh: str, sep: str, comp: str) -> None:
        fields = msh.split(sep)
        if len(fields) < 9:
            raise Hl7v2ParseError("the MSH segment declares no message type")
        parts = fields[8].split(comp)
        if tuple(parts[:2]) != _MESSAGE_TYPE:
            # The type is registry-shaped (a closed pair of codes), so it is
            # safe to name: it is not patient content.
            raise Hl7v2ParseError(
                "this channel accepts ORU^R01 only; another message type is refused"
            )

    @staticmethod
    def _observation(
        fields: list[str],
        index: int,
        comp: str,
        sub: str,
        rep: str,
        esc: str,
        sep: str,
    ) -> InboundObservation:
        # OBX-3 (observation identifier) is required; a truncated OBX with no
        # identifier is malformed. The error names the segment position, never
        # a neighbouring value (invariant 6).
        if len(fields) < 4 or not fields[3]:
            raise Hl7v2ParseError(f"OBX at segment {index} carries no observation identifier")

        identifier = fields[3].split(comp)
        raw_code = identifier[0]
        raw_label = identifier[1] if len(identifier) > 1 else ""
        raw_system = identifier[2] if len(identifier) > 2 else ""
        if not raw_code:
            raise Hl7v2ParseError(f"OBX at segment {index} carries an empty observation code")

        def component(field_index: int) -> str | None:
            if len(fields) <= field_index or not fields[field_index]:
                return None
            first_rep = fields[field_index].split(rep, 1)[0]
            token = first_rep.split(comp, 1)[0]
            decoded = _decode_escapes(token, sep, comp, sub, rep, esc)
            return decoded or None

        value_token = component(5)
        unit_token = component(6)
        abnormal_flag = fields[8] if len(fields) > 8 and fields[8] else None
        observed_at = _parse_ts(fields[14]) if len(fields) > 14 else None

        return InboundObservation(
            raw_system=_decode_escapes(raw_system, sep, comp, sub, rep, esc),
            raw_code=raw_code,
            raw_label=_decode_escapes(raw_label, sep, comp, sub, rep, esc),
            kind=RecordItemKind.LAB,
            value_token=value_token,
            unit_token=unit_token,
            observed_at=observed_at,
            abnormal_flag=abnormal_flag,
        )
