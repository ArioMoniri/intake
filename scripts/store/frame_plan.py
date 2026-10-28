"""INT-502: the frame spec, the captions and the geometry of every store image.

``docs/store/asc/frames.yaml`` sets which screens are captured, the app's own
colours and fonts, and the layout as fractions of the canvas.
:func:`frame_layout` and :func:`header_layout` turn those fractions into whole
pixels for one canvas size. They are pure functions, so the tests can hold the
geometry: the phone is whole and centred, its screen keeps the capture's aspect,
and the text stays readable. :func:`frame_paint` and :func:`header_paint` turn a
layout into the JSON plan ``paint.swift`` draws. The painter makes no decision of
its own.

Captions are store copy (CLAUDE.md invariant 18), so :func:`load_served_captions`
reads only the served file under ``docs/legal/store/screenshots/``. Until the legal
lane promotes the draft it refuses, and export fails closed.
:func:`load_captions` reads any caption file the caller names. ``--preview``
uses it to render a draft outside the repository.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "FRAMES",
    "HEADER_MAX_CHARS",
    "LINE_MAX_CHARS",
    "LOCALES",
    "Caption",
    "CaptionsMissingError",
    "FontSpec",
    "FrameLayout",
    "FrameSpec",
    "HeaderLayout",
    "PhoneGeometry",
    "PlanError",
    "Rect",
    "Target",
    "frame_layout",
    "frame_paint",
    "header_layout",
    "header_paint",
    "load_captions",
    "load_served_captions",
    "load_spec",
    "resolve_font",
    "served_captions_path",
]

REPO: Final[Path] = Path(__file__).resolve().parents[2]
FRAMES: Final[Path] = REPO / "docs" / "store" / "asc" / "frames.yaml"
LOCALES: Final[tuple[str, ...]] = ("tr", "en-US")
#: A headline line longer than this no longer fits two lines at a readable size.
LINE_MAX_CHARS: Final[int] = 18
#: The header headline is the served subtitle, which App Store Connect caps at 30.
HEADER_MAX_CHARS: Final[int] = 30


class PlanError(ValueError):
    """The spec, a caption or a font breaks its contract."""


class CaptionsMissingError(PlanError):
    """No served caption file: the draft has not been through the legal lane."""


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass(frozen=True)
class FontSpec:
    package: str
    version: str
    file: str
    licence: str
    sha256: str


@dataclass(frozen=True)
class Target:
    slot: str
    size: tuple[int, int]
    label: str


@dataclass(frozen=True)
class Frame:
    frame_id: str
    order: int
    route: str
    file: str
    appearance: str
    state: str
    #: An issue that must land before this frame can be captured truthfully.
    waits_for: str | None = None

    @property
    def capture_name(self) -> str:
        return f"{self.order:02d}-{self.frame_id}.png"


@dataclass(frozen=True)
class FrameSpec:
    capture_device: str
    capture_runtime: str
    capture_size: tuple[int, int]
    capture_mask: str
    status_bar: Mapping[str, Any]
    app_state: Mapping[str, str]
    capture_locales: Mapping[str, Mapping[str, str]]
    fonts: Mapping[str, FontSpec]
    theme: Mapping[str, Mapping[str, str]]
    shadows: Mapping[str, Mapping[str, float | str] | None]
    layout_frame: Mapping[str, Any]
    layout_header: Mapping[str, Any]
    targets: tuple[Target, ...]
    header_slot: str
    header_size: tuple[int, int]
    header_caption: str
    must_not_show: tuple[str, ...]
    frames: tuple[Frame, ...]

    @property
    def header_phones(self) -> tuple[str, ...]:
        return tuple(str(p) for p in self.layout_header["phones"])

    def frame(self, frame_id: str) -> Frame:
        for frame in self.frames:
            if frame.frame_id == frame_id:
                return frame
        raise PlanError(f"no frame {frame_id!r} in the spec")


@dataclass(frozen=True)
class Caption:
    caption_id: str
    screen: str
    #: locale → (eyebrow, headline); a headline line break is "\n".
    text: Mapping[str, tuple[str, str]]
    source: str
    quote: str


@dataclass(frozen=True)
class PhoneGeometry:
    body: Rect
    screen: Rect
    bezel: int
    outer_radius: float
    screen_radius: float


@dataclass(frozen=True)
class FrameLayout:
    canvas: tuple[int, int]
    eyebrow: Rect
    headline: Rect
    eyebrow_px: int
    headline_px: int
    phone: PhoneGeometry


@dataclass(frozen=True)
class HeaderLayout:
    canvas: tuple[int, int]
    eyebrow: Rect
    headline: Rect
    eyebrow_px: int
    headline_px: int
    phones: tuple[PhoneGeometry, ...]


def _size(raw: Any, where: str) -> tuple[int, int]:
    try:
        width, height = (int(v) for v in raw)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{where}: a size is [width, height]") from exc
    return width, height


def load_spec(path: Path) -> FrameSpec:
    """The frame spec, or the refusal that names what is malformed."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise PlanError(f"{path}: not a mapping")
    try:
        capture = raw["capture"]
        theme_raw = raw["theme"]
        frames = tuple(
            Frame(
                frame_id=str(row["id"]),
                order=index,
                route=str(row["route"]),
                file=str(row["file"]),
                appearance=str(row["appearance"]),
                state=str(row["state"]),
                waits_for=None if row.get("waits_for") is None else str(row["waits_for"]),
            )
            for index, row in enumerate(raw["frames"], start=1)
        )
        spec = FrameSpec(
            capture_device=str(capture["device"]),
            capture_runtime=str(capture["runtime"]),
            capture_size=_size(capture["size"], "capture.size"),
            capture_mask=str(capture["mask"]),
            status_bar=dict(capture["status_bar"]),
            app_state={str(k): str(v) for k, v in capture["app_state"].items()},
            capture_locales={str(k): dict(v) for k, v in capture["locales"].items()},
            fonts={
                str(k): FontSpec(**{key: str(v[key]) for key in FontSpec.__dataclass_fields__})
                for k, v in raw["fonts"].items()
            },
            theme={
                str(name): {k: str(v) for k, v in colours.items() if k != "shadow"}
                for name, colours in theme_raw.items()
            },
            shadows={str(name): colours.get("shadow") for name, colours in theme_raw.items()},
            layout_frame=dict(raw["layout"]["frame"]),
            layout_header=dict(raw["layout"]["header"]),
            targets=tuple(
                Target(str(t["slot"]), _size(t["size"], "targets"), str(t["label"]))
                for t in raw["targets"]
            ),
            header_slot=str(raw["header"]["slot"]),
            header_size=_size(raw["header"]["size"], "header.size"),
            header_caption=str(raw["header"]["caption"]),
            must_not_show=tuple(str(item) for item in raw["must_not_show"]),
            frames=frames,
        )
    except (KeyError, TypeError) as exc:
        raise PlanError(f"{path}: malformed ({exc})") from exc
    for frame in spec.frames:
        if frame.appearance not in spec.theme:
            raise PlanError(f"{frame.frame_id}: no theme {frame.appearance!r}")
    return spec


def _caption(row: Mapping[str, Any]) -> Caption:
    caption_id = str(row.get("id", "?"))
    if "tr" not in row:
        raise PlanError(f"caption {caption_id!r}: no tr text; Turkish is the source of truth")
    text: dict[str, tuple[str, str]] = {}
    for locale in LOCALES:
        if locale not in row:
            raise PlanError(f"caption {caption_id!r}: no {locale} text")
        entry = row[locale]
        text[locale] = (str(entry["eyebrow"]), str(entry["headline"]))
    return Caption(caption_id, str(row["screen"]), text, str(row["source"]), str(row["quote"]))


def load_captions(path: Path) -> dict[str, Caption]:
    """Every caption in ``path``, keyed by id. Turkish is required on each."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or not isinstance(raw.get("captions"), list):
        raise PlanError(f"{path}: no captions list")
    out: dict[str, Caption] = {}
    for row in raw["captions"]:
        caption = _caption(row)
        if caption.caption_id in out:
            raise PlanError(f"caption {caption.caption_id!r} appears twice")
        out[caption.caption_id] = caption
    return out


def served_captions_path(repo: Path) -> Path:
    return repo / "docs" / "legal" / "store" / "screenshots" / "app-store.captions.yaml"


def load_served_captions(repo: Path) -> dict[str, Caption]:
    """The served captions, or a refusal: export never reads a draft."""
    path = served_captions_path(repo)
    if not path.is_file():
        raise CaptionsMissingError(
            f"no served captions at {path.relative_to(repo)}: the draft "
            "docs/legal/drafts/store/app-store.screenshots.draft.yaml waits for the legal lane"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    status = str((raw or {}).get("provenance", {}).get("status", ""))
    if not status.startswith("served"):
        raise CaptionsMissingError(f"{path.name}: status {status!r} is not served (legal lane)")
    return load_captions(path)


def resolve_font(font: FontSpec, roots: Sequence[Path]) -> Path:
    """The font file under the first root holding it, checked against its pin."""
    for root in roots:
        candidate = root / font.package / font.file
        if candidate.is_file():
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest != font.sha256:
                raise PlanError(f"{font.package}/{font.file}: sha256 differs from the pin")
            return candidate
    raise PlanError(f"{font.package}/{font.file}: not installed under {[str(r) for r in roots]}")


def _phone(layout: Mapping[str, Any], x: int, y: int, width: int, aspect: float) -> PhoneGeometry:
    bezel = round(float(layout["bezel"]) * width)
    screen_w = width - 2 * bezel
    screen_h = round(screen_w * aspect)
    screen = Rect(x + bezel, y + bezel, screen_w, screen_h)
    screen_radius = float(layout["screen_radius"]) * screen_w
    return PhoneGeometry(
        body=Rect(x, y, width, screen_h + 2 * bezel),
        screen=screen,
        bezel=bezel,
        outer_radius=screen_radius + bezel,
        screen_radius=screen_radius,
    )


def _phone_width_for_height(layout: Mapping[str, Any], height: int, aspect: float) -> int:
    bezel = float(layout["bezel"])
    return int(height / ((1 - 2 * bezel) * aspect + 2 * bezel))


def frame_layout(spec: FrameSpec, canvas: tuple[int, int], capture: tuple[int, int]) -> FrameLayout:
    """Whole-pixel geometry of one screenshot frame at ``canvas`` size."""
    width, height = canvas
    lay = spec.layout_frame
    aspect = capture[1] / capture[0]
    side = round(float(lay["side"]) * width)
    eyebrow_px = round(float(lay["eyebrow_size"]) * width)
    headline_px = round(float(lay["headline_size"]) * width)
    line_h = round(headline_px * float(lay["headline_leading"]))
    eyebrow = Rect(
        side, round(float(lay["text_top"]) * height), width - 2 * side, round(eyebrow_px * 1.3)
    )
    headline = Rect(
        side,
        eyebrow.y + eyebrow.h + round(float(lay["eyebrow_gap"]) * height),
        width - 2 * side,
        int(lay["headline_lines"]) * line_h,
    )
    top = headline.y + headline.h + round(float(lay["phone_gap"]) * height)
    room = height - round(float(lay["bottom"]) * height) - top
    phone_w = min(_phone_width_for_height(lay, room, aspect), width - 2 * side)
    phone_w -= (width - phone_w) % 2  # even margins on both sides
    while True:
        phone = _phone(lay, (width - phone_w) // 2, top, phone_w, aspect)
        if phone.body.h <= room:
            break
        phone_w -= 2
    return FrameLayout(canvas, eyebrow, headline, eyebrow_px, headline_px, phone)


def header_layout(
    spec: FrameSpec, canvas: tuple[int, int], capture: tuple[int, int]
) -> HeaderLayout:
    """Whole-pixel geometry of the product page header: text over three phones."""
    width, height = canvas
    lay = spec.layout_header
    frame_lay = spec.layout_frame
    aspect = capture[1] / capture[0]
    eyebrow_px = round(float(lay["eyebrow_size"]) * height)
    headline_px = round(float(lay["headline_size"]) * height)
    eyebrow = Rect(0, round(float(lay["text_top"]) * height), width, round(eyebrow_px * 1.3))
    headline = Rect(
        0,
        eyebrow.y + eyebrow.h + round(float(lay["eyebrow_gap"]) * height),
        width,
        round(headline_px * 1.25),
    )
    top = headline.y + headline.h + round(float(lay["phone_gap"]) * height)
    room = height - round(float(lay["bottom"]) * height) - top
    count = len(lay["phones"])
    gutter = round(float(lay["gutter"]) * width)
    phone_w = _phone_width_for_height(frame_lay, room, aspect)
    while True:
        total = count * phone_w + (count - 1) * gutter
        total += (width - total) % 2
        probe = _phone(frame_lay, 0, top, phone_w, aspect)
        if probe.body.h <= room:
            break
        phone_w -= 1
    left = (width - total) // 2
    phones = tuple(
        _phone(frame_lay, left + i * (phone_w + gutter), top, phone_w, aspect) for i in range(count)
    )
    return HeaderLayout(canvas, eyebrow, headline, eyebrow_px, headline_px, phones)


def _phone_item(
    spec: FrameSpec, phone: PhoneGeometry, capture: Path, appearance: str, scale: float
) -> dict[str, Any]:
    colours = spec.theme[appearance]
    shadow = spec.shadows.get(appearance)
    return {
        "kind": "phone",
        "capture": str(capture),
        "body": phone.body.as_list(),
        "screen": phone.screen.as_list(),
        "outer_radius": phone.outer_radius,
        "screen_radius": phone.screen_radius,
        "body_color": colours["body"],
        "rim_color": colours["rim"],
        "rim_width": max(1, round(phone.bezel * 0.12)),
        "shadow": None
        if shadow is None
        else {
            "color": str(shadow["color"]),
            "opacity": float(shadow["opacity"]),
            "blur": float(shadow["radius"]) * scale,
            "offset_y": float(shadow["offset_y"]) * scale,
        },
    }


def _text_item(
    text: str, font: Path, px: int, colour: str, box: Rect, leading: float
) -> dict[str, Any]:
    return {
        "kind": "text",
        "text": text,
        "font": str(font),
        "size": px,
        "min_size": round(px * 0.85),
        "color": colour,
        "box": box.as_list(),
        "align": "center",
        "leading": leading,
    }


def frame_paint(
    spec: FrameSpec,
    layout: FrameLayout,
    text: tuple[str, str],
    capture: Path,
    appearance: str,
    fonts: Mapping[str, Path],
    out: Path,
) -> dict[str, Any]:
    """The painter's plan for one screenshot frame.

    The text block sits on the phone: a one-line headline moves the eyebrow and
    the headline down by one line, so the gap above the phone is the same on
    every frame."""
    colours = spec.theme[appearance]
    scale = layout.phone.screen.w / float(spec.layout_frame["pt_width"])
    leading = float(spec.layout_frame["headline_leading"])
    eyebrow, headline = text
    reserved = int(spec.layout_frame["headline_lines"])
    lines = headline.count("\n") + 1
    if lines > reserved:
        raise PlanError(f"{headline!r}: more than {reserved} lines")
    shift = (reserved - lines) * round(layout.headline_px * leading)
    eyebrow_box = Rect(
        layout.eyebrow.x, layout.eyebrow.y + shift, layout.eyebrow.w, layout.eyebrow.h
    )
    headline_box = Rect(
        layout.headline.x, layout.headline.y + shift, layout.headline.w, layout.headline.h - shift
    )
    plan: dict[str, Any] = {
        "out": str(out),
        "width": layout.canvas[0],
        "height": layout.canvas[1],
        "ground": colours["ground"],
        "items": [
            _text_item(
                eyebrow, fonts["label"], layout.eyebrow_px, colours["accent"], eyebrow_box, 1.0
            ),
            _text_item(
                headline,
                fonts["display"],
                layout.headline_px,
                colours["ink"],
                headline_box,
                leading,
            ),
            _phone_item(spec, layout.phone, capture, appearance, scale),
        ],
    }
    return plan


def header_paint(
    spec: FrameSpec,
    layout: HeaderLayout,
    text: tuple[str, str],
    captures: Sequence[Path],
    fonts: Mapping[str, Path],
    out: Path,
) -> dict[str, Any]:
    """The painter's plan for the product page header (light appearance)."""
    if len(captures) != len(layout.phones):
        raise PlanError(f"the header holds {len(layout.phones)} phones, not {len(captures)}")
    colours = spec.theme["light"]
    scale = layout.phones[0].screen.w / float(spec.layout_frame["pt_width"])
    eyebrow, headline = text
    plan: dict[str, Any] = {
        "out": str(out),
        "width": layout.canvas[0],
        "height": layout.canvas[1],
        "ground": colours["ground"],
        "items": [
            _text_item(
                eyebrow, fonts["label"], layout.eyebrow_px, colours["accent"], layout.eyebrow, 1.0
            ),
            _text_item(
                headline, fonts["display"], layout.headline_px, colours["ink"], layout.headline, 1.1
            ),
            *(
                _phone_item(spec, phone, capture, "light", scale)
                for phone, capture in zip(layout.phones, captures, strict=True)
            ),
        ],
    }
    return plan
