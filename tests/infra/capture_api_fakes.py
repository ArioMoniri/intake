"""INT-502 test doubles for infra/staging/capture_api_host.sh: docker, ss, openssl, curl, sleep.

Each tool is a two-line shell wrapper on ``PATH`` that execs this file with the tool's name, so
nothing reaches a real Docker, Postgres or Redis. State lives in ``$FAKE_STATE``:

- ``calls.jsonl``: one ``{"tool", "argv", "stdin", "envfile"}`` line per call. ``envfile`` is
  the content of a ``--env-file`` at the moment of the call, so a test can read what the
  container received, show that no argv carried a secret, and show that the file was gone after.
- ``world.json``: ``image`` (the public API's image, or null when it is not running),
  ``image_env`` (the lines that image bakes), ``container`` (the capture container's label, or
  null), ``network`` (whether the capture network exists), ``port_busy``, ``healthy``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

STATE = Path(os.environ["FAKE_STATE"])


def _world() -> dict[str, Any]:
    return json.loads((STATE / "world.json").read_text(encoding="utf-8"))


def _save(world: dict[str, Any]) -> None:
    (STATE / "world.json").write_text(json.dumps(world), encoding="utf-8")


def _log(tool: str, argv: list[str], stdin: str = "") -> None:
    envfile = ""
    if "--env-file" in argv:
        path = Path(argv[argv.index("--env-file") + 1])
        envfile = path.read_text(encoding="utf-8") if path.is_file() else "<missing>"
    with (STATE / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"tool": tool, "argv": argv, "stdin": stdin, "envfile": envfile}) + "\n"
        )


def _exit(code: int, out: str = "") -> NoReturn:
    if out:
        sys.stdout.write(out)
    sys.exit(code)


def _docker(argv: list[str]) -> NoReturn:
    world = _world()
    stdin = sys.stdin.read() if argv[:2] in (["exec", "-i"],) else ""
    _log("docker", argv, stdin)
    verb = argv[0]
    if verb == "inspect":
        target = argv[-1]
        if target == "intake-capture-api":
            if world["container"] is None:
                _exit(1)
            _exit(0, f"{world['container']}\n")
        if target == "intake-staging-api-1":
            if world["image"] is None:
                _exit(1)
            _exit(0, f"{world['image']}\n")
        _exit(1)
    if verb == "image":
        _exit(0, "".join(f"{line}\n" for line in world["image_env"]))
    if verb == "network":
        action = argv[1]
        if action == "inspect":
            _exit(0 if world["network"] else 1)
        if action == "create":
            world["network"] = True
        elif action == "rm":
            world["network"] = False
        _save(world)
        _exit(0)
    if verb == "create":
        world["container"] = argv[argv.index("--label") + 1].split("=", 1)[1]
        _save(world)
        _exit(0, "c0ffee\n")
    if verb == "rm":
        world["container"] = None
        _save(world)
        _exit(0)
    _exit(0)


def main() -> NoReturn:
    tool, argv = sys.argv[1], sys.argv[2:]
    if tool == "docker":
        _docker(argv)
    _log(tool, argv)
    world = _world()
    if tool == "ss":
        _exit(0, "LISTEN 0 4096 127.0.0.1:18502 0.0.0.0:*\n" if world["port_busy"] else "")
    if tool == "openssl":
        _exit(0, "ab" * 32 + "\n")
    if tool == "curl":
        _exit(0 if world["healthy"] else 7)
    _exit(0)


if __name__ == "__main__":
    main()
