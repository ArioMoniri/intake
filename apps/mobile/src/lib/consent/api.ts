/**
 * Consent server seam (INT-132), on the INT-131 client pattern: DPoP-bound
 * authedFetch against the dev-tier base discovered by /healthz probing.
 *
 * Honesty about the dev tier: services/api does not expose patient-facing
 * consent routes yet (INT-038 shipped the service layer and the guard). The
 * paths below are the seam those routes will land on; until then — and
 * whenever the device is offline — every call resolves to null/false and
 * the caller keeps its local state plus an in-memory queue. Nothing here
 * fakes a success, and no error narrative is ever surfaced (02 §8.2).
 */
import { authedFetch } from "@/lib/auth/api";

import type { QueuedOp, ServerScope, TextEntry } from "./ledger";
import { purposeDef, type PurposeId } from "./purposes";

export interface ConsentSnapshot {
  scopes: ServerScope[];
  texts: Partial<Record<PurposeId, TextEntry>>;
}

const REASONS: readonly ServerScope["reason"][] = [
  "granted",
  "default_on",
  "unbound",
  "absent",
  "withdrawn",
  "stale",
];

function parseScopes(raw: unknown): ServerScope[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const scopes: ServerScope[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const def = typeof entry.scope === "string" ? purposeDef(entry.scope) : null;
    const reason = REASONS.find((r) => r === entry.reason);
    if (def === null || reason === undefined) {
      continue; // outside the closed list — never guess a purpose
    }
    scopes.push({
      scope: def.id,
      reason,
      version: typeof entry.version === "string" ? entry.version : null,
      textHash: typeof entry.text_hash === "string" ? entry.text_hash : null,
    });
  }
  return scopes;
}

function parseTexts(raw: unknown): Partial<Record<PurposeId, TextEntry>> {
  const texts: Partial<Record<PurposeId, TextEntry>> = {};
  if (!Array.isArray(raw)) {
    return texts;
  }
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const def = typeof entry.purpose === "string" ? purposeDef(entry.purpose) : null;
    if (
      def === null ||
      typeof entry.version !== "string" ||
      typeof entry.text_hash !== "string" ||
      typeof entry.body !== "string" ||
      entry.body.trim().length === 0
    ) {
      continue; // an unversionable text cannot participate in re-prompt
    }
    texts[def.id] = {
      status: "loaded",
      text: { version: entry.version, textHash: entry.text_hash, body: entry.body },
    };
  }
  return texts;
}

/** The loader payload: per-purpose state + the versioned, hash-bound texts.
 * Null means "server unreachable or route absent" — local state stands. */
export async function fetchConsentSnapshot(): Promise<ConsentSnapshot | null> {
  try {
    const response = await authedFetch("/v1/consents");
    if (!response.ok) {
      return null;
    }
    const body = (await response.json()) as Record<string, unknown>;
    return { scopes: parseScopes(body.scopes), texts: parseTexts(body.texts) };
  } catch {
    return null;
  }
}

/** Push one queued op. False = keep it queued (offline / route absent). */
export async function pushConsentOp(op: QueuedOp): Promise<boolean> {
  const path = op.kind === "grant" ? "/v1/consents/grant" : "/v1/consents/withdraw";
  const payload =
    op.kind === "grant"
      ? { scope: op.scope, version: op.version, text_hash: op.textHash, at: op.atIso }
      : { scope: op.scope, at: op.atIso };
  try {
    const response = await authedFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.ok;
  } catch {
    return false;
  }
}
