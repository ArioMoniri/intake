/**
 * The Expo-bound side of the orb variant flag (INT-491). The rule lives in
 * orbVariants.ts, which is pure; this file only reads the build's
 * `extra.orbVariant` (app.config.ts fills it from EXPO_PUBLIC_ORB_VARIANT,
 * never in a production build) and parses it.
 *
 * Read once, at module load: the value is a property of the build and does
 * not change while the app runs. Unset, empty or unknown is off, and the
 * dialogue draws the ADR-039 sphere.
 */
import Constants from "expo-constants";

import { orbVariantFrom, type OrbVariant } from "./orbVariants";

const extra = (Constants.expoConfig?.extra ?? {}) as { orbVariant?: unknown };

/** The variant this build draws on the chat stage. */
export const ORB_VARIANT: OrbVariant = orbVariantFrom(extra.orbVariant);
