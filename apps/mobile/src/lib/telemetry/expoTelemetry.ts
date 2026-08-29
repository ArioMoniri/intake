/**
 * The one place telemetry reads Expo (INT-145).
 *
 * Same split as lib/dev/hosts.ts ↔ lib/dev/expoTelemetry.ts's sibling
 * expoHosts.ts: every rule lives in the pure modules so it is node-testable,
 * and the `expo-constants` / `react-native` reading is isolated here.
 *
 * NOTHING IS INVENTED WHEN CONFIGURATION IS MISSING. `app.json`'s
 * `extra.glitchtipDsn` is empty, so the reporter is inert by default and says
 * `not_configured` rather than posting anywhere. `buildId` and `sbomDigest`
 * are supplied by the EAS build (files/10 §6 requires all three in client
 * telemetry) and are absent until INT-146 wires them — the mechanism is here
 * and fails closed, dropping the tag rather than reporting a guess.
 */
import Constants from "expo-constants";
import * as Device from "expo-device";
import { Platform } from "react-native";

import { createTelemetryRuntime, type TelemetryRuntime } from "./runtime";
import type { CrashTransport } from "./client";
import type { TelemetryEnvironment, TelemetryIdentity, TelemetryPlatform } from "./scrub";

interface TelemetryExtra {
  glitchtipDsn?: string;
  buildId?: string;
  sbomDigest?: string;
  releaseChannel?: string;
  tenantId?: string;
}

function extra(): TelemetryExtra {
  return (Constants.expoConfig?.extra ?? {}) as TelemetryExtra;
}

/** The configured DSN, or null. There is no fallback endpoint. */
export function configuredDsn(): string | null {
  const dsn = extra().glitchtipDsn;
  return typeof dsn === "string" && dsn.trim() !== "" ? dsn.trim() : null;
}

function platform(): TelemetryPlatform {
  return Platform.OS === "ios" || Platform.OS === "android" ? Platform.OS : "web";
}

function environment(): TelemetryEnvironment {
  return __DEV__ ? "dev" : "prod";
}

/** Build metadata as this device knows it. Anything unknown becomes an empty
 * string, which fails its shape in scrub.ts and drops the tag. */
export function deviceIdentity(): TelemetryIdentity {
  const configured = extra();
  return {
    appVersion: Constants.expoConfig?.version ?? "",
    buildId: configured.buildId ?? "",
    sbomDigest: configured.sbomDigest ?? "",
    platform: platform(),
    osVersion: Device.osVersion ?? "",
    deviceModel: Device.modelId ?? "",
    environment: environment(),
    releaseChannel: configured.releaseChannel ?? "",
    tenantId: configured.tenantId ?? "",
  };
}

/** A `fetch`-backed transport. Non-2xx is a failure, not an exception, and a
 * thrown network error is handled by the client, which never rethrows. */
export const fetchCrashTransport: CrashTransport = {
  send: async (request) => {
    const response = await fetch(request.url, {
      method: "POST",
      headers: { ...request.headers },
      body: request.body,
    });
    return { ok: response.ok };
  },
};

/**
 * The runtime for this launch, created once.
 *
 * The metric sink defaults to the discarding one, and that is the honest state
 * rather than an oversight: no service ingests client metrics yet, which is
 * precisely why `client.*` and `web.core_web_vitals` are catalogued `planned`.
 * The readings are computed on device and available through `state()`; the
 * sink is the seam an ingest endpoint plugs into, and the PR that adds it
 * promotes the catalogue entries.
 */
let runtime: TelemetryRuntime | null = null;

export function clientTelemetry(): TelemetryRuntime {
  runtime ??= createTelemetryRuntime({
    dsn: configuredDsn(),
    identity: deviceIdentity(),
    transport: fetchCrashTransport,
  });
  return runtime;
}

type GlobalErrorHandler = (error: unknown, isFatal?: boolean) => void;

interface ErrorUtilsLike {
  getGlobalHandler?: () => GlobalErrorHandler | undefined;
  setGlobalHandler?: (handler: GlobalErrorHandler) => void;
}

/**
 * Route uncaught errors into the crash counter and the reporter.
 *
 * Only the error's CLASS NAME is passed on. `error.message` is left where it
 * is: a thrown `Error` carries whatever string was to hand, and on this app
 * that string can be an extraction failure quoting the patient. The scrubber
 * would refuse it anyway — this just refuses it one layer earlier, at the
 * boundary files/10 §3 calls `SafeError`.
 *
 * The previous handler is always called: swallowing a fatal would replace a
 * red box the developer needs with silence.
 */
let handlerInstalled = false;

export function installCrashHandler(errorCode = "uncaught_js_error"): void {
  const utils = (globalThis as { ErrorUtils?: ErrorUtilsLike }).ErrorUtils;
  if (handlerInstalled || utils?.setGlobalHandler === undefined) {
    // Idempotent: chaining twice would report one crash twice and skew the
    // crash-free share in the direction that hides a problem.
    return;
  }
  handlerInstalled = true;
  const previous = utils.getGlobalHandler?.();
  utils.setGlobalHandler((error, isFatal) => {
    const name = error instanceof Error ? error.name : "Error";
    void clientTelemetry().noteCrash({
      errorCode,
      exception: { values: [{ type: name }] },
    });
    previous?.(error, isFatal);
  });
}
