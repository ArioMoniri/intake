"""INT-502: capture the App Store frames from the real app on the iOS simulator.

The screens are the real app with simulated patients only. Each capture is the
simulator's own screenshot at the device's native size, 1320×2868 on the iPhone 17
Pro Max. Nothing is drawn, edited or mocked inside the phone. This script sets
what a store capture needs and checks what it gets:

- **Before the first shot:** a clean status bar (``xcrun simctl status_bar …
  override``) and the locale's language and region.
- **Before each shot:** the frame's appearance (``xcrun simctl ui … appearance``).
  The route opens by deep link when a visit id is given. Then the operator
  confirms that the screen shows the frame's state and nothing on the
  must-not-show list.
- **After each shot:** the file must be the device's exact size, or it is deleted
  and the run stops. Its sha256 goes into ``provenance.yaml``, together with the
  device, the runtime, the app's git sha, the API it talked to and the data class.
  No screen value is ever written there.

The session refuses anything but ``data_class: synthetic``, a build named by a full
git sha, and a locale the spec lists. Commands go through a :class:`Runner`, so the
tests drive the whole sequence without a simulator.

Usage (one locale per run)::

    uv run python scripts/store/capture_frames.py --locale tr --app-sha <40-hex sha> \
        --api-label "local dev API, mock SMS and attestation adapters" [--visit <id>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final, Protocol

import asc_assets
import frame_plan
import yaml

__all__ = [
    "CaptureError",
    "CaptureSession",
    "Runner",
    "Shot",
    "SubprocessRunner",
    "main",
    "prepare",
    "shoot",
    "write_provenance",
]

SCHEME: Final[str] = "onvizit"
_SHA: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")
_UDID: Final[re.Pattern[str]] = re.compile(r"[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}")


class CaptureError(Exception):
    """The session or a shot breaks a store-capture rule."""


class Runner(Protocol):
    def run(self, argv: Sequence[str]) -> str: ...


class SubprocessRunner:
    def run(self, argv: Sequence[str]) -> str:
        done = subprocess.run(  # noqa: S603 — argv built here from fixed parts
            list(argv), check=True, capture_output=True, text=True
        )
        return done.stdout


@dataclass(frozen=True)
class Shot:
    name: str
    sha256: str
    appearance: str
    route: str


@dataclass
class CaptureSession:
    spec: frame_plan.FrameSpec
    udid: str
    locale: str
    out_dir: Path
    app_sha: str
    data_class: str
    api_label: str
    runner: Runner
    confirm: Callable[[str], None]
    visit: str | None = None
    #: Issues the operator confirms have landed in this build (``--resolved``).
    resolved: frozenset[str] = frozenset()
    shots: list[Shot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.data_class != "synthetic":
            raise CaptureError(
                f"data class {self.data_class!r}: store captures use synthetic patients only"
            )
        if not _SHA.fullmatch(self.app_sha):
            raise CaptureError("app_sha must be the full 40-character git sha of the build")
        if self.locale not in self.spec.capture_locales:
            raise CaptureError(f"locale {self.locale!r} is not in the spec")
        if not _UDID.fullmatch(self.udid):
            raise CaptureError("udid is not a simulator UDID")


def prepare(session: CaptureSession) -> None:
    """Status bar and locale, once per run."""
    bar = session.spec.status_bar
    session.runner.run(
        [
            "xcrun", "simctl", "status_bar", session.udid, "override",
            "--time", str(bar["time"]),
            "--batteryState", "charged", "--batteryLevel", str(bar["battery"]),
            "--cellularMode", "active", "--cellularBars", str(bar["cellular_bars"]),
            "--dataNetwork", "wifi", "--wifiBars", str(bar["wifi_bars"]),
        ]
    )  # fmt: skip
    locale = session.spec.capture_locales[session.locale]
    for key, kind, value in (
        ("AppleLanguages", "-array", locale["apple_language"]),
        ("AppleLocale", "-string", locale["apple_locale"]),
    ):
        session.runner.run(
            ["xcrun", "simctl", "spawn", session.udid, "defaults", "write", "-g", key, kind, value]
        )
    state = ", ".join(f"{k} {v}" for k, v in session.spec.app_state.items())
    session.confirm(f"Set the app to: {state}. Press Enter when it is.")
    session.out_dir.mkdir(parents=True, exist_ok=True)


def _checklist(session: CaptureSession, frame: frame_plan.Frame) -> str:
    rules = "\n".join(f"  - {item}" for item in session.spec.must_not_show)
    return (
        f"[{frame.order:02d} {frame.frame_id}] {frame.state} ({frame.appearance})\n"
        + (
            f"Scroll: {frame.scroll}\nIf it cannot be held: drop the frame.\n"
            if frame.scroll
            else ""
        )
        + f"Never on screen:\n{rules}\nPress Enter to capture."
    )


def shoot(session: CaptureSession, frame: frame_plan.Frame) -> Shot:
    """Set the appearance, confirm the screen, capture, and check the size."""
    if frame.waits_for is not None:
        issue = frame.waits_for.split(" ", 1)[0]
        if issue not in session.resolved:
            raise CaptureError(
                f"{frame.frame_id} waits for {frame.waits_for}; capture it once {issue} "
                "is in the build (--resolved)"
            )
    session.runner.run(["xcrun", "simctl", "ui", session.udid, "appearance", frame.appearance])
    if session.visit is not None or "{visit}" not in frame.route:
        route = frame.route.replace("{visit}", session.visit or "")
        session.runner.run(["xcrun", "simctl", "openurl", session.udid, f"{SCHEME}://{route}"])
    session.confirm(_checklist(session, frame))
    path = session.out_dir / frame.capture_name
    session.runner.run(
        [
            "xcrun",
            "simctl",
            "io",
            session.udid,
            "screenshot",
            "--type=png",
            f"--mask={session.spec.capture_mask}",
            str(path),
        ]
    )
    facts = asc_assets.read_png_facts(path) if path.is_file() else None
    want = session.spec.capture_size
    if facts is None or (facts[0], facts[1]) != want:
        got = "nothing" if facts is None else f"{facts[0]}x{facts[1]}"
        path.unlink(missing_ok=True)
        raise CaptureError(
            f"{frame.capture_name}: got {got}, the {session.spec.capture_device} makes "
            f"{want[0]}x{want[1]}; wrong simulator?"
        )
    shot = Shot(
        name=path.name,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        appearance=frame.appearance,
        route=frame.route,
    )
    session.shots.append(shot)
    return shot


def write_provenance(session: CaptureSession, shots: Sequence[Shot], *, captured_on: str) -> Path:
    """``provenance.yaml`` beside the captures: hashes and the build, never a value."""
    record = {
        "issue": "INT-502",
        "captured_on": captured_on,
        "device": session.spec.capture_device,
        "runtime": session.spec.capture_runtime,
        "locale": session.locale,
        "app_sha": session.app_sha,
        "api": session.api_label,
        "data_class": session.data_class,
        "app_state": dict(session.spec.app_state),
        "resolved": sorted(session.resolved),
        "captures": [
            {"file": s.name, "sha256": s.sha256, "appearance": s.appearance, "route": s.route}
            for s in shots
        ],
    }
    path = session.out_dir / "provenance.yaml"
    path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _ask(message: str) -> None:
    input(message)


def _udid_for(runner: Runner, device: str, runtime: str) -> str:
    listing = json.loads(runner.run(["xcrun", "simctl", "list", "devices", "--json"]))
    wanted = "com.apple.CoreSimulator.SimRuntime." + runtime.replace(" ", "-").replace(".", "-")
    for row in listing.get("devices", {}).get(wanted, []):
        if row.get("name") == device and row.get("isAvailable", False):
            return str(row["udid"])
    raise CaptureError(f"no available {device} on {runtime}")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--locale", required=True, choices=frame_plan.LOCALES)
    parser.add_argument("--app-sha", required=True)
    parser.add_argument("--api-label", required=True)
    parser.add_argument("--data-class", default="synthetic")
    parser.add_argument("--visit")
    parser.add_argument("--udid")
    parser.add_argument("--frame", action="append", help="capture only these frame ids")
    parser.add_argument(
        "--resolved",
        action="append",
        default=[],
        help="an issue a frame waits for, now in the build",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(list(argv))
    spec = frame_plan.load_spec(frame_plan.FRAMES)
    runner = SubprocessRunner()
    try:
        udid = args.udid or _udid_for(runner, spec.capture_device, spec.capture_runtime)
        session = CaptureSession(
            spec=spec,
            udid=udid,
            locale=args.locale,
            out_dir=args.out
            or frame_plan.REPO / "docs" / "store" / "asc" / "captures" / args.locale,
            app_sha=args.app_sha,
            data_class=args.data_class,
            api_label=args.api_label,
            runner=runner,
            confirm=_ask,
            visit=args.visit,
            resolved=frozenset(args.resolved),
        )
        prepare(session)
        frames = [f for f in spec.frames if not args.frame or f.frame_id in args.frame]
        held = [
            f
            for f in frames
            if f.waits_for is not None and f.waits_for.split(" ", 1)[0] not in session.resolved
        ]
        for frame in held:
            print(f"HELD {frame.frame_id}: waits for {frame.waits_for}")
        shots = [shoot(session, frame) for frame in frames if frame not in held]
    except CaptureError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    path = write_provenance(session, shots, captured_on=date.today().isoformat())
    for shot in shots:
        print(f"OK {shot.name} {shot.sha256}")
    print(f"provenance {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
