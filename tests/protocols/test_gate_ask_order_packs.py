"""INT-375 — the files/13 §9.5 ask-order check over every pack on main.

Each pack is resolved by :func:`protocols.compile.resolve_protocol`, the resolver
``protocols compile`` and every served bundle go through, and the refusals it
returns are read for ``GATE_READS_LATER_SLOT``. Every pack here is L0, so the
resolver refuses each of them for maturity and sign-off anyway; that is why the
check is observed through a spy on the resolver's own call: a pack that never
reached the check (an early exit, or ops that did not apply) would otherwise
pass vacuously, and the spy makes that a failure instead.

Two registries, because a review candidate carries the same id as the served
draft it would replace (INT-353):

- **served** — ``packages/protocols/base`` and ``packages/protocols/specialty``.
  A served specialty draft extends a cluster pack that exists today only as a
  review candidate, so its chain is resolved against that candidate: the chain
  it would compile along once the cluster is signed. Enforced: no finding.
- **review** — ``base`` + ``review/cluster`` + ``review/specialty``. Enforced
  except for the six forward gates main carries today in three candidates,
  pinned below. PR #582 (INT-353) removes all six — the kadın ``reorder`` op
  and the two sibling rebinds — and should empty the set when it lands. Any
  other forward gate, in any candidate, fails here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from protocols.bindings import OperationalTemplate
from protocols.compile import CompileError, LifeThreatSet, RefusalCode, resolve_protocol
from protocols.compile import resolve as resolve_module
from protocols.dsl import Slot
from protocols.gates import LaterSlotRead, gates_reading_later_slots
from protocols.loader import PackRegistry, load_pack

PROTOCOLS = Path(__file__).resolve().parents[2] / "packages" / "protocols"
BASE = PROTOCOLS / "base" / "intake.yaml"
CLUSTERS = PROTOCOLS / "review" / "cluster"
SERVED_SPECIALTY = PROTOCOLS / "specialty"
REVIEW_SPECIALTY = PROTOCOLS / "review" / "specialty"

# (pack that wrote the gate, gated slot, slot the gate reads) — ids only.
KNOWN_REVIEW_FORWARD_GATES = frozenset(
    {
        (
            "specialty.cocuk_enfeksiyon_hastaliklari",
            "sorular.ates_suresi",
            "sorular.ates_oldu",
        ),
        ("specialty.endodonti", "sorular.agri_sonra_suruyor", "sorular.sicak_soguk_agri"),
        (
            "specialty.kadin_hastaliklari_ve_dogum",
            "sorular.gebelikte_kanama",
            "sorular.gebelik_durumu",
        ),
        (
            "specialty.kadin_hastaliklari_ve_dogum",
            "sorular.bebek_hareketlerinde_azalma",
            "sorular.gebelik_durumu",
        ),
        (
            "specialty.kadin_hastaliklari_ve_dogum",
            "sorular.gebelikte_siddetli_bas_agrisi",
            "sorular.gebelik_durumu",
        ),
        (
            "specialty.kadin_hastaliklari_ve_dogum",
            "sorular.gebelikte_gorme_bozuklugu",
            "sorular.gebelik_durumu",
        ),
    }
)


def _registry(specialty: Path) -> PackRegistry:
    registry = PackRegistry()
    for path in [BASE, *sorted(CLUSTERS.glob("*.yaml")), *sorted(specialty.glob("*.yaml"))]:
        registry.add(load_pack(path))
    return registry


SERVED = _registry(SERVED_SPECIALTY)
REVIEW = _registry(REVIEW_SPECIALTY)
SERVED_IDS = [
    "base.intake",
    *(f"specialty.{p.stem}" for p in sorted(SERVED_SPECIALTY.glob("*.yaml"))),
]
REVIEW_IDS = [
    *(f"cluster.{p.stem}" for p in sorted(CLUSTERS.glob("*.yaml"))),
    *(f"specialty.{p.stem}" for p in sorted(REVIEW_SPECIALTY.glob("*.yaml"))),
]


class _Spy:
    """Records what the resolver handed the check and what it found."""

    def __init__(self) -> None:
        self.calls = 0
        self.gated = 0
        self.found: tuple[LaterSlotRead, ...] = ()

    def __call__(self, slots: Iterable[tuple[str, str, Slot]]) -> tuple[LaterSlotRead, ...]:
        rows = tuple(slots)
        self.calls += 1
        self.gated += sum(1 for _, _, s in rows for g in (s.ask_if, s.skip_if) if g is not None)
        self.found = gates_reading_later_slots(rows)
        return self.found


def _forward_gates(
    pack_id: str,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    patch: Callable[[_Spy], None],
) -> tuple[_Spy, set[tuple[str, str, str]]]:
    spy = _Spy()
    patch(spy)
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=pack_id, registry=registry, life_threat=life_threat, template=template
        )
    assert spy.calls == 1, f"{pack_id}: the resolver never reached the ask-order check"
    refused = [r for r in excinfo.value.refusals if r.code is RefusalCode.GATE_READS_LATER_SLOT]
    assert len(refused) == len(spy.found)
    triples = set()
    for refusal, late in zip(refused, spy.found, strict=True):
        owner, reader = refusal.subject.split(":")
        assert reader == late.reader
        triples.add((owner, late.reader, late.read))
    return spy, triples


@pytest.fixture
def patch_check(monkeypatch: pytest.MonkeyPatch) -> Callable[[_Spy], None]:
    def _patch(spy: _Spy) -> None:
        monkeypatch.setattr(resolve_module, "gates_reading_later_slots", spy)

    return _patch


@pytest.mark.parametrize("pack_id", SERVED_IDS)
def test_no_served_pack_has_a_gate_that_reads_a_later_slot(
    pack_id: str,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    patch_check: Callable[[_Spy], None],
) -> None:
    spy, found = _forward_gates(pack_id, SERVED, life_threat, template, patch_check)
    assert found == set()
    assert spy.gated > 0, f"{pack_id}: no gate reached the check"


@pytest.mark.parametrize("pack_id", REVIEW_IDS)
def test_no_review_candidate_adds_a_forward_gate_beyond_the_six_pr_582_removes(
    pack_id: str,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    patch_check: Callable[[_Spy], None],
) -> None:
    spy, found = _forward_gates(pack_id, REVIEW, life_threat, template, patch_check)
    assert found <= KNOWN_REVIEW_FORWARD_GATES
    assert spy.gated > 0, f"{pack_id}: no gate reached the check"


def test_every_pack_on_main_is_swept() -> None:
    assert len(SERVED_IDS) == 1 + len(list(SERVED_SPECIALTY.glob("*.yaml"))) > 1
    assert len(REVIEW_IDS) == len(list(CLUSTERS.glob("*.yaml"))) + len(
        list(REVIEW_SPECIALTY.glob("*.yaml"))
    )
    assert {pack.id for pack in SERVED} >= set(SERVED_IDS)
    assert {pack.id for pack in REVIEW} == set(REVIEW_IDS) | {"base.intake"}
