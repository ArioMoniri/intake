"""INT-515: smoke.sh's view of the voice runtime, from inside its own container.

The runtime publishes no port and no edge routes to it, so smoke.sh asks from
within: ``compose exec -T voice-runtime python infra/staging/voice_probe.py
<healthz|readyz|turn>``. Each prints one line and exits 0 only on success:

- ``healthz`` — the process is alive;
- ``readyz`` — every readiness check passes; otherwise the line names the
  checks that do not (names and states only, invariant 6);
- ``turn`` — one scripted synthetic turn completed on the runtime's lanes
  (``POST /probe/synthetic-turn``); otherwise the stage it stopped at and its
  closed code. Exit 2 when the runtime's rate limit answered instead.

Standard library only.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

BASE = "http://127.0.0.1:8100"

Opener = Callable[[urllib.request.Request, float], Any]


def _default_open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 — loopback only


def fetch(path: str, method: str, opener: Opener = _default_open) -> tuple[int, Any]:
    # BASE is a fixed http loopback URL: no caller-chosen scheme reaches here
    request = urllib.request.Request(  # noqa: S310
        f"{BASE}{path}", method=method, data=b"" if method == "POST" else None
    )
    try:
        with opener(request, 60.0) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    try:
        return status, json.loads(raw.decode("utf-8") or "null")
    except ValueError:
        return status, None


def readyz_line(status: int, body: Any) -> str:
    checks = body.get("checks") if isinstance(body, dict) else None
    if not isinstance(checks, dict):
        return f"answered {status} without checks"
    failing = sorted(name for name, state in checks.items() if state != "ok")
    if status == 200 and not failing:
        return f"ready ({len(checks)} checks)"
    return "not ready: " + ", ".join(failing)


def turn_line(status: int, body: Any) -> tuple[int, str]:
    if status == 429:
        return 2, "rate limited: a turn ran within the last 30 s"
    stages = body.get("stages") if isinstance(body, dict) else None
    if not isinstance(stages, list):
        return 1, f"answered {status} without a report"
    if status == 200 and body.get("completed") is True:
        total = sum(float(stage.get("latency_ms", 0.0)) for stage in stages)
        return 0, f"turn completed in {total:.0f} ms over {len(stages)} stages"
    stopped = next((s for s in stages if isinstance(s, dict) and not s.get("ok")), {})
    return 1, f"turn stopped at {stopped.get('stage', 'unknown')}: {stopped.get('code', 'unknown')}"


def main(argv: list[str] | None = None, opener: Opener = _default_open) -> int:
    which = (argv if argv is not None else sys.argv[1:])[:1]
    if which == ["healthz"]:
        status, _ = fetch("/healthz", "GET", opener)
        print("alive" if status == 200 else f"healthz answered {status}")
        return 0 if status == 200 else 1
    if which == ["readyz"]:
        status, body = fetch("/readyz", "GET", opener)
        line = readyz_line(status, body)
        print(line)
        return 0 if line.startswith("ready") else 1
    if which == ["turn"]:
        code, line = turn_line(*fetch("/probe/synthetic-turn", "POST", opener))
        print(line)
        return code
    print("usage: voice_probe.py healthz|readyz|turn")
    return 64


if __name__ == "__main__":
    sys.exit(main())
