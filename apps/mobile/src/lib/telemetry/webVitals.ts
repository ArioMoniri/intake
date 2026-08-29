/**
 * Web RUM — Core Web Vitals (INT-145; files/10 §6 "RUM for web").
 *
 * The only web target in the repo today is this package's own web build
 * (`expo start --web`, react-native-web); apps/clinician-web and
 * apps/admin-web do not exist yet. So the vitals are read from the platform's
 * own `PerformanceObserver` and handed to the same catalogued sink the native
 * performance series use. When the two Next apps land they import this module
 * rather than growing a second collector.
 *
 * No `web-vitals` package, for the reason envelope.ts gives about crash SDKs:
 * the value a RUM library adds is attribution — the element, the URL, the
 * resource that caused the shift — and attribution is the part that carries
 * text off a clinical page. Five entry types, one number each, is the whole
 * requirement.
 *
 * NOTHING BUT A NUMBER IS READ OFF AN ENTRY. A `largest-contentful-paint`
 * entry carries `element`, `url` and `id`; a `layout-shift` carries `sources`
 * with node references. Those are never touched, so a page rendering a
 * patient's name cannot put it into a metric label.
 *
 * Inert wherever `PerformanceObserver` is absent, which is every native build.
 */
import {
  WEB_CORE_WEB_VITALS,
  webVitalSample,
  type ClientMetricSample,
  type ClientMetricSink,
} from "./metrics";

/** The entry types we subscribe to, one observer each. */
const OBSERVED_ENTRY_TYPES = [
  "largest-contentful-paint",
  "layout-shift",
  "event",
  "paint",
  "navigation",
] as const;

interface ObserverLike {
  observe(options: { type: string; buffered: boolean }): void;
  disconnect(): void;
}

type ObserverConstructor = new (
  callback: (list: { getEntries: () => unknown[] }) => void,
) => ObserverLike;

function field(entry: unknown, key: string): number | null {
  if (typeof entry !== "object" || entry === null) {
    return null;
  }
  const value = (entry as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringField(entry: unknown, key: string): string | null {
  if (typeof entry !== "object" || entry === null) {
    return null;
  }
  const value = (entry as Record<string, unknown>)[key];
  return typeof value === "string" ? value : null;
}

/**
 * Map one performance entry onto a catalogued sample, or null when the entry
 * is not one of the five we measure. Never guesses: an entry type we did not
 * ask for produces nothing rather than a vital chosen by resemblance.
 */
export function vitalFromEntry(entry: unknown): ClientMetricSample | null {
  const type = stringField(entry, "entryType");
  switch (type) {
    case "largest-contentful-paint":
      return sample("LCP", field(entry, "startTime"));
    case "layout-shift":
      return sample("CLS", field(entry, "value"));
    case "event":
      // Only an entry the browser assigned an interaction id contributes to
      // INP; without one it is an ordinary event timing, not a vital.
      return field(entry, "interactionId") === null
        ? null
        : sample("INP", field(entry, "duration"));
    case "paint":
      return stringField(entry, "name") === "first-contentful-paint"
        ? sample("FCP", field(entry, "startTime"))
        : null;
    case "navigation":
      return sample("TTFB", field(entry, "responseStart"));
    default:
      return null;
  }
}

function sample(vital: Parameters<typeof webVitalSample>[0], value: number | null) {
  return value === null ? null : webVitalSample(vital, value);
}

/**
 * Subscribe to the five entry types. Returns a stop function, or null when the
 * scope has no `PerformanceObserver` (every native build).
 *
 * An observer that throws — an engine that does not know an entry type — is
 * skipped rather than allowed to break the page it is measuring.
 */
export function observeWebVitals(scope: unknown, sink: ClientMetricSink): (() => void) | null {
  const constructor = (scope as { PerformanceObserver?: ObserverConstructor } | null)
    ?.PerformanceObserver;
  if (typeof constructor !== "function") {
    return null;
  }
  const observers: ObserverLike[] = [];
  for (const type of OBSERVED_ENTRY_TYPES) {
    try {
      const observer = new constructor((list) => {
        for (const entry of list.getEntries()) {
          const reading = vitalFromEntry(entry);
          if (reading !== null && reading.metricId === WEB_CORE_WEB_VITALS) {
            sink.emit(reading);
          }
        }
      });
      observer.observe({ type, buffered: true });
      observers.push(observer);
    } catch {
      // This engine does not support the entry type. Measuring four vitals is
      // a better outcome than a page that fails to render.
      continue;
    }
  }
  if (observers.length === 0) {
    return null;
  }
  return () => {
    for (const observer of observers) {
      observer.disconnect();
    }
  };
}
