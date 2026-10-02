"""Writes docs/store/screenshots/app-store-screenshots.json (INT-425).

One spec, three decks: iPhone (1320×2868 canvas), Android phone (1080×1920)
and the Play feature graphic (1024×500). Every frame uses the same grid: an
eyebrow and a two-line headline flush-left on an 8 % margin, and one real
capture in a full, centred device frame below it. The order is the patient's
journey. Turkish is the store copy; English is carried for a bilingual listing
and exported only if "en" is added to `locales`.

    python3 docs/store/screenshots/tools/gen_project.py [iphone|android|feature-graphic]

The optional argument is the deck the editor opens on, which is the deck its
"Export bundle" button renders.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app-store-screenshots.json"

# (capture, eyebrow tr/en, headline tr/en, dark ground)
FRAMES = [
    (
        "01-bugun",
        ("Önvizit", "Önvizit"),
        ("Muayeneye\nhazır gidin.", "Arrive at your\nvisit ready."),
        False,
    ),
    (
        "02-konusma",
        ("Sesle ya da yazarak", "By voice or by text"),
        ("Anlatın,\nbiz not alalım.", "You talk,\nwe take notes."),
        False,
    ),
    (
        "03-tek-soru",
        ("Adım adım", "Step by step"),
        ("Her seferde\ntek soru.", "One question\nat a time."),
        False,
    ),
    (
        "04-not",
        ("Hekiminize gidecek not", "Your note for the doctor"),
        ("Paylaşılanı\nsiz seçin.", "You choose\nwhat is shared."),
        False,
    ),
    (
        "05-onceki-bilgiler",
        ("Önceki kayıtlar", "Earlier records"),
        ("Eski bilgiler\nsize sorulur.", "Old details\nare checked with you."),
        False,
    ),
    (
        "06-not-durumu",
        ("Not durumu", "Note status"),
        ("Notunuzun\ndurumunu görün.", "See where\nyour note is."),
        False,
    ),
    (
        "07-paylasim",
        ("Paylaşım bağlantısı", "Share link"),
        ("Hekiminize\ngösterin.", "Show it to\nyour doctor."),
        False,
    ),
    (
        "08-gorunum",
        ("Görünüm", "Appearance"),
        ("Yazı boyu\nsize göre.", "Text sized\nfor you."),
        True,
    ),
]

FEATURE = {
    "tr": "Muayeneden önce anlatın,\nhekiminize hazır gidin.",
    "en": "Tell it before the visit.\nArrive ready.",
}

# Grid per deck, in canvas pixels.
GRID = {
    "iphone": {
        "caption": (104, 250, 1112, 440),
        "device": (170, 720, 980, 980 / (1022 / 2082)),
        "icon": (104, 96, 128),
    },
    "android": {
        "caption": (85, 160, 910, 360),
        "device": (230, 520, 620, 620 / (9 / 19.5)),
        "icon": (85, 52, 96),
    },
}


def rect(x: float, y: float, w: float, h: float, z: int) -> dict[str, float]:
    return {"x": x, "y": y, "width": w, "height": round(h, 2), "rotation": 0, "zIndex": z}


def slides(device: str) -> list[dict[str, object]]:
    g = GRID[device]
    out: list[dict[str, object]] = []
    for i, (shot, label, headline, dark) in enumerate(FRAMES):
        slide: dict[str, object] = {
            "id": f"{device}-{i + 1:02d}",
            "layout": "device-bottom",
            "captionAlign": "left",
            "label": {"tr": label[0], "en": label[1]},
            "headline": {"tr": headline[0], "en": headline[1]},
            # The app ships a Turkish UI only, so both locales use the Turkish captures.
            "screenshot": f"/screenshots/captures/{shot}.png",
            "transforms": {"caption": rect(*g["caption"], 4), "device": rect(*g["device"], 3)},
        }
        if dark:
            slide["inverted"] = True
        if i == 0:
            x, y, size = g["icon"]
            slide["imageElements"] = [
                {
                    "id": "app-icon",
                    "src": "/onvizit-icon-rounded.png",
                    "fit": "contain",
                    "transform": rect(x, y, size, size, 6),
                }
            ]
        out.append(slide)
    return out


def main(active: str) -> None:
    project = {
        "schemaVersion": 2,
        "appName": "Önvizit",
        "themeId": "onvizit-clinical",
        "fontId": "platform-native",
        "connectedCanvas": False,
        "locales": ["tr"],
        "locale": "tr",
        "device": active,
        "orientation": "portrait",
        "appIcon": "/onvizit-icon.png",
        "slidesByDevice": {
            "iphone": slides("iphone"),
            "android": slides("android"),
            "feature-graphic": [
                {
                    "id": "feature-graphic-01",
                    "layout": "feature-graphic",
                    "label": {},
                    "headline": FEATURE,
                    "screenshot": "",
                }
            ],
        },
    }
    OUT.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "iphone")
