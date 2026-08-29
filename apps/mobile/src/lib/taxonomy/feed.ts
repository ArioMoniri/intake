/**
 * INT-134 — the taxonomy feed client.
 *
 * `GET /v1/taxonomy/branches` serves a VERSIONED projection of
 * packages/protocols/taxonomy/branches.yaml. This module parses that
 * payload strictly (anything outside the shape is refused, never coerced)
 * and resolves what the picker actually renders:
 *
 *     fresh server feed → cached last-good → the bundled seed
 *
 * so the branch picker is never empty. An empty `branches` array is itself
 * refused: that is an outage, not a taxonomy, and rendering it would tell
 * the patient their hospital has no clinics.
 */
import { ALL_VISIT_TYPE_IDS, SEED_BRANCHES, SEED_CLUSTERS } from "./branches";
import type { Branch, Cluster, VisitTypeId } from "./branches";

export interface TaxonomyFeed {
  /** sha256 of the served branches.yaml — the client's cache key. */
  version: string;
  /** HB-A11: the seed still awaits confirmation against the live MHRS list. */
  verifyLiveList: boolean;
  clusters: Cluster[];
  branches: Branch[];
}

export interface ResolvedBranchList {
  source: "server" | "cache" | "seed";
  version: string | null;
  clusters: readonly Cluster[];
  branches: readonly Branch[];
}

const VISIT_TYPES = new Set<string>(ALL_VISIT_TYPE_IDS);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseCluster(raw: unknown): Cluster | null {
  if (!isRecord(raw) || typeof raw.id !== "string" || typeof raw.intake !== "boolean") {
    return null;
  }
  if (raw.pack !== null && typeof raw.pack !== "string") {
    return null;
  }
  return { id: raw.id, pack: raw.pack, intake: raw.intake };
}

function parseBranch(raw: unknown): Branch | null {
  if (
    !isRecord(raw) ||
    typeof raw.id !== "string" ||
    typeof raw.name_tr !== "string" ||
    typeof raw.cluster !== "string" ||
    !Array.isArray(raw.visit_types)
  ) {
    return null;
  }
  // a visit type outside the closed files/09 §1 set is dropped, never guessed
  const visitTypes = raw.visit_types.filter(
    (value): value is VisitTypeId => typeof value === "string" && VISIT_TYPES.has(value),
  );
  return { id: raw.id, nameTr: raw.name_tr, cluster: raw.cluster, visitTypes };
}

/** Strict parse of the wire payload; null means "do not trust this". */
export function parseTaxonomyFeed(raw: unknown): TaxonomyFeed | null {
  if (
    !isRecord(raw) ||
    typeof raw.version !== "string" ||
    typeof raw.verify_live_list !== "boolean" ||
    !Array.isArray(raw.clusters) ||
    !Array.isArray(raw.branches) ||
    raw.branches.length === 0
  ) {
    return null;
  }
  const clusters: Cluster[] = [];
  for (const entry of raw.clusters) {
    const cluster = parseCluster(entry);
    if (cluster === null) {
      return null;
    }
    clusters.push(cluster);
  }
  const branches: Branch[] = [];
  for (const entry of raw.branches) {
    const branch = parseBranch(entry);
    if (branch === null) {
      return null;
    }
    branches.push(branch);
  }
  return {
    version: raw.version,
    verifyLiveList: raw.verify_live_list,
    clusters,
    branches,
  };
}

/** Fresh feed, else last-good, else the bundled seed — never empty. */
export function resolveBranchList(
  fetched: TaxonomyFeed | null,
  cached: TaxonomyFeed | null,
): ResolvedBranchList {
  if (fetched !== null) {
    return {
      source: "server",
      version: fetched.version,
      clusters: fetched.clusters,
      branches: fetched.branches,
    };
  }
  if (cached !== null) {
    return {
      source: "cache",
      version: cached.version,
      clusters: cached.clusters,
      branches: cached.branches,
    };
  }
  return {
    source: "seed",
    version: null,
    clusters: SEED_CLUSTERS,
    branches: SEED_BRANCHES,
  };
}
