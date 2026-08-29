/**
 * INT-133 — the profile / companion server seam.
 *
 * Transport only. Everything decidable without a network lives in
 * `./refusals.ts` so the rules stay testable on their own; this file is the
 * one place that dials.
 *
 * `GET /v1/me/profile` returns SYSTEM facts only — which attributions exist,
 * whether the acknowledgement is required, whether a guardian flow can be
 * started at all. It carries nothing about the subject, and the app must not
 * infer anything about the subject from it: a minor never reaches this body,
 * because the route goes through the one enforcement point and the age gate
 * answers first with its typed 403.
 *
 * Failure posture follows the INT-132 consent seam: an unreachable route
 * resolves to null rather than fabricating a capability, and no error
 * narrative ever reaches the patient (02 §8.2).
 */
import { authedFetch } from "@/lib/auth/api";

import { parseProfile, type ProfileCapabilities } from "./refusals";

/** Read the capabilities, or null when the route is unreachable. Callers
 * fall back to `PROFILE_FALLBACK`, which is closed on both axes. */
export async function fetchProfile(): Promise<ProfileCapabilities | null> {
  try {
    const response = await authedFetch("/v1/me/profile");
    if (!response.ok) {
      return null;
    }
    return parseProfile(await response.json());
  } catch {
    return null;
  }
}
