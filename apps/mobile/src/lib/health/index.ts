/**
 * Health connector wiring (INT-208): the only file in lib/health that reads
 * the real runtime (Platform, Expo Constants). Everything it composes is
 * pure and node-tested; this switch is mechanical.
 */
import Constants from "expo-constants";
import { Platform } from "react-native";

import { selectConnectorKind } from "./capability";
import { expoGoStub, unsupportedConnector } from "./expoGoStub";
import { createHealthConnectConnector } from "./healthConnectConnector";
import { createHealthKitConnector } from "./healthKitConnector";
import type { HealthConnector } from "./types";

export function getHealthConnector(): HealthConnector {
  const kind = selectConnectorKind({
    os: Platform.OS,
    executionEnvironment: Constants.executionEnvironment ?? "bare",
  });
  switch (kind) {
    case "expo_go_stub":
      return expoGoStub;
    case "healthkit":
      return createHealthKitConnector();
    case "health_connect":
      return createHealthConnectConnector();
    case "unsupported":
      return unsupportedConnector;
  }
}

export { healthConsentOn, selectConnectorKind } from "./capability";
export { lastSevenDayRange, summaryNoteLines } from "./format";
export type {
  HealthAvailability,
  HealthAvailabilityStatus,
  HealthConnector,
  HealthRange,
  HealthSummary,
} from "./types";
