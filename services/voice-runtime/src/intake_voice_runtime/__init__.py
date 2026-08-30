"""services/voice-runtime — the two-layer voice runtime (ADR-009, files/03 §4).

This package carries Layer A, the Talker: the six-tool boundary, the streaming
PolicyGuard, the safe-insertion-window scheduler and the clip player. Layer B
is the deterministic ``clinical_agent`` FSM (INT-081) and the per-session FIFO
Work queue that serialises every write to it
(:mod:`intake_voice_runtime.work_queue`, INT-092), both reached only through
the ports in :mod:`intake_voice_runtime.ports`. The RED preemption path —
flush, cancel, pre-positioned clip over the data channel — is INT-093.
"""

from __future__ import annotations

__all__: list[str] = []
