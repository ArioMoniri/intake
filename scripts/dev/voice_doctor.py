"""INT-246 — `make voice-doctor`: is the dev voice lane up, from the host?

The incident this exists for: an SSH port forward to the speech box died. The
app's ASR probe returned null, ``DialogueGate`` fell through to the typed
steps exactly as designed, and nothing said so. Hours went into "the voice UI
is not implemented" while the voice UI was merged, running, and starved of a
transport.

The app-side half of the fix is a ``__DEV__`` banner. This is the other half,
and it answers the question from the side where the answer actually lives:
this machine's sockets. One line per lane, every configured host probed (not
just the first that answers — the point is the whole picture), and an exit
code a script can branch on.

Lanes, and what "expected" means for each:

* ``asr`` (8802) — REQUIRED. Down means the dialogue never starts; this is
  the lane whose silence cost the hours.
* ``tts:*`` (the app.json ladder, VoxCPM2 8805 then Freya 8803) — REQUIRED as
  a GROUP. One tier answering is a healthy ladder; that is the whole point of
  a ladder, and the app picks the first that answers.
* ``extract`` (8804) — DEGRADED, not required. The dialogue runs without it:
  ``useDialogueSession`` keeps the verbatim transcript when the extract call
  fails, an answer given in the pack's own option words is still recognised on
  the device (``lib/intake/answerMatch.ts``, INT-293), and anything neither can
  place is asked again rather than dropped. What is lost with this lane down is
  the reading of free narrative onto slots — not the answer. Exiting non-zero on a lane
  the product tolerates would teach people to ignore the exit code.

Ports and hosts are the app's own, read from ``apps/mobile/app.json`` and
pinned against the TypeScript constants by tests/mobile/test_voice_doctor.py.
A doctor that probes a port the app no longer uses is worse than no doctor.

Usage:
    make voice-doctor
    make voice-doctor HOST=192.168.1.7        # add the Metro LAN host
    uv run python scripts/dev/voice_doctor.py --timeout 3 --json
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
APP_JSON = REPO / "apps" / "mobile" / "app.json"

# Pinned to the app's constants by tests/mobile/test_voice_doctor.py.
ASR_PORT = 8802
EXTRACT_PORT = 8804
DEFAULT_TTS_LANES: tuple[tuple[str, int], ...] = (("voxcpm2", 8805), ("freya", 8803))

#: Groups the dev voice profile cannot run without.
REQUIRED_GROUPS: tuple[str, ...] = ("asr", "tts")
#: Groups whose absence degrades the run without stopping it.
DEGRADED_GROUPS: tuple[str, ...] = ("extract",)

HEALTH_PATH = "/health"


class VoiceDoctorError(RuntimeError):
    """The configuration cannot be probed — say so instead of reporting green."""


@dataclass(frozen=True)
class Lane:
    """One service the dev voice profile talks to, on one port."""

    id: str
    port: int
    group: str


@dataclass(frozen=True)
class Verdict:
    """What one (lane, host) pair answered."""

    base: str
    ok: bool
    #: "ok" | "refused" | "timeout" | "dns" | "http <code>" | "unreachable (<err>)"
    detail: str
    elapsed_s: float


@dataclass(frozen=True)
class LaneResult:
    lane: Lane
    verdicts: tuple[Verdict, ...]


def read_extra(config_path: Path = APP_JSON) -> dict[str, Any]:
    """The `expo.extra` block the app itself reads at runtime."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - a broken checkout
        raise VoiceDoctorError(f"no app config at {config_path}") from exc
    extra = config.get("expo", {}).get("extra")
    if not isinstance(extra, dict):
        raise VoiceDoctorError(f"{config_path} has no expo.extra block")
    return extra


def plan_hosts(extra: Mapping[str, Any], extra_hosts: Sequence[str] = ()) -> list[str]:
    """`--host` first (it is the one the caller just named), then app.json.

    Mirrors the app's own walk in src/lib/dev/hosts.ts, minus the Metro
    hostUri, which only exists inside a running Metro. `--host` is how you
    hand that one in.
    """
    hosts: list[str] = []
    for host in [*extra_hosts, *(extra.get("asrHosts") or [])]:
        if host and host not in hosts:
            hosts.append(host)
    if not hosts:
        raise VoiceDoctorError(
            "no hosts to probe: set expo.extra.asrHosts in apps/mobile/app.json "
            "or pass --host <addr>"
        )
    return hosts


def plan_lanes(extra: Mapping[str, Any]) -> list[Lane]:
    """Every lane the dev voice profile uses, in the order it needs them."""
    lanes = [
        Lane(id="asr", port=ASR_PORT, group="asr"),
        Lane(id="extract", port=EXTRACT_PORT, group="extract"),
    ]
    configured = extra.get("ttsLanes")
    ladder: Iterable[tuple[str, int]]
    if isinstance(configured, list) and configured:
        ladder = [(str(entry["id"]), int(entry["port"])) for entry in configured]
    else:
        ladder = DEFAULT_TTS_LANES
    lanes.extend(Lane(id=f"tts:{name}", port=port, group="tts") for name, port in ladder)
    return lanes


def probe(host: str, port: int, timeout_s: float) -> Verdict:
    """GET /health on one host:port, classified by what the socket actually did."""
    base = f"http://{host}:{port}"
    started = time.monotonic()
    conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        conn.request("GET", HEALTH_PATH)
        status = conn.getresponse().status
        elapsed = time.monotonic() - started
        if 200 <= status < 300:
            return Verdict(base=base, ok=True, detail="ok", elapsed_s=elapsed)
        return Verdict(base=base, ok=False, detail=f"http {status}", elapsed_s=elapsed)
    except socket.gaierror:
        return Verdict(base, False, "dns", time.monotonic() - started)
    except TimeoutError:  # socket.timeout is this, since 3.10
        return Verdict(base, False, "timeout", time.monotonic() - started)
    except ConnectionRefusedError:
        return Verdict(base, False, "refused", time.monotonic() - started)
    except OSError as exc:
        name = type(exc).__name__
        return Verdict(base, False, f"unreachable ({name})", time.monotonic() - started)
    finally:
        conn.close()


def check(lanes: Sequence[Lane], hosts: Sequence[str], timeout_s: float) -> list[LaneResult]:
    """Probe every host for every lane — the whole picture, not the first hit."""
    return [
        LaneResult(lane=lane, verdicts=tuple(probe(host, lane.port, timeout_s) for host in hosts))
        for lane in lanes
    ]


def lane_up(result: LaneResult) -> bool:
    return any(verdict.ok for verdict in result.verdicts)


def lane_line(result: LaneResult) -> str:
    """One line, one lane: id, verdict, and where that verdict came from."""
    up = lane_up(result)
    if up:
        answered = next(v for v in result.verdicts if v.ok)
        where = f"{answered.base} ({answered.elapsed_s * 1000:.0f} ms)"
    else:
        where = " · ".join(f"{v.base} {v.detail}" for v in result.verdicts)
    note = "" if result.lane.group not in DEGRADED_GROUPS or up else "  [degraded, not fatal]"
    return f"{result.lane.id:<14}{'UP  ' if up else 'DOWN'}  {where}{note}"


def _down_groups(results: Sequence[LaneResult], groups: Sequence[str]) -> list[str]:
    down: list[str] = []
    for group in groups:
        in_group = [r for r in results if r.lane.group == group]
        if in_group and not any(lane_up(r) for r in in_group):
            down.append(group)
    return down


def summary_line(results: Sequence[LaneResult]) -> str:
    """One sentence, and it never overstates.

    A dead VoxCPM2 behind a live Freya is a healthy ladder, so the verdict is
    UP — but the summary still NAMES the tier that did not answer. Saying
    "every configured lane answered" when one did not is the same failure
    this whole issue is about, one level up.
    """
    required_down = _down_groups(results, REQUIRED_GROUPS)
    if required_down:
        return (
            f"voice: DOWN — {', '.join(required_down)} unreachable; "
            "the app falls through to the typed steps"
        )
    down = [r.lane.id for r in results if not lane_up(r)]
    if not down:
        return "voice: UP — every configured lane answered"
    note = " (no answer suggestions)" if _down_groups(results, DEGRADED_GROUPS) else ""
    return f"voice: UP — {', '.join(down)} unreachable{note}"


def exit_code(results: Sequence[LaneResult]) -> int:
    return 1 if _down_groups(results, REQUIRED_GROUPS) else 0


def _as_json(hosts: Sequence[str], results: Sequence[LaneResult]) -> str:
    return json.dumps(
        {
            "hosts": list(hosts),
            "lanes": [
                {
                    "id": r.lane.id,
                    "group": r.lane.group,
                    "port": r.lane.port,
                    "up": lane_up(r),
                    "probes": [
                        {"base": v.base, "ok": v.ok, "detail": v.detail} for v in r.verdicts
                    ],
                }
                for r in results
            ],
            "summary": summary_line(results),
        },
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe every configured dev voice lane.")
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="ADDR",
        help="extra host to probe first (the Metro LAN address, typically)",
    )
    parser.add_argument("--timeout", type=float, default=1.5, help="per-probe timeout in seconds")
    parser.add_argument("--config", type=Path, default=APP_JSON, help="path to app.json")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        extra = read_extra(args.config)
        hosts = plan_hosts(extra, args.host)
        lanes = plan_lanes(extra)
    except VoiceDoctorError as exc:
        print(f"voice-doctor: {exc}", file=sys.stderr)
        return 2

    results = check(lanes, hosts, args.timeout)

    if args.json:
        print(_as_json(hosts, results))
        return exit_code(results)

    print(f"voice-doctor · {args.config} · hosts: {', '.join(hosts)}")
    for result in results:
        print(lane_line(result))
    print(summary_line(results))
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
