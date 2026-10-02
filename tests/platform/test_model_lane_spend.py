"""INT-439 — every hosted model-lane call is charged against the 80 USD monthly cap.

00_STATE §3 D19 (owner, 3 Oct 2026: *"make limit 80 dollars"*), wired into
INT-428's :func:`~intake_platform.model_lanes.dispatch` (PR #751). A hosted call is
admitted only inside the month's cap and charged after it runs; at the cap it is
refused with a closed code before the provider is asked. Each case has its
near-miss. The provider is a recorded double; no socket opens.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from intake_platform.cost.caps import RateRoute
from intake_platform.cost.spend import ChargeClass, InMemorySpendStore
from intake_platform.model_lanes import (
    Lane,
    LaneRefused,
    LaneResult,
    LaneSetting,
    ModelAssignment,
    ModelLanesControl,
    ProviderId,
    RouteKind,
    dispatch,
)
from intake_platform.model_lanes.hosted import HostedUsage
from model_lanes_kit import NOW, TEST_RATES, build_lanes, spend_gate

HOSTED_LLM = LaneSetting(route="hosted:openai", model="gpt-4o-mini")
HOSTED_TTS = LaneSetting(route="hosted:openai", model="gpt-4o-mini-tts")
MONTH = NOW.strftime("%Y-%m")


def _control(**lanes: LaneSetting) -> ModelLanesControl:
    settings = {lane: LaneSetting() for lane in Lane}
    settings.update({Lane(name): setting for name, setting in lanes.items()})
    return ModelLanesControl(lanes=settings)


def _call(log: list[str], usage: HostedUsage | None = None) -> object:
    def call(assignment: ModelAssignment) -> LaneResult[str]:
        assert assignment.route is not None
        log.append(assignment.route.wire)
        if assignment.route.kind is RouteKind.SELF_HOSTED:
            raise ConnectionError("gpu down")
        return LaneResult("ok", usage or HostedUsage(input_tokens=100, output_tokens=50))

    return call


def _usd(store: InMemorySpendStore) -> Decimal:
    return Decimal(store.total(MONTH)) / Decimal(1_000_000)


class TestEveryHostedCallIsCharged:
    def test_a_hosted_call_is_priced_and_counted_against_the_month(self) -> None:
        store = InMemorySpendStore()
        lanes = build_lanes(
            control=_control(llm=HOSTED_LLM), served=False, spend=spend_gate(store=store)
        )
        log: list[str] = []
        assert dispatch(lanes.router, "llm", tenant_id=None, call=_call(log)) == "ok"
        assert log == ["hosted:openai"]
        # 100 input x 0.01 + 50 output x 0.02 (synthetic test rates)
        assert _usd(store) == Decimal(2)

    def test_near_miss_a_self_hosted_call_is_not_charged_here(self) -> None:
        store = InMemorySpendStore()
        lanes = build_lanes(spend=spend_gate(store=store))

        def call(assignment: ModelAssignment) -> LaneResult[str]:
            return LaneResult("ok", HostedUsage(input_tokens=100))

        assert dispatch(lanes.router, "llm", tenant_id=None, call=call) == "ok"
        assert store.total(MONTH) == 0

    def test_the_fallback_retry_is_charged_too(self) -> None:
        store = InMemorySpendStore()
        lanes = build_lanes(
            control=_control(llm=LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI)),
            spend=spend_gate(store=store),
        )
        log: list[str] = []
        dispatch(lanes.router, "llm", tenant_id=None, call=_call(log), failures=(ConnectionError,))
        assert log == ["self_hosted", "hosted:openai"]
        assert _usd(store) == Decimal(2)


class TestTheCapRefusesHostedCalls:
    def test_a_hosted_call_at_the_cap_is_refused_before_the_provider_is_asked(self) -> None:
        store = InMemorySpendStore()
        gate = spend_gate(store=store)
        gate.ledger.record(Decimal(80), ChargeClass.ELECTIVE)
        lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, spend=gate)
        log: list[str] = []
        with pytest.raises(LaneRefused, match="spend_cap_reached"):
            dispatch(lanes.router, "llm", tenant_id=None, call=_call(log))
        assert log == []

    def test_near_miss_one_cent_below_the_cap_runs(self) -> None:
        gate = spend_gate()
        gate.ledger.record(Decimal("79.99"), ChargeClass.ELECTIVE)
        lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, spend=gate)
        assert dispatch(lanes.router, "llm", tenant_id=None, call=_call([])) == "ok"

    def test_the_call_that_crosses_the_cap_is_the_last_one(self) -> None:
        gate = spend_gate(cap_usd="3")
        lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, spend=gate)
        dispatch(lanes.router, "llm", tenant_id=None, call=_call([]))  # 2 USD
        dispatch(lanes.router, "llm", tenant_id=None, call=_call([]))  # 4 USD, crosses
        with pytest.raises(LaneRefused, match="spend_cap_reached"):
            dispatch(lanes.router, "llm", tenant_id=None, call=_call([]))

    def test_the_fallback_retry_is_refused_at_the_cap(self) -> None:
        gate = spend_gate()
        gate.ledger.record(Decimal(80), ChargeClass.ELECTIVE)
        lanes = build_lanes(
            control=_control(llm=LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI)),
            spend=gate,
        )
        log: list[str] = []
        with pytest.raises(LaneRefused, match="spend_cap_reached"):
            dispatch(
                lanes.router, "llm", tenant_id=None, call=_call(log), failures=(ConnectionError,)
            )
        assert log == ["self_hosted"]


class TestFailClosed:
    def test_a_router_with_no_gate_refuses_every_hosted_call(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, unmetered=True)
        log: list[str] = []
        with pytest.raises(LaneRefused, match="hosted_spend_unmetered"):
            dispatch(lanes.router, "llm", tenant_id=None, call=_call(log))
        assert log == []

    def test_near_miss_a_router_with_no_gate_still_runs_self_hosted(self) -> None:
        lanes = build_lanes(unmetered=True)

        def call(_assignment: ModelAssignment) -> LaneResult[str]:
            return LaneResult("ok")

        assert dispatch(lanes.router, "llm", tenant_id=None, call=call) == "ok"

    def test_a_hosted_lane_with_no_rate_is_refused(self) -> None:
        rates = {k: v for k, v in TEST_RATES.items() if k[2] != "gpt-4o-mini-tts"}
        lanes = build_lanes(
            control=_control(tts=HOSTED_TTS), served=False, spend=spend_gate(rates=rates)
        )
        with pytest.raises(LaneRefused, match="hosted_lane_unpriced"):
            dispatch(lanes.router, "tts", tenant_id=None, call=_call([]))

    def test_near_miss_the_same_lane_with_a_rate_runs(self) -> None:
        store = InMemorySpendStore()
        lanes = build_lanes(
            control=_control(tts=HOSTED_TTS), served=False, spend=spend_gate(store=store)
        )
        usage = HostedUsage(characters=300)
        assert dispatch(lanes.router, "tts", tenant_id=None, call=_call([], usage)) == "ok"
        assert _usd(store) == Decimal(3)

    def test_usage_the_rate_cannot_price_is_a_visible_miss_not_a_crash(self) -> None:
        store = InMemorySpendStore()
        lanes = build_lanes(
            control=_control(llm=HOSTED_LLM), served=False, spend=spend_gate(store=store)
        )
        usage = HostedUsage(characters=10)  # the llm rate prices tokens only
        assert dispatch(lanes.router, "llm", tenant_id=None, call=_call([], usage)) == "ok"
        assert store.total(MONTH) == 0

    def test_the_committed_rates_cover_the_hosted_llm_and_asr_lanes_not_tts(self) -> None:
        from pathlib import Path

        from intake_platform.cost.config import load_cost_config
        from intake_platform.cost.spend import lane_rates

        repo = Path(__file__).resolve().parents[2]
        rates = lane_rates(load_cost_config(repo / "infra" / "costs" / "unit-prices.yaml"))
        hosted = {key[2] for key in rates if key[0] is RateRoute.HOSTED and key[1] == "openai"}
        assert hosted == {"gpt-4o-mini", "gpt-4o-mini-transcribe"}
