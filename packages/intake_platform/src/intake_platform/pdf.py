"""A minimal, deterministic PDF writer for the KVKK m.13 export document.

SCOPE, stated so it is not mistaken for a general renderer: this exists for
the INT-037 data-subject export document. The clinician-facing pre-visit note
PDF is INT-084's own artefact with its own layout, sections and sign-off, and
it does not reuse this module's page design — only, if it wants it later, this
module's byte-level plumbing.

Design constraints, in the order that decided the code:

1. **No new dependency.** Every PDF library in reach is either a heavyweight
   transitive tree or a licence that needs its own raw-LICENSE audit before it
   may touch a workspace that ships to a hospital. Nine hundred lines of
   Type1-font machinery are not needed to lay out text lines; the format's own
   primitives are enough.
2. **Turkish must survive intact.** The six Turkish-specific letters
   (ğĞşŞıİ) are absent from WinAnsi, so they ride a ``/Differences`` array
   under their standard Adobe glyph names. WinAnsi leaves exactly **five**
   codes undefined (0x81, 0x8D, 0x8F, 0x90, 0x9D), so the sixth slot re-points
   0x8E, which WinAnsi assigns to ``Zcaron``. That is safe rather than lucky:
   ``/Differences`` overrides the base encoding at that code, and ``Ž`` is
   itself unencodable here, so no collision can arise. The consequence worth
   knowing is that a text extractor which ignores ``/Differences`` for a
   standard-14 font will read ``ı`` back as ``Ž`` — and that **0x9E is not
   free either** (``zcaron``), so a seventh letter needs a real answer, not
   another borrowed code.
3. **Never silently transliterate.** A character this encoding cannot carry
   either raises :class:`UnsupportedGlyphError` or, for a caller that must
   produce a document anyway, renders as ``[U+<codepoint>]``. A legal document that
   quietly turns "ğ" into "g" is a document that misstates what the patient
   wrote; one that names what it could not draw does not.
4. **Deterministic bytes.** No creation date, no object ids that depend on
   iteration order, no randomness: the same content renders the same bytes, so
   an export's SHA-256 is a stable receipt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "PAGE_HEIGHT_PT",
    "PAGE_WIDTH_PT",
    "UnsupportedGlyphError",
    "encode_text",
    "render_text_pdf",
]


class UnsupportedGlyphError(ValueError):
    """A character the export encoding cannot carry. Refused, never mapped to
    a lookalike: the exported text must be the text that was stored."""


# A4 at 72 dpi.
PAGE_WIDTH_PT = 595
PAGE_HEIGHT_PT = 842

_MARGIN_PT = 56
_TITLE_SIZE_PT = 14
_BODY_SIZE_PT = 10
_LEADING_PT = 14
_LINES_PER_PAGE = (PAGE_HEIGHT_PT - 2 * _MARGIN_PT) // _LEADING_PT - 2

#: The six Turkish letters WinAnsi lacks. Five ride WinAnsi's undefined codes
#: (0x81, 0x8D, 0x8F, 0x90, 0x9D); 0x8E re-points ``Zcaron`` — see the module
#: docstring for why that is safe. Named by Adobe glyph name in /Differences.
_TURKISH_SLOTS: tuple[tuple[str, int, str], ...] = (
    ("ğ", 0x81, "gbreve"),
    ("Ğ", 0x8D, "Gbreve"),
    ("ı", 0x8E, "dotlessi"),
    ("İ", 0x8F, "Idotaccent"),
    ("ş", 0x90, "scedilla"),
    ("Ş", 0x9D, "Scedilla"),
)

#: The WinAnsi (CP1252) printable extras in 0x80–0x9F we actually emit. Kept
#: short on purpose: an unlisted character raises rather than guessing.
_WINANSI_EXTRAS: dict[str, int] = {
    "€": 0x80,
    "‚": 0x82,
    "„": 0x84,
    "…": 0x85,
    "‰": 0x89,
    "‹": 0x8B,
    "‘": 0x91,
    "’": 0x92,
    "“": 0x93,
    "”": 0x94,
    "•": 0x95,
    "–": 0x96,
    "—": 0x97,
    "™": 0x99,
    "›": 0x9B,
}

_ENCODING: dict[str, int] = {
    **{char: code for char, code, _ in _TURKISH_SLOTS},
    **_WINANSI_EXTRAS,
}


def encode_text(text: str, *, escape_unencodable: bool = False) -> bytes:
    """Text → the page's single-byte encoding.

    Two behaviours, because two callers need different things and neither may
    transliterate. The default REFUSES an unencodable character — right for a
    caller that can go back and ask. ``escape_unencodable`` instead writes
    ``[U+<codepoint>]``, naming the codepoint — right for a caller under a statutory
    duty to produce the document, where refusing for ever discharges nothing.
    Neither substitutes a lookalike: ``250 ₺`` must not become ``250 ?`` or
    ``250 TL``.
    """
    out = bytearray()
    for char in text:
        code = _ENCODING.get(char)
        if code is None:
            point = ord(char)
            if 0x20 <= point <= 0x7E or 0xA0 <= point <= 0xFF:
                code = point
            elif escape_unencodable:
                out.extend(f"[U+{point:04X}]".encode("ascii"))
                continue
            else:
                raise UnsupportedGlyphError(
                    f"U+{point:04X} is outside the export encoding (WinAnsi plus the "
                    "Turkish slots); the exporter refuses rather than substituting a "
                    "lookalike. Pass escape_unencodable=True to name it instead."
                )
        out.append(code)
    return bytes(out)


def _pdf_string(text: str, *, escape_unencodable: bool = False) -> bytes:
    escaped = bytearray()
    for byte in encode_text(text, escape_unencodable=escape_unencodable):
        if byte in (0x28, 0x29, 0x5C):  # ( ) \
            escaped.append(0x5C)
        escaped.append(byte)
    return b"(" + bytes(escaped) + b")"


@dataclass(frozen=True)
class _Page:
    lines: tuple[str, ...]
    title: str | None


def _content_stream(page: _Page, *, escape_unencodable: bool) -> bytes:
    parts = [b"BT\n"]
    y = PAGE_HEIGHT_PT - _MARGIN_PT
    if page.title is not None:
        parts.append(f"/F1 {_TITLE_SIZE_PT} Tf\n".encode("ascii"))
        parts.append(f"1 0 0 1 {_MARGIN_PT} {y} Tm\n".encode("ascii"))
        parts.append(_pdf_string(page.title, escape_unencodable=escape_unencodable) + b" Tj\n")
        y -= _LEADING_PT * 2
    parts.append(f"/F1 {_BODY_SIZE_PT} Tf\n".encode("ascii"))
    for line in page.lines:
        parts.append(f"1 0 0 1 {_MARGIN_PT} {y} Tm\n".encode("ascii"))
        parts.append(_pdf_string(line, escape_unencodable=escape_unencodable) + b" Tj\n")
        y -= _LEADING_PT
    parts.append(b"ET\n")
    return b"".join(parts)


def _differences() -> bytes:
    items = " ".join(f"{code} /{name}" for _, code, name in _TURKISH_SLOTS)
    return f"[ {items} ]".encode("ascii")


def render_text_pdf(*, title: str, lines: Sequence[str], escape_unencodable: bool = False) -> bytes:
    """Render ``lines`` as a paginated PDF. Deterministic for equal inputs.

    ``escape_unencodable`` passes through to :func:`encode_text`: off, an
    undrawable character raises; on, it renders as ``[U+<codepoint>]``.
    """
    chunks: list[_Page] = []
    remaining = list(lines)
    first = True
    while remaining or first:
        take = _LINES_PER_PAGE - (2 if first else 0)
        chunks.append(_Page(tuple(remaining[:take]), title if first else None))
        remaining = remaining[take:]
        first = False

    # object ids: 1 catalog, 2 pages, 3 font, 4 encoding, then page/content pairs
    page_ids = [5 + 2 * index for index in range(len(chunks))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            "<< /Type /Pages /Count {count} /Kids [{kids}] >>".format(
                count=len(chunks),
                kids=" ".join(f"{pid} 0 R" for pid in page_ids),
            ).encode("ascii")
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding 4 0 R >>",
        b"<< /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences "
        + _differences()
        + b" >>",
    ]
    for index, page in enumerate(chunks):
        content_id = page_ids[index] + 1
        objects.append(
            (
                f"<< /Type /Page\n/Parent 2 0 R\n"
                f"/MediaBox [0 0 {PAGE_WIDTH_PT} {PAGE_HEIGHT_PT}]\n"
                f"/Resources << /Font << /F1 3 0 R >> >>\n/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        stream = _content_stream(page, escape_unencodable=escape_unencodable)
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)
