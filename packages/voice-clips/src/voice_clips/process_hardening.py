"""Process-level controls for a worker that holds decoded frames in memory.

CLAUDE.md invariant 3 says raw audio is *"never reachable through a core dump,
a swap page or a crash report"*. Two of those three are decided by the process,
not by the buffer, and files/10 §3 names both controls:

- **Core dumps** — *"``RLIMIT_CORE=(0,0)`` set at worker start, container
  ``ulimit -c 0``, and the node's ``kernel.core_pattern`` verified"*
  (files/10 §9.1 invariant 16, ``audio_no_core_guard``).
- **Process hardening** — *"non-root, ``no-new-privileges``,
  ``CAP_SYS_PTRACE`` dropped, ``kernel.yama.ptrace_scope=1``. Without the last
  one, ``/proc/pid/mem`` reads the buffer regardless of every control above"*
  (invariant 28, ``process_hardening_guard``).

``prctl(PR_SET_DUMPABLE, 0)`` is what this module can do about the second from
inside the process: a non-dumpable process is one the kernel will not let a
peer attach to or read ``/proc/<pid>/mem`` from without ``CAP_SYS_PTRACE``,
and it stops the kernel writing a core for it at all. The container and node
halves — the dropped capability, the seccomp/no-new-privileges posture and the
Yama sysctl — are deployment settings this module can only *report*, which is
what :func:`yama_ptrace_scope` and :func:`core_dump_environment` are for: a
control nobody reads back is a control nobody notices losing.

Every function here fails closed. Setting a limit is not the same as having
one, so each setter reads its value back and raises if the kernel disagreed.

**Placement.** These are worker controls, not clip-cache ones; the module sits
in this package because INT-278's change owns no other, imports nothing from
:mod:`voice_clips`, and moves without edits. See ADR-025.
"""

from __future__ import annotations

import ctypes
import resource
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "CORE_PATTERN_PATH",
    "PR_GET_DUMPABLE",
    "PR_SET_DUMPABLE",
    "YAMA_PTRACE_SCOPE_PATH",
    "CoreDumpEnvironment",
    "HardeningReport",
    "ProcessHardeningError",
    "core_dump_environment",
    "deny_ptrace_attach",
    "disable_core_dumps",
    "harden_process",
    "yama_ptrace_scope",
]

#: ``linux/prctl.h``. Named rather than inlined so a reader can check them.
PR_SET_DUMPABLE: Final = 4
PR_GET_DUMPABLE: Final = 3

CORE_PATTERN_PATH: Final = Path("/proc/sys/kernel/core_pattern")
YAMA_PTRACE_SCOPE_PATH: Final = Path("/proc/sys/kernel/yama/ptrace_scope")


class ProcessHardeningError(Exception):
    """A control was asked for and the kernel did not grant it."""


@dataclass(frozen=True, slots=True)
class HardeningReport:
    """What the process looks like after :func:`harden_process`.

    Sizes and settings only — nothing here can carry content, so the report is
    safe to log (CLAUDE.md invariant 6).
    """

    core_limit: tuple[int, int]
    dumpable: int
    core_pattern: str
    yama_ptrace_scope: int | None


@dataclass(frozen=True, slots=True)
class CoreDumpEnvironment:
    """Whether this host would write a core beside a crashing process.

    A container that discards cores by default makes "no core was written"
    true for reasons that have nothing to do with our controls, so the
    environment is read and stated rather than assumed. ``reason`` is empty
    exactly when :attr:`writes_a_core_beside_the_process` is true.
    """

    hard_limit: int
    pattern: str
    writes_a_core_beside_the_process: bool
    reason: str


def _prctl(option: int, argument: int) -> int:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    unsigned = (ctypes.c_ulong,) * 4
    libc.prctl.argtypes = (ctypes.c_int, *unsigned)
    libc.prctl.restype = ctypes.c_int
    ctypes.set_errno(0)
    result: int = libc.prctl(option, argument, 0, 0, 0)
    if result < 0:
        raise ProcessHardeningError(
            f"prctl({option}, {argument}) failed, errno {ctypes.get_errno()}"
        )
    return result


def _require_linux(control: str) -> None:
    if sys.platform != "linux":  # pragma: no cover - CI and prod are Linux
        raise ProcessHardeningError(
            f"{control} is a Linux control; this host reports {sys.platform!r}, where "
            "files/10 §3's core-dump and ptrace guarantees do not hold either"
        )


def yama_ptrace_scope() -> int | None:
    """The Yama LSM's ``ptrace_scope``, or ``None`` where the LSM is absent.

    ``None`` is not ``0``: a kernel without Yama has no such setting, and
    reporting a number nobody set would read as a control that exists.
    """
    try:
        return int(YAMA_PTRACE_SCOPE_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def core_dump_environment() -> CoreDumpEnvironment:
    """Read ``RLIMIT_CORE`` and ``kernel.core_pattern`` and say what they mean."""
    _require_linux("core-dump accounting")
    _, hard = resource.getrlimit(resource.RLIMIT_CORE)
    try:
        pattern = CORE_PATTERN_PATH.read_text(encoding="utf-8").strip()
    except OSError as error:
        return CoreDumpEnvironment(
            hard_limit=hard,
            pattern="",
            writes_a_core_beside_the_process=False,
            reason=f"{CORE_PATTERN_PATH} is unreadable ({error.errno})",
        )
    if hard == 0:
        reason = "RLIMIT_CORE's hard limit is 0, so no process here can raise it"
    elif pattern.startswith("|"):
        reason = f"kernel.core_pattern pipes to a handler ({pattern}), not to a file"
    elif pattern.startswith("/"):
        reason = f"kernel.core_pattern writes to an absolute path ({pattern})"
    else:
        reason = ""
    return CoreDumpEnvironment(
        hard_limit=hard,
        pattern=pattern,
        writes_a_core_beside_the_process=not reason,
        reason=reason,
    )


def disable_core_dumps() -> tuple[int, int]:
    """``RLIMIT_CORE=(0,0)`` — the hard limit too, so nothing can raise it back."""
    _require_linux("RLIMIT_CORE")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    limit = resource.getrlimit(resource.RLIMIT_CORE)
    if limit != (0, 0):
        raise ProcessHardeningError(f"RLIMIT_CORE is {limit} after being set to (0, 0)")
    return limit


def deny_ptrace_attach() -> int:
    """``prctl(PR_SET_DUMPABLE, 0)`` — no attach, no ``/proc/<pid>/mem``, no core.

    Read back with ``PR_GET_DUMPABLE`` because the guarantee is the kernel's
    state, not the call's return code.
    """
    _require_linux("prctl(PR_SET_DUMPABLE)")
    _prctl(PR_SET_DUMPABLE, 0)
    dumpable = _prctl(PR_GET_DUMPABLE, 0)
    if dumpable != 0:
        raise ProcessHardeningError(f"the process is still dumpable ({dumpable})")
    return dumpable


def harden_process() -> HardeningReport:
    """Apply both process controls and report the resulting state.

    Idempotent: calling it twice leaves the same state and returns the same
    report. Call it at worker start, before any frame is decoded.
    """
    core_limit = disable_core_dumps()
    dumpable = deny_ptrace_attach()
    environment = core_dump_environment()
    return HardeningReport(
        core_limit=core_limit,
        dumpable=dumpable,
        core_pattern=environment.pattern,
        yama_ptrace_scope=yama_ptrace_scope(),
    )
