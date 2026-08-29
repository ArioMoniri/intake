/**
 * INT-246 — the probe reports DETAIL, not a bare null.
 *
 * The incident this issue closes: the SSH tunnel to the speech box died,
 * `reachableAsrBaseUrl()` returned null, the typed steps took over silently,
 * and hours went into "the voice UI is not implemented" when the voice UI was
 * fine. A null cannot say which bases were tried or how each one failed, so
 * nothing downstream could say it either.
 *
 * `probeReachability` is that missing detail: every candidate in order, and
 * for each one whether it answered, timed out, refused the connection, or
 * answered with a non-2xx status. `reachableBaseUrl` keeps its exact
 * signature on top of it — existing callers are untouched.
 *
 * The no-hammering property is pinned here too: the walk stops at the first
 * lane that answers, and a dead host is probed once per call, never retried.
 */
import { describe, expect, it, vi } from "vitest";

import { probeHealth, probeReachability, reachableBaseUrl } from "./hosts";

const OK = { ok: true, status: 200 } as unknown as Response;

function answering(...upBases: string[]): typeof fetch {
  return vi.fn(async (url: RequestInfo | URL) =>
    upBases.some((base) => String(url).startsWith(base))
      ? OK
      : Promise.reject(new TypeError("Network request failed")),
  ) as unknown as typeof fetch;
}

/** A host that accepts the socket and then says nothing — the dead tunnel. */
const silent: typeof fetch = (_url, init) =>
  new Promise((_resolve, reject) => {
    const signal = (init as RequestInit | undefined)?.signal;
    signal?.addEventListener("abort", () => reject(new Error("aborted")));
  });

describe("probeReachability (INT-246: which bases, and how each failed)", () => {
  it("names every candidate it tried when nothing answers", async () => {
    const report = await probeReachability(["http://10.0.0.9:8802", "http://127.0.0.1:8802"], {
      fetchImpl: answering(),
    });
    expect(report.base).toBeNull();
    expect(report.probes.map((p) => p.base)).toEqual([
      "http://10.0.0.9:8802",
      "http://127.0.0.1:8802",
    ]);
  });

  it("distinguishes a refused connection from a timeout", async () => {
    const refused = await probeReachability(["http://127.0.0.1:8802"], {
      fetchImpl: answering(),
    });
    expect(refused.probes[0].failure).toEqual({ kind: "refused" });

    const timedOut = await probeReachability(["http://127.0.0.1:8802"], {
      fetchImpl: silent,
      timeoutMs: 5,
    });
    expect(timedOut.probes[0].failure).toEqual({ kind: "timeout", timeoutMs: 5 });
  });

  it("reports a served-but-unhealthy host as its status, not as unreachable", async () => {
    const fetchImpl = vi.fn(
      async () => ({ ok: false, status: 503 }) as unknown as Response,
    ) as unknown as typeof fetch;
    const report = await probeReachability(["http://127.0.0.1:8802"], { fetchImpl });
    expect(report.base).toBeNull();
    expect(report.probes[0].failure).toEqual({ kind: "status", status: 503 });
  });

  it("stops at the first lane that answers — no hammering past a hit", async () => {
    const fetchImpl = answering("http://127.0.0.1:8802");
    const report = await probeReachability(["http://127.0.0.1:8802", "http://10.0.0.9:8802"], {
      fetchImpl,
    });
    expect(report.base).toBe("http://127.0.0.1:8802");
    expect(report.probes).toEqual([{ base: "http://127.0.0.1:8802", failure: null }]);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("probes each dead candidate exactly once per call — no retry loop", async () => {
    const fetchImpl = answering();
    await probeReachability(["http://10.0.0.9:8802", "http://127.0.0.1:8802"], { fetchImpl });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("an empty candidate list is a report with nothing tried, not a crash", async () => {
    expect(await probeReachability([], { fetchImpl: answering() })).toEqual({
      base: null,
      probes: [],
    });
  });
});

describe("the existing callers are untouched", () => {
  it("reachableBaseUrl still answers with a base or null", async () => {
    const fetchImpl = answering("http://127.0.0.1:8802");
    expect(
      await reachableBaseUrl(["http://10.0.0.9:8802", "http://127.0.0.1:8802"], { fetchImpl }),
    ).toBe("http://127.0.0.1:8802");
    expect(await reachableBaseUrl(["http://10.0.0.9:8802"], { fetchImpl: answering() })).toBeNull();
  });

  it("probeHealth still answers true/false", async () => {
    expect(
      await probeHealth("http://127.0.0.1:8802", { fetchImpl: answering("http://127.0.0.1") }),
    ).toBe(true);
    expect(await probeHealth("http://127.0.0.1:8802", { fetchImpl: answering() })).toBe(false);
  });
});
