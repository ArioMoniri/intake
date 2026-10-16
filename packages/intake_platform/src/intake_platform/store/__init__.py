"""INT-224 — store compliance: the labels are a derivation, not a document.

files/06 §1 row ``STORE`` asks for privacy labels "generated from the single
data inventory so they can never drift from reality". Four modules do that and
nothing else:

- :mod:`~intake_platform.store.facts` — the inventory, both halves: the schema
  annotations of invariant 18, and the flows that have no column (microphone
  audio, health-platform reads, document bytes, crash diagnostics);
- :mod:`~intake_platform.store.taxonomy` — the vendors' published form
  vocabularies, loadable only from a dated, hash-bound verbatim snapshot;
- :mod:`~intake_platform.store.declaration` — facts × taxonomy → form rows,
  refusing any fact the taxonomy does not map;
- :mod:`~intake_platform.store.listing` — listing copy under ``docs/legal``,
  gated for performance claims (invariant 20 / App Review 1.4.1) and for
  `device_functions` claims (invariant 18);
- :mod:`~intake_platform.store.checklist` — the automatable rows, and the rows
  that are blocked because a published vendor requirement may not be recalled;
- :mod:`~intake_platform.store.answers` (INT-482) — the privacy answers in our
  own words, one row per inventory fact, before any vendor vocabulary;
- :mod:`~intake_platform.store.eas_metadata` (INT-482) — ``store.config.json``
  for EAS Metadata, rendered only from served, hash-bound copy.
"""

from __future__ import annotations

__all__: list[str] = []
