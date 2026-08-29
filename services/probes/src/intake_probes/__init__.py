"""Synthetic health probes + self-hosting registry + release gate (INT-022).

The registry (observability/registry.yaml) is the data plane of CLAUDE.md
invariant 13: every model/service on the PHI path declares `self_hostable`
and a probe here. The runner executes the probes against injected clients;
the release gate (scripts/release/release_gate.py) blocks when an enabled
`phi_path` component lacks a healthy self-hosted fallback (invariant 19).
"""

from __future__ import annotations
