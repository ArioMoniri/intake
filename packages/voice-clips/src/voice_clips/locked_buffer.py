"""A byte region that is page-aligned, wholly mlocked and never dumped.

**This module holds no speech of any kind.** It is the memory primitive
CLAUDE.md invariant 3 names — *"Memory buffers ≤ 60 s, mlocked, zeroed on
every trigger"* — and files/10 §3 specifies precisely: *"allocate the ring
buffer once as a page-aligned ``mmap(MAP_ANONYMOUS|MAP_PRIVATE)`` region plus
``mlock`` … Verify via ``/proc/self/smaps``: ``Locked:`` == region size"*.

**Why the verification is in the constructor rather than in a test.**
``mlock`` returns 0 for a partial lock exactly as it does for a complete one,
so a caller that checks the return value has checked nothing: half a window of
audio can stay pageable while every log line says the buffer is locked. This
type therefore reads its own region back out of ``/proc/self/smaps`` and
refuses to exist unless the kernel agrees that all of it is locked
(:class:`PartialLockError`). The same reader is what
``tests/voice/test_audio_memory_hygiene.py`` asserts against, and its control
locks half a region, gets 0 back, and watches the shortfall appear.

Three kernel controls, not one, because they close different doors:

- ``mlock`` keeps the pages out of swap (files/10 §9.1 invariant 17).
- ``MADV_DONTDUMP`` keeps the region out of a core file even when something
  else raises ``RLIMIT_CORE`` (invariant 16). Belt and braces: the process
  control can be undone by a caller, the region flag cannot be undone by
  accident.
- ``MADV_DONTFORK`` keeps the region out of any forked child, so a crash
  handler that forks to collect diagnostics inherits nothing to collect
  (invariant 19).

Zeroization is a ``memset`` **on the region's address**, never a Python slice
assignment, for the reason files/10 §3 gives: a slice assignment is a claim
about an object, and the guarantee is about the pages.

**Placement.** Process- and memory-level controls belong to the worker that
hosts lane buffers, not to the clip cache; this module sits here because
INT-278's change owns no other package. It imports nothing from
:mod:`voice_clips`, has no dependency on the clip builder, and moves without
edits. See ADR-025 and docs/evidence/INT-278.md.
"""

from __future__ import annotations

import ctypes
import mmap
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final

__all__ = [
    "MAX_WINDOW_S",
    "PAGE_SIZE",
    "SMAPS_PATH",
    "BufferClosedError",
    "BufferOverflowError",
    "LockedBuffer",
    "LockedBufferError",
    "PartialLockError",
    "RegionLockFailedError",
    "SmapsRegion",
    "WindowTooLongError",
    "locked_bytes_in",
    "smaps_regions",
    "swap_bytes_in",
    "vm_flags_in",
]

SMAPS_PATH: Final = Path("/proc/self/smaps")

PAGE_SIZE: Final = mmap.PAGESIZE

#: CLAUDE.md invariant 3's ceiling on held audio. Enforced here as a second,
#: independent bound on top of the runtime's own frame accounting: a buffer
#: that cannot be allocated for 61 seconds cannot hold 61 seconds.
MAX_WINDOW_S: Final = 60.0

_HEADER = re.compile(r"^([0-9a-f]+)-([0-9a-f]+) ")
_KB_FIELDS: Final = ("Size", "Locked", "Swap")


class LockedBufferError(Exception):
    """Base for every refusal on the locked-region path."""


class RegionLockFailedError(LockedBufferError):
    """``mlock`` itself refused — usually ``RLIMIT_MEMLOCK`` or a missing
    ``CAP_IPC_LOCK`` (files/10 §3: the container needs one of the two)."""


class PartialLockError(LockedBufferError):
    """``mlock`` returned 0 but the kernel locked less than the whole region."""


class WindowTooLongError(LockedBufferError):
    """A window longer than :data:`MAX_WINDOW_S` (CLAUDE.md invariant 3)."""


class BufferOverflowError(LockedBufferError):
    """More bytes offered than the region holds. Refused, never wrapped."""


class BufferClosedError(LockedBufferError):
    """The region was released; its address means nothing now."""


@dataclass(frozen=True, slots=True)
class SmapsRegion:
    """One mapping as ``/proc/self/smaps`` reports it."""

    start: int
    end: int
    size_bytes: int
    locked_bytes: int
    swap_bytes: int
    vm_flags: frozenset[str]


_LIBC: ctypes.CDLL | None = None


def _libc() -> ctypes.CDLL:
    global _LIBC
    if _LIBC is not None:
        return _LIBC
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.mlock.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    libc.mlock.restype = ctypes.c_int
    libc.munlock.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    libc.munlock.restype = ctypes.c_int
    libc.memset.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t)
    libc.memset.restype = ctypes.c_void_p
    _LIBC = libc
    return libc


def smaps_regions() -> tuple[SmapsRegion, ...]:
    """Every mapping of this process, with its locked and swapped sizes.

    Reading our own ``smaps`` is the only way to learn what the kernel
    actually did: the syscall return value cannot distinguish a whole lock
    from a partial one.
    """
    regions: list[SmapsRegion] = []
    start = end = 0
    values: dict[str, int] = {}
    flags: frozenset[str] = frozenset()

    def flush() -> None:
        if end > start:
            regions.append(
                SmapsRegion(
                    start=start,
                    end=end,
                    size_bytes=values.get("Size", 0),
                    locked_bytes=values.get("Locked", 0),
                    swap_bytes=values.get("Swap", 0),
                    vm_flags=flags,
                )
            )

    for line in SMAPS_PATH.read_text(encoding="utf-8").splitlines():
        header = _HEADER.match(line)
        if header:
            flush()
            start, end = int(header.group(1), 16), int(header.group(2), 16)
            values, flags = {}, frozenset()
            continue
        key, _, rest = line.partition(":")
        if key in _KB_FIELDS:
            values[key] = int(rest.split()[0]) * 1024
        elif key == "VmFlags":
            flags = frozenset(rest.split())
    flush()
    return tuple(regions)


def _overlap(region: SmapsRegion, start: int, length: int) -> int:
    return max(0, min(region.end, start + length) - max(region.start, start))


def _sum_over(start: int, length: int, field: str) -> int:
    """Sum a per-mapping size over the mappings covering ``[start, start+length)``.

    Clamped to the overlap, so a mapping wider than the region cannot inflate
    the total — a partial lock splits the mapping in two and this sees the
    locked half only, which is the whole point.
    """
    total = 0
    for region in smaps_regions():
        overlap = _overlap(region, start, length)
        if overlap:
            total += min(getattr(region, field), overlap)
    return total


def locked_bytes_in(start: int, length: int) -> int:
    """How many of ``length`` bytes at ``start`` the kernel reports locked."""
    return _sum_over(start, length, "locked_bytes")


def swap_bytes_in(start: int, length: int) -> int:
    """How many bytes of the region the kernel reports swapped out."""
    return _sum_over(start, length, "swap_bytes")


def vm_flags_in(start: int, length: int) -> frozenset[str]:
    """The union of the kernel's flags over the mappings covering the region."""
    flags: set[str] = set()
    for region in smaps_regions():
        if _overlap(region, start, length):
            flags |= region.vm_flags
    return frozenset(flags)


def _page_aligned(length: int) -> int:
    return -(-length // PAGE_SIZE) * PAGE_SIZE


class LockedBuffer:
    """A page-aligned region that is locked, undumpable and zeroable.

    The only public way to read it is :meth:`view`, which hands back a
    read-only ``memoryview`` rather than ``bytes``: a ``bytes`` copy would be
    an unlocked, dumpable duplicate of exactly what the lock exists to
    contain.
    """

    __slots__ = ("_address", "_capacity", "_length", "_region")

    def __init__(self, capacity_bytes: int) -> None:
        if sys.platform != "linux":  # pragma: no cover - CI and prod are Linux
            raise LockedBufferError(
                f"mlock accounting is read from /proc/self/smaps, which {sys.platform} "
                "does not provide; files/10 §3's controls are Linux controls"
            )
        if capacity_bytes <= 0:
            raise LockedBufferError(f"capacity must be positive, got {capacity_bytes}")
        capacity = _page_aligned(capacity_bytes)
        region = mmap.mmap(-1, capacity, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        address = ctypes.addressof((ctypes.c_char * capacity).from_buffer(region))
        libc = _libc()
        if libc.mlock(address, capacity) != 0:
            errno = ctypes.get_errno()
            region.close()
            raise RegionLockFailedError(
                f"mlock refused {capacity} bytes (errno {errno}); the worker needs "
                "CAP_IPC_LOCK or a raised RLIMIT_MEMLOCK (files/10 §3)"
            )
        # Order matters: touch the pages so the kernel accounts them before
        # the region is read back, then exclude them from a core and a fork.
        libc.memset(address, 0, capacity)
        region.madvise(mmap.MADV_DONTDUMP)
        region.madvise(mmap.MADV_DONTFORK)
        locked = locked_bytes_in(address, capacity)
        if locked != capacity:
            libc.munlock(address, capacity)
            region.close()
            raise PartialLockError(
                f"the kernel locked {locked} of {capacity} bytes — mlock returned 0 "
                "for a partial lock, which is why this is read back rather than trusted"
            )
        self._region: mmap.mmap | None = region
        self._address = address
        self._capacity = capacity
        self._length = 0

    @classmethod
    def for_window(
        cls, *, seconds: float, sample_rate_hz: int, sample_width_bytes: int = 2
    ) -> LockedBuffer:
        """Size a region by the window it must hold, refusing over 60 seconds."""
        if seconds <= 0:
            raise LockedBufferError(f"a window must be positive, got {seconds}")
        if seconds > MAX_WINDOW_S:
            raise WindowTooLongError(
                f"{seconds} s exceeds the {MAX_WINDOW_S} s ceiling of CLAUDE.md invariant 3"
            )
        return cls(int(seconds * sample_rate_hz) * sample_width_bytes)

    # --- reads ------------------------------------------------------------------------

    @property
    def capacity(self) -> int:
        """Bytes the region holds, rounded up to a whole number of pages."""
        return self._capacity

    @property
    def length(self) -> int:
        """Bytes written since the last zeroization."""
        return self._length

    @property
    def address(self) -> int:
        """The region's base address, for ``smaps`` accounting."""
        self._require_open()
        return self._address

    @property
    def closed(self) -> bool:
        return self._region is None

    def view(self) -> memoryview:
        """A read-only view of what has been written. Release before closing."""
        region = self._require_open()
        return memoryview(region)[: self._length].toreadonly()

    def locked_bytes(self) -> int:
        """What the kernel says is locked of this region, right now."""
        return locked_bytes_in(self.address, self._capacity)

    def swap_bytes(self) -> int:
        """What the kernel says is swapped out of this region, right now."""
        return swap_bytes_in(self.address, self._capacity)

    def vm_flags(self) -> frozenset[str]:
        """The kernel's flags for this region — ``lo`` locked, ``dd`` no-dump."""
        return vm_flags_in(self.address, self._capacity)

    def is_zeroed(self) -> bool:
        """Whether every byte of the whole region is zero.

        Reads through ``ctypes`` rather than copying the region out, so the
        check itself never makes an unlocked duplicate.
        """
        self._require_open()
        block = (ctypes.c_char * self._capacity).from_address(self._address)
        return not any(block.raw)

    # --- writes -----------------------------------------------------------------------

    def write(self, data: bytes | bytearray | memoryview) -> int:
        """Append bytes. Refuses an overflow rather than wrapping or truncating."""
        region = self._require_open()
        if self._length + len(data) > self._capacity:
            raise BufferOverflowError(
                f"{len(data)} bytes do not fit in {self._capacity - self._length} remaining"
            )
        region.seek(self._length)
        written = region.write(data)
        self._length += written
        return written

    def zeroize(self) -> int:
        """``memset`` the whole region and forget the length. Returns bytes wiped.

        The whole region, not the written prefix: what a previous, longer
        window left behind is exactly what must not survive.
        """
        self._require_open()
        _libc().memset(self._address, 0, self._capacity)
        self._length = 0
        return self._capacity

    def close(self) -> None:
        """Zero, unlock and release. Safe to call twice."""
        region = self._region
        if region is None:
            return
        self.zeroize()
        _libc().munlock(self._address, self._capacity)
        self._region = None
        region.close()

    # --- protocol ---------------------------------------------------------------------

    def __enter__(self) -> LockedBuffer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        """Sizes and state only.

        A ``repr`` is how a buffer reaches a traceback, a log line and a crash
        report; one that rendered its contents would defeat every control in
        this module (CLAUDE.md invariants 3 and 6).
        """
        state = "closed" if self.closed else "open"
        return (
            f"<LockedBuffer {state} capacity={self._capacity} "
            f"length={self._length} page={PAGE_SIZE}>"
        )

    def _require_open(self) -> mmap.mmap:
        if self._region is None:
            raise BufferClosedError("the region was released; its address means nothing now")
        return self._region
