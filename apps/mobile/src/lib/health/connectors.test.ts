import { describe, expect, it } from "vitest";

import { setLocale } from "../i18n";
import { expoGoStub, unsupportedConnector } from "./expoGoStub";
import { NBSP } from "./format";
import { createHealthConnectConnector, type HealthConnectApi } from "./healthConnectConnector";
import { createHealthKitConnector, type HealthKitApi } from "./healthKitConnector";
import type { HealthRange } from "./types";

const range: HealthRange = {
  startISO: "2026-08-21T00:00:00.000Z",
  endISO: "2026-08-28T10:00:00.000Z",
};

describe("expoGoStub — honest about the Expo Go limitation", () => {
  it("always reports needs_dev_build", async () => {
    await expect(expoGoStub.available()).resolves.toEqual({ status: "needs_dev_build" });
  });

  it("refuses to pretend it can read (no fake data, ever)", async () => {
    await expect(expoGoStub.readSummary(range)).rejects.toThrow();
  });
});

describe("unsupportedConnector", () => {
  it("reports platform_unsupported and refuses reads", async () => {
    await expect(unsupportedConnector.available()).resolves.toEqual({
      status: "platform_unsupported",
    });
    await expect(unsupportedConnector.readSummary(range)).rejects.toThrow();
  });
});

function fakeHealthKitApi(overrides: Partial<HealthKitApi> = {}): HealthKitApi {
  return {
    isAvailable: () => true,
    requestReadAuthorization: () => Promise.resolve(true),
    dailyStepTotals: () => Promise.resolve([{ dateISO: "2026-08-27", count: 8123 }]),
    restingHeartRateBpm: () => Promise.resolve([58, 64]),
    sleepSessions: () => Promise.resolve([{ endDateISO: "2026-08-28", minutes: 390 }]),
    ...overrides,
  };
}

describe("createHealthKitConnector", () => {
  it("a failing native import degrades to needs_dev_build — Expo Go must never crash", async () => {
    const connector = createHealthKitConnector(() =>
      Promise.reject(new Error("Cannot find native module")),
    );
    await expect(connector.available()).resolves.toEqual({ status: "needs_dev_build" });
  });

  it("HealthKit missing on the device is platform_unsupported", async () => {
    const connector = createHealthKitConnector(() =>
      Promise.resolve(fakeHealthKitApi({ isAvailable: () => false })),
    );
    await expect(connector.available()).resolves.toEqual({ status: "platform_unsupported" });
  });

  it("a failed authorization request surfaces permission_denied", async () => {
    const denied = createHealthKitConnector(() =>
      Promise.resolve(fakeHealthKitApi({ requestReadAuthorization: () => Promise.resolve(false) })),
    );
    await expect(denied.available()).resolves.toEqual({ status: "permission_denied" });

    const threw = createHealthKitConnector(() =>
      Promise.resolve(
        fakeHealthKitApi({ requestReadAuthorization: () => Promise.reject(new Error("denied")) }),
      ),
    );
    await expect(threw.available()).resolves.toEqual({ status: "permission_denied" });
  });

  it("reads and formats the summary when authorized", async () => {
    setLocale("tr");
    const connector = createHealthKitConnector(() => Promise.resolve(fakeHealthKitApi()));
    await expect(connector.available()).resolves.toEqual({ status: "ok" });
    const summary = await connector.readSummary(range);
    expect(summary.steps).toEqual([{ dateISO: "2026-08-27", value: `8123${NBSP}adım` }]);
    expect(summary.restingHeartRate).toBe(`58–64${NBSP}atım/dk`);
    expect(summary.sleepHours).toBe(`6,5${NBSP}saat`);
  });
});

function fakeHealthConnectApi(overrides: Partial<HealthConnectApi> = {}): HealthConnectApi {
  return {
    sdkStatus: () => Promise.resolve("available"),
    initialize: () => Promise.resolve(true),
    requestReadPermissions: (types) => Promise.resolve(types),
    dailyStepTotals: () => Promise.resolve([{ dateISO: "2026-08-27", count: 8123 }]),
    restingHeartRateBpm: () => Promise.resolve([58, 64]),
    sleepSessions: () => Promise.resolve([{ endDateISO: "2026-08-28", minutes: 390 }]),
    ...overrides,
  };
}

describe("createHealthConnectConnector", () => {
  it("a failing native import degrades to needs_dev_build", async () => {
    const connector = createHealthConnectConnector(() =>
      Promise.reject(new Error("Cannot find native module")),
    );
    await expect(connector.available()).resolves.toEqual({ status: "needs_dev_build" });
  });

  it("Health Connect app missing or outdated is platform_unsupported", async () => {
    for (const status of ["unavailable", "update_required"] as const) {
      const connector = createHealthConnectConnector(() =>
        Promise.resolve(fakeHealthConnectApi({ sdkStatus: () => Promise.resolve(status) })),
      );
      await expect(connector.available()).resolves.toEqual({ status: "platform_unsupported" });
    }
  });

  it("zero granted read permissions is permission_denied — surfaced, not silent", async () => {
    const connector = createHealthConnectConnector(() =>
      Promise.resolve(fakeHealthConnectApi({ requestReadPermissions: () => Promise.resolve([]) })),
    );
    await expect(connector.available()).resolves.toEqual({ status: "permission_denied" });
  });

  it("reads and formats the summary when granted", async () => {
    setLocale("tr");
    const connector = createHealthConnectConnector(() => Promise.resolve(fakeHealthConnectApi()));
    await expect(connector.available()).resolves.toEqual({ status: "ok" });
    const summary = await connector.readSummary(range);
    expect(summary.steps).toEqual([{ dateISO: "2026-08-27", value: `8123${NBSP}adım` }]);
    expect(summary.restingHeartRate).toBe(`58–64${NBSP}atım/dk`);
    expect(summary.sleepHours).toBe(`6,5${NBSP}saat`);
  });
});
