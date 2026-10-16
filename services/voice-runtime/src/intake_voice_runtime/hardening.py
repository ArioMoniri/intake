"""Process hardening for raw audio's lifetime in memory (CLAUDE.md invariant 3).

*"Raw audio is never written to disk, DB, object store or logs — and never
reachable through a core dump, a swap page or a crash report. Memory buffers
≤ 60 s, mlocked, zeroed on every trigger."* The buffers belong to the media
plane; what the *process* owes them is three facts, each set once at start and
each reported rather than assumed (files/10 §3, the threat model's
``voice-runtime`` row: ``RLIMIT_CORE=(0,0)``, process hardening):

- **core dumps off** — ``RLIMIT_CORE`` is ``(0, 0)``, soft and hard, so no
  child or later ``setrlimit`` can raise it back;
- **not dumpable** — ``prctl(PR_SET_DUMPABLE, 0)``: no core even if a limit
  were raised, and no same-uid ``ptrace`` or ``/proc/<pid>/mem`` read;
- **memory locked** — ``mlockall(MCL_CURRENT | MCL_FUTURE)``: every page this
  process has or will have stays out of swap, so an audio buffer cannot reach a
  swap page whatever the host's swap policy. The staging compose gives the
  container an unlimited ``memlock`` limit for this, and no capability.

Each is a readiness check (``core_dumps_off``, ``memory_locked``). On a kernel
that does not offer one — macOS, where the dev tier runs — the fact is false
and the worker is not ready, which is the honest answer: a speech worker that
cannot lock its memory does not take a session.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import resource
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

__all__ = [
    "MCL_CURRENT",
    "MCL_FUTURE",
    "PR_SET_DUMPABLE",
    "ProcessHardening",
    "harden_process",
]

logger = logging.getLogger("intake_voice_runtime.hardening")

#: <linux/prctl.h>
PR_SET_DUMPABLE: Final = 4
#: <sys/mman.h>
MCL_CURRENT: Final = 1
MCL_FUTURE: Final = 2


class Libc(Protocol):
    """The two libc calls used, as ctypes exposes them: 0 on success, -1 on failure."""

    def prctl(self, option: int, arg2: int, arg3: int, arg4: int, arg5: int, /) -> int: ...

    def mlockall(self, flags: int, /) -> int: ...


@dataclass(frozen=True)
class ProcessHardening:
    """What the process could make true about itself at start."""

    core_dumps_off: bool
    not_dumpable: bool
    memory_locked: bool


def _linux_libc() -> Libc | None:
    name = ctypes.util.find_library("c")
    if name is None:
        return None
    libc: Libc = ctypes.CDLL(name, use_errno=True)
    return libc


def harden_process(
    *,
    libc: Libc | None = None,
    setrlimit: Callable[[int, tuple[int, int]], None] = resource.setrlimit,
    platform: str = sys.platform,
) -> ProcessHardening:
    """Make the three facts true where the kernel allows, and say which held."""
    try:
        setrlimit(resource.RLIMIT_CORE, (0, 0))
        core_dumps_off = True
    except (OSError, ValueError) as err:
        logger.error("core dumps could not be turned off", extra={"error": type(err).__name__})
        core_dumps_off = False

    if not platform.startswith("linux"):
        # prctl and an mlockall of the whole process are Linux facts; anywhere
        # else neither is claimed
        return ProcessHardening(core_dumps_off, not_dumpable=False, memory_locked=False)

    bound = libc if libc is not None else _linux_libc()
    if bound is None:
        return ProcessHardening(core_dumps_off, not_dumpable=False, memory_locked=False)
    not_dumpable = bound.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) == 0
    memory_locked = bound.mlockall(MCL_CURRENT | MCL_FUTURE) == 0
    if not not_dumpable:
        logger.error("the process could not be made non-dumpable")
    if not memory_locked:
        # errno names the cause (ENOMEM: the memlock limit; EPERM); no address
        logger.error("process memory could not be locked", extra={"errno": ctypes.get_errno()})
    return ProcessHardening(core_dumps_off, not_dumpable, memory_locked)
