/**
 * The Expo-bound side of the API-base resolver (INT-328). The rule lives in
 * apiBase.ts, which is pure; this file only supplies what it needs:
 * `__DEV__`, the build's `extra.apiBaseUrl`, and the dev LAN walk.
 *
 * The walk (Metro hostUri + `extra.asrHosts`, plain http, /healthz) is the one
 * the auth client and the dev George clip source always used. It is reached
 * through a lazy import, and the resolver calls it only when `isDev` — so in a
 * release build lib/dev is never evaluated and no LAN host is ever probed.
 */
import Constants from "expo-constants";

import { resolveApiBase } from "./apiBase";

/** services/api's dev port — the same host the auth and records clients use. */
const DEV_API_PORT = 8000;

async function probeHealthz(base: string): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`${base}/healthz`, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** Dev only: the first LAN candidate whose /healthz answers, or null. */
async function firstReachableDevApiBase(): Promise<string | null> {
  const { configuredServiceCandidates } = await import("../dev/expoHosts");
  for (const base of configuredServiceCandidates(DEV_API_PORT)) {
    if (await probeHealthz(base)) {
      return base;
    }
  }
  return null;
}

/**
 * This build's API base. Release: the configured https base, or a thrown
 * `ApiBaseUnconfigured`. Dev: the LAN walk's answer, null when nothing answers.
 * Not cached here — each caller keeps its own cache and re-probe policy.
 */
export function buildApiBase(): Promise<string | null> {
  const extra = (Constants.expoConfig?.extra ?? {}) as { apiBaseUrl?: unknown };
  return resolveApiBase({
    isDev: __DEV__,
    configured: extra.apiBaseUrl,
    devBase: firstReachableDevApiBase,
  });
}
