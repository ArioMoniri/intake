"""The ops collector: GPU host, CI and clip-build counts as catalogued series (INT-351).

The admin ops console (``GET /admin/ops``, rendered by ``apps/admin-web``) reads
Prometheus and the self-hosting registry and nothing else. Three of its tiles
need facts that live outside both — the GPU a model host sees, the latest CI
run on ``main``, the last clip build's hits and syntheses — and this module is
where they are gathered, **server-side, with the collector's own access**:

- ``nvidia-smi`` on the host the collector runs beside (:mod:`.ops_gpu`);
- a read-only GitHub token read from OpenBao, through the egress guard
  (:mod:`.ops_ci`; files/10 §4, invariant 14);
- the textfile ``make clips`` writes (:mod:`voice_clips.metrics`), re-exported
  family by family — only the two clip families, nothing else the file holds.

Every family is catalogued in ``observability/metrics_catalog.yaml``
(invariant 13) and every label is an id (invariant 6).

**Failure clears, it never zeroes (invariant 17).** A host whose query failed
reads ``ops_gpu_host_up 0`` with no utilisation or memory child; a CI read that
failed removes every run series. ``ops_collector_source_up{source}`` says which
source is failing, so the console can tell "the collector is failing" from
"nothing is configured".

**Unconfigured means absent.** No env, no source, no loop: the probes service
serves its contract exactly as before, and the tiles read *unknown*.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol

from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressPolicy,
    EgressPurpose,
    guarded_transport,
    load_allowlist,
)
from prometheus_client import Gauge
from prometheus_client.core import CounterMetricFamily
from prometheus_client.metrics_core import Metric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.registry import Collector

from intake_probes.ops_ci import GITHUB_API, CiSourceError, GithubActionsSource
from intake_probes.ops_gpu import GpuSourceError, NvidiaSmiSource, OpsConfigError

__all__ = [
    "CLIP_FAMILIES",
    "ENV_CLIP_TEXTFILE",
    "ENV_GITHUB_API",
    "ENV_GITHUB_BRANCH",
    "ENV_GITHUB_REPO",
    "ENV_GITHUB_TOKEN_PATH",
    "ENV_GPU_HOST_ID",
    "ENV_INTERVAL_S",
    "OPS_CI_LAST_RUN",
    "OPS_CI_LAST_RUN_UPDATED_SECONDS",
    "OPS_COLLECTOR_SOURCE_UP",
    "OPS_GPU_HOST_UP",
    "OPS_GPU_MEMORY_TOTAL_BYTES",
    "OPS_GPU_MEMORY_USED_BYTES",
    "OPS_GPU_UTILIZATION_RATIO",
    "ClipTextfileCollector",
    "OpsCollector",
    "OpsConfigError",
    "interval_from_env",
    "ops_collector_from_env",
    "run_collector",
]

ENV_GPU_HOST_ID: Final = "INTAKE_OPS_GPU_HOST_ID"
ENV_GITHUB_REPO: Final = "INTAKE_OPS_GITHUB_REPO"
ENV_GITHUB_TOKEN_PATH: Final = "INTAKE_OPS_GITHUB_TOKEN_PATH"  # noqa: S105 — an OpenBao path name
ENV_GITHUB_BRANCH: Final = "INTAKE_OPS_GITHUB_BRANCH"
ENV_GITHUB_API: Final = "INTAKE_OPS_GITHUB_API"
ENV_CLIP_TEXTFILE: Final = "INTAKE_OPS_CLIP_METRICS_TEXTFILE"
ENV_INTERVAL_S: Final = "INTAKE_OPS_COLLECT_INTERVAL_S"
_ENV_ALLOWLIST: Final = "INTAKE_EGRESS_ALLOWLIST_PATH"
_DEFAULT_INTERVAL_S: Final = 60.0
_MIN_INTERVAL_S: Final = 15.0

# --- the families (observability/metrics_catalog.yaml, group "ops") --------------

OPS_GPU_HOST_UP = Gauge(
    "ops_gpu_host_up",
    "1 when the collector's GPU query on this host succeeded, 0 when it failed.",
    ["host_id"],
)
OPS_GPU_UTILIZATION_RATIO = Gauge(
    "ops_gpu_utilization_ratio",
    "GPU utilisation as a ratio (0-1), per host and GPU index.",
    ["host_id", "gpu_index"],
)
OPS_GPU_MEMORY_USED_BYTES = Gauge(
    "ops_gpu_memory_used_bytes",
    "GPU memory in use, in bytes, per host and GPU index.",
    ["host_id", "gpu_index"],
)
OPS_GPU_MEMORY_TOTAL_BYTES = Gauge(
    "ops_gpu_memory_total_bytes",
    "GPU memory visible to the host (the slice or pod quota), in bytes.",
    ["host_id", "gpu_index"],
)
OPS_CI_LAST_RUN = Gauge(
    "ops_ci_last_run",
    "1 for the newest CI run of each workflow on the watched branch; the run's "
    "state is carried in its labels.",
    ["workflow", "branch", "status", "conclusion", "head_sha"],
)
OPS_CI_LAST_RUN_UPDATED_SECONDS = Gauge(
    "ops_ci_last_run_updated_seconds",
    "Unix time the newest CI run of each workflow was last updated.",
    ["workflow", "branch"],
)
OPS_COLLECTOR_SOURCE_UP = Gauge(
    "ops_collector_source_up",
    "1 when the ops collector's last read of a source succeeded, 0 when it failed.",
    ["source"],
)

#: The only families the clip textfile may re-export (voice_clips.metrics).
CLIP_FAMILIES: Final = frozenset({"voice_clip_cache_lookups", "voice_clip_syntheses"})
_CLIP_LABELS: Final[Mapping[str, tuple[str, ...]]] = {
    "voice_clip_cache_lookups": ("outcome",),
    "voice_clip_syntheses": ("gateway", "outcome"),
}


class _Secrets(Protocol):
    def get_kv(self, path: str) -> Mapping[str, Any]: ...


def _default_secrets() -> _Secrets:
    from intake_platform.secrets import SecretsProvider

    return SecretsProvider.from_env()


# --- the clip textfile ------------------------------------------------------------


class ClipTextfileCollector(Collector):
    """Re-export the clip build's two counter families from its textfile.

    A textfile is a file on disk; re-exporting whatever it holds would make it
    a way to publish an uncatalogued series (invariant 13). Only the two clip
    families pass, only with their declared label names, and a missing or
    unreadable file exports nothing — never zeros.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def collect(self) -> Iterator[Metric]:
        try:
            text = self._path.read_text(encoding="utf-8")
            families = list(text_string_to_metric_families(text))
        except (OSError, ValueError):
            return
        for family in families:
            labels = _CLIP_LABELS.get(family.name)
            if family.type != "counter" or labels is None:
                continue
            out = CounterMetricFamily(family.name, family.documentation, labels=list(labels))
            for sample in family.samples:
                if sample.name != f"{family.name}_total" or set(sample.labels) != set(labels):
                    continue
                out.add_metric([sample.labels[name] for name in labels], sample.value)
            yield out


# --- collection ------------------------------------------------------------------


@dataclass
class OpsCollector:
    gpu_host: NvidiaSmiSource | None = None
    ci: GithubActionsSource | None = None
    clip_textfile: Path | None = None
    _clip_registered: bool = field(default=False, repr=False)

    @property
    def configured(self) -> bool:
        return any(source is not None for source in (self.gpu_host, self.ci, self.clip_textfile))

    def _collect_gpu(self) -> str:
        source = self.gpu_host
        if source is None:
            return "unconfigured"
        for family in (
            OPS_GPU_UTILIZATION_RATIO,
            OPS_GPU_MEMORY_USED_BYTES,
            OPS_GPU_MEMORY_TOTAL_BYTES,
        ):
            family.clear()
        try:
            readings = source.read()
        except GpuSourceError as failure:
            OPS_GPU_HOST_UP.labels(host_id=source.host_id).set(0)
            OPS_COLLECTOR_SOURCE_UP.labels(source="gpu_host").set(0)
            return failure.code
        for reading in readings:
            labels = {"host_id": source.host_id, "gpu_index": reading.gpu_index}
            OPS_GPU_UTILIZATION_RATIO.labels(**labels).set(reading.utilization_ratio)
            OPS_GPU_MEMORY_USED_BYTES.labels(**labels).set(reading.memory_used_bytes)
            OPS_GPU_MEMORY_TOTAL_BYTES.labels(**labels).set(reading.memory_total_bytes)
        OPS_GPU_HOST_UP.labels(host_id=source.host_id).set(1)
        OPS_COLLECTOR_SOURCE_UP.labels(source="gpu_host").set(1)
        return "ok"

    def _collect_ci(self) -> str:
        source = self.ci
        if source is None:
            return "unconfigured"
        OPS_CI_LAST_RUN.clear()
        OPS_CI_LAST_RUN_UPDATED_SECONDS.clear()
        try:
            runs = source.read()
        except CiSourceError as failure:
            OPS_COLLECTOR_SOURCE_UP.labels(source="ci").set(0)
            return failure.code
        for run in runs:
            OPS_CI_LAST_RUN.labels(
                workflow=run.workflow,
                branch=run.branch,
                status=run.status,
                conclusion=run.conclusion,
                head_sha=run.head_sha,
            ).set(1)
            OPS_CI_LAST_RUN_UPDATED_SECONDS.labels(workflow=run.workflow, branch=run.branch).set(
                run.updated_at.timestamp()
            )
        OPS_COLLECTOR_SOURCE_UP.labels(source="ci").set(1)
        return "ok"

    def register_clip_textfile(self, registry: Any) -> None:
        """Attach the clip re-export to ``registry`` once (the default one in prod)."""
        if self.clip_textfile is None or self._clip_registered:
            return
        registry.register(ClipTextfileCollector(self.clip_textfile))
        self._clip_registered = True

    def collect_once(self) -> dict[str, str]:
        """One pass over every configured source; what each one answered."""
        return {"gpu_host": self._collect_gpu(), "ci": self._collect_ci()}


async def run_collector(collector: OpsCollector, interval_s: float, stop: asyncio.Event) -> None:
    """Collect every ``interval_s`` until ``stop`` is set. Off the event loop."""
    while not stop.is_set():
        await asyncio.to_thread(collector.collect_once)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            continue


# --- env wiring --------------------------------------------------------------------


def interval_from_env(env: Mapping[str, str]) -> float:
    raw = env.get(ENV_INTERVAL_S, "").strip()
    if not raw:
        return _DEFAULT_INTERVAL_S
    try:
        value = float(raw)
    except ValueError:
        raise OpsConfigError(f"{ENV_INTERVAL_S} must be a number of seconds") from None
    if value < _MIN_INTERVAL_S:
        raise OpsConfigError(
            f"{ENV_INTERVAL_S} below {_MIN_INTERVAL_S:.0f} s would hammer the sources"
        )
    return value


def _token_reader(path: str, secrets: Callable[[], _Secrets]) -> Callable[[], str]:
    def read() -> str:
        try:
            value = secrets().get_kv(path).get("token")
        except Exception:  # noqa: BLE001 — any OpenBao failure is one refusal; nothing echoed
            raise CiSourceError("token_unavailable") from None
        if not isinstance(value, str) or not value.strip():
            raise CiSourceError("token_unavailable")
        return value.strip()

    return read


def _allowlist_path(env: Mapping[str, str]) -> Path:
    raw = env.get(_ENV_ALLOWLIST, "").strip()
    if raw:
        return Path(raw)
    from intake_probes.residency import default_allowlist_path

    return default_allowlist_path()


def ops_collector_from_env(
    env: Mapping[str, str] | None = None,
    *,
    secrets: Callable[[], _Secrets] = _default_secrets,
) -> OpsCollector:
    """Build the collector the environment asks for — and nothing it does not."""
    env = os.environ if env is None else env
    host_id = env.get(ENV_GPU_HOST_ID, "").strip()
    repo = env.get(ENV_GITHUB_REPO, "").strip()
    token_path = env.get(ENV_GITHUB_TOKEN_PATH, "").strip()
    textfile = env.get(ENV_CLIP_TEXTFILE, "").strip()

    gpu = NvidiaSmiSource(host_id=host_id) if host_id else None

    ci: GithubActionsSource | None = None
    if repo or token_path:
        if not (repo and token_path):
            raise OpsConfigError(
                f"{ENV_GITHUB_REPO} and {ENV_GITHUB_TOKEN_PATH} come together: a CI source "
                "without its read-only token would read as 'GitHub is down'"
            )
        policy = EgressPolicy.for_tier(load_allowlist(_allowlist_path(env)), "dev")
        transport = guarded_transport(
            policy,
            # api.github.com is allow-listed for issue_tracking: repository
            # metadata read by the same client class as `gh` (LOOP.md). A run
            # list carries no personal data by construction (ops_ci drops the
            # actor and the commit message before anything is exported).
            EgressContext(purpose=EgressPurpose.ISSUE_TRACKING, data_class=DataClass.NON_PERSONAL),
        )
        ci = GithubActionsSource(
            repo=repo,
            token=_token_reader(token_path, secrets),
            branch=env.get(ENV_GITHUB_BRANCH, "").strip() or "main",
            api_base=env.get(ENV_GITHUB_API, "").strip() or GITHUB_API,
            transport=transport,
        )

    return OpsCollector(gpu_host=gpu, ci=ci, clip_textfile=Path(textfile) if textfile else None)
