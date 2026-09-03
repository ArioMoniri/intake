"""INT-150 — Doctor Link: 128-bit token + OTP + expiry + view limit + revoke +
watermark + access log + no-index (files/10 §2 clinicians, §9 `doctor-link`).

The package is split the way the surfaces are:

- :mod:`intake_api.doctor_link.router` — the patient's grants (issue, list,
  mint an opening code, revoke, access log);
- :mod:`intake_api.doctor_link.redeem` — the clinician's redemption, with no
  principal and a token in the body;
- :mod:`intake_api.doctor_link.store` — the durable half (the atomic view
  budget lives there);
- :mod:`intake_api.doctor_link.service` — the volatile half (the shared OTP
  gate and the token routing hint);
- :mod:`intake_api.doctor_link.common` / ``schemas`` — what both share.

The primitives that carry the rules — the 128-bit token, the visit-anchored
expiry and the watermark — live in :mod:`intake_platform.doctor_link`, so the
renderer that stamps a PDF and the route that composes the stamp agree by
construction.
"""

from __future__ import annotations

from intake_api.doctor_link.redeem import public_router
from intake_api.doctor_link.router import router

__all__ = ["public_router", "router"]
