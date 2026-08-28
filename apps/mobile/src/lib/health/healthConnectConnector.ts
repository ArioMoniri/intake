/**
 * Health Connect connector (INT-200, Android). Same shape as the HealthKit
 * side: the native module (react-native-health-connect, MIT) loads via a
 * dynamic import behind an injectable loader, so Expo Go degrades to
 * `needs_dev_build` and the decision logic is unit-testable with a fake api.
 * Unlike HealthKit, Health Connect reports read grants explicitly, so a
 * refusal surfaces as `permission_denied` rather than empty data.
 *
 * Read-only by design: steps, resting heart rate and sleep — nothing else —
 * and nothing here writes, uploads or persists.
 */
import { getLocale } from "../i18n";
import { buildSummary } from "./format";
import type { HealthConnector, HealthRange } from "./types";

export type HealthRecordType = "Steps" | "RestingHeartRate" | "SleepSession";

export type HealthConnectSdkStatus = "available" | "unavailable" | "update_required";

/** The narrow surface this connector needs from the native module. */
export interface HealthConnectApi {
  sdkStatus(): Promise<HealthConnectSdkStatus>;
  initialize(): Promise<boolean>;
  /** Requests read access and returns the record types actually granted. */
  requestReadPermissions(types: readonly HealthRecordType[]): Promise<readonly HealthRecordType[]>;
  dailyStepTotals(
    range: HealthRange,
  ): Promise<readonly { readonly dateISO: string; readonly count: number }[]>;
  restingHeartRateBpm(range: HealthRange): Promise<readonly number[]>;
  sleepSessions(
    range: HealthRange,
  ): Promise<readonly { readonly endDateISO: string; readonly minutes: number }[]>;
}

const RECORD_TYPES: readonly HealthRecordType[] = ["Steps", "RestingHeartRate", "SleepSession"];

async function loadNativeHealthConnectApi(): Promise<HealthConnectApi> {
  const hc = await import("react-native-health-connect");
  const between = (range: HealthRange) => ({
    operator: "between" as const,
    startTime: range.startISO,
    endTime: range.endISO,
  });
  return {
    sdkStatus: async () => {
      const status = await hc.getSdkStatus();
      if (status === hc.SdkAvailabilityStatus.SDK_AVAILABLE) {
        return "available";
      }
      if (status === hc.SdkAvailabilityStatus.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED) {
        return "update_required";
      }
      return "unavailable";
    },
    initialize: () => hc.initialize(),
    requestReadPermissions: async (types) => {
      const granted = await hc.requestPermission(
        types.map((recordType) => ({ accessType: "read" as const, recordType })),
      );
      return types.filter((recordType) =>
        granted.some(
          (grant) =>
            "accessType" in grant && grant.accessType === "read" && grant.recordType === recordType,
        ),
      );
    },
    dailyStepTotals: async (range) => {
      const groups = await hc.aggregateGroupByPeriod({
        recordType: "Steps",
        timeRangeFilter: between(range),
        timeRangeSlicer: { period: "DAYS", length: 1 },
      });
      return groups.flatMap((group) =>
        group.result.COUNT_TOTAL > 0
          ? [{ dateISO: group.startTime.slice(0, 10), count: group.result.COUNT_TOTAL }]
          : [],
      );
    },
    restingHeartRateBpm: async (range) => {
      const result = await hc.readRecords("RestingHeartRate", { timeRangeFilter: between(range) });
      return result.records.map((record) => record.beatsPerMinute);
    },
    sleepSessions: async (range) => {
      const result = await hc.readRecords("SleepSession", { timeRangeFilter: between(range) });
      return result.records.map((record) => ({
        endDateISO: record.endTime.slice(0, 10),
        minutes: Math.round((Date.parse(record.endTime) - Date.parse(record.startTime)) / 60_000),
      }));
    },
  };
}

export function createHealthConnectConnector(
  loadApi: () => Promise<HealthConnectApi> = loadNativeHealthConnectApi,
): HealthConnector {
  return {
    available: async () => {
      let api: HealthConnectApi;
      try {
        api = await loadApi();
      } catch {
        return { status: "needs_dev_build" };
      }
      try {
        if ((await api.sdkStatus()) !== "available" || !(await api.initialize())) {
          return { status: "platform_unsupported" };
        }
      } catch {
        return { status: "platform_unsupported" };
      }
      try {
        const granted = await api.requestReadPermissions(RECORD_TYPES);
        return { status: granted.length > 0 ? "ok" : "permission_denied" };
      } catch {
        return { status: "permission_denied" };
      }
    },
    readSummary: async (range) => {
      const api = await loadApi();
      const [stepsByDay, restingHeartRateBpm, sleepSessions] = await Promise.all([
        api.dailyStepTotals(range),
        api.restingHeartRateBpm(range),
        api.sleepSessions(range),
      ]);
      return buildSummary({ stepsByDay, restingHeartRateBpm, sleepSessions }, getLocale());
    },
  };
}
