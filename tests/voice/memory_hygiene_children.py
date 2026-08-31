"""INT-278 — the child programs the memory-hygiene proofs need.

Neither property can be a function in the test module: both are about what a
**separate operating-system process** does. The core-dump child has to die of
``SIGABRT`` so the kernel decides whether to write a core; the ptrace pair has
to be two processes so one can try to attach to the other.

Everything these programs hold is the synthetic marker in
:data:`SYNTHETIC_MARKER` — a repeated ASCII string authored here. **No real
audio is written, held or produced anywhere in this file** (CLAUDE.md
invariant 3), and nothing here creates the artefact the test then looks for:
where a core file appears, the kernel wrote it.

**Why the fill is done in 38-byte steps.** A core dump contains the process's
whole heap, so a one-shot ``SYNTHETIC_MARKER * n`` would leave two
multi-megabyte copies of the marker in ordinary, unlocked memory — the
intermediate and the slice — and a search of the core would find them whatever
the locked region did. Filling in place from the small module constant keeps
the only bulk copy inside the buffer under test, which is what makes counting
occurrences in the core mean something.

Run as::

    python tests/voice/memory_hygiene_children.py crash <mode>
    python tests/voice/memory_hygiene_children.py tracer <mode>
    python tests/voice/memory_hygiene_children.py report hardened

``crash`` never returns; the other two print one JSON object on stdout.
``report`` exists because ``harden_process`` lowers ``RLIMIT_CORE``'s **hard**
limit, which no process can raise again: running it inside pytest would leave
every later crash control unable to produce a core and would turn this suite's
strongest assertions into vacuous ones.
"""

from __future__ import annotations

import ctypes
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from voice_clips.locked_buffer import LockedBuffer
from voice_clips.process_hardening import harden_process

__all__ = [
    "CAPACITY_BYTES",
    "CRASH_MODES",
    "SYNTHETIC_MARKER",
    "TRACEE_MODES",
    "main",
]

#: Obviously not audio, obviously authored, and long enough that a byte-wise
#: search over a multi-megabyte core file cannot hit it by chance.
SYNTHETIC_MARKER = b"INT278-SYNTHETIC-MARKER-NEVER-A-VOICE-"

#: Small enough to lock under any plausible ``RLIMIT_MEMLOCK``, large enough
#: to span many pages, so a partial lock is visible and so a full copy in a
#: core file is thousands of occurrences rather than a handful.
CAPACITY_BYTES = 256 * 1024

#: How many whole markers a filled region holds — the number a core dump of an
#: unprotected buffer contains, and the number the locked one must not.
MARKERS_PER_REGION = CAPACITY_BYTES // len(SYNTHETIC_MARKER)

#: The modes ``crash`` understands. ``hardened`` is the property; the other two
#: are its controls, and ``unprotected`` proves the marker search works at all.
CRASH_MODES = ("hardened", "limit_raised", "unprotected")

#: The modes ``tracee`` understands: with and without the process hardening.
TRACEE_MODES = ("hardened", "unprotected")

_PTRACE_ATTACH = 16
_PTRACE_DETACH = 17
_CAP_VERSION_3 = 0x20080522
_TRACEE_LIFETIME_S = 20


def _libc() -> ctypes.CDLL:
    return ctypes.CDLL("libc.so.6", use_errno=True)


def _fill_locked(buffer: LockedBuffer) -> None:
    while buffer.length + len(SYNTHETIC_MARKER) <= buffer.capacity:
        buffer.write(SYNTHETIC_MARKER)


def _fill_ordinary() -> bytearray:
    """The same content in a plain mutable buffer: invariant 3 unimplemented."""
    holder = bytearray(CAPACITY_BYTES)
    step = len(SYNTHETIC_MARKER)
    for offset in range(0, CAPACITY_BYTES - step, step):
        holder[offset : offset + step] = SYNTHETIC_MARKER
    return holder


def _raise_core_limit() -> None:
    _, hard = resource.getrlimit(resource.RLIMIT_CORE)
    resource.setrlimit(resource.RLIMIT_CORE, (hard, hard))


def _crash(mode: str) -> None:
    """Fill a buffer with the marker and abort. Never returns."""
    if mode == "hardened":
        harden_process()
        _fill_locked(LockedBuffer(CAPACITY_BYTES))
    elif mode == "limit_raised":
        _raise_core_limit()
        _fill_locked(LockedBuffer(CAPACITY_BYTES))
    elif mode == "unprotected":
        _raise_core_limit()
        globals()["_ORDINARY"] = _fill_ordinary()  # bound so it stays resident
    else:
        raise SystemExit(f"unknown crash mode {mode!r}")
    sys.stdout.flush()
    os.abort()


# --- the ptrace pair ------------------------------------------------------------------


class _CapHeader(ctypes.Structure):
    _fields_ = (("version", ctypes.c_uint32), ("pid", ctypes.c_int))


class _CapData(ctypes.Structure):
    _fields_ = (
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    )


def _drop_capabilities(*, permitted_too: bool) -> None:
    """Become an ordinary process inside the container.

    files/10 §9.1 invariant 28 requires the workload to run without
    ``CAP_SYS_PTRACE``, so both halves of this pair model that: the tracee
    drops every capability it inherited through ``exec`` (``permitted_too``),
    and the tracer drops its effective set. A tracer that kept the capability
    would sail past every control and prove only that root is root.

    Both sets matter because the kernel compares different ones on different
    paths: ``PTRACE_ATTACH`` checks the tracer's *permitted* set against the
    target's, while ``/proc/<pid>/mem`` checks the *effective* set. A workload
    that kept capabilities the peer had dropped would be unreadable for that
    reason rather than because it was hardened, which would make the control
    below silently meaningless.
    """
    libc = _libc()
    header = _CapHeader(_CAP_VERSION_3, 0)
    data = (_CapData * 2)()
    if libc.capget(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), "capget failed")
    for slot in data:
        slot.effective = 0
        if permitted_too:
            slot.permitted = 0
            slot.inheritable = 0
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), "capset failed")


def _tracee(mode: str) -> None:
    """Hold the marker in a locked buffer and announce where it is."""
    _drop_capabilities(permitted_too=True)
    if mode == "hardened":
        harden_process()
    buffer = LockedBuffer(CAPACITY_BYTES)
    _fill_locked(buffer)
    print(
        json.dumps({"pid": os.getpid(), "address": buffer.address, "length": buffer.length}),
        flush=True,
    )
    time.sleep(_TRACEE_LIFETIME_S)
    buffer.close()


def _attach(pid: int) -> int:
    """``PTRACE_ATTACH``; returns 0, or the errno the kernel refused with."""
    libc = _libc()
    libc.ptrace.restype = ctypes.c_long
    libc.ptrace.argtypes = (ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.set_errno(0)
    result = libc.ptrace(ctypes.c_long(_PTRACE_ATTACH), ctypes.c_long(pid), None, None)
    if result == 0:
        os.waitpid(pid, 0)
        libc.ptrace(ctypes.c_long(_PTRACE_DETACH), ctypes.c_long(pid), None, None)
        return 0
    return ctypes.get_errno()


def _read_process_memory(pid: int, address: int, length: int) -> tuple[int, bool]:
    """Try to read the buffer straight out of ``/proc/<pid>/mem``.

    files/10 §3: *"without ``ptrace_scope``, ``/proc/pid/mem`` reads the buffer
    regardless of every control above"*. Returns ``(errno, marker_found)``;
    errno 0 means the read succeeded.
    """
    try:
        with open(f"/proc/{pid}/mem", "rb", buffering=0) as handle:
            handle.seek(address)
            return 0, SYNTHETIC_MARKER in handle.read(length)
    except OSError as error:
        return error.errno or -1, False


def _tracer(mode: str) -> None:
    """Drop capabilities, start a tracee, and report what it could reach."""
    _drop_capabilities(permitted_too=False)
    child = subprocess.Popen(  # noqa: S603 - fixed argv, our own file
        [sys.executable, str(Path(__file__).resolve()), "tracee", mode],
        stdout=subprocess.PIPE,
        text=True,
    )
    report: dict[str, Any] = {"mode": mode}
    try:
        if child.stdout is None:  # pragma: no cover - a pipe was requested
            raise SystemExit("the tracee produced no pipe")
        announced = json.loads(child.stdout.readline())
        report["attach_errno"] = _attach(announced["pid"])
        mem_errno, found = _read_process_memory(
            announced["pid"], announced["address"], announced["length"]
        )
        report["mem_errno"] = mem_errno
        report["marker_found"] = found
    finally:
        child.terminate()
        child.wait(timeout=10)
    print(json.dumps(report), flush=True)


def _report() -> None:
    """Harden this process and print what the kernel ended up holding."""
    report = harden_process()
    print(
        json.dumps(
            {
                "core_limit": list(report.core_limit),
                "dumpable": report.dumpable,
                "core_pattern": report.core_pattern,
                "yama_ptrace_scope": report.yama_ptrace_scope,
                "rendered": repr(report),
            }
        ),
        flush=True,
    )


def main(argv: list[str]) -> int:
    role, mode = argv[1], argv[2]
    if role == "crash":
        _crash(mode)
    elif role == "tracee":
        _tracee(mode)
    elif role == "tracer":
        _tracer(mode)
    elif role == "report":
        _report()
    else:
        raise SystemExit(f"unknown role {role!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
