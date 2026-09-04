"""The file-drop inbound channel (INT-162).

A file drop is the other common Turkish HBYS/SBYS interface: results written as
files to an agreed spool — an HL7 batch, or a delimited export — rather than
pushed over a socket. This channel is the validation gate in front of that
spool, and it holds two things the socket channels do not have to:

**The filename is untrusted and is checked before the bytes are.** A drop names
its own file, and a name is where traversal (``../../etc/passwd``) and a second
path are smuggled in. The grammar here is a single safe segment — the same
refusal :func:`~intake_connectors.destinations.require_path_shape` makes for an
outbound path, applied to a name that must contain no separator at all.

**The format is a closed set, not a guess.** A drop declares its format and the
channel dispatches on it; an HL7 file is handed to the very same
:class:`~intake_connectors.hl7v2.Hl7v2OruChannel` a stream would use (one parser,
one set of invariants), and a CSV of observations is read with the stdlib CSV
reader — never ``eval``, never a format inferred from the bytes. An
unrecognised format is refused rather than parsed hopefully.
"""

from __future__ import annotations

import csv
import io
import re

from clinical_schemas.records import RecordItemKind

from intake_connectors.hl7v2 import Hl7v2OruChannel, _parse_ts
from intake_connectors.inbound import (
    InboundMessage,
    InboundObservation,
    InboundParseError,
)

__all__ = ["FileDropChannel", "FileDropError"]

#: HL7 over a stream is bounded in the HL7 channel; a dropped file is bounded
#: here, before it is decoded or split.
_MAX_BYTES = 8 * 1024 * 1024

#: A single safe filename segment: letters, digits and ``._-`` only, so no
#: separator, no ``..`` and no traversal can appear. Anchored, bounded.
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: The declared formats this channel accepts, mapped to how each is read.
_FORMAT_HL7 = "application/hl7-v2+er7"
_FORMAT_CSV = "text/csv"

#: The columns a CSV drop must carry, in a fixed header. A missing or reordered
#: header is refused rather than mapped positionally, because a silently
#: mis-aligned column is how a value lands under the wrong analyte.
_CSV_COLUMNS = ("system", "code", "label", "value", "unit", "observed_at")


class FileDropError(InboundParseError):
    """A dropped file is not one this channel accepts. Names no value from it."""


class FileDropChannel:
    """Validate and dispatch one dropped file."""

    channel_id = "file-drop"

    def __init__(self, hl7: Hl7v2OruChannel | None = None) -> None:
        self._hl7 = hl7 if hl7 is not None else Hl7v2OruChannel()

    def parse(self, message: InboundMessage) -> tuple[InboundObservation, ...]:
        if message.filename is None:
            raise FileDropError("a file drop names its file; a drop with no filename is refused")
        if _FILENAME.match(message.filename) is None:
            raise FileDropError(
                "a dropped filename must be one safe segment (no separator, no traversal)"
            )
        if message.byte_count > _MAX_BYTES:
            raise FileDropError(
                f"dropped file exceeds {_MAX_BYTES} bytes and is refused before parsing"
            )
        if message.media_type == _FORMAT_HL7:
            return self._hl7.parse(message)
        if message.media_type == _FORMAT_CSV:
            return self._parse_csv(message.body)
        raise FileDropError(
            f"declared format {message.media_type!r} is not a file-drop format this channel accepts"
        )

    @staticmethod
    def _parse_csv(body: bytes) -> tuple[InboundObservation, ...]:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("iso-8859-1")
        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration:
            raise FileDropError("an observations CSV has a header row") from None
        if tuple(column.strip() for column in header) != _CSV_COLUMNS:
            raise FileDropError(
                "an observations CSV must declare the fixed header "
                "system,code,label,value,unit,observed_at"
            )
        observations: list[InboundObservation] = []
        for number, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != len(_CSV_COLUMNS):
                raise FileDropError(f"row {number} does not have {len(_CSV_COLUMNS)} columns")
            system, code, label, value, unit, observed_at = (cell.strip() for cell in row)
            if not code:
                raise FileDropError(f"row {number} carries no observation code")
            observations.append(
                InboundObservation(
                    raw_system=system,
                    raw_code=code,
                    raw_label=label,
                    kind=RecordItemKind.LAB,
                    value_token=value or None,
                    unit_token=unit or None,
                    observed_at=_parse_ts(observed_at) if observed_at else None,
                )
            )
        return tuple(observations)
