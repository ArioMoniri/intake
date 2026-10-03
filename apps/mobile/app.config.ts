/**
 * Dynamic Expo config over app.json (INT-328). app.json stays the static
 * source; this file adds only what a static file cannot say.
 *
 * - F01: `extra.apiBaseUrl` is the release build's API base, and its value
 *   still comes only from the EAS environment variable
 *   `EXPO_PUBLIC_API_BASE_URL`; app.json cannot supply it. eas.json's
 *   production profile sets that variable, so the base a store build carries
 *   is a reviewed diff, and it must pass lib/auth/apiBase.ts's release parser
 *   (https, public DNS name). HB-I14, the final FQDN, stays open. With the
 *   variable unset the value is empty, and lib/auth/apiBase.ts refuses to talk
 *   to anything — it never falls back to the dev LAN walk.
 * - F17: the production profile never declares the iOS local-network usage
 *   string (nor the Bonjour list that goes with it). A release build reaches no
 *   LAN host, and declaring the key is what puts the local-network prompt in
 *   front of a patient. Every other profile keeps what app.json declares.
 * - F29: `extra.asrHosts` and `extra.ttsLanes` are sets in all but type; each
 *   entry is kept once, in first-seen order.
 * - INT-421: the production profile carries no dev-only lane. `extra.asrHosts`
 *   and `extra.ttsLanes` are the LAN and loopback hosts of the `__DEV__` voice
 *   lanes, so they resolve to empty lists there, and the release config names
 *   no private address. Every other profile keeps them, deduplicated.
 */
import type { ConfigContext, ExpoConfig } from "expo/config";

/** The EAS variable the owner sets for a store build (public, not a secret). */
export const API_BASE_ENV = "EXPO_PUBLIC_API_BASE_URL";

/** EAS Build sets this to the eas.json profile being built. */
const PROFILE_ENV = "EAS_BUILD_PROFILE";
const PRODUCTION_PROFILE = "production";
const LOCAL_NETWORK_PLIST_KEYS = ["NSLocalNetworkUsageDescription", "NSBonjourServices"];

type Env = Readonly<Record<string, string | undefined>>;

function uniqueBy<T>(items: readonly T[], key: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const k = key(item);
    if (seen.has(k)) {
      return false;
    }
    seen.add(k);
    return true;
  });
}

function laneKey(lane: unknown): string {
  if (typeof lane === "object" && lane !== null) {
    const { id, port } = lane as { id?: unknown; port?: unknown };
    return `${String(id)}@${String(port)}`;
  }
  return JSON.stringify(lane);
}

function withoutLocalNetwork(ios: ExpoConfig["ios"]): ExpoConfig["ios"] {
  if (ios?.infoPlist === undefined) {
    return ios;
  }
  const infoPlist = { ...ios.infoPlist };
  for (const key of LOCAL_NETWORK_PLIST_KEYS) {
    delete infoPlist[key];
  }
  return { ...ios, infoPlist };
}

/** The resolved config for one environment. Pure, so the rules are testable. */
export function resolveAppConfig(config: ExpoConfig, env: Env): ExpoConfig {
  const production = env[PROFILE_ENV] === PRODUCTION_PROFILE;
  const extra: Record<string, unknown> = { ...(config.extra ?? {}) };
  if (production) {
    extra.asrHosts = [];
    extra.ttsLanes = [];
  } else {
    if (Array.isArray(extra.asrHosts)) {
      extra.asrHosts = uniqueBy(extra.asrHosts as unknown[], (host) => String(host));
    }
    if (Array.isArray(extra.ttsLanes)) {
      extra.ttsLanes = uniqueBy(extra.ttsLanes as unknown[], laneKey);
    }
  }
  extra.apiBaseUrl = (env[API_BASE_ENV] ?? "").trim();

  const resolved: ExpoConfig = { ...config, extra };
  if (production && config.ios !== undefined) {
    resolved.ios = withoutLocalNetwork(config.ios);
  }
  return resolved;
}

export default function appConfig({ config }: ConfigContext): ExpoConfig {
  return resolveAppConfig(config as ExpoConfig, process.env);
}
