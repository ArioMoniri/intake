/**
 * INT-582 (D36) — the native passkey module, behind a lazy `import()`.
 *
 * react-native-passkeys 0.4.2 (MIT, LICENSE blob read at tag v0.4.2 on
 * 2026-10-30; docs/evidence/INT-582.md) wraps ASAuthorization on iOS and
 * Credential Manager on Android. It is loaded ONLY here and only through a
 * lazy `import()`: vitest is node-only and must never pull a native module
 * into its graph, and a build without the module (or a phone without passkey
 * support) simply has none — `null`, which every caller reads as "this phone
 * cannot do passkeys", never as a pass.
 *
 * The module's own option types come from a package it does not ship, so the
 * calls cross this boundary as the WebAuthn JSON shapes ./rp and ./ceremony
 * define, checked there.
 */
import type { AssertionCredential, PasskeyNative, RegistrationCredential } from "./ceremony";
import type { CreationOptions, RequestOptions } from "./rp";

interface PasskeysModule {
  isSupported(): boolean;
  create(request: unknown): Promise<unknown>;
  get(request: unknown): Promise<unknown>;
}

let loaded: Promise<PasskeysModule> | null = null;

function passkeysModule(): Promise<PasskeysModule> {
  loaded ??= import("react-native-passkeys") as unknown as Promise<PasskeysModule>;
  return loaded;
}

export async function loadPasskeyNative(): Promise<PasskeyNative | null> {
  try {
    const module = await passkeysModule();
    if (!module.isSupported()) {
      return null;
    }
    return {
      create: async (options: CreationOptions) =>
        (await module.create(options)) as RegistrationCredential | null,
      get: async (options: RequestOptions) =>
        (await module.get(options)) as AssertionCredential | null,
    };
  } catch {
    return null;
  }
}
