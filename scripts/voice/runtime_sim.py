"""INT-094 — `make runtime-sim SCENARIO=<id> PROFILE=<residency_tr|typed>`.

CLAUDE.md names this command; files/03 §7 names what it is: the *"latency
harness with fake clocks (asserts §4.6 invariants without vendors)"*. It runs
one RT scenario against the composed runtime on the shared virtual clock and
prints, per turn, what the run cost server-side beside what files/02 §8.1
publishes as the budget for that profile and network profile.

**It imports the scenario from the test suite on purpose.** The doubles the
scenarios run against live in ``tests/voice`` because CLAUDE.md invariant 17
puts mocks nowhere else, and a harness whose scenario is a *second* copy of the
suite's scenario would report a number nobody asserted. So the budget table,
the scenario catalogue and the report are production code
(``intake_voice_runtime.simulator``) and the drivers are the tests'.

**It never dials anything.** No model, no LiveKit room, no socket — except in
``--measure``, which is opt-in, refuses to run under pytest, and is described
where it is defined.

``--parity`` is INT-096's half: files/03 §4.6 invariant 8 asks that *"the same
simulator scenarios pass on ``typed`` … and ``residency_tr`` with mock
adapters"*, and this flag is that sentence made runnable. It drives the named
scenario on **every** profile the scenario declares and compares the runs with
every transport-specific quantity removed — see
:class:`~intake_voice_runtime.simulator.report.ParityTrace` for what is
compared and why an equality over the whole report would be false rather than
strict. A divergence is printed field by field, because a parity failure that
says only "not equal" is one nobody can act on.

Exit codes: 0 ran · 2 the scenario or profile is not runnable · 3 the lane
probe in ``--measure`` could not reach a service · 4 the profiles diverged.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "voice"))

from intake_voice_runtime.profiles import VoiceProfile  # noqa: E402
from intake_voice_runtime.simulator import (  # noqa: E402
    SCENARIOS,
    NetworkProfile,
    ParityTrace,
    ScenarioNotRunnable,
    render_report,
)

#: The dev TTS ladder's first tier, as `scripts/dev/voice_doctor.py` pins it.
#: `--measure` asks this one lane how long a real short synthesis takes; it is
#: the only leg of the turn this process can measure, and it is a measurement
#: of *this bridge on this day*, never a property of the product (CLAUDE.md
#: invariant 20).
MEASURE_LANES: tuple[tuple[str, int], ...] = (("voxcpm2", 8805), ("freya", 8803))
MEASURE_HOST = "127.0.0.1"
#: Synthetic, non-clinical, and free of numerals (invariant 22).
MEASURE_CORPUS: tuple[str, ...] = (
    "Sentetik birinci cumle.",
    "Sentetik ikinci cumle biraz daha uzun olsun.",
    "Sentetik ucuncu cumle en uzunudur ve birkac kelime daha icerir.",
)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="runtime-sim", description=__doc__)
    parser.add_argument("--scenario", required=True, help="RT-01 … RT-08")
    parser.add_argument("--profile", required=True, choices=[p.value for p in VoiceProfile])
    parser.add_argument(
        "--network",
        default=NetworkProfile.TR_MOBILE_MID_LTE.value,
        choices=[n.value for n in NetworkProfile],
        help="The named network profile the budget is published for (files/02 §8.1).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable report.")
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Also time a real synthesis on the dev TTS ladder. Opt-in, dev only, "
        "never CI: it dials localhost. The figures are of this bridge on this day.",
    )
    parser.add_argument(
        "--parity",
        action="store_true",
        help="Run the scenario on every profile it declares and compare the runs "
        "with transport-specific quantities removed (files/03 §4.6 invariant 8). "
        "Exit 4 on a divergence.",
    )
    return parser.parse_args(argv)


def _measure_tts() -> dict[str, object]:
    """Time one short synthesis per corpus line on the first answering lane."""
    for lane_id, port in MEASURE_LANES:
        base = f"http://{MEASURE_HOST}:{port}"
        timings: list[float] = []
        try:
            # httpx, not urllib: urlopen honours file:/ and any other scheme the
            # URL happens to carry, which is what bandit B310 is about. httpx
            # speaks http/https only, so the class of risk is removed at the
            # call rather than annotated away.
            with httpx.Client(timeout=30.0) as client:
                for text in MEASURE_CORPUS:
                    started = time.perf_counter()
                    response = client.post(f"{base}/synthesize", json={"text": text})
                    response.raise_for_status()
                    timings.append((time.perf_counter() - started) * 1000.0)
                    if not response.content:
                        raise httpx.HTTPError("empty body")
        except (httpx.HTTPError, TimeoutError, OSError):
            continue
        return {
            "lane": lane_id,
            "base": base,
            "corpus": "runtime-sim/synthetic-tr-3",
            "per_line_ms": [round(value, 1) for value in timings],
            "max_ms": round(max(timings), 1),
        }
    raise SystemExit(3)


def _parity(scenario: Any, run_scenario: Any, network: NetworkProfile) -> int:
    """Every profile the scenario declares, compared pairwise against the first.

    Against the first rather than every pair: parity is an equivalence, so a
    divergence anywhere shows up against the reference run, and naming one
    reference keeps the report readable when a third profile is impossible
    anyway (ADR-010 closes the registry at two).
    """
    profiles = scenario.require_runnable()
    reference, *others = profiles
    base = ParityTrace.of(run_scenario(scenario.id, reference, network))
    diverged = False
    print(f"runtime-sim · parity · {scenario.id} · reference={reference.value}")
    for profile in others:
        trace = ParityTrace.of(run_scenario(scenario.id, profile, network))
        lines = base.divergence(trace)
        if not lines:
            print(f"  {profile.value}: identical on step, text, work_id, delivery, hold")
            continue
        diverged = True
        print(f"  {profile.value}: DIVERGED")
        for line in lines:
            print(f"    {line}")
    return 4 if diverged else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    scenario = SCENARIOS.get(args.scenario)
    if scenario is None:
        print(f"runtime-sim: no such scenario {args.scenario!r}; known: {sorted(SCENARIOS)}")
        return 2

    from test_invariants import run_scenario  # noqa: PLC0415 - see the module docstring

    try:
        report = run_scenario(
            args.scenario, VoiceProfile(args.profile), NetworkProfile(args.network)
        )
    except ScenarioNotRunnable as refusal:
        print(f"runtime-sim: {refusal}")
        return 2

    if args.parity:
        return _parity(scenario, run_scenario, NetworkProfile(args.network))

    measured = _measure_tts() if args.measure else None
    if args.json:
        payload = report.model_dump(mode="json")
        payload["measured_tts"] = measured
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(render_report((report,)))
    if measured is not None:
        print(
            "measured TTS lane (dev bridge, this machine, this day — NOT a product "
            f"property):\n  lane={measured['lane']} corpus={measured['corpus']} "
            f"per-line ms={measured['per_line_ms']} max={measured['max_ms']} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
