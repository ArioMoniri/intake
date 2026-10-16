"""The ADR-035 guard: who a hosted lane may serve (INT-428).

The owner's decision (2 Oct 2026) relaxes invariant 19 for one population
only, until the GPU lanes are healthy, and the medical challenger review
(finding 12, binding) narrows it to its floor:

- a tenant whose data class is **synthetic** (simulated patients — the stress
  tests run like real patients, but nobody in them exists) may be served by a
  hosted provider, and its traffic leaves as
  ``DataClass.NON_PERSONAL``;
- for a **real_phi** tenant a hosted lane is **unrepresentable** (and a
  ``mock`` lane does not exist for anyone — it is no route at all):
  there is no transfer-basis escape hatch, no DPA that admits one, and no
  object that can carry one — :class:`HostedPermit` and
  :class:`~intake_platform.model_lanes.router.ModelAssignment` refuse to be
  constructed for it (invariant 19).

**The data class is declared, never inferred, and it does not move.** It comes
from ``INTAKE_DEPLOYMENT_DATA_CLASS``; the one value that admits a hosted lane
is the literal ``synthetic``, and unset, misspelt or anything else reads as
``real_phi``. The first control write binds the declared class into the
control record, and from then on a declaration that disagrees with the bound
class reads as ``real_phi`` (:func:`effective_data_class`) — so no redeploy
can turn a deployment that held real patients into a synthetic one.

Synthetic and hosted runs never count as clinical evidence (files/04 §8.3):
see :attr:`~intake_platform.model_lanes.router.ModelAssignment.clinical_evidence`.

**The forward proxy is the synthetic deployment's alone** (INT-442). The
synthetic host's API sits on internal networks only; its one route out is the
default-deny forward proxy rendered from the allow-list's hosted rows
(``infra/staging/egress/squid.conf``), named by ``INTAKE_EGRESS_PROXY_URL``.
:func:`egress_proxy_url` is the only reader of that variable, and it refuses —
the process does not boot — when the variable is set in a deployment that is
not synthetic: a PHI deployment has no vendor row to reach and no business
naming a proxy that leads to one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from intake_platform.egress import DataClass
from intake_platform.model_lanes.model import ProviderId, TenantDataClass

__all__ = [
    "ENV_DEPLOYMENT_DATA_CLASS",
    "ENV_EGRESS_PROXY_URL",
    "EgressProxyRefused",
    "HostedLaneRefused",
    "HostedPermit",
    "TenantDataClass",
    "check_hosted_permitted",
    "deployment_data_class",
    "effective_data_class",
    "egress_proxy_url",
]

ENV_DEPLOYMENT_DATA_CLASS: Final = "INTAKE_DEPLOYMENT_DATA_CLASS"
#: INT-442: the synthetic host's forward proxy (``http://egress-proxy:3128``).
ENV_EGRESS_PROXY_URL: Final = "INTAKE_EGRESS_PROXY_URL"


class EgressProxyRefused(RuntimeError):
    """``INTAKE_EGRESS_PROXY_URL`` is set where it may not be, or is not a bare
    ``http://host:port``. The message names the variable, never its value."""


class HostedLaneRefused(Exception):
    """The guard refused a hosted lane. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def deployment_data_class(env: Mapping[str, str]) -> TenantDataClass:
    """``synthetic`` only for the exact literal; everything else is real PHI."""
    raw = env.get(ENV_DEPLOYMENT_DATA_CLASS, "")
    if raw == TenantDataClass.SYNTHETIC.value:
        return TenantDataClass.SYNTHETIC
    return TenantDataClass.REAL_PHI


def effective_data_class(
    declared: TenantDataClass, bound: TenantDataClass | None
) -> TenantDataClass:
    """The class a decision uses. Unbound: the declaration. Bound: the bound
    class, unless the two disagree — then ``real_phi``, whichever way round."""
    if bound is None or bound is declared:
        return declared
    return TenantDataClass.REAL_PHI


@dataclass(frozen=True)
class HostedPermit:
    """What the guard admits: the provider, and the data class the egress
    policy is told the traffic carries — always ``NON_PERSONAL``, because
    the only tenant a permit exists for is synthetic."""

    provider: ProviderId
    tenant: TenantDataClass
    egress_data_class: DataClass = DataClass.NON_PERSONAL

    def __post_init__(self) -> None:
        if self.tenant is not TenantDataClass.SYNTHETIC:
            raise TypeError("a hosted lane is unrepresentable for a real_phi tenant (ADR-035)")
        if self.egress_data_class is not DataClass.NON_PERSONAL:
            raise TypeError("a hosted lane carries synthetic, non-personal data only")


def check_hosted_permitted(*, data_class: TenantDataClass, provider: ProviderId) -> HostedPermit:
    """Admit a hosted provider for a synthetic tenant, or raise
    :class:`HostedLaneRefused`. There is no other way in."""
    if data_class is not TenantDataClass.SYNTHETIC:
        raise HostedLaneRefused("hosted_lane_real_phi_refused")
    return HostedPermit(provider=provider, tenant=data_class)


def egress_proxy_url(env: Mapping[str, str]) -> str | None:
    """The synthetic deployment's forward proxy, ``None`` when none is named.

    Raises :class:`EgressProxyRefused` when the variable is set in a deployment
    that is not synthetic (INT-442: never in the PHI deployment), or when it is
    anything but ``http://<host>:<port>`` — no credentials, no path, no query.
    The proxy speaks CONNECT on an internal network; TLS runs end to end
    through it, so the scheme to the proxy itself is plain ``http``.
    """
    raw = env.get(ENV_EGRESS_PROXY_URL, "").strip()
    if not raw:
        return None
    if deployment_data_class(env) is not TenantDataClass.SYNTHETIC:
        raise EgressProxyRefused(
            f"{ENV_EGRESS_PROXY_URL} is set in a deployment that is not synthetic; the "
            "forward proxy belongs to the synthetic deployment only (INT-442, ADR-035)"
        )
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise EgressProxyRefused(f"{ENV_EGRESS_PROXY_URL} is not a URL") from None
    if (
        parts.scheme != "http"
        or not parts.hostname
        or port is None
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise EgressProxyRefused(f"{ENV_EGRESS_PROXY_URL} must be exactly http://<host>:<port>")
    return f"http://{parts.hostname}:{port}"
