"""INT-240 — services/metrics: catalogue rollups over the event streams.

files/08 §7: *"services/metrics materialises the catalogue in Postgres (hourly
rollups; ClickHouse when volume requires) and serves /admin/metrics/*"*. This
issue lands the satisfaction half of that — the files/08 §4 group F series
(``csat.score``, ``csat.reason``, ``nps.monthly``, ``clinician.pulse``) rolled
up from the ``csat.v1`` / ``nps.v1`` / ``clinician_pulse.v1`` events.

Two rules the modules below encode rather than comment:

- a rollup is a measurement of a NAMED COHORT over a STATED WINDOW, taken on a
  date, and cannot be constructed without all three (invariant 20);
- a rollup carries counts and scores, never a fragment of what anyone wrote
  (invariant 6) — the reader projects through a point type with no text field.
"""

from __future__ import annotations
