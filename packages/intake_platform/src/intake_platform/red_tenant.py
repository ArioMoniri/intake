"""The tenant facts a RED is served under (INT-465).

Two facts about the tenant change what a RED rule set may do, and nothing else
about the tenant does:

- **kind.** ``synthetic`` is the synthetic AWS test host, which serves simulated
  patients only (D18; the owner's decision of 3 Oct 2026). It is the only kind that
  admits the synthetic-only test-key signature (:mod:`intake_platform.red_signature`).
  Every other kind is ``real``, and a real tenant keeps the physician's sign-off
  interlock (HB-C1) unchanged. ``real`` is the default: a tenant that has not said it
  is synthetic is treated as one that may see a real patient.
- **acil_location_tr.** The tenant's own location string for its acil servis, for
  example "zemin kat". files/02 §5.3 makes it a per-tenant configuration field.
  files/04 §8.2 ``tenant_acil_location_string_is_never_defaulted``: where it is unset,
  the ON_SITE segment that carries it is dropped (:mod:`protocols.red_render`), and
  it never falls back to an invented floor, wing or direction. No tenant record holds
  this field yet: files/08 asks for it with a change tier, and that is not built.
  Every caller therefore passes ``None`` today.
- **deployment.** The host this tenant runs on, for example the synthetic AWS host's
  instance id. The test-key signature names the one host it is for, so a synthetic
  tenant on any other host, or one that names no host, refuses it
  (``intake_platform.red_signature``). It is configuration, not attestation: the
  synthetic host's compose file declares it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = ["TenantKind", "TenantRedConfig"]


class TenantKind(enum.StrEnum):
    """Whether this tenant may serve a test-key-signed rule set (INT-465)."""

    SYNTHETIC = "synthetic"
    REAL = "real"


@dataclass(frozen=True)
class TenantRedConfig:
    """The tenant facts a RED depends on. The defaults are the fail-closed ones."""

    kind: TenantKind = TenantKind.REAL
    acil_location_tr: str | None = None
    deployment: str | None = None
