/**
 * The React and storage adapter for ./appearance (INT-260).
 *
 * Thin on purpose: every rule lives in the pure module beside it, where the
 * node suite can hold it. What is here is the two things a pure module cannot
 * do — hold the value for the tree, and write it somewhere it survives a
 * restart.
 *
 * **Why the keychain, and not a key-value file store.** files/10 §2 admits
 * exactly one on-device store and `e2e/auth.spec.ts` enforces it by name, so
 * the alternative was never available — but it is also the wrong choice on its
 * own merits here. A record under the app's Documents / Library directory is
 * INCLUDED in the device's iCloud and finder backups, so the preference would
 * leave the phone, to Apple and to the patient's other devices, and the
 * inventory annotation's `recipients: none` would be a claim rather than a
 * fact. `expo-secure-store` with `WHEN_UNLOCKED_THIS_DEVICE_ONLY` is the same
 * accessibility class the token and DPoP slots already use
 * (lib/auth/tokens.ts, lib/auth/dpop.ts): excluded from backups, never synced.
 * It is heavier protection than this data needs, which is the safe direction
 * to be wrong in, and it adds no dependency.
 *
 * Failure posture: a slot that cannot be read, or holds something this build
 * does not recognise, yields the device-following defaults. There is no
 * error state to show, because there is nothing the patient could do about it
 * and nothing is lost — the OS setting is still obeyed.
 */
import * as SecureStore from "expo-secure-store";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  APPEARANCE_SLOT,
  DEFAULT_APPEARANCE,
  decodeAppearance,
  encodeAppearance,
  type AppearancePrefs,
} from "./appearance";

export interface Appearance {
  readonly prefs: AppearancePrefs;
  /** False until the stored record has been read once. */
  readonly ready: boolean;
  /** Change one or more fields; the whole record is rewritten. */
  update: (patch: Partial<AppearancePrefs>) => void;
}

/**
 * The default is the device-following state, so a component rendered outside
 * the provider behaves exactly as the app did before this issue rather than
 * throwing. `update` is inert there for the same reason: a write with nowhere
 * to go must not look like it succeeded.
 */
const AppearanceContext = createContext<Appearance>({
  prefs: DEFAULT_APPEARANCE,
  ready: false,
  update: () => undefined,
});

export function useAppearance(): Appearance {
  return useContext(AppearanceContext);
}

function sameAsDefaults(prefs: AppearancePrefs): boolean {
  return (
    prefs.textStep === DEFAULT_APPEARANCE.textStep &&
    prefs.theme === DEFAULT_APPEARANCE.theme &&
    prefs.reduceMotion === DEFAULT_APPEARANCE.reduceMotion &&
    prefs.startMode === DEFAULT_APPEARANCE.startMode
  );
}

/**
 * Persist, or stop persisting.
 *
 * Returning every control to its default DELETES the slot rather than writing
 * a record that says "nothing chosen" — which is what makes the annotation's
 * *retention: until uninstall or reset* literally true instead of nearly true.
 */
function persist(prefs: AppearancePrefs): void {
  const write = sameAsDefaults(prefs)
    ? SecureStore.deleteItemAsync(APPEARANCE_SLOT)
    : SecureStore.setItemAsync(APPEARANCE_SLOT, encodeAppearance(prefs), {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
  // A failed write costs the patient the setting on next launch and nothing
  // else; it must never take the app down or block the control they pressed.
  void write.catch(() => undefined);
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<AppearancePrefs>(DEFAULT_APPEARANCE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    const settle = (raw: string | null) => {
      if (live) {
        setPrefs(decodeAppearance(raw));
        setReady(true);
      }
    };
    try {
      void SecureStore.getItemAsync(APPEARANCE_SLOT).then(settle, () => settle(null));
    } catch {
      settle(null);
    }
    return () => {
      live = false;
    };
  }, []);

  const update = useCallback((patch: Partial<AppearancePrefs>) => {
    setPrefs((current) => {
      const next = { ...current, ...patch };
      persist(next);
      return next;
    });
  }, []);

  const value = useMemo<Appearance>(() => ({ prefs, ready, update }), [prefs, ready, update]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}
