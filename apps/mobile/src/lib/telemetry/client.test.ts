/**
 * The crash client (INT-145): inert without a DSN, one envelope item, nothing
 * held on disk. Every dependency is injected, so the suite runs in node.
 */
import { describe, expect, it, vi } from "vitest";

import { createCrashClient, type CrashTransport } from "./client";
import type { TelemetryIdentity } from "./scrub";

const IDENTITY: TelemetryIdentity = {
  appVersion: "0.1.0",
  buildId: "eas-1841",
  sbomDigest: `sha256:${"cd".repeat(32)}`,
  platform: "android",
  osVersion: "15",
  deviceModel: "Pixel8",
  environment: "dev",
  releaseChannel: "preview",
  tenantId: "acibadem-maslak",
};

function spyTransport(ok = true): { transport: CrashTransport; sent: unknown[] } {
  const sent: unknown[] = [];
  return {
    sent,
    transport: {
      send: vi.fn(async (request) => {
        sent.push(request);
        return { ok };
      }),
    },
  };
}

describe("createCrashClient — inert until configured", () => {
  it("is inert with no DSN and names why", () => {
    const { transport, sent } = spyTransport();
    const client = createCrashClient({ dsn: null, identity: IDENTITY, transport });
    expect(client.status()).toEqual({ active: false, reason: "not_configured" });
    expect(sent).toEqual([]);
  });

  it("an inert client sends nothing and says so", async () => {
    const { transport, sent } = spyTransport();
    const client = createCrashClient({ dsn: "", identity: IDENTITY, transport });
    await expect(client.captureCrash({ errorCode: "boot_failed" })).resolves.toBe("inert");
    expect(transport.send).not.toHaveBeenCalled();
    expect(sent).toEqual([]);
  });

  it("a malformed DSN is inert with its own reason, not a fallback host", () => {
    const { transport } = spyTransport();
    const client = createCrashClient({
      dsn: "http://127.0.0.1:8010/7",
      identity: IDENTITY,
      transport,
    });
    expect(client.status()).toEqual({ active: false, reason: "malformed_dsn" });
  });

  it("stays inert when the reporter is switched off, DSN or not", () => {
    const { transport } = spyTransport();
    const client = createCrashClient({
      dsn: "http://f00d@127.0.0.1:8010/7",
      identity: IDENTITY,
      transport,
      enabled: false,
    });
    expect(client.status()).toEqual({ active: false, reason: "disabled" });
  });
});

describe("createCrashClient — what goes on the wire", () => {
  const dsn = "http://f00d@127.0.0.1:8010/7";

  it("posts one envelope to the DSN's endpoint with the GlitchTip auth header", async () => {
    const { transport, sent } = spyTransport();
    const client = createCrashClient({
      dsn,
      identity: IDENTITY,
      transport,
      now: () => 1_772_000_000_000,
    });
    expect(client.status()).toEqual({
      active: true,
      endpoint: "http://127.0.0.1:8010/api/7/envelope/",
    });
    await expect(client.captureCrash({ errorCode: "boot_failed" })).resolves.toBe("sent");
    expect(sent).toHaveLength(1);
    const request = sent[0] as { url: string; headers: Record<string, string>; body: string };
    expect(request.url).toBe("http://127.0.0.1:8010/api/7/envelope/");
    expect(request.headers["Content-Type"]).toBe("application/x-sentry-envelope");
    expect(request.headers["X-Sentry-Auth"]).toContain("sentry_key=f00d");
    expect(request.headers["X-Sentry-Auth"]).toContain("sentry_version=7");
  });

  it("the envelope carries exactly one item and that item is an event", async () => {
    const { transport, sent } = spyTransport();
    const client = createCrashClient({ dsn, identity: IDENTITY, transport });
    await client.captureCrash({ errorCode: "boot_failed" });
    const { body } = sent[0] as { body: string };
    const lines = body.trimEnd().split("\n");
    expect(lines).toHaveLength(3); // envelope header, item header, item body
    expect(JSON.parse(lines[1])).toEqual({ type: "event", content_type: "application/json" });
    // No replay, no screenshot, no attachment item type can ever appear.
    expect(body).not.toContain("replay");
    expect(body).not.toContain("attachment");
    expect(body).not.toContain("screenshot");
  });

  it("a transport failure is reported, never queued to disk", async () => {
    const { transport } = spyTransport(false);
    const client = createCrashClient({ dsn, identity: IDENTITY, transport });
    await expect(client.captureCrash({ errorCode: "boot_failed" })).resolves.toBe("failed");
    // The next capture must not carry the failed one with it: nothing is held.
    await client.captureCrash({ errorCode: "boot_failed" });
    expect(transport.send).toHaveBeenCalledTimes(2);
  });

  it("a throwing transport is swallowed — a crash reporter may never crash", async () => {
    const transport: CrashTransport = {
      send: vi.fn(async () => {
        throw new Error("network down");
      }),
    };
    const client = createCrashClient({ dsn, identity: IDENTITY, transport });
    await expect(client.captureCrash({ errorCode: "boot_failed" })).resolves.toBe("failed");
  });
});
