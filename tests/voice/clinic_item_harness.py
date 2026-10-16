"""The clinic-item route as a test double (INT-547).

Like ``red_harness.RecordingClinicNotifier``: it records what the session
raised and has no awaitable member, so it cannot delay anything. ``fail``
makes the next N calls raise, to prove an item is retried, never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from intake_voice_runtime.clinical_agent.clinic_items import ClinicItem


class RouteDown(RuntimeError):
    """The route could not take the item (a synthetic fault)."""


@dataclass
class RecordingClinicItems:
    """Every item the session handed the route, in order."""

    items: list[ClinicItem] = field(default_factory=list)
    calls: int = 0
    fail: int = 0

    def raise_item(self, item: ClinicItem) -> None:
        self.calls += 1
        if self.fail > 0:
            self.fail -= 1
            raise RouteDown("synthetic route fault")
        self.items.append(item)
