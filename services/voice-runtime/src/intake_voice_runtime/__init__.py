"""services/voice-runtime — the two-layer voice runtime (ADR-009, files/03 §4).

This package carries Layer A, the Talker: the six-tool boundary, the streaming
PolicyGuard, the safe-insertion-window scheduler and the clip player. Layer B
(the Clinical Backend Agent, its FIFO Work queue and the RED preemption path)
lands with INT-092 and INT-093 behind the ports in
:mod:`intake_voice_runtime.ports`.
"""

from __future__ import annotations

__all__: list[str] = []
