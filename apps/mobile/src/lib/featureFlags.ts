/**
 * The Expo-bound side of the feature flags (INT-492). The rules live in
 * ./flags, which is pure; this file supplies only what they need: the
 * build's `extra.flags` (app.config.ts fills it from the build variable
 * `INTAKE_FLAGS`, and nothing else does) and `__DEV__`, which keeps an
 * approval-needed flag out of every release build.
 *
 * Resolved once, at module load: a build's flags do not change while it runs.
 */
import Constants from "expo-constants";

import { resolveFlags, type Flags } from "./flags";

const extra = (Constants.expoConfig?.extra ?? {}) as { flags?: unknown };

export const flags: Flags = resolveFlags(extra.flags, { dev: __DEV__ });
