/**
 * Token custody (INT-131, files/10 §2 + MASVS: tokens in SecureStore).
 *
 * The refresh token — the long-lived credential — lives ONLY in
 * expo-secure-store (Keychain / Keystore-encrypted), never a plain
 * key-value store, never a log, never navigation params. The 15-minute access token stays in
 * module memory only: it dies with the process, which is exactly the
 * lifetime files/10 §2 gives it.
 */
import * as SecureStore from "expo-secure-store";

import { SESSION_SNAPSHOT_SLOT } from "./sessionSnapshot";

const REFRESH_SLOT = "intake.auth.refresh";
const PATIENT_SLOT = "intake.auth.patient";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export async function saveRefreshToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(REFRESH_SLOT, token, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_SLOT);
}

export async function savePatientId(patientId: string): Promise<void> {
  await SecureStore.setItemAsync(PATIENT_SLOT, patientId);
}

export async function getPatientId(): Promise<string | null> {
  return SecureStore.getItemAsync(PATIENT_SLOT);
}

/** Sign-out / family-revoked hygiene: drop every credential at once — and the
 * restore snapshot bound to the same session (INT-131), so a revoked family can
 * never leave the patient's name or visits restorable on the next launch. */
export async function clearSession(): Promise<void> {
  accessToken = null;
  await SecureStore.deleteItemAsync(REFRESH_SLOT);
  await SecureStore.deleteItemAsync(PATIENT_SLOT);
  await SecureStore.deleteItemAsync(SESSION_SNAPSHOT_SLOT);
}
