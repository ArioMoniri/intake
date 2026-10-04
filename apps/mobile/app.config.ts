/**
 * Dynamic Expo config over app.json (INT-328). app.json stays the static
 * source; this file adds only what a static file cannot say.
 *
 * - F01: `extra.apiBaseUrl` is the release build's API base, and its ONLY
 *   source is the EAS environment variable `EXPO_PUBLIC_API_BASE_URL`. No
 *   hostname is committed anywhere: the production FQDN is a human decision
 *   (HB-I14). Until it is set the value is empty, and lib/auth/apiBase.ts
 *   refuses to talk to anything — it never falls back to the dev LAN walk.
 * - F17: the production profile never declares the iOS local-network usage
 *   string (nor the Bonjour list that goes with it). A release build reaches no
 *   LAN host, and declaring the key is what puts the local-network prompt in
 *   front of a patient. Every other profile keeps what app.json declares.
 * - F29: `extra.asrHosts` and `extra.ttsLanes` are sets in all but type; each
 *   entry is kept once, in first-seen order.
 * - INT-340: every Android build blocks VIBRATE. The haptics library declares
 *   it in its own manifest, but the app plays haptics on Android only through
 *   View.performHapticFeedback, which needs no permission, so the inventory
 *   does not grow. Expo writes the block as `tools:node="remove"`, which wins
 *   over any library's declaration in the manifest merge, and drops the
 *   permission from `android.permissions` if app.json ever asks for it.
 * - INT-491: `extra.orbVariant` is the orb variant flag, and its ONLY source
 *   is `EXPO_PUBLIC_ORB_VARIANT`. Empty means off: the ADR-039 sphere. The
 *   production profile never carries a variant, so none reaches a store build
 *   before the owner picks one and the ADR records it. The app parses the
 *   value with lib/stage/orbVariants.ts, where anything unknown is off.
 */
import type { ConfigContext, ExpoConfig } from "expo/config";

/** The EAS variable the owner sets for a store build (public, not a secret). */
export const API_BASE_ENV = "EXPO_PUBLIC_API_BASE_URL";

/** The orb variant a development or preview build draws (INT-491). */
export const ORB_VARIANT_ENV = "EXPO_PUBLIC_ORB_VARIANT";

/** EAS Build sets this to the eas.json profile being built. */
const PROFILE_ENV = "EAS_BUILD_PROFILE";
const PRODUCTION_PROFILE = "production";
const LOCAL_NETWORK_PLIST_KEYS = ["NSLocalNetworkUsageDescription", "NSBonjourServices"];
/** Android permissions no build may carry, whoever declares them. */
const BLOCKED_ANDROID_PERMISSIONS = ["android.permission.VIBRATE"];

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

/** Expo's own spelling rule: a bare name is an `android.permission.` one. */
function qualifiedPermission(permission: string): string {
  return permission.includes(".") ? permission : `android.permission.${permission}`;
}

function withBlockedPermissions(android: ExpoConfig["android"]): ExpoConfig["android"] {
  const blocked = uniqueBy(
    [...(android?.blockedPermissions ?? []), ...BLOCKED_ANDROID_PERMISSIONS],
    qualifiedPermission,
  );
  const refused = new Set(blocked.map(qualifiedPermission));
  const resolved = { ...android, blockedPermissions: blocked };
  if (android?.permissions !== undefined) {
    resolved.permissions = android.permissions.filter((p) => !refused.has(qualifiedPermission(p)));
  }
  return resolved;
}

/** The resolved config for one environment. Pure, so the rules are testable. */
export function resolveAppConfig(config: ExpoConfig, env: Env): ExpoConfig {
  const extra: Record<string, unknown> = { ...(config.extra ?? {}) };
  if (Array.isArray(extra.asrHosts)) {
    extra.asrHosts = uniqueBy(extra.asrHosts as unknown[], (host) => String(host));
  }
  if (Array.isArray(extra.ttsLanes)) {
    extra.ttsLanes = uniqueBy(extra.ttsLanes as unknown[], laneKey);
  }
  extra.apiBaseUrl = (env[API_BASE_ENV] ?? "").trim();
  const production = env[PROFILE_ENV] === PRODUCTION_PROFILE;
  extra.orbVariant = production ? "" : (env[ORB_VARIANT_ENV] ?? "").trim();

  const resolved: ExpoConfig = {
    ...config,
    extra,
    android: withBlockedPermissions(config.android),
  };
  if (production && config.ios !== undefined) {
    resolved.ios = withoutLocalNetwork(config.ios);
  }
  return resolved;
}

export default function appConfig({ config }: ConfigContext): ExpoConfig {
  return resolveAppConfig(config as ExpoConfig, process.env);
}
