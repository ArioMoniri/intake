/**
 * HealthKit connector (INT-208, iOS). The native module is loaded via a
 * DYNAMIC import behind an injectable loader: in Expo Go the import fails
 * and the connector degrades to `needs_dev_build` instead of crashing; in a
 * development build the loader adapts @kingstinct/react-native-healthkit
 * (MIT) to the narrow HealthKitApi this connector needs, so the decision
 * logic stays unit-testable in node with a fake api.
 *
 * Read-only by design: the read scopes are steps, resting heart rate and
 * sleep — nothing else — and nothing here writes, uploads or persists.
 */
import { getLocale } from "../i18n";
import { buildSummary, localISODay } from "./format";
import type { HealthConnector, HealthRange } from "./types";

/** The narrow surface this connector needs from the native module. */
export interface HealthKitApi {
  isAvailable(): boolean;
  /**
   * Resolves true when the authorization request completes. Apple hides
   * READ denial from apps by design, so a completed request means "ok" and
   * a denied read simply yields empty data downstream; only a failed or
   * refused request surfaces as permission_denied.
   */
  requestReadAuthorization(): Promise<boolean>;
  dailyStepTotals(
    range: HealthRange,
  ): Promise<readonly { readonly dateISO: string; readonly count: number }[]>;
  restingHeartRateBpm(range: HealthRange): Promise<readonly number[]>;
  sleepSessions(
    range: HealthRange,
  ): Promise<readonly { readonly endDateISO: string; readonly minutes: number }[]>;
}

/**
 * HKCategoryValueSleepAnalysis: asleepUnspecified(1), asleepCore(3),
 * asleepDeep(4), asleepREM(5) count as sleep; inBed(0)/awake(2) do not.
 */
const ASLEEP_VALUES: ReadonlySet<number> = new Set([1, 3, 4, 5]);

async function loadNativeHealthKitApi(): Promise<HealthKitApi> {
  const hk = await import("@kingstinct/react-native-healthkit");
  const dateFilter = (range: HealthRange) => ({
    date: { startDate: new Date(range.startISO), endDate: new Date(range.endISO) },
  });
  return {
    isAvailable: () => hk.isHealthDataAvailable(),
    requestReadAuthorization: () =>
      hk.requestAuthorization({
        toRead: [
          "HKQuantityTypeIdentifierStepCount",
          "HKQuantityTypeIdentifierRestingHeartRate",
          "HKCategoryTypeIdentifierSleepAnalysis",
        ],
      }),
    dailyStepTotals: async (range) => {
      const stats = await hk.queryStatisticsCollectionForQuantity(
        "HKQuantityTypeIdentifierStepCount",
        ["cumulativeSum"],
        new Date(range.startISO),
        { day: 1 },
        { filter: dateFilter(range), unit: "count" },
      );
      return stats.flatMap((stat) =>
        stat.sumQuantity !== undefined && stat.startDate !== undefined
          ? [{ dateISO: localISODay(new Date(stat.startDate)), count: stat.sumQuantity.quantity }]
          : [],
      );
    },
    restingHeartRateBpm: async (range) => {
      const samples = await hk.queryQuantitySamples("HKQuantityTypeIdentifierRestingHeartRate", {
        filter: dateFilter(range),
        limit: 0,
        unit: "count/min",
      });
      return samples.map((sample) => sample.quantity);
    },
    sleepSessions: async (range) => {
      const samples = await hk.queryCategorySamples("HKCategoryTypeIdentifierSleepAnalysis", {
        filter: dateFilter(range),
        limit: 0,
      });
      return samples
        .filter((sample) => ASLEEP_VALUES.has(sample.value))
        .map((sample) => {
          const end = new Date(sample.endDate);
          const start = new Date(sample.startDate);
          return {
            endDateISO: localISODay(end),
            minutes: Math.round((end.getTime() - start.getTime()) / 60_000),
          };
        });
    },
  };
}

export function createHealthKitConnector(
  loadApi: () => Promise<HealthKitApi> = loadNativeHealthKitApi,
): HealthConnector {
  return {
    available: async () => {
      let api: HealthKitApi;
      try {
        api = await loadApi();
      } catch {
        return { status: "needs_dev_build" };
      }
      if (!api.isAvailable()) {
        return { status: "platform_unsupported" };
      }
      try {
        const completed = await api.requestReadAuthorization();
        return { status: completed ? "ok" : "permission_denied" };
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
