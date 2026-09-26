"""A Prometheus instant-query reader for the ops console (INT-351).

files/08 §0b F1: the browser never names a datasource. The console's panels
are built here, server-side, from PromQL the API itself holds
(:data:`intake_api.admin.ops_console.OPS_QUERIES`) — a caller cannot pass a
query, a host or a datasource through ``/admin/ops``.

Prometheus is internal observability (``infra/docker-compose.obs.yml``), so this
is not vendor egress and does not pass the vendor allow-list; the URL is the
operator's, from ``INTAKE_OPS_PROMETHEUS_URL``, and must be a plain http(s)
origin with no credentials in it. Unset, there is no client and every tile it
would feed reads *unknown* (invariant 17).

**Every failure is one refusal with a machine code** — unreachable, a non-2xx
status, an error body, a body of the wrong shape — never a partial result and
never the server's own error text (which can echo the query).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

__all__ = ["ENV_PROMETHEUS_URL", "PromClient", "PromUnavailable", "Sample", "prom_client_from_env"]

ENV_PROMETHEUS_URL: Final = "INTAKE_OPS_PROMETHEUS_URL"
_TIMEOUT_S: Final = 5.0


class PromUnavailable(Exception):
    """Prometheus could not answer. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Sample:
    labels: Mapping[str, str]
    value: float


def _value(raw: object) -> float | None:
    """One sample value; ``None`` for NaN/Inf — "no observation", never 0."""
    if not isinstance(raw, list) or len(raw) != 2 or not isinstance(raw[1], str):
        raise PromUnavailable("prometheus_bad_response")
    try:
        value = float(raw[1])
    except ValueError:
        raise PromUnavailable("prometheus_bad_response") from None
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class PromClient:
    base_url: str
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout_s: float = _TIMEOUT_S

    def _body(self, expr: str) -> Mapping[str, Any]:
        url = f"{self.base_url.rstrip('/')}/api/v1/query"
        try:
            with httpx.Client(
                transport=self.transport, timeout=self.timeout_s, follow_redirects=False
            ) as client:
                response = client.get(url, params={"query": expr})
        except httpx.HTTPError:
            raise PromUnavailable("prometheus_unreachable") from None
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("status") == "error":
            raise PromUnavailable("prometheus_query_error")
        if response.status_code // 100 != 2:
            raise PromUnavailable(f"prometheus_http_{response.status_code}")
        if not isinstance(body, dict) or body.get("status") != "success":
            raise PromUnavailable("prometheus_bad_response")
        return body

    def vector(self, expr: str) -> tuple[Sample, ...]:
        """An instant vector. Samples whose value is NaN/Inf are dropped."""
        data = self._body(expr).get("data")
        if not isinstance(data, dict) or data.get("resultType") != "vector":
            raise PromUnavailable("prometheus_bad_response")
        result = data.get("result")
        if not isinstance(result, list):
            raise PromUnavailable("prometheus_bad_response")
        samples: list[Sample] = []
        for row in result:
            if not isinstance(row, dict) or not isinstance(row.get("metric"), dict):
                raise PromUnavailable("prometheus_bad_response")
            value = _value(row.get("value"))
            if value is None:
                continue
            labels = {str(k): str(v) for k, v in row["metric"].items() if k != "__name__"}
            samples.append(Sample(labels=labels, value=value))
        return tuple(samples)


def prom_client_from_env(env: Mapping[str, str]) -> PromClient | None:
    """The configured client, ``None`` when unset; a malformed URL raises."""
    raw = env.get(ENV_PROMETHEUS_URL, "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            f"{ENV_PROMETHEUS_URL} must be a plain http(s) origin with no credentials, "
            "query or fragment"
        )
    return PromClient(base_url=raw)
