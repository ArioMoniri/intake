"""The tool registry, and the gate that keeps it at six (invariant 9).

files/03 §4.2: *"The Talker has **exactly six tools**; a test introspects the
registered tool list and fails on any addition"*, and the negative half —
*"The Talker has **no** tools for: setting triage, editing slots, choosing
protocols, reading records, writing notes, sharing, or ending the session."*

The registry itself is deliberately dumb: it maps names to handlers and can be
sealed. The invariant lives in :func:`assert_six_tool_surface`, which is a
**set equality**, not a subset check — a missing tool is as much a defect as an
extra one, because a Talker that cannot cancel Work leaves the declared
``cancelled`` state unreachable (files/12 §7.1).

Separating the two is what lets the gate be tested for its ability to fail: the
suite builds synthetic registries of seven and five and asserts the gate names
the difference, then runs the same gate over the real
:func:`intake_voice_runtime.talker.tools.build_talker_tools` output.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from intake_voice_runtime.metrics import TALKER_TOOL_CALLS_TOTAL

__all__ = ["TALKER_TOOLS", "ToolRegistry", "ToolSurfaceError", "assert_six_tool_surface"]

#: The surface, verbatim from files/03 §4.2 and ADR-009. Six names, no more.
TALKER_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "protocol_next",
        "submit_utterance",
        "cancel_work",
        "request_repeat_or_clarify",
        "patient_memory",
        "respond_permission",
    }
)


class ToolSurfaceError(RuntimeError):
    """The registered tool surface is not the six of invariant 9."""


class ToolRegistry:
    """Name → handler, sealable. Counts every call by tool name."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._sealed = False

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    @property
    def sealed(self) -> bool:
        return self._sealed

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        if self._sealed:
            raise ToolSurfaceError(
                f"the Talker tool surface is sealed; {name!r} cannot be added at "
                "runtime (CLAUDE.md invariant 9)"
            )
        if name in self._handlers:
            raise ToolSurfaceError(f"tool {name!r} is already registered")
        self._handlers[name] = handler

    def seal(self) -> None:
        self._sealed = True

    def handler(self, name: str) -> Callable[..., Any]:
        """The handler, wrapped so ``talker_tool_calls_total`` sees every call."""
        inner = self._handlers[name]

        def counted(*args: Any, **kwargs: Any) -> Any:
            TALKER_TOOL_CALLS_TOTAL.labels(tool=name).inc()
            return inner(*args, **kwargs)

        counted.__name__ = inner.__name__
        counted.__doc__ = inner.__doc__
        counted.__wrapped__ = inner  # type: ignore[attr-defined]
        return counted


def assert_six_tool_surface(registry: ToolRegistry) -> None:
    """Set equality against :data:`TALKER_TOOLS`. Both directions are errors."""
    extra = sorted(registry.names - TALKER_TOOLS)
    missing = sorted(TALKER_TOOLS - registry.names)
    if extra or missing:
        raise ToolSurfaceError(
            "the Talker must register exactly the six tools of CLAUDE.md invariant 9 "
            f"(extra: {extra or 'none'}; missing: {missing or 'none'})"
        )
