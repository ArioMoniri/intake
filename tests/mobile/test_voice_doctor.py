"""INT-246 — `make voice-doctor`, the host-side answer to "is voice up?".

The incident: the SSH tunnel to the speech box died, the app's probe returned
null, the typed steps took over by design, and the only place that knew
anything was a log nobody was reading. The dev-side half of the fix is a
banner in the app; this is the other half — one command on the HOST that
probes every configured lane and prints a verdict per lane.

What is proven here:

* the lane table does not drift from the app. The ports are the app's own
  constants and the app's own ``app.json``; a change on either side that is
  not made on both fails a test rather than producing a doctor that probes
  the wrong port and cheerfully reports UP.
* the verdicts are real. Every probe below runs against a real local socket —
  a live server, a closed port, a slow handler, a 503 — because a mocked
  ``ConnectionRefusedError`` would prove only that the mock was written.
* the exit code is the contract. A required lane down exits non-zero, which
  is what makes this usable from a script.

INT-294 adds the second half of that first bullet. INT-249 had proved one
level down that ``GET /health`` is the wrong question — a VoxCPM2 pinned to
CPU answers it in milliseconds and cannot finish a turn — and the doctor had
not caught up, so on 2 Sep 2026 it printed ``voice: UP — every configured lane
answered`` while the app was muting itself (docs/evidence/INT-293.md). Every
TTS tier is now asked to SPEAK, with the app's own probe word, timed against
the app's own committed admission budget; ``asr`` and ``extract`` are not,
because neither has a healthy-but-unusable mode and POSTing a synthesis at an
ASR daemon probes something else.
"""

from __future__ import annotations

import dataclasses
import http.server
import importlib.util
import json
import re
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "dev" / "voice_doctor.py"
MOBILE = REPO / "apps" / "mobile"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("voice_doctor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their annotations through sys.modules, so the
    # module has to be registered before its body runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vd = _load()

APP_JSON = json.loads((MOBILE / "app.json").read_text(encoding="utf-8"))
EXTRA = APP_JSON["expo"]["extra"]


# ---------------------------------------------------------------------------
# Real sockets, not mocked failures
# ---------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200
    delay_s = 0.0

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        if self.delay_s:
            threading.Event().wait(self.delay_s)
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args: object) -> None:
        return


@contextmanager
def serving(status: int = 200, delay_s: float = 0.0) -> Iterator[int]:
    handler = type("H", (_Handler,), {"status": status, "delay_s": delay_s})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def closed_port() -> int:
    """A port that nothing is listening on — the dead-tunnel case."""
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# The lane table is the app's, not a second copy of it
# ---------------------------------------------------------------------------


def _ts_const(relative: str, name: str) -> int:
    source = (MOBILE / relative).read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", source)
    assert match is not None, f"{name} not found in {relative}"
    return int(match.group(1))


def test_asr_port_matches_the_app_constant() -> None:
    assert vd.ASR_PORT == _ts_const("src/lib/voice.ts", "ASR_PORT")


def test_extract_port_matches_the_app_constant() -> None:
    assert vd.EXTRACT_PORT == _ts_const("src/lib/extract.ts", "EXTRACT_PORT")


def test_default_tts_ladder_matches_the_app_default() -> None:
    source = (MOBILE / "src/lib/dialogue/ttsLane.ts").read_text(encoding="utf-8")
    block = source.split("DEFAULT_TTS_LANES", 1)[1].split("([", 1)[1].split("])", 1)[0]
    declared = [(m[0], int(m[1])) for m in re.findall(r'id: "(\w+)", port: (\d+)', block)]
    assert declared, "the ladder regex found nothing — the gate would be vacuous"
    assert declared == list(vd.DEFAULT_TTS_LANES)


def test_lanes_planned_from_the_real_app_json() -> None:
    lanes = vd.plan_lanes(EXTRA)
    assert [(lane.id, lane.port) for lane in lanes] == [
        ("asr", vd.ASR_PORT),
        ("extract", vd.EXTRACT_PORT),
        ("tts:voxcpm2", 8805),
        ("tts:freya", 8803),
    ]


def test_tts_ladder_follows_app_json_over_the_built_in_default() -> None:
    lanes = vd.plan_lanes({"asrHosts": ["127.0.0.1"], "ttsLanes": [{"id": "only", "port": 9001}]})
    assert [(lane.id, lane.port) for lane in lanes if lane.group == "tts"] == [("tts:only", 9001)]


def test_hosts_come_from_app_json_and_the_flag_wins_the_front() -> None:
    assert vd.plan_hosts(EXTRA) == EXTRA["asrHosts"]
    assert vd.plan_hosts(EXTRA, ["192.168.1.7"])[0] == "192.168.1.7"
    # a host named twice is probed once
    assert vd.plan_hosts(EXTRA, ["127.0.0.1"]).count("127.0.0.1") == 1


def test_a_host_list_that_is_empty_is_an_error_not_an_empty_report() -> None:
    with pytest.raises(vd.VoiceDoctorError):
        vd.plan_hosts({"asrHosts": []})


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def test_a_live_lane_reads_up() -> None:
    with serving() as port:
        verdict = vd.probe("127.0.0.1", port, timeout_s=2.0)
    assert verdict.ok is True
    assert verdict.detail == "ok"
    assert verdict.base == f"http://127.0.0.1:{port}"


def test_a_closed_port_reads_refused_not_merely_down() -> None:
    verdict = vd.probe("127.0.0.1", closed_port(), timeout_s=2.0)
    assert verdict.ok is False
    assert verdict.detail == "refused"


def test_a_slow_host_reads_timeout_which_is_the_dead_tunnel() -> None:
    with serving(delay_s=2.0) as port:
        verdict = vd.probe("127.0.0.1", port, timeout_s=0.05)
    assert verdict.ok is False
    assert verdict.detail == "timeout"


def test_a_served_but_unhealthy_lane_reads_its_status() -> None:
    with serving(status=503) as port:
        verdict = vd.probe("127.0.0.1", port, timeout_s=2.0)
    assert verdict.ok is False
    assert verdict.detail == "http 503"


def test_a_name_that_does_not_resolve_reads_dns() -> None:
    verdict = vd.probe("no-such-host.invalid", 8802, timeout_s=2.0)
    assert verdict.ok is False
    assert verdict.detail == "dns"


# ---------------------------------------------------------------------------
# One line per lane, and an exit code a script can trust
# ---------------------------------------------------------------------------


def _result(lane_id: str, group: str, ok: bool, detail: str = "refused") -> object:
    lane = vd.Lane(id=lane_id, port=1, group=group)
    verdict = vd.Verdict(base="http://127.0.0.1:1", ok=ok, detail=detail, elapsed_s=0.001)
    return vd.LaneResult(lane=lane, verdicts=(verdict,))


def test_the_line_names_the_lane_its_verdict_and_the_base() -> None:
    line = vd.lane_line(_result("asr", "asr", ok=False))
    assert line.startswith("asr")
    assert "DOWN" in line
    assert "http://127.0.0.1:1" in line
    assert "refused" in line
    assert "\n" not in line


def test_a_down_required_lane_exits_non_zero() -> None:
    results = [
        _result("asr", "asr", ok=False),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    assert vd.exit_code(results) == 1


def test_every_required_lane_up_exits_zero() -> None:
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    assert vd.exit_code(results) == 0


def test_one_live_tts_tier_is_enough_for_the_ladder() -> None:
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    assert vd.exit_code(results) == 0


def test_the_whole_ladder_down_exits_non_zero() -> None:
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False),
        _result("tts:freya", "tts", ok=False),
    ]
    assert vd.exit_code(results) == 1


def test_extract_down_alone_is_degraded_and_said_so_not_a_failure() -> None:
    # The dialogue still runs without the extract daemon — it loses slot
    # suggestions, not the conversation (useDialogueSession keeps the
    # verbatim transcript when the extract call fails). Exiting non-zero on
    # it would train people to ignore the exit code.
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=False),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    assert vd.exit_code(results) == 0
    assert "extract" in vd.summary_line(results)


def test_the_summary_never_says_every_lane_answered_when_one_did_not() -> None:
    # Caught on the first real run: a dead VoxCPM2 with a live Freya is a
    # healthy LADDER, and the summary happily called that "every configured
    # lane answered". A summary that overstates is the same failure mode this
    # whole issue is about, one level up.
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    summary = vd.summary_line(results)
    assert "every configured lane answered" not in summary
    assert "tts:voxcpm2" in summary
    assert summary.startswith("voice: UP")


def test_the_summary_says_down_when_a_required_lane_is_down() -> None:
    results = [_result("asr", "asr", ok=False), _result("tts:freya", "tts", ok=True, detail="ok")]
    assert "DOWN" in vd.summary_line(results)


# ---------------------------------------------------------------------------
# End to end, against real sockets
# ---------------------------------------------------------------------------


def test_check_probes_every_host_for_a_lane_so_the_picture_is_whole() -> None:
    dead = closed_port()
    with serving() as live:
        lanes = [vd.Lane(id="asr", port=live, group="asr")]
        results = vd.check(lanes, ["127.0.0.1", "127.0.0.2"], timeout_s=2.0)
    assert len(results[0].verdicts) == 2
    assert vd.lane_up(results[0]) is True
    assert dead != live


def test_the_makefile_exposes_the_target() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^voice-doctor:", makefile, re.MULTILINE)
    assert re.search(r"^\.PHONY:.*\bvoice-doctor\b", makefile, re.MULTILINE)


# ---------------------------------------------------------------------------
# INT-294 — a lane that is health-green and cannot speak is not UP
# ---------------------------------------------------------------------------

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "


class _Speaker(http.server.BaseHTTPRequestHandler):
    """Two endpoints, independently controllable — the defect in one class."""

    health_status = 200
    speak_status = 200
    speak_delay_s = 0.0
    speak_body = WAV
    seen: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        type(self).seen.append(f"GET {self.path}")
        self.send_response(self.health_status)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        type(self).seen.append(f"POST {self.path} {body.decode('utf-8')}")
        if self.speak_delay_s:
            threading.Event().wait(self.speak_delay_s)
        self.send_response(self.speak_status)
        self.end_headers()
        self.wfile.write(self.speak_body)

    def log_message(self, *_args: object) -> None:
        return


@contextmanager
def speaking(
    health_status: int = 200,
    speak_status: int = 200,
    speak_delay_s: float = 0.0,
    speak_body: bytes = WAV,
) -> Iterator[tuple[int, list[str]]]:
    seen: list[str] = []
    handler = type(
        "H",
        (_Speaker,),
        {
            "health_status": health_status,
            "speak_status": speak_status,
            "speak_delay_s": speak_delay_s,
            "speak_body": speak_body,
            "seen": seen,
        },
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1]), seen
    finally:
        server.shutdown()
        server.server_close()


def test_the_probe_word_is_the_apps_own() -> None:
    source = (MOBILE / "src/lib/dialogue/ttsLane.ts").read_text(encoding="utf-8")
    match = re.search(r'export const LANE_PROBE_TEXT = "([^"]+)";', source)
    assert match is not None, "LANE_PROBE_TEXT not found — the gate would be vacuous"
    assert vd.TTS_PROBE_TEXT == match.group(1)


def test_the_probe_word_carries_no_numeral() -> None:
    # Invariant 22: no numeral reaches any TTS model, including from a doctor.
    assert not any(ch.isdigit() for ch in vd.TTS_PROBE_TEXT)
    assert vd.TTS_PROBE_TEXT.strip()


def test_the_budget_is_the_apps_committed_admission_budget() -> None:
    source = (MOBILE / "src/lib/dialogue/tts.ts").read_text(encoding="utf-8")
    match = re.search(r"export const TURN_ROUND_TRIP_BUDGET_MS = (\d+);", source)
    assert match is not None, "TURN_ROUND_TRIP_BUDGET_MS not found in the app"
    assert vd.TTS_BUDGET_MS == int(match.group(1))


# ---------------------------------------------------------------------------
# A lane that is health-green and cannot speak is not UP
# ---------------------------------------------------------------------------


def test_a_healthy_lane_that_speaks_inside_the_budget_is_up() -> None:
    # The near-miss control for every assertion below it: the change must not
    # simply make TTS lanes fail.
    with speaking() as (port, _seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:freya", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    assert verdict.ok is True
    assert verdict.detail == "ok"


def test_a_healthy_lane_that_cannot_speak_in_time_reads_over_budget() -> None:
    with speaking(speak_delay_s=0.3) as (port, _seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:voxcpm2", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=50,
        )
    assert verdict.ok is False
    assert "over budget" in verdict.detail


def test_a_lane_that_answers_with_no_audio_reads_silent_not_up() -> None:
    with speaking(speak_body=b"") as (port, _seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:voxcpm2", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    assert verdict.ok is False
    assert verdict.detail == "silent"


def test_a_lane_that_refuses_the_synthesis_says_so() -> None:
    with speaking(speak_status=503) as (port, _seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:voxcpm2", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    assert verdict.ok is False
    assert "503" in verdict.detail


def test_a_lane_whose_health_is_down_is_never_asked_to_speak() -> None:
    with speaking(health_status=503) as (port, seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:voxcpm2", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    assert verdict.ok is False
    assert verdict.detail == "http 503"
    assert not [line for line in seen if line.startswith("POST")]


def test_the_probe_posts_the_apps_word_to_synthesize() -> None:
    with speaking() as (port, seen):
        vd.probe_lane(
            vd.Lane(id="tts:freya", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    posts = [line for line in seen if line.startswith("POST")]
    assert len(posts) == 1
    path, body = posts[0][len("POST ") :].split(" ", 1)
    assert path == "/synthesize"
    assert json.loads(body) == {"text": vd.TTS_PROBE_TEXT}


def test_asr_and_extract_are_not_asked_to_speak() -> None:
    # A doctor that POSTs /synthesize at the ASR daemon is probing something
    # the app never asks of it, and would report a lane down that is not.
    for group in ("asr", "extract"):
        with speaking() as (port, seen):
            verdict = vd.probe_lane(
                vd.Lane(id=group, port=port, group=group),
                "127.0.0.1",
                timeout_s=2.0,
                budget_ms=1000,
            )
        assert verdict.ok is True
        assert not [line for line in seen if line.startswith("POST")], group


def test_the_probe_keeps_a_duration_and_never_the_audio() -> None:
    # Invariant 3's posture for agent audio by construction: there is no path
    # from a doctor probe to a byte anyone can read back.
    with speaking() as (port, _seen):
        verdict = vd.probe_lane(
            vd.Lane(id="tts:freya", port=port, group="tts"),
            "127.0.0.1",
            timeout_s=2.0,
            budget_ms=1000,
        )
    fields = {f.name for f in dataclasses.fields(verdict)}
    assert fields == {"base", "ok", "detail", "elapsed_s"}


# ---------------------------------------------------------------------------
# The exit code reflects it
# ---------------------------------------------------------------------------


def test_a_ladder_that_is_green_but_mute_exits_non_zero() -> None:
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False, detail="over budget (3990 ms)"),
        _result("tts:freya", "tts", ok=False, detail="over budget (2800 ms)"),
    ]
    assert vd.exit_code(results) == 1
    assert "DOWN" in vd.summary_line(results)


def test_one_tier_that_can_actually_speak_is_still_a_healthy_ladder() -> None:
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("extract", "extract", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False, detail="over budget (3990 ms)"),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    assert vd.exit_code(results) == 0
    summary = vd.summary_line(results)
    assert summary.startswith("voice: UP")
    assert "every configured lane answered" not in summary
    assert "tts:voxcpm2" in summary


def test_the_over_budget_reason_reaches_the_printed_line() -> None:
    line = vd.lane_line(_result("tts:voxcpm2", "tts", ok=False, detail="over budget (3990 ms)"))
    assert "over budget" in line
    assert "DOWN" in line


def test_the_summary_names_what_a_lane_did_rather_than_renaming_it() -> None:
    # The first real run after this change printed "voice: UP — tts:voxcpm2
    # unreachable" about a tier that was reachable, health-green, and merely
    # too slow to speak. A summary that renames the verdict hides it.
    results = [
        _result("asr", "asr", ok=True, detail="ok"),
        _result("tts:voxcpm2", "tts", ok=False, detail="over budget (>1684 ms)"),
        _result("tts:freya", "tts", ok=True, detail="ok"),
    ]
    summary = vd.summary_line(results)
    assert "over budget" in summary
    assert "unreachable" not in summary
