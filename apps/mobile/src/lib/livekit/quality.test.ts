/** Per-turn quality arithmetic (INT-103). */
import { describe, expect, it } from "vitest";

import { addSample, closeWindow, median, openWindow } from "./quality";
import type { TransportSample } from "./types";

function sample(over: Partial<TransportSample> = {}): TransportSample {
  return { rttMs: 0, jitterMs: 0, packetsLost: 0, packetsTotal: 0, relayed: false, ...over };
}

describe("median", () => {
  it("is zero for an empty window", () => {
    expect(median([])).toBe(0);
  });

  it("takes the lower middle rather than interpolating a value never measured", () => {
    expect(median([10, 20, 30, 40])).toBe(20);
    expect(median([30, 10, 20])).toBe(20);
  });
});

describe("loss is a rate over the turn's own window", () => {
  it("differences cumulative counters instead of inheriting session history", () => {
    // The session has already lost 500 of 10000 packets before this turn.
    let window = openWindow(1, sample({ packetsLost: 500, packetsTotal: 10_000 }));
    window = addSample(window, sample({ packetsLost: 505, packetsTotal: 10_100 }));
    const quality = closeWindow(window);
    // 5 lost out of the 100 that moved during the turn — not 505/10100.
    expect(quality.lossRate).toBeCloseTo(0.05, 6);
  });

  it("reports zero when no packets moved, and says so via samples", () => {
    let window = openWindow(2, sample({ packetsTotal: 100 }));
    window = addSample(window, sample({ packetsTotal: 100 }));
    const quality = closeWindow(window);
    expect(quality.lossRate).toBe(0);
    expect(quality.samples).toBe(1);
  });

  it("clamps a counter reset instead of reporting a negative rate", () => {
    let window = openWindow(3, sample({ packetsLost: 90, packetsTotal: 900 }));
    // An ICE restart resets the counters to a lower value.
    window = addSample(window, sample({ packetsLost: 1, packetsTotal: 10 }));
    expect(closeWindow(window).lossRate).toBe(0);
  });

  it("never exceeds one", () => {
    let window = openWindow(4, sample({ packetsLost: 0, packetsTotal: 0 }));
    window = addSample(window, sample({ packetsLost: 500, packetsTotal: 10 }));
    expect(closeWindow(window).lossRate).toBeLessThanOrEqual(1);
  });
});

describe("an unmeasured window is not a perfect window", () => {
  it("reports zero samples so the caller can tell the zeros apart", () => {
    const quality = closeWindow(openWindow(5, null));
    expect(quality.samples).toBe(0);
    expect(quality.rttMsP50).toBe(0);
    expect(quality.lossRate).toBe(0);
  });
});

describe("relay stickiness (files/03 §4.4b trigger T4)", () => {
  it("one relayed sample marks the whole turn degraded", () => {
    let window = openWindow(6, sample());
    window = addSample(window, sample({ relayed: true }));
    window = addSample(window, sample({ relayed: false }));
    expect(closeWindow(window).relayed).toBe(true);
  });
});

describe("the first sample can serve as the baseline", () => {
  it("adopts it when the turn opened before ICE settled", () => {
    let window = openWindow(7, null);
    window = addSample(window, sample({ packetsLost: 0, packetsTotal: 100 }));
    window = addSample(window, sample({ packetsLost: 10, packetsTotal: 200 }));
    expect(closeWindow(window).lossRate).toBeCloseTo(0.1, 6);
  });
});
