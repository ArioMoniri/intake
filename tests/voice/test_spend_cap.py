"""INT-439 — the monthly elective model-spend cap (00_STATE §3 D19; HB-O8 closed).

Owner decision, 3 Oct 2026: *"make limit 80 dollars"*. Acceptance: an 80 USD
monthly limit on elective model spend (council members, hosted lanes), enforced
by the existing ledger, refusing beyond the limit and warning at 80 %; obligatory
primary extraction never refused; a sourced price book.

Every boundary has its near-miss: 79.99 vs 80.00, 63.99 vs 64.00, the last
second of a UTC month vs the first of the next, an elective vs an obligatory
charge, a reachable vs an unreachable store. No socket is opened: the Redis
store runs over ``fakeredis``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import fakeredis
import pytest
import redis
from intake_platform.cost.caps import Measure, RateRoute
from intake_platform.cost.config import load_cost_config
from intake_platform.cost.spend import (
    MODEL_SPEND_CAP_EVENTS_TOTAL,
    CallUsage,
    InMemorySpendStore,
    MonthlySpendLedger,
    RedisSpendStore,
    SpendReason,
    UnpricedCall,
    lane_rates,
    month_of,
    price_call,
)
from intake_voice_runtime.metering import (
    ChargeClass,
    MeteredComponent,
    SessionLedger,
    SessionMeter,
)
from intake_voice_runtime.metering.ledger import AdmissionReason

REPO = Path(__file__).resolve().parents[2]
CONFIG = load_cost_config(REPO / "infra" / "costs" / "unit-prices.yaml")
RATES = lane_rates(CONFIG)
GPU = RATES[(RateRoute.SELF_HOSTED, "aws", "g6.2xlarge")]
ELEVEN = RATES[(RateRoute.HOSTED, "elevenlabs", "eleven_multilingual_v2")]
MINI = RATES[(RateRoute.HOSTED, "openai", "gpt-4o-mini")]
TRANSCRIBE = RATES[(RateRoute.HOSTED, "openai", "gpt-4o-mini-transcribe")]
MID_OCTOBER = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
SESSION = "55555555-6666-4777-8888-999999999999"


def _ledger(store: InMemorySpendStore | RedisSpendStore | None = None) -> MonthlySpendLedger:
    return MonthlySpendLedger.from_config(
        CONFIG, store or InMemorySpendStore(), wall_clock=lambda: MID_OCTOBER
    )


def _event(name: str) -> float:
    return MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event=name)._value.get()


# --- the committed decision -------------------------------------------------------------


class TestTheOwnersDecision:
    def test_the_cap_is_80_usd_a_month_warning_at_80_percent(self) -> None:
        (cap,) = CONFIG.spend_caps
        assert cap.limit.usd == Decimal(80)
        assert cap.warn_at_usd == Decimal(64)
        assert cap.covers == "elective_model_spend"
        assert "make limit 80 dollars" in cap.limit.source and "D19" in cap.limit.source
        assert cap.limit.as_of.isoformat() == "2026-10-03"

    def test_every_rate_points_at_a_sourced_list_price(self) -> None:
        by_id = {c.component: c for c in CONFIG.components}
        for rate in CONFIG.model_rates:
            for priced_by in rate.charges.values():
                price = by_id[priced_by].price
                assert price.url is not None and price.url.startswith("https://")
                assert price.source and price.as_of is not None

    def test_the_rates_are_the_published_figures(self) -> None:
        # AWS g6.2xlarge us-east-1 on-demand, per host-hour
        assert GPU.prices == {Measure.BUSY_SECONDS: Decimal("0.9776")}
        # ElevenLabs v2 Multilingual, $0.08 per 1K characters
        assert ELEVEN.prices == {Measure.CHARACTERS: Decimal("0.00008")}
        # OpenAI standard tier, per token ($0.15 / $0.60 and $1.25 / $5.00 per 1M)
        assert MINI.prices == {
            Measure.INPUT_TOKENS: Decimal("1.5E-7"),
            Measure.OUTPUT_TOKENS: Decimal("6E-7"),
        }
        assert TRANSCRIBE.prices == {
            Measure.INPUT_TOKENS: Decimal("0.00000125"),
            Measure.OUTPUT_TOKENS: Decimal("0.000005"),
        }

    def test_hosted_tts_has_no_rate_until_it_has_a_list_price(self) -> None:
        assert not any(key[1:] == ("openai", "gpt-4o-mini-tts") for key in RATES)


# --- pricing ---------------------------------------------------------------------------


class TestPricing:
    def test_self_hosted_is_charged_for_the_host_seconds_it_occupied(self) -> None:
        assert price_call(GPU, CallUsage(busy_seconds=Decimal(3600))) == Decimal("0.9776")
        assert price_call(GPU, CallUsage(busy_seconds=Decimal(36))) == Decimal("0.009776")

    def test_tokens_on_a_host_hour_lane_are_unpriced_not_free(self) -> None:
        with pytest.raises(UnpricedCall):
            price_call(GPU, CallUsage(input_tokens=10_000, output_tokens=500))

    def test_input_and_output_tokens_carry_their_own_prices(self) -> None:
        usd = price_call(MINI, CallUsage(input_tokens=1_000_000, output_tokens=1_000_000))
        assert usd == Decimal("0.75")

    def test_near_miss_an_unused_measure_needs_no_price(self) -> None:
        assert price_call(MINI, CallUsage(input_tokens=2_000_000)) == Decimal("0.3")

    def test_hosted_tts_is_charged_per_character(self) -> None:
        assert price_call(ELEVEN, CallUsage(characters=1000)) == Decimal("0.08000")

    def test_a_lane_without_a_rate_is_unpriced_never_zero(self) -> None:
        with pytest.raises(UnpricedCall):
            price_call(None, CallUsage(input_tokens=1))

    def test_negative_usage_is_refused(self) -> None:
        with pytest.raises(ValueError):
            CallUsage(input_tokens=-1)


# --- the month ----------------------------------------------------------------------------


class TestTheMonth:
    def test_the_month_is_the_utc_calendar_month(self) -> None:
        last = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
        assert month_of(last) == "2026-10"
        assert month_of(last + timedelta(seconds=1)) == "2026-11"

    def test_near_miss_istanbul_midnight_is_still_the_utc_month_before(self) -> None:
        istanbul = timezone(timedelta(hours=3))
        assert month_of(datetime(2026, 11, 1, 1, 0, tzinfo=istanbul)) == "2026-10"

    def test_a_naive_clock_is_refused(self) -> None:
        with pytest.raises(ValueError):
            month_of(datetime(2026, 10, 1))  # noqa: DTZ001 — the naive value is the point

    def test_a_new_month_starts_from_zero(self) -> None:
        store = InMemorySpendStore()
        now = [MID_OCTOBER]
        ledger = MonthlySpendLedger.from_config(CONFIG, store, wall_clock=lambda: now[0])
        ledger.record(Decimal(80), ChargeClass.ELECTIVE)
        assert not ledger.admits(ChargeClass.ELECTIVE).admitted
        now[0] = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        assert ledger.admits(ChargeClass.ELECTIVE).admitted


# --- admission and the warning ---------------------------------------------------------------


class TestTheCap:
    def test_elective_work_is_refused_once_the_month_reaches_80(self) -> None:
        ledger = _ledger()
        ledger.record(Decimal(80), ChargeClass.ELECTIVE)
        verdict = ledger.admits(ChargeClass.ELECTIVE)
        assert (verdict.admitted, verdict.reason) == (False, SpendReason.CAP_REACHED)
        assert verdict.spent_usd == Decimal(80)

    def test_near_miss_one_cent_below_the_cap_is_admitted(self) -> None:
        ledger = _ledger()
        ledger.record(Decimal("79.99"), ChargeClass.ELECTIVE)
        assert ledger.admits(ChargeClass.ELECTIVE).reason is SpendReason.WITHIN_CAP

    def test_obligatory_extraction_is_never_refused_past_the_cap(self) -> None:
        ledger = _ledger()
        ledger.record(Decimal(500), ChargeClass.OBLIGATORY)
        assert ledger.admits(ChargeClass.OBLIGATORY).admitted
        assert ledger.admits(ChargeClass.OBLIGATORY).reason is SpendReason.OBLIGATORY

    def test_near_miss_obligatory_spend_still_counts_toward_the_month(self) -> None:
        ledger = _ledger()
        ledger.record(Decimal(80), ChargeClass.OBLIGATORY)
        assert not ledger.admits(ChargeClass.ELECTIVE).admitted

    def test_the_warning_fires_once_at_64(self) -> None:
        ledger = _ledger()
        before = _event("warn")
        ledger.record(Decimal("63.99"), ChargeClass.ELECTIVE)
        assert _event("warn") == before
        ledger.record(Decimal("0.01"), ChargeClass.ELECTIVE)
        assert _event("warn") == before + 1
        ledger.record(Decimal(1), ChargeClass.ELECTIVE)
        assert _event("warn") == before + 1

    def test_no_cap_configured_refuses_elective_work(self) -> None:
        ledger = MonthlySpendLedger(cap=None, store=InMemorySpendStore())
        verdict = ledger.admits(ChargeClass.ELECTIVE)
        assert (verdict.admitted, verdict.reason) == (False, SpendReason.CAP_NOT_CONFIGURED)

    def test_a_negative_record_is_refused(self) -> None:
        with pytest.raises(ValueError):
            _ledger().record(Decimal(-1), ChargeClass.ELECTIVE)

    def test_sub_micro_spend_rounds_up_never_to_zero(self) -> None:
        store = InMemorySpendStore()
        _ledger(store).record(Decimal("0.0000001"), ChargeClass.ELECTIVE)
        assert store.total("2026-10") == 1


# --- one total across workers, and a store that fails --------------------------------------


class _DownRedis(fakeredis.FakeRedis):
    def mget(self, *args: object, **kwargs: object) -> list[object]:
        raise redis.ConnectionError("down")

    def pipeline(self, *args: object, **kwargs: object) -> object:
        raise redis.ConnectionError("down")


class TestTheSharedStore:
    def test_two_workers_count_one_total(self) -> None:
        server = fakeredis.FakeServer()
        one = _ledger(RedisSpendStore(fakeredis.FakeRedis(server=server), deployment="syn"))
        two = _ledger(RedisSpendStore(fakeredis.FakeRedis(server=server), deployment="syn"))
        one.record(Decimal(50), ChargeClass.ELECTIVE)
        two.record(Decimal(30), ChargeClass.OBLIGATORY)
        assert not one.admits(ChargeClass.ELECTIVE).admitted
        assert not two.admits(ChargeClass.ELECTIVE).admitted

    def test_near_miss_another_deployment_is_another_total(self) -> None:
        server = fakeredis.FakeServer()
        a = _ledger(RedisSpendStore(fakeredis.FakeRedis(server=server), deployment="aa"))
        b = _ledger(RedisSpendStore(fakeredis.FakeRedis(server=server), deployment="bb"))
        a.record(Decimal(80), ChargeClass.ELECTIVE)
        assert b.admits(ChargeClass.ELECTIVE).admitted

    def test_a_month_key_expires(self) -> None:
        client = fakeredis.FakeRedis()
        RedisSpendStore(client, deployment="syn").add("2026-10", ChargeClass.ELECTIVE, 5)
        ttl = client.ttl("intake:spend:syn:2026-10:elective")
        assert isinstance(ttl, int) and 0 < ttl <= 62 * 24 * 3600

    def test_an_unreachable_store_refuses_elective_and_admits_obligatory(self) -> None:
        ledger = _ledger(RedisSpendStore(_DownRedis(), deployment="syn"))
        assert ledger.admits(ChargeClass.ELECTIVE).reason is SpendReason.STORE_UNAVAILABLE
        assert ledger.admits(ChargeClass.OBLIGATORY).admitted
        before = _event("store_unavailable")
        assert ledger.record(Decimal(1), ChargeClass.OBLIGATORY) is None
        assert _event("store_unavailable") == before + 1

    def test_a_malformed_counter_reads_as_unavailable(self) -> None:
        client = fakeredis.FakeRedis()
        client.set("intake:spend:syn:2026-10:elective", "not-a-number")
        ledger = _ledger(RedisSpendStore(client, deployment="syn"))
        assert ledger.admits(ChargeClass.ELECTIVE).reason is SpendReason.STORE_UNAVAILABLE

    @pytest.mark.parametrize("bad", ["", "a:b", "a b"])
    def test_a_deployment_id_with_a_separator_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError):
            RedisSpendStore(fakeredis.FakeRedis(), deployment=bad)


# --- the existing ledger enforces it ----------------------------------------------------------


class TestTheSessionLedger:
    def test_elective_extraction_runs_under_the_monthly_cap(self) -> None:
        ledger = SessionLedger(SESSION, spend=_ledger())
        verdict = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE)
        assert (verdict.admitted, verdict.reason) == (True, AdmissionReason.WITHIN_MONTHLY_CAP)

    def test_near_miss_without_the_monthly_ledger_it_is_still_refused(self) -> None:
        verdict = SessionLedger(SESSION).admits(
            MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE
        )
        assert (verdict.admitted, verdict.reason) == (False, AdmissionReason.CAP_UNDECLARED)

    def test_a_reached_month_refuses_every_elective_component(self) -> None:
        spend = _ledger()
        spend.record(Decimal(80), ChargeClass.ELECTIVE)
        ledger = SessionLedger(SESSION, spend=spend)
        for component in MeteredComponent:
            verdict = ledger.admits(component, ChargeClass.ELECTIVE)
            assert verdict.reason is AdmissionReason.MONTHLY_CAP_REACHED
        assert ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.OBLIGATORY).admitted

    def test_an_unreadable_month_is_unknown_spend(self) -> None:
        ledger = SessionLedger(
            SESSION, spend=_ledger(RedisSpendStore(_DownRedis(), deployment="syn"))
        )
        verdict = ledger.admits(MeteredComponent.TTS, ChargeClass.ELECTIVE)
        assert verdict.reason is AdmissionReason.MONTHLY_SPEND_UNKNOWN


class TestTheMeter:
    def test_a_call_is_priced_and_counted_against_the_month(self) -> None:
        spend = _ledger()
        meter = SessionMeter(ledger=SessionLedger(SESSION, spend=spend))
        total = meter.charge_model_call(
            GPU, CallUsage(busy_seconds=Decimal(1800)), ChargeClass.ELECTIVE
        )
        assert total == Decimal("0.4888")

    def test_an_elective_call_on_an_unpriced_lane_raises(self) -> None:
        meter = SessionMeter(ledger=SessionLedger(SESSION, spend=_ledger()))
        with pytest.raises(UnpricedCall):
            meter.charge_model_call(None, CallUsage(input_tokens=5), ChargeClass.ELECTIVE)

    def test_near_miss_an_obligatory_call_on_an_unpriced_lane_is_counted_not_raised(
        self,
    ) -> None:
        meter = SessionMeter(ledger=SessionLedger(SESSION, spend=_ledger()))
        before = _event("unpriced_obligatory")
        assert meter.charge_model_call(None, CallUsage(), ChargeClass.OBLIGATORY) is None
        assert _event("unpriced_obligatory") == before + 1

    def test_a_meter_with_no_monthly_ledger_counts_nothing(self) -> None:
        meter = SessionMeter(ledger=SessionLedger(SESSION))
        assert meter.charge_model_call(GPU, CallUsage(), ChargeClass.ELECTIVE) is None
