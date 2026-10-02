"""INT-425: the store screenshot set and its source project.

Holds what a reviewer of a store listing would otherwise have to check by eye:
every required size exists for every frame, the deck is the Önvizit brand only,
the copy carries no performance or medical claim, and every frame is built from
a committed real capture.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
from pathlib import Path


def png_header(path: Path) -> tuple[int, int, int]:
    """(width, height, colour type) from the IHDR chunk; type 2 is RGB, no alpha."""
    head = path.read_bytes()[:26]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR", path
    width, height = struct.unpack(">II", head[16:24])
    return width, height, head[25]


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "docs" / "store" / "screenshots"
PROJECT = json.loads((STORE / "app-store-screenshots.json").read_text(encoding="utf-8"))

# App Store Connect iPhone slots and Google Play phone + feature graphic.
SIZES = {
    "ios/iphone": [(1320, 2868), (1284, 2778), (1206, 2622), (1125, 2436)],
    "android/android": [(1080, 1920)],
    "android/feature-graphic": [(1024, 500)],
}
FRAMES = {"ios/iphone": 8, "android/android": 8, "android/feature-graphic": 1}
OLD_BRAND = "Viz" + "ite"  # the retired name, spelled so this file never matches itself


def test_every_required_size_exists_for_every_frame() -> None:
    for deck, sizes in SIZES.items():
        for w, h in sizes:
            folder = STORE / "export" / deck / f"{w}x{h}" / "tr"
            pngs = sorted(folder.glob("*.png"))
            assert len(pngs) == FRAMES[deck], f"{folder}: {len(pngs)} frames"
            for png in pngs:
                width, height, colour = png_header(png)
                assert (width, height) == (w, h), png
                assert colour == 2, f"{png}: stores reject alpha"


def test_frames_follow_the_journey_one_capture_each() -> None:
    for device in ("iphone", "android"):
        slides = PROJECT["slidesByDevice"][device]
        shots = [s["screenshot"] for s in slides]
        assert len(shots) == len(set(shots)) == 8, "one benefit, one capture per frame"
        assert shots == sorted(shots), "frames stay in journey order"
        for shot in shots:
            assert (STORE / "captures" / Path(shot).name).is_file(), shot


def test_brand_is_onvizit_and_copy_is_turkish_first() -> None:
    assert PROJECT["appName"] == "Önvizit"
    assert PROJECT["locales"][0] == "tr"
    text = json.dumps(PROJECT, ensure_ascii=False)
    assert OLD_BRAND not in text
    for slide in PROJECT["slidesByDevice"]["iphone"]:
        headline = slide["headline"]["tr"]
        assert 1 <= headline.count("\n") + 1 <= 2, headline
        assert all(len(line) <= 16 for line in headline.split("\n")), headline


def test_copy_passes_the_claims_gate_and_names_no_diagnosis_or_ai() -> None:
    files = [
        str(STORE / "app-store-screenshots.json"),
        str(ROOT / "docs/design/store-screenshots.md"),
    ]
    run = subprocess.run(  # noqa: S603 — fixed argv, repo script
        ["bash", str(ROOT / "scripts/ci/claims_scan.sh"), "--strict", *files],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    copy = " ".join(
        f"{s['label'].get('tr', '')} {s['headline'].get('tr', '')}"
        for s in PROJECT["slidesByDevice"]["iphone"]
    ).lower()
    for word in ("teşhis", "tanı koy", "yapay zek", "%", "kesin", "garanti"):
        assert word not in copy, word
    assert not re.search(r"\bai\b", copy)
