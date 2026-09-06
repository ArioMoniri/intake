"""INT-231 — reproducible analysis notebooks under tests.

A notebook here is a deterministic, ordered sequence of pure cells run over a
blinded extract. Determinism is the whole point: the same input must give the
same output byte-for-byte, in CI, on any host — otherwise a "result" is an
accident of when and where it ran. So the runner:

- injects a FROZEN clock (``context["now"]``), so a time-dependent cell is still
  reproducible;
- injects a SEEDED RNG (``context["rng"]``), so a cell that needs randomness
  draws it deterministically;
- BLOCKS the network while cells run, so a notebook that phones home fails
  rather than embedding a remote answer; and
- runs the notebook TWICE and refuses to return unless the two runs agree
  byte-for-byte. This is what actively catches the wall clock and the unseeded
  global RNG: a cell that ignores the injected clock or RNG produces different
  output on the two runs and is refused (:class:`NondeterministicNotebookError`).

A notebook may DECLARE a :class:`ResearchResource` it needs — a held-out
clinical corpus (HB-C10, HB-R1) or a GO-licensed instrument (C-SSRS and WHO-5
are BLOCKED, HB-L2/HB-L3). The runner refuses to run such a notebook until the
resource is supplied (:class:`ResourceUnavailableError`), naming the blocker.
The mechanism ships, the gate fails closed, and no corpus, instrument or figure
is invented (HUMAN_BLOCKERS.md rule 2; invariants 17, 20).
"""

from __future__ import annotations

import hashlib
import json
import random
import socket
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from intake_platform.research.blinding import BlindedExtract

__all__ = [
    "Cell",
    "CellResult",
    "NondeterministicNotebookError",
    "Notebook",
    "NotebookError",
    "NotebookResult",
    "NotebookRunner",
    "ResearchResource",
    "ResourceUnavailableError",
]

#: The runner seeds the per-notebook RNG with a fixed value, so a cell that
#: draws from ``context["rng"]`` is reproducible. Not a secret — it is the
#: opposite of one: a published constant so the result is pinnable.
_RNG_SEED = 231


class NotebookError(Exception):
    """A notebook could not be run to a reproducible result."""


class ResourceUnavailableError(NotebookError):
    """A notebook declared a resource — a held-out corpus or a GO instrument —
    that no human has supplied. Fail closed: the analysis does not run."""


class NondeterministicNotebookError(NotebookError):
    """Two independent runs of the notebook disagreed, or a cell reached for the
    wall clock, the network or the unseeded RNG. The result is not
    reproducible, so none is returned."""


@dataclass(frozen=True)
class ResearchResource:
    """Something a notebook needs before it can produce a valid result.

    ``available`` is ``False`` for everything gated today; a human flips it when
    the resource is actually supplied. ``blocker`` names the HUMAN_BLOCKERS.md
    row that must close first, so a refusal points at the person who can unblock
    it rather than at a missing file.
    """

    kind: str
    resource_id: str
    blocker: str
    available: bool = False


@dataclass(frozen=True)
class Cell:
    """One notebook cell: a pure function of the run context to a
    JSON-serialisable value."""

    name: str
    run: Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class Notebook:
    """An ordered analysis. ``requires`` lists the resources the runner checks
    before it runs a single cell."""

    notebook_id: str
    track: str
    cells: tuple[Cell, ...]
    requires: tuple[ResearchResource, ...] = ()


@dataclass(frozen=True)
class CellResult:
    name: str
    value: Any


@dataclass(frozen=True)
class NotebookResult:
    notebook_id: str
    cells: tuple[CellResult, ...]
    content_sha256: str


@contextmanager
def _network_blocked() -> Any:
    """Refuse every outbound connection while cells run. A notebook that reaches
    the network is not reproducible in CI, and it is also a PHI-egress surface a
    research analysis must never open (invariant 14)."""

    def _refuse(*_args: object, **_kwargs: object) -> Any:
        raise NondeterministicNotebookError(
            "a notebook cell attempted a network connection; analysis notebooks are offline"
        )

    saved_connect = socket.socket.connect
    saved_connect_ex = socket.socket.connect_ex
    saved_create = socket.create_connection
    socket.socket.connect = _refuse  # type: ignore[method-assign]
    socket.socket.connect_ex = _refuse  # type: ignore[method-assign]
    socket.create_connection = _refuse
    try:
        yield
    finally:
        socket.socket.connect = saved_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = saved_connect_ex  # type: ignore[method-assign]
        socket.create_connection = saved_create


class NotebookRunner:
    """Runs a :class:`Notebook` to a reproducible :class:`NotebookResult`."""

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def run(
        self,
        notebook: Notebook,
        *,
        extract: BlindedExtract,
        params: Mapping[str, Any] | None = None,
    ) -> NotebookResult:
        self._check_resources(notebook)
        parameters = dict(params or {})
        first = self._one_pass(notebook, extract, parameters)
        second = self._one_pass(notebook, extract, parameters)
        if first != second:
            raise NondeterministicNotebookError(
                f"notebook {notebook.notebook_id!r} produced different output on two runs; "
                "a cell read the wall clock, the network or the unseeded RNG"
            )
        cells = tuple(CellResult(name=name, value=value) for name, value in first)
        return NotebookResult(
            notebook_id=notebook.notebook_id,
            cells=cells,
            content_sha256=_digest(notebook.notebook_id, first),
        )

    def _check_resources(self, notebook: Notebook) -> None:
        missing = [resource for resource in notebook.requires if not resource.available]
        if missing:
            detail = "; ".join(
                f"{resource.kind}:{resource.resource_id} ({resource.blocker})"
                for resource in missing
            )
            raise ResourceUnavailableError(
                f"notebook {notebook.notebook_id!r} requires resources no human has supplied: "
                f"{detail}. The mechanism ships and fails closed (HUMAN_BLOCKERS.md rule 2); "
                "no corpus, instrument or figure is invented"
            )

    def _one_pass(
        self,
        notebook: Notebook,
        extract: BlindedExtract,
        params: Mapping[str, Any],
    ) -> tuple[tuple[str, Any], ...]:
        context: dict[str, Any] = {
            "extract": extract,
            "now": self._clock,
            # A deterministic, seeded RNG for cells that need randomness — the
            # opposite of a cryptographic use: seeded ON PURPOSE so the result
            # is reproducible (that is the whole contract of this runner).
            "rng": random.Random(_RNG_SEED),  # noqa: S311
            "params": dict(params),
            "results": {},
        }
        outputs: list[tuple[str, Any]] = []
        with _network_blocked():
            for cell in notebook.cells:
                value = cell.run(context)
                context["results"][cell.name] = value
                outputs.append((cell.name, value))
        return tuple(outputs)


def _digest(notebook_id: str, outputs: Sequence[tuple[str, Any]]) -> str:
    payload = {
        "notebook_id": notebook_id,
        "cells": [{"name": name, "value": value} for name, value in outputs],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()
