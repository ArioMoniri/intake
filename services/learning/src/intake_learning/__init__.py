"""INT-172 — ``services/learning``: Loop 2, and why it cannot apply anything.

files/09 §4 describes a weekly **Inspector → Architect** pipeline over
de-identified aggregates that emits **proposals, never direct changes**.
CLAUDE.md invariant 12 states the same thing as a prohibition and names the
six subjects it covers: red-flag levels, instruments, consent texts, the
Talker tool list, PolicyGuard and profile routing.

Nothing is re-exported here. Import the module you mean — each one's docstring
carries the part of the boundary it holds up, and a star-import would make it
easy to reach the proposal schema without reading why it looks the way it
does. The modules, in the order they run:

- :mod:`intake_learning.inspector` — reads
  :class:`~intake_platform.analytics.Measurement` values from INT-171 and
  nothing else, and issues :class:`~intake_learning.inspector.Finding` values
  through a sealed constructor.
- :mod:`intake_learning.architect` — applies files/09 §4's thresholds. Three
  are stated by the blueprint; the fourth is not, and the constructor a
  scheduled run would use raises rather than choosing it.
- :mod:`intake_learning.proposals` — the closed vocabulary of things a
  proposal may name. No member carries a triage level or a path.
- :mod:`intake_learning.evidence` — ids, counts and citations, re-gated
  through INT-171's k floor on the way in.
- :mod:`intake_learning.signing` — HMAC-SHA256 over the canonical digest, with
  the key handed in rather than fetched.
- :mod:`intake_learning.publisher` — the open-not-merge PR request, as data.
- :mod:`intake_learning.app` — the invariant-15 shell.

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16.
"""

from __future__ import annotations

__version__ = "0.1.0"
