/**
 * The honest stubs (INT-208): Expo Go cannot load native health modules, and
 * unsupported platforms cannot read health data at all. Both say so through
 * the availability status and REFUSE to read — never fake data, never a dead
 * button (the UI renders guidance instead of controls for these states).
 */
import type { HealthConnector } from "./types";

export const expoGoStub: HealthConnector = {
  available: () => Promise.resolve({ status: "needs_dev_build" }),
  readSummary: () =>
    Promise.reject(
      new Error("health data is not readable in Expo Go — a development build is required"),
    ),
};

export const unsupportedConnector: HealthConnector = {
  available: () => Promise.resolve({ status: "platform_unsupported" }),
  readSummary: () => Promise.reject(new Error("health data is not readable on this platform")),
};
