"""INT-465: a RED script's authoring markup is expanded before the screen and before TTS.

The generic RED ON_SITE line comes from CD-24 verbatim:
``**Acil Servis'e gidin[ — {{tenant.acil_location_tr}}].** Randevuyu beklemeyin. …``.
It carries two kinds of authoring markup:
- bold markers;
- an optional segment that holds the tenant's ``acil_location_tr``.

Neither may reach a patient's screen or a TTS request as written:
- An asterisk read aloud is noise inside a RED.
- A literal ``{{…}}`` is worse.

files/02 §5.3 and files/04 §8.2 (``tenant_acil_location_string_is_never_defaulted``)
fix what the segment means. With the tenant's value it reads "Acil Servis'e gidin — <value>".
With no value the whole segment is dropped, and it never falls back to an invented floor,
wing or direction.

Invariant 22: every numeral is expanded before TTS. So the spoken form is the rendered text
run through the compiler's Turkish expander, and 112 becomes "yüz on iki".

Each refusal below has a near miss.
"""

from __future__ import annotations

import re

import pytest
from protocols.compile.number_expansion import expand_for_locale
from protocols.red_render import (
    RedRenderError,
    assert_markup_free,
    assert_speakable_red,
    render_red_text,
    spoken_red_text,
)

ON_SITE = (
    "**Acil Servis'e gidin[ — {{tenant.acil_location_tr}}].** Randevuyu beklemeyin. "
    "Görevlilere haber verildi."
)
REMOTE = "Hemen 112 Acil Çağrı Merkezi'ni arayın."
MARKUP = re.compile(r"[*{}\[\]]")


def test_unset_location_drops_the_segment_and_the_bold_markers() -> None:
    assert render_red_text(ON_SITE, acil_location_tr=None) == (
        "Acil Servis'e gidin. Randevuyu beklemeyin. Görevlilere haber verildi."
    )


def test_a_set_location_is_rendered_into_the_segment() -> None:
    assert render_red_text(ON_SITE, acil_location_tr="zemin kat") == (
        "Acil Servis'e gidin — zemin kat. Randevuyu beklemeyin. Görevlilere haber verildi."
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_location_is_unset_never_a_default(blank: str) -> None:
    """files/04 §8.2: the segment is dropped, never filled with a guess."""
    assert render_red_text(ON_SITE, acil_location_tr=blank) == render_red_text(
        ON_SITE, acil_location_tr=None
    )


def test_text_without_markup_is_unchanged() -> None:
    """Near miss: the REMOTE line has no markup, so rendering leaves it alone."""
    assert render_red_text(REMOTE, acil_location_tr="zemin kat") == REMOTE


@pytest.mark.parametrize(
    "authored",
    [
        "Gidin[ — {{tenant.floor}}].",  # a template field nobody defined
        "Gidin {{tenant.acil_location_tr}}.",  # the location outside its optional segment
        "**Gidin.",  # an unpaired bold marker
        "Gi*din.",  # a lone asterisk
        "Gidin[ — {{tenant.acil_location_tr}}.",  # an unclosed segment
        "Gidin].",  # a stray closing bracket
        "Gidin[ yukarı ].",  # a segment with no template field in it
    ],
    ids=[
        "unknown-template-field",
        "bare-template-field",
        "unpaired-bold",
        "lone-asterisk",
        "unclosed-segment",
        "stray-bracket",
        "segment-without-template-field",
    ],
)
def test_markup_the_renderer_does_not_define_is_refused(authored: str) -> None:
    with pytest.raises(RedRenderError):
        render_red_text(authored, acil_location_tr=None)


@pytest.mark.parametrize(
    "value",
    ["**kat**", "{{x}}", "[kat]", "kat\nB blok", "a" * 121, "112 kapısı", "yüz on iki kapısı"],
)
def test_a_tenant_value_cannot_smuggle_markup_or_lines(value: str) -> None:
    with pytest.raises(RedRenderError):
        render_red_text(ON_SITE, acil_location_tr=value)


def test_the_spoken_form_expands_112_and_carries_no_markup() -> None:
    spoken = spoken_red_text(REMOTE, acil_location_tr=None)
    assert spoken == "Hemen yüz on iki Acil Çağrı Merkezi'ni arayın."
    assert not re.search(r"\d", spoken)
    on_site = spoken_red_text(ON_SITE, acil_location_tr=None)
    assert not MARKUP.search(on_site)
    assert not re.search(r"\d", on_site)


@pytest.mark.parametrize(
    "row",
    ["Hemen 112 Acil Çağrı Merkezi'ni arayın.", "Hemen **yüz on iki** arayın.", "Gidin {{x}}."],
    ids=["digit", "markup", "template-field"],
)
def test_a_red_clip_row_with_a_digit_or_markup_is_refused(row: str) -> None:
    """Invariant 22: no numeral reaches a TTS model. This is the last check before a
    RED clip row is handed over. Near miss: the expanded form is speakable."""
    with pytest.raises(RedRenderError):
        assert_speakable_red(row)
    assert_speakable_red("Hemen yüz on iki Acil Çağrı Merkezi'ni arayın.")


def test_the_served_cardiac_remote_line_has_no_spoken_form_yet() -> None:
    """INT-455 and INT-456 stay blockers to any spoken RED rule script: the
    exemplar's "**112**'yi" cannot be expanded, so it can never be handed to a TTS
    model. Near miss: the generic's bare "112 " can."""
    from protocols.compile.tr_orthography import TrExpansionError

    with pytest.raises(TrExpansionError):
        spoken_red_text("Hemen **112**'yi arayın.", acil_location_tr=None)
    assert spoken_red_text(REMOTE, acil_location_tr=None)


def test_without_the_render_step_markup_would_reach_tts() -> None:
    """Near miss: the expander alone passes the markup straight through, so
    the render step is what keeps an asterisk or a template field out of a TTS request."""
    raw = expand_for_locale(ON_SITE, "tr").text
    assert MARKUP.search(raw)
    with pytest.raises(RedRenderError):
        assert_markup_free(raw)
    assert_markup_free(spoken_red_text(ON_SITE, acil_location_tr=None))
