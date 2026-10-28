"""GPU host status for the ops collector (INT-351).

The collector runs **beside** the GPU it reports on — a sidecar on the model
host, with the host's own access to its driver — and asks ``nvidia-smi`` one
documented CSV query. Nothing here dials a cloud API and nothing here is
reachable from a browser: the admin console reads what the collector exported,
through Prometheus.

What one reading carries: the GPU's index, its utilisation, and its memory used
and total. On a MIG slice or a shared pod the *total* is the memory the host is
allotted — the quota the models on it share — which is the figure an operator
needs before loading a fifth model onto a slice that holds four.

**A reading the parser cannot trust is refused, never repaired.** An empty
answer (no GPU visible), a short row, a driver that reports ``[N/A]``, a
percentage above 100 or more memory used than exists all raise
:class:`GpuSourceError`: the collector then marks the host down and clears the
old reading, so the console says *unknown* rather than painting a stale or
invented one (invariant 17).
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 — one fixed argv, no shell, see _run_nvidia_smi
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

__all__ = [
    "ID_SHAPED",
    "NVIDIA_SMI_QUERY",
    "GpuReading",
    "GpuSourceError",
    "NvidiaSmiSource",
    "OpsConfigError",
    "parse_nvidia_smi",
    "require_id",
]

#: The one query, fixed. ``nounits`` makes utilisation a bare percent and
#: memory bare MiB; ``noheader`` drops the column names.
NVIDIA_SMI_QUERY: Final[tuple[str, ...]] = (
    "nvidia-smi",
    "--query-gpu=index,utilization.gpu,memory.used,memory.total",
    "--format=csv,noheader,nounits",
)

#: Label values are ids: lowercase, digits, ``_`` and ``-`` (invariant 6). No
#: dots, so an IP address cannot become a host label; no spaces, so a name
#: cannot either. Every shape here is held with ``fullmatch``: ``$`` also
#: matches before a final newline, so ``match`` would pass ``"gpu-a\n"`` (INT-487).
ID_SHAPED: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_MIB: Final = 1024 * 1024
_TIMEOUT_S: Final = 10.0


class OpsConfigError(ValueError):
    """The collector was configured with a value it will not export."""


class GpuSourceError(Exception):
    """The GPU query failed or answered something unreadable.

    ``code`` is machine-shaped; the driver's own message is not carried, so a
    path or a hostname in it never reaches a log line (invariant 6).
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require_id(value: str, what: str) -> str:
    if not ID_SHAPED.fullmatch(value):
        raise OpsConfigError(f"{what} must be id-shaped ([a-z0-9][a-z0-9_-]{{0,63}})")
    return value


@dataclass(frozen=True)
class GpuReading:
    gpu_index: str
    utilization_ratio: float
    memory_used_bytes: int
    memory_total_bytes: int


def _number(cell: str) -> float:
    try:
        return float(cell)
    except ValueError:
        raise GpuSourceError("malformed_output") from None


def _row(line: str) -> GpuReading:
    cells = [cell.strip() for cell in line.split(",")]
    if len(cells) != 4:
        raise GpuSourceError("malformed_output")
    index, util, used, total = cells
    if not index.isdigit():
        raise GpuSourceError("malformed_output")
    percent, used_mib, total_mib = _number(util), _number(used), _number(total)
    if not 0 <= percent <= 100 or used_mib < 0 or total_mib <= 0 or used_mib > total_mib:
        raise GpuSourceError("implausible_reading")
    return GpuReading(
        gpu_index=index,
        utilization_ratio=round(percent / 100.0, 4),
        memory_used_bytes=int(used_mib) * _MIB,
        memory_total_bytes=int(total_mib) * _MIB,
    )


def parse_nvidia_smi(output: str) -> tuple[GpuReading, ...]:
    """Parse the CSV answer to :data:`NVIDIA_SMI_QUERY`, or refuse it."""
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise GpuSourceError("no_gpu_visible")
    return tuple(_row(line) for line in lines)


def _run_nvidia_smi(argv: Sequence[str]) -> str:
    """Run the fixed query. No shell, a fixed argv, a timeout, output only."""
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603 — fixed argv, no shell
            list(argv),
            capture_output=True,
            check=False,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GpuSourceError("query_failed") from None
    if completed.returncode != 0:
        raise GpuSourceError("query_failed")
    return completed.stdout


@dataclass(frozen=True)
class NvidiaSmiSource:
    """The GPUs visible to this host, under the operator's id for the host."""

    host_id: str
    run: Callable[[Sequence[str]], str] = field(default=_run_nvidia_smi)

    def __post_init__(self) -> None:
        require_id(self.host_id, "the GPU host id")

    def read(self) -> tuple[GpuReading, ...]:
        return parse_nvidia_smi(self.run(NVIDIA_SMI_QUERY))
