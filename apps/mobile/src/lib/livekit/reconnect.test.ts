/** Reconnect backoff and the token-staleness decision (INT-103). */
import { describe, expect, it } from "vitest";

import {
  BASE_DELAY_MS,
  MAX_ATTEMPTS,
  MAX_DELAY_MS,
  TOKEN_REFRESH_MARGIN_MS,
  backoffDelayMs,
  nextReconnect,
  tokenNeedsRemint,
} from "./reconnect";

const NOW = 1_000_000;
const FRESH = NOW + 600_000;

describe("backoffDelayMs", () => {
  it("doubles per attempt under full jitter", () => {
    const full = () => 1 - Number.EPSILON;
    expect(backoffDelayMs(1, full)).toBe(BASE_DELAY_MS - 1);
    expect(backoffDelayMs(2, full)).toBe(2 * BASE_DELAY_MS - 1);
    expect(backoffDelayMs(3, full)).toBe(4 * BASE_DELAY_MS - 1);
  });

  it("is uniform in [0, capped] — full jitter, not equal jitter", () => {
    expect(backoffDelayMs(4, () => 0)).toBe(0);
    // attempt 4 caps at 500 * 2^3 = 4000 ms; half of that is 2000 ms.
    expect(backoffDelayMs(4, () => 0.5)).toBe(2000);
  });

  it("never exceeds the ceiling however many attempts have failed", () => {
    for (const attempt of [6, 10, 40]) {
      expect(backoffDelayMs(attempt, () => 1 - Number.EPSILON)).toBeLessThanOrEqual(MAX_DELAY_MS);
    }
  });
});

describe("tokenNeedsRemint", () => {
  it("is false for a token with margin to spare", () => {
    expect(tokenNeedsRemint(FRESH, NOW)).toBe(false);
  });

  it("is true inside the refresh margin, before the token actually dies", () => {
    expect(tokenNeedsRemint(NOW + TOKEN_REFRESH_MARGIN_MS - 1, NOW)).toBe(true);
  });

  it("is true for an already expired token", () => {
    expect(tokenNeedsRemint(NOW - 1, NOW)).toBe(true);
  });
});

describe("nextReconnect", () => {
  it("resumes with a valid token", () => {
    const decision = nextReconnect({
      attempt: 1,
      tokenExpiresAtMs: FRESH,
      nowMs: NOW,
      jitter: () => 0.5,
    });
    expect(decision.action).toBe("resume");
  });

  it("re-mints rather than retrying a token that cannot work", () => {
    const decision = nextReconnect({
      attempt: 1,
      tokenExpiresAtMs: NOW + 1_000,
      nowMs: NOW,
      jitter: () => 0.5,
    });
    expect(decision.action).toBe("remint");
  });

  it("gives up past the attempt ceiling instead of looping forever", () => {
    expect(
      nextReconnect({
        attempt: MAX_ATTEMPTS,
        tokenExpiresAtMs: FRESH,
        nowMs: NOW,
        jitter: () => 0.5,
      }).action,
    ).not.toBe("give_up");
    expect(
      nextReconnect({
        attempt: MAX_ATTEMPTS + 1,
        tokenExpiresAtMs: FRESH,
        nowMs: NOW,
        jitter: () => 0.5,
      }).action,
    ).toBe("give_up");
  });

  it("carries the attempt number and a bounded delay on every decision", () => {
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      const decision = nextReconnect({
        attempt,
        tokenExpiresAtMs: FRESH,
        nowMs: NOW,
        jitter: () => 0.9,
      });
      expect(decision.attempt).toBe(attempt);
      if (decision.action !== "give_up") {
        expect(decision.delayMs).toBeGreaterThanOrEqual(0);
        expect(decision.delayMs).toBeLessThanOrEqual(MAX_DELAY_MS);
      }
    }
  });
});
