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
"""

from __future__ import annotations

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
