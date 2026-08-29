/**
 * INT-134 — the taxonomy feed client: strict parse of the versioned server
 * payload, and the last-good/seed fallback that keeps the picker from ever
 * rendering empty.
 */
import { describe, expect, it } from "vitest";

import { SEED_BRANCHES } from "./branches";
import { parseTaxonomyFeed, resolveBranchList } from "./feed";

const WIRE_FEED = {
  version: "a".repeat(64),
  verify_live_list: true,
  clusters: [
    { id: "medical", pack: "cluster.medical", intake: true },
    { id: "excluded", pack: null, intake: false },
  ],
  branches: [
    {
      id: "kardiyoloji",
      name_tr: "Kardiyoloji",
      cluster: "medical",
      visit_types: ["first", "followup"],
    },
    { id: "acil_tip", name_tr: "Acil Tıp", cluster: "excluded", visit_types: [] },
  ],
};

describe("parseTaxonomyFeed", () => {
  it("parses the wire shape into the picker shape", () => {
    const feed = parseTaxonomyFeed(WIRE_FEED);
    expect(feed).not.toBeNull();
    expect(feed?.version).toBe("a".repeat(64));
    expect(feed?.branches[0]).toEqual({
      id: "kardiyoloji",
      nameTr: "Kardiyoloji",
      cluster: "medical",
      visitTypes: ["first", "followup"],
    });
    expect(feed?.clusters[1]).toEqual({ id: "excluded", pack: null, intake: false });
  });

  it("drops visit types outside the files/09 §1 set instead of guessing", () => {
    const feed = parseTaxonomyFeed({
      ...WIRE_FEED,
      branches: [
        {
          id: "kardiyoloji",
          name_tr: "Kardiyoloji",
          cluster: "medical",
          visit_types: ["first", "walk_in"],
        },
      ],
    });
    expect(feed?.branches[0].visitTypes).toEqual(["first"]);
  });

  it("refuses malformed payloads outright", () => {
    expect(parseTaxonomyFeed(null)).toBeNull();
    expect(parseTaxonomyFeed({})).toBeNull();
    expect(parseTaxonomyFeed({ ...WIRE_FEED, version: 7 })).toBeNull();
    expect(parseTaxonomyFeed({ ...WIRE_FEED, branches: "yok" })).toBeNull();
    expect(
      parseTaxonomyFeed({ ...WIRE_FEED, branches: [{ id: "x", cluster: "medical" }] }),
    ).toBeNull();
  });

  it("refuses an EMPTY branch list — that is an outage, not a taxonomy", () => {
    expect(parseTaxonomyFeed({ ...WIRE_FEED, branches: [] })).toBeNull();
  });
});

describe("resolveBranchList — the picker is never empty", () => {
  const fetched = parseTaxonomyFeed(WIRE_FEED);

  it("serves the fresh feed when the fetch succeeded", () => {
    const list = resolveBranchList(fetched, null);
    expect(list.source).toBe("server");
    expect(list.version).toBe("a".repeat(64));
    expect(list.branches).toHaveLength(2);
  });

  it("serves the last-good feed when the fetch failed", () => {
    const list = resolveBranchList(null, fetched);
    expect(list.source).toBe("cache");
    expect(list.branches).toHaveLength(2);
  });

  it("falls back to the bundled seed when nothing else exists", () => {
    const list = resolveBranchList(null, null);
    expect(list.source).toBe("seed");
    expect(list.version).toBeNull();
    expect(list.branches).toEqual(SEED_BRANCHES);
  });
});
