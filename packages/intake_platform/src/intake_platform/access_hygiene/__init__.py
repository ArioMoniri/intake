"""INT-366 — the scheduled 60-day auto-disable (files/08 §2.4).

- :mod:`.job` — one idempotent tick: every staff account with no login for
  sixty days is offboarded through the console's own pipeline, audited under
  ``svc:access-hygiene``; the tick refuses when the realm keeps too little
  login history to tell;
- :mod:`.cli` — ``python -m intake_platform.access_hygiene`` (``make
  access-hygiene``), the entry point the scheduler calls. What calls it, and
  the credentials it runs with, are in docs/runbooks/access-review.md.

It lives outside :mod:`intake_platform.admin` on purpose: the job holds an
audit-chain writer, and the console package must never name one (HB-I12,
tests/admin/test_admin_audit.py).
"""

from intake_platform.access_hygiene.job import HYGIENE_ACTOR, HygieneReport, run_auto_disable

__all__ = ["HYGIENE_ACTOR", "HygieneReport", "run_auto_disable"]
