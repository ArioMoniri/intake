/**
 * Client telemetry (INT-145): PHI-scrubbed crash reporting to a self-hosted
 * GlitchTip, client performance series, and Core Web Vitals for the web build.
 *
 * The Expo reader is deliberately NOT re-exported here: importing this barrel
 * from a test must not drag `expo-constants` and `react-native` into node.
 * Screens import `./expoTelemetry` directly.
 */
export { createCrashClient } from "./client";
export type {
  CaptureOutcome,
  CrashClient,
  CrashClientOptions,
  CrashClientStatus,
  CrashTransport,
  CrashTransportRequest,
} from "./client";
export { parseDsn } from "./dsn";
export type { Dsn } from "./dsn";
export { authHeader, buildEnvelopeBody } from "./envelope";
export type { DsnParts } from "./envelope";
export {
  CLIENT_ANR_RATE,
  CLIENT_COLD_START_P95_MS,
  CLIENT_CRASH_FREE_SESSIONS,
  EMITTED_CLIENT_METRIC_IDS,
  WEB_CORE_WEB_VITALS,
  WEB_VITALS,
  anrRate,
  coldStartP95Ms,
  crashFreeRatio,
  emitPerf,
  emptyPerfState,
  noopClientMetricSink,
  perfSamples,
  recordColdStart,
  recordCrash,
  recordSession,
  recordStall,
  webVitalSample,
} from "./metrics";
export type { ClientMetricSample, ClientMetricSink, PerfState, WebVital } from "./metrics";
export { createTelemetryRuntime } from "./runtime";
export type { TelemetryRuntime, TelemetryRuntimeOptions } from "./runtime";
export {
  ALLOWED_TAG_KEYS,
  BREADCRUMB_CATEGORIES,
  EVENT_TAG_KEYS,
  IDENTITY_TAG_KEYS,
  UNCLASSIFIED_ERROR_CODE,
  buildCrashReport,
} from "./scrub";
export type {
  BreadcrumbCategory,
  CrashBreadcrumb,
  CrashFrame,
  CrashReport,
  TelemetryEnvironment,
  TelemetryIdentity,
  TelemetryPlatform,
} from "./scrub";
export { observeWebVitals, vitalFromEntry } from "./webVitals";
