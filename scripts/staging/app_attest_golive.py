"""INT-528 — App Attest go-live, laptop side.

Owner decision, 16 Oct 2026 ("keychain"): the Apple team id is read at deploy
time from the subject OU of the owner's Apple Development certificate in the
login keychain. It never enters git, a log, a chat, a command line or SSM
parameters (those are kept in the command history).

What this does, in order:

1. Reads the Apple Development certificates from the login keychain with
   ``security find-certificate`` (certificates are public; no private key is
   read and no keychain password is asked for).
2. Keeps the ones valid now, takes their subject OU, and refuses unless that
   is exactly one 10-character team id of the shape
   ``intake_api.app_attest`` enforces. A refusal names no value.
3. Opens an interactive SSM session on the synthetic host that runs
   ``infra/staging/app_attest_env.sh`` and types the team id at its prompt on
   a pseudo-terminal, echo off, with any echo masked in what is relayed. The
   host script refuses unless Netgsm is already live in OpenBao, so App Attest
   goes live together with SMS.

Then run ``./deploy.sh`` on the host (docs/runbooks/staging.md, "App Attest
and SMS").

Usage:
    uv run python scripts/staging/app_attest_golive.py --check   # read and validate only
    uv run python scripts/staging/app_attest_golive.py           # and set it on the host
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Final

from cryptography import x509
from cryptography.x509.oid import NameOID

#: intake_api.app_attest._TEAM_ID (a test holds the two equal)
TEAM_ID_PATTERN: Final = re.compile(r"^[A-Z0-9]{10}$")
CERT_NAME: Final = "Apple Development:"
LOGIN_KEYCHAIN: Final = Path.home() / "Library" / "Keychains" / "login.keychain-db"
#: The synthetic staging host and where its tree lives (docs/runbooks/staging.md)
INSTANCE: Final = "i-0e489e48739f5de98"
REGION: Final = "us-east-1"
HOST_SCRIPT: Final = "/opt/intake/infra/staging/app_attest_env.sh"
#: What app_attest_env.sh shows before each read (its PROMPT_* plus ": ")
PROMPT_TEAM_ID: Final = "INTAKE_APP_ATTEST_TEAM_ID: "
PROMPT_BUNDLE_ID: Final = "INTAKE_APP_ATTEST_BUNDLE_ID (empty: the app's committed bundle id): "
PROMPT_ENVIRONMENT: Final = "INTAKE_APP_ATTEST_ENVIRONMENT (empty: production): "


class TeamIdError(Exception):
    """No single valid team id could be read. The message names no value."""


def certificates_pem(keychain: Path) -> bytes:
    """Every certificate whose name contains ``Apple Development:``, as PEM."""
    completed = subprocess.run(  # noqa: S603 — fixed argv, the macOS keychain tool
        ["security", "find-certificate", "-a", "-c", CERT_NAME, "-p", str(keychain)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    return completed.stdout


def _values(name: x509.Name, oid: x509.ObjectIdentifier) -> list[str]:
    return [str(attribute.value) for attribute in name.get_attributes_for_oid(oid)]


def team_id_from_pem_bundle(pem: bytes, *, now: datetime) -> str:
    """The one team id among the Apple Development certificates valid at ``now``."""
    certificates = x509.load_pem_x509_certificates(pem) if pem.strip() else []
    teams: set[str] = set()
    for certificate in certificates:
        names = _values(certificate.subject, NameOID.COMMON_NAME)
        if not any(name.startswith(CERT_NAME) for name in names):
            continue
        if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
            continue
        teams.update(_values(certificate.subject, NameOID.ORGANIZATIONAL_UNIT_NAME))
    if not teams:
        raise TeamIdError(
            "no Apple Development certificate valid today with a subject OU is in the keychain"
        )
    if len(teams) > 1:
        raise TeamIdError(
            f"{len(teams)} different team ids among the Apple Development certificates valid "
            "today; delete the ones for other teams from the keychain, or pass --keychain"
        )
    team = teams.pop()
    if not TEAM_ID_PATTERN.fullmatch(team):
        raise TeamIdError(
            "the certificate's subject OU is not a team id (ten upper-case letters or digits)"
        )
    return team


def ssm_command(target: str, region: str) -> list[str]:
    """An interactive session running the host script. It carries no value."""
    return [
        "aws",
        "ssm",
        "start-session",
        "--region",
        region,
        "--target",
        target,
        "--document-name",
        "AWS-StartInteractiveCommand",
        "--parameters",
        json.dumps({"command": [f"sudo {HOST_SCRIPT}"]}),
    ]


def answers(team: str, bundle_id: str) -> list[tuple[str, str]]:
    """(prompt, what to type) in the order the host script asks."""
    return [(PROMPT_TEAM_ID, team), (PROMPT_BUNDLE_ID, bundle_id), (PROMPT_ENVIRONMENT, "")]


class Masker:
    """Relays output with every occurrence of ``secret`` starred out, holding
    back just enough bytes to catch one split across two reads."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self._held = b""

    def feed(self, chunk: bytes) -> bytes:
        data = (self._held + chunk).replace(self._secret, b"*" * len(self._secret))
        keep = len(self._secret) - 1
        if len(data) <= keep:
            self._held = data
            return b""
        self._held = data[len(data) - keep :] if keep else b""
        return data[: len(data) - keep] if keep else data

    def flush(self) -> bytes:
        held, self._held = self._held, b""
        return held


def _child(argv: Sequence[str], env: Mapping[str, str] | None) -> None:
    """In the forked child: echo off on the pseudo-terminal, then exec."""
    attributes = termios.tcgetattr(0)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(0, termios.TCSANOW, attributes)
    os.execvpe(argv[0], list(argv), dict(env) if env is not None else dict(os.environ))  # noqa: S606


def drive(
    argv: Sequence[str],
    replies: Sequence[tuple[str, str]],
    *,
    secret: str,
    out: BinaryIO,
    env: Mapping[str, str] | None = None,
    timeout: float = 120.0,
) -> int:
    """Run ``argv`` on a pseudo-terminal, type each reply after its prompt and
    relay what the session shows, masked. Returns the session's exit code."""
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover — the child process execs
        _child(argv, env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    masker = Masker(secret.encode())
    pending = list(replies)
    since_reply = b""
    deadline = time.monotonic() + timeout
    try:
        while True:
            if time.monotonic() > deadline:
                os.kill(pid, signal.SIGTERM)
                raise TimeoutError(
                    "the session did not show the next prompt in time; nothing more was typed"
                )
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:  # the session closed its end
                break
            if not chunk:
                break
            out.write(masker.feed(chunk))
            out.flush()
            since_reply += chunk
            if pending and pending[0][0].encode() in since_reply:
                os.write(fd, pending.pop(0)[1].encode() + b"\r")
                since_reply = b""
                deadline = time.monotonic() + timeout
        out.write(masker.flush())
        out.flush()
    finally:
        os.close(fd)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="App Attest go-live (INT-528)")
    parser.add_argument("--check", action="store_true", help="read and validate only")
    parser.add_argument("--keychain", type=Path, default=LOGIN_KEYCHAIN)
    parser.add_argument("--target", default=INSTANCE)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--bundle-id", default="", help="empty: the app's committed bundle id")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    try:
        team = team_id_from_pem_bundle(certificates_pem(args.keychain), now=datetime.now(UTC))
    except (TeamIdError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"app_attest_golive: {exc}", file=sys.stderr)
        return 1
    print("Apple Development certificate: team id found, of the shape the API accepts (not shown)")
    if args.check:
        return 0
    try:
        return drive(
            ssm_command(args.target, args.region),
            answers(team, args.bundle_id),
            secret=team,
            out=sys.stdout.buffer,
            timeout=args.timeout,
        )
    except TimeoutError as exc:
        print(f"app_attest_golive: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
