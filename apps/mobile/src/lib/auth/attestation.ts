/**
 * Client attestation payload (INT-131) — honest about what it is.
 *
 * REAL App Attest / Play Integrity need a dev-build native module plus
 * Apple/Google server-side verification keys (awaiting-human, HB-A3;
 * docs/evidence/INT-131.md). Until those land, this builds the payload the
 * server's DEV verifier accepts ONLY under
 * INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes: it declares itself
 * `dev-unattested` so a misconfigured server can never mistake it for a
 * verified device. The nonce is the server's single-use challenge — the
 * same binding the real attestation objects will carry.
 */
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import { b64url } from "./jws";

const DEVICE_SLOT = "intake.auth.device_id";

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

/** JSON for the X-Intake-Attestation header; null where no platform
 * attestation surface exists at all (web). */
export async function buildAttestation(nonce: string): Promise<string | null> {
  if (Platform.OS !== "ios" && Platform.OS !== "android") {
    return null;
  }
  return JSON.stringify({
    platform: Platform.OS,
    mode: "dev-unattested",
    token: b64url(new TextEncoder().encode("intake-dev-attest")),
    device_id: await deviceId(),
    nonce,
  });
}
