"""INT-037 — the minimal PDF primitive behind the DSAR export document.

Scope is deliberately narrow: this writer exists for the KVKK m.13 export
document (INT-037) and nothing else — the clinician-note renderer is INT-084's
own artefact. What is pinned here is the part a legal document cannot get
wrong: Turkish letters survive, nothing is silently dropped or transliterated,
the bytes are deterministic, and PDF string syntax is escaped rather than
injected into.
"""

from __future__ import annotations

import re

import pytest
from intake_platform.pdf import UnsupportedGlyphError, render_text_pdf

TURKISH = "Ağrı şikâyeti: İstanbul'da çok üşüdüm, ığdır, ĞŞİ."


def _render(lines: list[str]) -> bytes:
    return render_text_pdf(title="Test", lines=lines)


def test_output_is_a_pdf_with_a_terminated_trailer() -> None:
    data = _render(["satir bir"])
    assert data.startswith(b"%PDF-1.7")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in data
    assert b"startxref" in data


def test_the_cross_reference_offsets_point_at_their_objects() -> None:
    data = _render(["satir bir", "satir iki"])
    start = int(re.search(rb"startxref\s+(\d+)", data).group(1))  # type: ignore[union-attr]
    assert data[start : start + 4] == b"xref"
    offsets = [int(m.group(1)) for m in re.finditer(rb"^(\d{10}) 00000 n", data[start:], re.M)]
    assert offsets, "the xref table must list the objects"
    for index, offset in enumerate(offsets, start=1):
        assert data[offset:].startswith(f"{index} 0 obj".encode("ascii"))


def test_turkish_letters_round_trip_through_the_encoding() -> None:
    data = _render([TURKISH])
    # every Turkish-specific letter is carried by a /Differences slot, and the
    # six slots are declared on the font
    for glyph in (b"/gbreve", b"/Gbreve", b"/dotlessi", b"/Idotaccent", b"/scedilla", b"/Scedilla"):
        assert glyph in data, glyph
    assert b"/WinAnsiEncoding" in data


def test_a_character_outside_the_encoding_is_refused_not_dropped() -> None:
    with pytest.raises(UnsupportedGlyphError, match="U\\+4E2D"):
        _render(["中"])


def test_pdf_string_syntax_is_escaped() -> None:
    data = _render([r"paren ( close ) backslash \ end"])
    assert rb"paren \( close \) backslash \\ end" in data


def test_control_characters_are_refused() -> None:
    with pytest.raises(UnsupportedGlyphError):
        _render(["bir\x00iki"])


def test_rendering_is_deterministic() -> None:
    assert _render([TURKISH, "iki"]) == _render([TURKISH, "iki"])


def test_long_documents_paginate() -> None:
    data = render_text_pdf(title="Test", lines=[f"satir {n}" for n in range(200)])
    assert data.count(b"/Type /Page\n") >= 2, "200 lines must not be crushed onto one page"
    assert b"satir 199" in data
