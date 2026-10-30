"""INT-502: render the App Store screenshots and the product page header.

It takes the real captures in ``docs/store/asc/captures/<locale>/`` and lays each
one into its frame at every target size, and builds the header from three of them
(:mod:`frame_plan`). It paints them with ``paint.swift`` (CoreGraphics, macOS) and
checks every file it wrote against its App Store slot with :mod:`asc_assets`.

Two modes, and only one reads served copy:

``--export``
    Captions come only from the served file under ``docs/legal/store/screenshots/``.
    With no served file it exits 3 and writes nothing. Output goes to
    ``docs/store/asc/export/<slot>/<locale>/``, the paths
    ``docs/store/asc/assets.yaml`` lists.
``--preview --captions FILE --out DIR``
    Renders any caption file, a draft included, so the owner and the legal lane can
    see the frames before approving them. DIR must be outside the repository, so a
    preview can never be committed or uploaded by mistake.

Every capture must be the capture device's exact size (1320×2868, the iPhone 17 Pro
Max simulator) and carry a production file name. Anything else is refused before
painting.

Exit codes: 0 done · 2 refused (usage, preview inside the repo) · 3 no served
captions · 4 a capture is missing or wrong · 5 painting failed or an output failed
its slot check.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import asc_assets
import frame_plan

__all__ = ["EXPORT", "check_capture", "main", "plan_jobs"]

EXPORT: Final[str] = "docs/store/asc/export"
CAPTURES: Final[str] = "docs/store/asc/captures"
PAINTER: Final[Path] = Path(__file__).resolve().parent / "paint.swift"


def check_capture(path: Path, spec: frame_plan.FrameSpec) -> tuple[str, ...]:
    """Every reason ``path`` is not a usable capture, or ``()``."""
    problems: list[str] = []
    if asc_assets.banned_name(path.name):
        problems.append(f"{path.name}: the file name marks a non-production capture")
    if not path.is_file():
        return (*problems, f"{path}: no such capture")
    facts = asc_assets.read_png_facts(path)
    want = f"{spec.capture_size[0]}x{spec.capture_size[1]}"
    if facts is None:
        problems.append(f"{path.name}: not a PNG")
    elif (facts[0], facts[1]) != spec.capture_size:
        problems.append(f"{path.name}: {facts[0]}x{facts[1]}, the capture device makes {want}")
    return tuple(problems)


def plan_jobs(
    spec: frame_plan.FrameSpec,
    captions: dict[str, frame_plan.Caption],
    captures_root: Path,
    out_root: Path,
    fonts: dict[str, Path],
    locales: Sequence[str],
) -> tuple[list[dict[str, Any]], list[tuple[Path, str]]]:
    """Every paint plan, and each output with the slot it must fill."""
    jobs: list[dict[str, Any]] = []
    outputs: list[tuple[Path, str]] = []
    for locale in locales:
        for target in spec.targets:
            layout = frame_plan.frame_layout(spec, target.size, spec.capture_size)
            for frame in spec.shipped_frames:
                out = out_root / target.slot / locale / frame.capture_name
                capture = captures_root / locale / frame.capture_name
                text = captions[frame.frame_id].text[locale]
                jobs.append(
                    frame_plan.frame_paint(
                        spec, layout, text, capture, frame.appearance, fonts, out
                    )
                )
                outputs.append((out, target.slot))
        header = frame_plan.header_layout(spec, spec.header_size, spec.capture_size)
        phones = [
            captures_root / locale / spec.frame(fid).capture_name for fid in spec.header_phones
        ]
        out = out_root / spec.header_slot / locale / "header.png"
        jobs.append(
            frame_plan.header_paint(
                spec, header, captions[spec.header_caption].text[locale], phones, fonts, out
            )
        )
        outputs.append((out, spec.header_slot))
    return jobs, outputs


def _paint(jobs: list[dict[str, Any]]) -> None:
    with tempfile.TemporaryDirectory(prefix="int502-paint-") as work:
        binary = Path(work) / "paint"
        subprocess.run(  # noqa: S603 — fixed argv, repo source
            ["xcrun", "swiftc", "-O", "-o", str(binary), str(PAINTER)],  # noqa: S607
            check=True,
        )
        plans = Path(work) / "plans.json"
        plans.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        subprocess.run([str(binary), str(plans)], check=True)  # noqa: S603


def _verify(outputs: list[tuple[Path, str]]) -> list[str]:
    manifest = asc_assets.load_manifest(asc_assets.MANIFEST)
    slots = {entry.asset_id: entry for entry in manifest.entries}
    return [p for out, slot in outputs for p in asc_assets.check_file(out, slots[slot])]


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--preview", action="store_true")
    parser.add_argument("--repo", type=Path, default=frame_plan.REPO)
    parser.add_argument("--captions", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--locale", action="append", choices=frame_plan.LOCALES)
    parser.add_argument("--fonts-root", type=Path, action="append", default=[])
    return parser.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    repo = args.repo.resolve()
    if args.export:
        try:
            captions = frame_plan.load_served_captions(repo)
        except frame_plan.CaptionsMissingError as exc:
            print(f"REFUSED {exc}", file=sys.stderr)
            return 3
        captures_root, out_root = repo / CAPTURES, repo / EXPORT
    else:
        if args.captions is None or args.captures is None or args.out is None:
            print("REFUSED --preview needs --captions, --captures and --out", file=sys.stderr)
            return 2
        out_root = args.out.resolve()
        if out_root == repo or repo in out_root.parents:
            print("REFUSED a preview is written outside the repository", file=sys.stderr)
            return 2
        captions = frame_plan.load_captions(args.captions)
        captures_root = args.captures.resolve()
    spec = frame_plan.load_spec(repo / "docs" / "store" / "asc" / "frames.yaml")
    foreign = [loc for loc in args.locale or [] if loc not in spec.capture_locales]
    if foreign:
        print(f"REFUSED {foreign}: ships no frames of its own (frames.yaml)", file=sys.stderr)
        return 2
    locales = args.locale or [loc for loc in spec.capture_locales if (captures_root / loc).is_dir()]
    problems = [
        p
        for loc in locales
        for frame in spec.shipped_frames
        for p in check_capture(captures_root / loc / frame.capture_name, spec)
    ]
    if not locales or problems:
        print("REFUSED captures:\n" + "\n".join(problems or ["no locale has captures"]))
        return 4
    roots = [*args.fonts_root, repo / "apps" / "mobile" / "node_modules"]
    fonts = {name: frame_plan.resolve_font(font, roots) for name, font in spec.fonts.items()}
    jobs, outputs = plan_jobs(spec, captions, captures_root, out_root, fonts, locales)
    try:
        _paint(jobs)
    except subprocess.CalledProcessError as exc:
        print(f"FAILED painting: {exc}", file=sys.stderr)
        return 5
    failed = _verify(outputs)
    if failed:
        print("FAILED slot checks:\n" + "\n".join(failed), file=sys.stderr)
        return 5
    for out, slot in outputs:
        print(f"OK {slot} {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
