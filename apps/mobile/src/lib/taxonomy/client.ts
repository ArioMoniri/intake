/**
 * INT-134 — fetching the versioned taxonomy feed.
 *
 * `GET /v1/taxonomy/branches` over the INT-131 authedFetch. The last good
 * feed is kept in module memory for the session, so a later screen opens on
 * the cached list instead of an empty one while the refetch is in flight; a
 * failed fetch falls back to that cache and finally to the bundled seed
 * (`resolveBranchList`). No branch data is written to disk: the taxonomy is
 * a committed artefact, not patient data, and the bundled seed already
 * covers the cold-start case.
 */
import { authedFetch } from "@/lib/auth/api";

import { parseTaxonomyFeed, resolveBranchList } from "./feed";
import type { ResolvedBranchList, TaxonomyFeed } from "./feed";

let lastGood: TaxonomyFeed | null = null;

/** What the picker can render right now, without waiting on the network. */
export const cachedTaxonomy: ResolvedBranchList = resolveBranchList(null, null);

export function currentTaxonomy(): ResolvedBranchList {
  return resolveBranchList(null, lastGood);
}

/**
 * Fetch the feed; on any failure resolve to last-good, then to the seed.
 * Never throws and never returns an empty list — an empty branch picker
 * would tell the patient their hospital has no clinics.
 */
export async function loadTaxonomy(): Promise<ResolvedBranchList> {
  let fetched: TaxonomyFeed | null = null;
  try {
    const response = await authedFetch("/v1/taxonomy/branches");
    if (response.ok) {
      fetched = parseTaxonomyFeed(await response.json().catch(() => null));
    }
  } catch {
    fetched = null; // offline, unconfigured server, refused session — all fall back
  }
  if (fetched !== null) {
    lastGood = fetched;
  }
  return resolveBranchList(fetched, lastGood);
}
