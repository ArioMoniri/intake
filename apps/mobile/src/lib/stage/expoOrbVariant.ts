/**
 * The Expo-bound side of the orb's body (INT-491). The rule lives in
 * orbVariants.ts, which is pure; this file only reads the build's
 * `extra.orbVariant` (app.config.ts fills it from EXPO_PUBLIC_ORB_VARIANT,
 * never in a production build) and parses it.
 *
 * Read once, at module load: the value is a property of the build and does
 * not change while the app runs. Unset, empty or unknown is the lens, the
 * orb ADR-039 names; only `classic` draws the earlier sphere.
 */
import Constants from "expo-constants";

import { orbVariantFrom, type OrbVariant } from "./orbVariants";

const extra = (Constants.expoConfig?.extra ?? {}) as { orbVariant?: unknown };

/** The body this build draws on the chat stage and the welcome mark. */
export const ORB_VARIANT: OrbVariant = orbVariantFrom(extra.orbVariant);
