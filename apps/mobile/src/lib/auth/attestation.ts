/**
 * Device attestation, the native half (INT-131, INT-344).
 *
 * Builds the `AttestationPorts` that attestationPlan.ts runs its key
 * lifecycle over: Apple App Attest through @expo/app-integrity, the key id in
 * SecureStore, the per-install device id. The decisions — which mode, what is
 * signed, when a key is replaced — all live in attestationPlan.ts and are
 * vitest-covered there.
 *
 * @expo/app-integrity is loaded ONLY through a lazy `import()` on a release
 * iOS path: vitest is node-only and must never pull the native module into
 * its graph, and __DEV__ builds (which send the honest `dev-unattested`
 * payload) never load it at all. App Attest needs a development or store
 * build — Expo Go cannot provide it, and the mode says `unsupported` there.
 */
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import {
  type AttestationMode,
  type AttestationPorts,
  type KeyRegistration,
  selectAttestationMode,
} from "./attestationPlan";
import { b64url } from "./jws";

const DEVICE_SLOT = "intake.auth.device_id";
const ATTEST_KEY_SLOT = "intake.auth.app_attest_key";

type AppIntegrity = typeof import("@expo/app-integrity");

let appIntegrityModule: Promise<AppIntegrity> | null = null;

function appIntegrity(): Promise<AppIntegrity> {
  appIntegrityModule ??= import("@expo/app-integrity");
  return appIntegrityModule;
}

/** Stable random per-install id — never a hardware identifier. */
export async function deviceId(): Promise<string> {
  const stored = await SecureStore.getItemAsync(DEVICE_SLOT);
  if (stored !== null) {
    return stored;
  }
  const fresh = b64url(new Uint8Array(Crypto.getRandomBytes(18)));
  await SecureStore.setItemAsync(DEVICE_SLOT, fresh);
  return fresh;
}

async function appAttestSupported(): Promise<boolean> {
  try {
    return (await appIntegrity()).isSupported;
  } catch {
    return false;
  }
}

export async function attestationMode(): Promise<AttestationMode> {
  const platform = Platform.OS;
  const probe = !__DEV__ && platform === "ios";
  return selectAttestationMode({
    isDev: __DEV__,
    platform,
    appAttestSupported: probe ? await appAttestSupported() : false,
  });
}

/** Drop the stored App Attest key id; the next call attests a new key. */
export async function forgetAttestKey(): Promise<void> {
  await SecureStore.deleteItemAsync(ATTEST_KEY_SLOT);
}

export async function attestationPorts(io: {
  challenge(): Promise<string>;
  registerKey(body: KeyRegistration): Promise<void>;
}): Promise<AttestationPorts> {
  return {
    mode: await attestationMode(),
    platform: Platform.OS === "android" ? "android" : "ios",
    deviceId,
    challenge: io.challenge,
    registerKey: io.registerKey,
    store: {
      load: () => SecureStore.getItemAsync(ATTEST_KEY_SLOT),
      save: (raw) => SecureStore.setItemAsync(ATTEST_KEY_SLOT, raw),
      forget: forgetAttestKey,
    },
    appAttest: {
      generateKey: async () => (await appIntegrity()).generateKeyAsync(),
      // the module hashes this string with SHA-256 into clientDataHash —
      // the same hash services/api computes over the clientData it rebuilds
      attestKey: async (keyId, clientData) =>
        (await appIntegrity()).attestKeyAsync(keyId, clientData),
      generateAssertion: async (keyId, clientData) =>
        (await appIntegrity()).generateAssertionAsync(keyId, clientData),
    },
  };
}
