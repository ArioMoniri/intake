/** WebRTC stats parsing (INT-103). The unit conversions are the point. */
import { describe, expect, it } from "vitest";

import { flattenReports, parseTransportStats, type RtcStatsEntry } from "./stats";

const PAIR: RtcStatsEntry = {
  type: "candidate-pair",
  id: "pair-1",
  selected: true,
  state: "succeeded",
  currentRoundTripTime: 0.042,
  localCandidateId: "local-1",
};

const INBOUND: RtcStatsEntry = {
  type: "inbound-rtp",
  kind: "audio",
  jitter: 0.006,
  packetsLost: 12,
  packetsReceived: 988,
};

const OUTBOUND: RtcStatsEntry = { type: "outbound-rtp", kind: "audio", packetsSent: 1000 };

describe("parseTransportStats", () => {
  it("converts seconds to milliseconds for RTT and jitter", () => {
    const sample = parseTransportStats([PAIR, INBOUND, OUTBOUND]);
    expect(sample?.rttMs).toBeCloseTo(42, 6);
    expect(sample?.jitterMs).toBeCloseTo(6, 6);
  });

  it("counts expected packets — received plus lost — as the loss denominator", () => {
    const sample = parseTransportStats([PAIR, INBOUND, OUTBOUND]);
    expect(sample?.packetsLost).toBe(12);
    // 988 received + 1000 sent + 12 lost (lost never arrived, so they are not
    // inside packetsReceived and must be added to the expected total).
    expect(sample?.packetsTotal).toBe(2000);
  });

  it("returns null when ICE has not selected a pair — no reading, not a good one", () => {
    expect(parseTransportStats([INBOUND, OUTBOUND])).toBeNull();
    expect(parseTransportStats([])).toBeNull();
  });

  it("falls back to a nominated succeeded pair when `selected` is absent", () => {
    const nominated: RtcStatsEntry = {
      type: "candidate-pair",
      nominated: true,
      state: "succeeded",
      currentRoundTripTime: 0.1,
    };
    expect(parseTransportStats([nominated, INBOUND])?.rttMs).toBeCloseTo(100, 6);
  });

  it("ignores a nominated pair that has not succeeded", () => {
    const failed: RtcStatsEntry = {
      type: "candidate-pair",
      nominated: true,
      state: "failed",
      currentRoundTripTime: 9,
    };
    expect(parseTransportStats([failed, INBOUND])).toBeNull();
  });

  it("detects a relayed path from relayProtocol", () => {
    const relayed = { ...PAIR, relayProtocol: "tls" };
    expect(parseTransportStats([relayed, INBOUND])?.relayed).toBe(true);
  });

  it("detects a relayed path from the selected local candidate type", () => {
    const local: RtcStatsEntry = { type: "local-candidate", id: "local-1", candidateType: "relay" };
    expect(parseTransportStats([PAIR, local, INBOUND])?.relayed).toBe(true);
  });

  it("reports a direct path as not relayed", () => {
    const local: RtcStatsEntry = { type: "local-candidate", id: "local-1", candidateType: "srflx" };
    expect(parseTransportStats([PAIR, local, INBOUND])?.relayed).toBe(false);
  });

  it("takes the worst jitter across several inbound streams", () => {
    const quiet = { ...INBOUND, jitter: 0.001 };
    const noisy = { ...INBOUND, jitter: 0.02 };
    expect(parseTransportStats([PAIR, quiet, noisy])?.jitterMs).toBeCloseTo(20, 6);
  });

  it("tolerates entries with fields missing", () => {
    const bare: RtcStatsEntry = { type: "candidate-pair", selected: true };
    const sample = parseTransportStats([bare]);
    expect(sample).toEqual({
      rttMs: 0,
      jitterMs: 0,
      packetsLost: 0,
      packetsTotal: 0,
      relayed: false,
    });
  });
});

describe("flattenReports", () => {
  it("merges several report maps and skips undefined ones", () => {
    const first = new Map<string, unknown>([["a", PAIR]]);
    const second = new Map<string, unknown>([["b", INBOUND]]);
    expect(flattenReports([first, undefined, second])).toEqual([PAIR, INBOUND]);
  });

  it("skips values that are not stats entries", () => {
    const report = new Map<string, unknown>([
      ["a", PAIR],
      ["b", null],
      ["c", "text"],
      ["d", { noType: true }],
    ]);
    expect(flattenReports([report])).toEqual([PAIR]);
  });
});
