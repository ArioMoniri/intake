"""INT-278 — invariant 3's memory half, proved with a control for each half.

Acceptance, verbatim from ``docs/backlog/issues.yaml``:

    "**mlock is proved, not declared**: a test reads ``/proc/self/smaps`` for
    the live buffer region and asserts a non-zero ``Locked:`` line, with a
    near-miss control over an ordinary allocation that must show zero — an
    assertion that only checks the mlock CALL RETURNED proves nothing, because
    a partial lock and a full one both return 0"

    "**core dumps are proved by crashing**: a subprocess sets RLIMIT_CORE to
    (0,0), fills a buffer with a known synthetic marker, calls os.abort(), and
    the test asserts no core file exists AND that the marker appears in no file
    the process could have written; the control is the same subprocess with the
    limit RAISED, which must produce a core, or the test is asserting the
    platform rather than the code"

    "**the crash-report path is closed rather than assumed**: files/10 §3 names
    it a live defect, so the handler that would ship a report is identified and
    a test proves the audio buffer is unreachable from it — and if no crash
    reporter is wired yet, that is asserted as the reason rather than left
    implied, so the test starts failing the day one is added"

    "**ptrace is refused** (files/10 §3 invariant 28): the process denies
    attach, with a control showing an unprotected child permits it — and the
    platform dependence is stated, since this is a Linux assertion and the CI
    runner is the only place it holds"

    "each property names the files/10 §3 row it discharges, and INT-094's
    ``INVARIANTS[2].not_covered_here`` list shrinks by exactly the rows proved —
    never by rewording the entry"

**The row each class discharges** is in its own docstring, and the four are
files/10 §9.1 invariants 17 (``audio_no_swap_guard``), 16
(``audio_no_core_guard``), 19 (``audio_no_telemetry_guard``) and 28
(``process_hardening_guard``).

**Platform dependence, stated once.** Every assertion below reads
``/proc``, ``prctl`` or ``RLIMIT_CORE``. All three are Linux interfaces; the
production workers and the CI runner (``ubuntu-latest``) are the only places
these hold, and :class:`TestThePlatformIsStated` says so as an assertion
rather than as a comment. On any other platform this module fails loudly,
which is the correct outcome: the controls it describes are not in force
there either.

**What this module still does not make true.** It proves the *mechanism* —
:class:`~voice_clips.locked_buffer.LockedBuffer` and
:func:`~voice_clips.process_hardening.harden_process` — and the crash-report
handler, which is production code on the PHI path. It does **not** prove that
``services/voice-runtime``'s lane frames are allocated from that buffer or
that its worker entry point calls that function: today
``observers/buffer.py`` holds a plain ``bytearray``, so invariant 3's
*mlocked* clause is unimplemented there, not merely untested. Wiring the two
together, and the container half of invariant 28 (non-root,
``no-new-privileges``, ``CAP_SYS_PTRACE`` dropped, ``ptrace_scope=1``, which
``infra/`` carries nowhere today), are outside this change and recorded in
docs/evidence/INT-278.md.

**No real audio anywhere.** Every byte held here is the authored ASCII string
in :data:`SYNTHETIC_MARKER`, and no test writes the artefact it then looks
for: where a core file appears, the kernel wrote it.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import resource
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from intake_platform.errors import ERROR_REPORTING_FLAG, scrub_event, setup_error_reporting
from intake_platform.flags import InMemoryProvider
from memory_hygiene_children import CAPACITY_BYTES, MARKERS_PER_REGION, SYNTHETIC_MARKER
from voice_clips.locked_buffer import (
    PAGE_SIZE,
    BufferClosedError,
    BufferOverflowError,
    LockedBuffer,
    LockedBufferError,
    PartialLockError,
    RegionLockFailedError,
    WindowTooLongError,
    locked_bytes_in,
    smaps_regions,
    vm_flags_in,
)
from voice_clips.process_hardening import (
    CORE_PATTERN_PATH,
    PR_GET_DUMPABLE,
    PR_SET_DUMPABLE,
    YAMA_PTRACE_SCOPE_PATH,
    ProcessHardeningError,
    _prctl,
    core_dump_environment,
    deny_ptrace_attach,
    yama_ptrace_scope,
)

REPO = Path(__file__).resolve().parents[2]
CHILDREN = Path(__file__).resolve().parent / "memory_hygiene_children.py"

#: The one module in the workspace that may hand an event to the crash
#: reporter (files/10 §3, INT-023). Named here so this suite starts failing
#: the day a second one appears.
CRASH_REPORTER_MODULE = "packages/intake_platform/src/intake_platform/errors.py"

#: Anything larger than this in a crash-report payload is a buffer, not a
#: field — files/10 §9.1 invariant 19 states the bound as 1 KB.
MAX_PAYLOAD_VALUE_BYTES = 1024

SCAN_ROOTS = ("packages", "services")
SKIP_PARTS = frozenset({"tests", ".venv", "node_modules", "build", "dist", ".cache"})


def _python_sources() -> list[Path]:
    return [
        path
        for root in SCAN_ROOTS
        if (REPO / root).is_dir()
        for path in sorted((REPO / root).rglob("*.py"))
        if SKIP_PARTS.isdisjoint(path.parts)
    ]


def _run_child(role: str, mode: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, our own file
        [sys.executable, str(CHILDREN), role, mode],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _crash_in(directory: Path, mode: str) -> tuple[int, int]:
    """Fork, exec the crash child in ``directory``, and report how it died.

    ``os.fork`` rather than :mod:`subprocess` because only a raw wait status
    carries ``WCOREDUMP``, which is the bit files/10 §9.1 invariant 16 names.
    """
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns to pytest
        try:
            os.chdir(directory)
            os.execv(  # noqa: S606 - fixed argv, our own file, no shell
                sys.executable, [sys.executable, str(CHILDREN), "crash", mode]
            )
        finally:
            os._exit(127)
    _, status = os.waitpid(pid, 0)
    return os.WTERMSIG(status), int(os.WCOREDUMP(status))


def _files_under(directory: Path) -> list[Path]:
    return [path for path in sorted(directory.rglob("*")) if path.is_file()]


def _marker_bearing_files(directory: Path) -> list[str]:
    return [
        str(path.relative_to(directory))
        for path in _files_under(directory)
        if SYNTHETIC_MARKER in path.read_bytes()
    ]


def _marker_occurrences(directory: Path) -> int:
    """How many whole markers the crash left behind, over every file written.

    Counted rather than merely detected: the marker's own module constant and
    the compiled module that carries it are ordinary heap and file-backed
    pages, so a core will always hold a handful. What must never appear is a
    *region's worth* — :data:`MARKERS_PER_REGION` of them.
    """
    return sum(path.read_bytes().count(SYNTHETIC_MARKER) for path in _files_under(directory))


#: Above this, a core is carrying a buffer rather than a stray constant. Set
#: two orders of magnitude below a filled region (6898 markers) and two orders
#: above what a core of the locked build actually contains (measured: 2).
INCIDENTAL_MARKER_CEILING = 50


#: An option number ``prctl`` does not define, so the call fails without
#: changing anything about this process.
_UNKNOWN_PRCTL_OPTION = 0x7FFF


def _dumpable() -> int:
    """This process's ``PR_GET_DUMPABLE``.

    ``_prctl`` is imported private on purpose: its failure path is a control
    of its own (a ``prctl`` that returned -1 quietly would read as applied),
    and there is no public function that can reach it without also applying an
    irreversible setting.
    """
    return _prctl(PR_GET_DUMPABLE, 0)


def _restore_dumpable() -> None:
    """Undo :func:`~voice_clips.process_hardening.deny_ptrace_attach`.

    Production never does this — hardening is one-way — so the inverse lives
    here rather than in the module, where it would be a footgun.
    """
    _prctl(PR_SET_DUMPABLE, 1)


@pytest.fixture
def buffer() -> Iterator[LockedBuffer]:
    held = LockedBuffer(CAPACITY_BYTES)
    try:
        yield held
    finally:
        held.close()


class TestThePlatformIsStated:
    """The dependence the acceptance asks to be stated, as an assertion."""

    def test_every_proof_here_is_a_linux_proof(self) -> None:
        assert sys.platform == "linux", (
            "/proc/self/smaps, prctl(PR_SET_DUMPABLE) and RLIMIT_CORE core "
            "files are Linux interfaces. The production workers and the CI "
            f"runner are Linux; this host reports {sys.platform!r}, where the "
            "controls of files/10 §3 are not in force either"
        )

    def test_the_kernel_surfaces_these_proofs_read_are_present(self) -> None:
        assert Path("/proc/self/smaps").is_file()
        assert CORE_PATTERN_PATH.is_file()


class TestMlockIsProvedNotDeclared:
    """files/10 §9.1 invariant 17 — ``audio_no_swap_guard``.

    *"Verify via /proc/self/smaps: ``Locked:`` == region size, and
    ``SwapTotal: 0``."* The call's return value is not evidence: the control
    :meth:`test_a_partial_lock_also_returns_zero_and_smaps_shows_it` locks half
    a region, gets 0 back, and reads the shortfall out of smaps.
    """

    def test_the_live_region_reports_a_non_zero_locked_line(self, buffer: LockedBuffer) -> None:
        buffer.write(SYNTHETIC_MARKER * 8)
        assert buffer.locked_bytes() > 0

    def test_the_whole_region_is_locked_not_merely_some_of_it(self, buffer: LockedBuffer) -> None:
        assert buffer.locked_bytes() == buffer.capacity

    def test_the_region_holds_no_swapped_page(self, buffer: LockedBuffer) -> None:
        buffer.write(SYNTHETIC_MARKER * 8)
        assert buffer.swap_bytes() == 0

    def test_the_region_carries_the_locked_and_no_dump_kernel_flags(
        self, buffer: LockedBuffer
    ) -> None:
        flags = buffer.vm_flags()
        assert "lo" in flags, f"the region is not marked locked: {sorted(flags)}"
        assert "dd" in flags, f"the region is not excluded from a core: {sorted(flags)}"

    # --- controls -----------------------------------------------------------------

    def test_an_ordinary_allocation_reports_zero_locked(self) -> None:
        """Without this the suite asserts the platform, not the code."""
        import mmap

        ordinary = mmap.mmap(-1, CAPACITY_BYTES, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        try:
            ordinary.write(SYNTHETIC_MARKER * 8)
            import ctypes

            address = ctypes.addressof((ctypes.c_char * CAPACITY_BYTES).from_buffer(ordinary))
            assert locked_bytes_in(address, CAPACITY_BYTES) == 0
            assert "lo" not in vm_flags_in(address, CAPACITY_BYTES)
        finally:
            ordinary.close()

    def test_a_partial_lock_also_returns_zero_and_smaps_shows_it(self) -> None:
        """The whole reason this issue exists, as an executable statement."""
        import ctypes
        import mmap

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.mlock.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
        region = mmap.mmap(-1, CAPACITY_BYTES, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
        try:
            address = ctypes.addressof((ctypes.c_char * CAPACITY_BYTES).from_buffer(region))
            half = CAPACITY_BYTES // 2
            assert libc.mlock(address, half) == 0, "the half-lock itself must succeed"
            assert locked_bytes_in(address, CAPACITY_BYTES) == half
            assert locked_bytes_in(address, CAPACITY_BYTES) < CAPACITY_BYTES
        finally:
            libc.munlock(address, CAPACITY_BYTES)
            region.close()

    def test_the_constructor_refuses_a_region_it_cannot_fully_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed: a partial lock is a refusal, not a warning."""
        monkeypatch.setattr(
            "voice_clips.locked_buffer.locked_bytes_in",
            lambda start, length: length // 2,
        )
        with pytest.raises(PartialLockError):
            LockedBuffer(CAPACITY_BYTES)

    def test_the_scan_walks_a_real_map(self) -> None:
        """A smaps reader that parsed nothing would pass every test above."""
        regions = smaps_regions()
        assert len(regions) >= 5
        assert all(region.end > region.start for region in regions)
        assert any(region.locked_bytes == 0 for region in regions)

    # --- the clauses of invariant 3 this must not weaken ---------------------------

    def test_the_sixty_second_ceiling_still_refuses_a_longer_window(self) -> None:
        with pytest.raises(WindowTooLongError):
            LockedBuffer.for_window(seconds=60.5, sample_rate_hz=16000)

    def test_a_sixty_second_window_is_accepted_and_fully_locked(self) -> None:
        held = LockedBuffer.for_window(seconds=60.0, sample_rate_hz=16000)
        try:
            assert held.capacity >= 60 * 16000 * 2
            assert held.locked_bytes() == held.capacity
        finally:
            held.close()

    def test_zeroize_overwrites_the_region_through_its_address(self, buffer: LockedBuffer) -> None:
        buffer.write(SYNTHETIC_MARKER * 8)
        assert bytes(buffer.view())[: len(SYNTHETIC_MARKER)] == SYNTHETIC_MARKER
        assert buffer.zeroize() == buffer.capacity
        assert bytes(buffer.view()) == b""
        assert buffer.is_zeroed()


class TestCoreDumpsAreProvedByCrashing:
    """files/10 §9.1 invariant 16 — ``audio_no_core_guard``.

    *"Prove it by actually crashing: fork a child, set the limit,
    ``os.abort()``, assert ``WCOREDUMP`` false and no core file at the pattern
    path."*
    """

    def test_the_environment_can_run_the_control_or_says_exactly_why(self) -> None:
        """A container that discards cores by default would make the hardened
        assertion pass for the wrong reason, so the environment is read and
        stated before anything is concluded from it."""
        environment = core_dump_environment()
        pattern = CORE_PATTERN_PATH.read_text(encoding="utf-8").strip()
        _, hard = resource.getrlimit(resource.RLIMIT_CORE)
        assert environment.pattern == pattern
        assert environment.hard_limit == hard
        if environment.writes_a_core_beside_the_process:
            assert environment.reason == ""
        else:
            assert environment.reason != ""
            assert pattern.startswith(("|", "/")) or hard == 0, (
                "the environment claims the control cannot run, but the kernel "
                f"says core_pattern={pattern!r} and RLIMIT_CORE hard={hard}"
            )

    def test_a_hardened_crash_leaves_no_core_and_no_marker(self, tmp_path: Path) -> None:
        signal_number, core_written = _crash_in(tmp_path, "hardened")
        assert signal_number == 6, "the child must die of SIGABRT, not something else"
        assert core_written == 0, "WCOREDUMP is set: the kernel wrote a core"
        assert _files_under(tmp_path) == [], f"the crash left {_files_under(tmp_path)}"
        assert _marker_bearing_files(tmp_path) == []

    def test_the_control_with_the_limit_raised_writes_a_core(self, tmp_path: Path) -> None:
        """Without this the hardened assertion is a claim about the platform."""
        environment = core_dump_environment()
        if not environment.writes_a_core_beside_the_process:
            assert environment.reason != ""
            return
        signal_number, core_written = _crash_in(tmp_path, "limit_raised")
        assert signal_number == 6
        assert core_written == 1, environment.reason
        cores = [path.name for path in _files_under(tmp_path)]
        assert cores, "the limit was raised and the kernel still wrote nothing"

    def test_a_whole_region_reaches_a_core_when_the_buffer_is_an_ordinary_one(
        self, tmp_path: Path
    ) -> None:
        """The search is proved to work before it is used as a negative.

        An unhardened ``bytearray`` — invariant 3 without an implementation —
        lands in the core verbatim, a whole region's worth of it. That is the
        leak the locked buffer closes, and it is why "no marker" means
        something above.
        """
        environment = core_dump_environment()
        if not environment.writes_a_core_beside_the_process:
            assert environment.reason != ""
            return
        signal_number, core_written = _crash_in(tmp_path, "unprotected")
        assert signal_number == 6
        assert core_written == 1
        found = _marker_occurrences(tmp_path)
        assert found >= MARKERS_PER_REGION, (
            f"an ordinary buffer left {found} markers in the core, fewer than the "
            f"{MARKERS_PER_REGION} it held, so the byte search proves nothing"
        )

    def test_the_locked_region_is_excluded_even_when_a_core_is_written(
        self, tmp_path: Path
    ) -> None:
        """``MADV_DONTDUMP``, not only ``RLIMIT_CORE``: two independent doors.

        The count is not zero and saying so is the honest form: the marker is
        a module constant, so the interpreter's own heap and the compiled
        module hold a few copies whatever the buffer does. What is absent is
        the region.
        """
        environment = core_dump_environment()
        if not environment.writes_a_core_beside_the_process:
            assert environment.reason != ""
            return
        _crash_in(tmp_path, "limit_raised")
        assert _files_under(tmp_path), "the control produced no core to inspect"
        found = _marker_occurrences(tmp_path)
        assert found <= INCIDENTAL_MARKER_CEILING, (
            f"{found} markers reached the core; a filled region is "
            f"{MARKERS_PER_REGION}, so the locked region was dumped"
        )


class TestTheCrashReportPathIsClosed:
    """files/10 §9.1 invariant 19 — ``audio_no_telemetry_guard``.

    files/10 §3 calls this *"the leak nobody mentioned and the one likeliest to
    actually happen"* and records it as **a live defect today**. The handler
    that would ship a report is
    :func:`intake_platform.errors.setup_error_reporting`, which initialises
    ``sentry_sdk`` (the protocol GlitchTip speaks) behind
    ``INTAKE_GLITCHTIP_DSN`` and the ``error_reporting`` flag. It is
    identified here by name and by a scan that fails if a second initialiser
    appears anywhere under ``packages/`` or ``services/``.

    The half files/10 runs *"against a local GlitchTip"* is a compose-tier
    integration and is not run here; what is proved is the property that
    matters for invariant 3 — that a report built from an exception raised
    while a locked buffer is live carries none of its bytes.
    """

    def test_exactly_one_module_can_initialise_the_crash_reporter(self) -> None:
        offenders = [
            str(path.relative_to(REPO))
            for path in _python_sources()
            if any(
                isinstance(node, ast.Import | ast.ImportFrom)
                and any(
                    name.split(".")[0] == "sentry_sdk"
                    for name in (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                )
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            )
        ]
        assert offenders == [CRASH_REPORTER_MODULE], (
            "a second crash-report initialiser would ship events this suite "
            f"never sees: {offenders}"
        )

    def test_the_reporter_refuses_to_serialise_local_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A local named for a buffer is the leak; the option is the door."""
        import types

        recorded: dict[str, Any] = {}
        monkeypatch.setenv("INTAKE_GLITCHTIP_DSN", "https://k@localhost/1")
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk",
            types.SimpleNamespace(init=lambda **options: recorded.update(options)),
        )
        flags = InMemoryProvider({ERROR_REPORTING_FLAG: True})
        assert setup_error_reporting(flags) is True
        assert recorded["include_local_variables"] is False
        assert recorded["before_send"] is scrub_event
        assert recorded["attach_stacktrace"] is False
        assert recorded["max_request_body_size"] == "never"

    def _event_holding_the_buffer(self, held: LockedBuffer) -> dict[str, Any]:
        """A report shaped the way the SDK builds one.

        The buffer sits in each of the five slots the SDK fills **on its own**
        from a raise in the audio path: the frame locals it serialises, the
        request body it attaches, ``extra``, ``tags``, and breadcrumb data.
        Free-text fields the raising code writes itself — the message and the
        exception string — carry ids only, because a raise that quotes the
        buffer into its own message is a different control (files/10 §3's
        ``SafeError`` boundary, and CLAUDE.md invariant 6 for the log path).
        """
        payload = bytes(held.view())
        return {
            "message": "decode failed in the window scorer",
            "logentry": {"message": "decode failed: %s", "params": ["work-1"]},
            "request": {"data": payload.decode("latin-1"), "headers": {"x-work-id": "work-1"}},
            "extra": {"window": payload.decode("latin-1"), "session_id": "s-1"},
            "tags": {"window": payload.hex(), "route": "voice"},
            "breadcrumbs": {
                "values": [{"message": "window scored", "data": {"window": payload.hex()}}]
            },
            "exception": {
                "values": [
                    {
                        "value": "cannot decode the window",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "observers/buffer.py",
                                    "vars": {"window": repr(payload)},
                                }
                            ]
                        },
                    }
                ]
            },
        }

    def test_a_report_raised_over_a_live_buffer_carries_none_of_it(
        self, buffer: LockedBuffer
    ) -> None:
        buffer.write(SYNTHETIC_MARKER * (CAPACITY_BYTES // len(SYNTHETIC_MARKER)))
        scrubbed = scrub_event(self._event_holding_the_buffer(buffer), None)
        serialised = json.dumps(scrubbed, default=repr)
        assert SYNTHETIC_MARKER.decode() not in serialised
        assert SYNTHETIC_MARKER.hex() not in serialised
        oversized = [
            value
            for value in _walk_values(scrubbed)
            if isinstance(value, str | bytes | bytearray) and len(value) > MAX_PAYLOAD_VALUE_BYTES
        ]
        assert oversized == [], f"{len(oversized)} value(s) larger than 1 KB survived"

    def test_the_same_report_unscrubbed_still_carries_the_marker(
        self, buffer: LockedBuffer
    ) -> None:
        """The control: without the hook the search finds what it looks for."""
        buffer.write(SYNTHETIC_MARKER * (CAPACITY_BYTES // len(SYNTHETIC_MARKER)))
        raw = copy.deepcopy(self._event_holding_the_buffer(buffer))
        serialised = json.dumps(raw, default=repr)
        assert SYNTHETIC_MARKER.decode() in serialised
        assert any(
            isinstance(value, str) and len(value) > MAX_PAYLOAD_VALUE_BYTES
            for value in _walk_values(raw)
        )

    def test_the_buffer_never_puts_its_contents_in_a_repr(self, buffer: LockedBuffer) -> None:
        """A repr is how a buffer reaches a traceback, a log and a report."""
        buffer.write(SYNTHETIC_MARKER * 8)
        rendered = f"{buffer!r} {buffer!s}"
        assert SYNTHETIC_MARKER.decode() not in rendered
        assert "LockedBuffer" in rendered
        assert str(buffer.capacity) in rendered


class TestPtraceIsRefused:
    """files/10 §9.1 invariant 28 — ``process_hardening_guard``.

    files/10 §3: *"Without ``kernel.yama.ptrace_scope=1``, ``/proc/pid/mem``
    reads the buffer regardless of every control above."* The tracer in
    ``memory_hygiene_children.py`` drops its effective capabilities first, so
    it models the attacker invariant 28 describes — a process in a container
    that had ``CAP_SYS_PTRACE`` dropped — rather than root, which can attach to
    anything.

    Platform dependence: ``prctl(PR_SET_DUMPABLE)`` and ``/proc/<pid>/mem``
    are Linux; ``kernel.yama.ptrace_scope`` is a Linux Security Module that
    this container does not carry at all, which
    :meth:`test_the_yama_setting_is_read_and_stated` asserts rather than
    assumes.
    """

    def _probe(self, mode: str, tmp_path: Path) -> dict[str, Any]:
        completed = _run_child("tracer", mode, tmp_path)
        assert completed.returncode == 0, completed.stderr
        report: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
        return report

    def test_the_yama_setting_is_read_and_stated(self) -> None:
        scope = yama_ptrace_scope()
        if YAMA_PTRACE_SCOPE_PATH.is_file():
            assert scope == int(YAMA_PTRACE_SCOPE_PATH.read_text(encoding="utf-8").strip())
        else:
            assert scope is None, (
                "yama_ptrace_scope must report None where the LSM is absent, "
                "not a number nobody set"
            )

    def test_a_hardened_process_denies_attach(self, tmp_path: Path) -> None:
        report = self._probe("hardened", tmp_path)
        assert report["attach_errno"] == 1, "PTRACE_ATTACH was not refused with EPERM"

    def test_the_marker_cannot_be_read_out_of_a_hardened_process(self, tmp_path: Path) -> None:
        report = self._probe("hardened", tmp_path)
        assert report["marker_found"] is False
        assert report["mem_errno"] != 0, "/proc/<pid>/mem opened on a hardened process"

    def test_an_unprotected_child_permits_attach(self, tmp_path: Path) -> None:
        """The control. Without it, ``EPERM`` might be the container's doing."""
        scope = yama_ptrace_scope()
        if scope is not None and scope > 1:
            assert YAMA_PTRACE_SCOPE_PATH.read_text(encoding="utf-8").strip() == str(scope)
            return
        report = self._probe("unprotected", tmp_path)
        assert report["attach_errno"] == 0, (
            "an unprotected child refused attach too, so the hardened refusal "
            "above is the platform's doing rather than the code's"
        )

    def test_an_unprotected_child_hands_the_marker_over(self, tmp_path: Path) -> None:
        """mlock and ``MADV_DONTDUMP`` do not close this door — only the
        process control does, which is exactly what files/10 §3 says."""
        scope = yama_ptrace_scope()
        if scope is not None and scope > 1:
            assert YAMA_PTRACE_SCOPE_PATH.read_text(encoding="utf-8").strip() == str(scope)
            return
        report = self._probe("unprotected", tmp_path)
        assert report["mem_errno"] == 0
        assert report["marker_found"] is True


class TestTheHardeningPrimitivesThemselves:
    """The two controls' own contracts, at the boundary each can be tested from.

    ``harden_process`` lowers ``RLIMIT_CORE``'s **hard** limit, which nothing
    can raise again, so it is exercised in a child that exits cleanly rather
    than inside pytest: running it here would leave every core control above
    unable to produce a core and would turn their assertions vacuous. The
    reversible half — ``prctl(PR_SET_DUMPABLE)`` — is exercised in process and
    restored, which is safe because the kernel resets dumpability across
    ``execve`` (asserted below, since the safety of the restore depends on it).
    """

    def test_the_hardening_report_states_what_the_kernel_ended_up_holding(
        self, tmp_path: Path
    ) -> None:
        completed = _run_child("report", "hardened", tmp_path)
        assert completed.returncode == 0, completed.stderr
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        assert report["core_limit"] == [0, 0]
        assert report["dumpable"] == 0
        assert report["core_pattern"] == CORE_PATTERN_PATH.read_text(encoding="utf-8").strip()
        assert report["yama_ptrace_scope"] == yama_ptrace_scope()
        assert SYNTHETIC_MARKER.decode() not in report["rendered"]

    def test_dumpability_does_not_survive_an_exec(self, tmp_path: Path) -> None:
        """Why the in-process test below is safe, as an assertion.

        A non-dumpable pytest process that leaked the setting into its
        children would silently disarm the core controls above.
        """
        try:
            assert deny_ptrace_attach() == 0
            completed = _run_child("report", "hardened", tmp_path)
            assert completed.returncode == 0, completed.stderr
        finally:
            _restore_dumpable()
        assert _dumpable() == 1

    def test_deny_ptrace_attach_reads_its_own_result_back(self) -> None:
        try:
            assert deny_ptrace_attach() == 0
            assert _dumpable() == 0
        finally:
            _restore_dumpable()
        assert _dumpable() == 1

    def test_prctl_raises_rather_than_returning_a_failure(self) -> None:
        """A control that returned -1 quietly would read as applied."""
        with pytest.raises(ProcessHardeningError):
            _prctl(_UNKNOWN_PRCTL_OPTION, 0)

    def test_a_piped_core_pattern_is_reported_as_a_reason(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pattern = tmp_path / "core_pattern"
        pattern.write_text("|/usr/lib/systemd/systemd-coredump %P\n", encoding="utf-8")
        monkeypatch.setattr("voice_clips.process_hardening.CORE_PATTERN_PATH", pattern)
        environment = core_dump_environment()
        assert environment.writes_a_core_beside_the_process is False
        assert "pipes to a handler" in environment.reason

    def test_an_absolute_core_pattern_is_reported_as_a_reason(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pattern = tmp_path / "core_pattern"
        pattern.write_text("/var/crash/core.%p\n", encoding="utf-8")
        monkeypatch.setattr("voice_clips.process_hardening.CORE_PATTERN_PATH", pattern)
        assert "absolute path" in core_dump_environment().reason

    def test_a_zero_hard_limit_is_reported_as_a_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "voice_clips.process_hardening.resource.getrlimit", lambda which: (0, 0)
        )
        environment = core_dump_environment()
        assert environment.writes_a_core_beside_the_process is False
        assert "hard limit is 0" in environment.reason

    def test_an_unreadable_core_pattern_is_reported_rather_than_raised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr("voice_clips.process_hardening.CORE_PATTERN_PATH", tmp_path / "absent")
        environment = core_dump_environment()
        assert environment.pattern == ""
        assert "unreadable" in environment.reason


class TestTheLockedBufferRefusals:
    """Every refusal the buffer owes its callers, each with its own case."""

    def test_a_non_positive_capacity_is_refused(self) -> None:
        with pytest.raises(LockedBufferError):
            LockedBuffer(0)

    def test_a_non_positive_window_is_refused(self) -> None:
        with pytest.raises(LockedBufferError):
            LockedBuffer.for_window(seconds=0.0, sample_rate_hz=16000)

    def test_a_failing_mlock_is_a_refusal_not_a_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A region the kernel would not lock must not exist at all."""

        class _RefusingLibc:
            def __getattr__(self, name: str) -> Any:
                return lambda *arguments: -1 if name == "mlock" else 0

        monkeypatch.setattr("voice_clips.locked_buffer._libc", _RefusingLibc)
        with pytest.raises(RegionLockFailedError):
            LockedBuffer(CAPACITY_BYTES)

    def test_more_bytes_than_the_region_holds_are_refused(self, buffer: LockedBuffer) -> None:
        with pytest.raises(BufferOverflowError):
            buffer.write(b"x" * (buffer.capacity + 1))
        assert buffer.length == 0

    def test_the_region_is_released_once_and_stays_released(self) -> None:
        held = LockedBuffer(CAPACITY_BYTES)
        held.write(SYNTHETIC_MARKER)
        held.close()
        held.close()
        assert held.closed is True
        with pytest.raises(BufferClosedError):
            held.view()
        with pytest.raises(BufferClosedError):
            _ = held.address

    def test_the_context_manager_closes_and_zeroes(self) -> None:
        with LockedBuffer(CAPACITY_BYTES) as held:
            held.write(SYNTHETIC_MARKER)
            assert held.length == len(SYNTHETIC_MARKER)
        assert held.closed is True

    def test_the_written_length_is_reported(self, buffer: LockedBuffer) -> None:
        buffer.write(SYNTHETIC_MARKER)
        assert buffer.length == len(SYNTHETIC_MARKER)
        assert buffer.capacity % PAGE_SIZE == 0


def _walk_values(value: Any) -> Iterator[Any]:
    """Every leaf in a nested report payload."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_values(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value
