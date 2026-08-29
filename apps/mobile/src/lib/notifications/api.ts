/**
 * INT-141 — the notification-preference seam, on the INT-132 client pattern:
 * DPoP-bound authedFetch against the dev-tier base discovered by /healthz
 * probing.
 *
 * The register of record is the server: a quiet-hours setting that lived on
 * the device would stop applying the moment the phone was replaced, and the
 * scheduler that has to honour it does not run here. So a read that fails
 * resolves to null and the caller keeps showing what it already had —
 * nothing here fabricates a default, and no server narrative is surfaced
 * (02 §8.2, generic errors).
 */
import { authedFetch } from "@/lib/auth/api";

import type { NotificationPrefs } from "./preferences";

const PATH = "/v1/me/notifications";

function parsePrefs(raw: unknown): NotificationPrefs | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const entry = raw as Record<string, unknown>;
  if (typeof entry.opted_out !== "boolean") {
    return null;
  }
  const start = entry.quiet_start;
  const end = entry.quiet_end;
  const startOk = start === null || typeof start === "string";
  const endOk = end === null || typeof end === "string";
  if (!startOk || !endOk) {
    return null;
  }
  return {
    optedOut: entry.opted_out,
    quietStart: (start as string | null) ?? null,
    quietEnd: (end as string | null) ?? null,
  };
}

/** Null means "server unreachable or route absent" — local state stands. */
export async function fetchNotificationPrefs(): Promise<NotificationPrefs | null> {
  try {
    const response = await authedFetch(PATH);
    if (!response.ok) {
      return null;
    }
    return parsePrefs(await response.json());
  } catch {
    return null;
  }
}

/** Null means the change did not land; the caller keeps the shown state. */
export async function pushNotificationPrefs(
  prefs: NotificationPrefs,
): Promise<NotificationPrefs | null> {
  try {
    const response = await authedFetch(PATH, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        opted_out: prefs.optedOut,
        quiet_start: prefs.quietStart,
        quiet_end: prefs.quietEnd,
      }),
    });
    if (!response.ok) {
      return null;
    }
    return parsePrefs(await response.json());
  } catch {
    return null;
  }
}
