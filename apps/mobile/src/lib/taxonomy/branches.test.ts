/**
 * INT-134 — the bundled branch seed and the picker helpers.
 *
 * The seed is a hand-projection of packages/protocols/taxonomy/branches.yaml
 * (files/09 §1 source of truth). The first block parses that YAML from the
 * repo (its entries are one uniform line each) and pins the seed to it
 * FIELD FOR FIELD — the offline list and the served taxonomy cannot drift.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ALL_VISIT_TYPE_IDS,
  COMMON_BRANCH_IDS,
  SEED_BRANCHES,
  SEED_CLUSTERS,
  branchById,
  foldTr,
  intakeBranches,
  orderBranches,
  searchBranches,
  visibleBranches,
} from "./branches";

const YAML_PATH = join(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "packages",
  "protocols",
  "taxonomy",
  "branches.yaml",
);

interface YamlBranch {
  id: string;
  nameTr: string;
  cluster: string;
  allTypes: boolean;
  types: string[];
}

/** branches.yaml entries are one uniform flow-mapping line each. */
function parseYamlBranches(): { clusters: string[]; branches: YamlBranch[] } {
  const text = readFileSync(YAML_PATH, "utf8");
  const clusters: string[] = [];
  const branches: YamlBranch[] = [];
  let inClusters = false;
  let inBranches = false;
  for (const line of text.split("\n")) {
    if (line.startsWith("clusters:")) {
      inClusters = true;
      inBranches = false;
      continue;
    }
    if (line.startsWith("branches:")) {
      inBranches = true;
      inClusters = false;
      continue;
    }
    const entry = line.match(/^ {2}- \{id: ([a-z0-9_]+)(.*)\}\s*$/);
    if (!entry) {
      continue;
    }
    if (inClusters) {
      clusters.push(entry[1]);
      continue;
    }
    if (!inBranches) {
      continue;
    }
    const rest = entry[2];
    const name = rest.match(/name_tr: "([^"]+)"/);
    const cluster = rest.match(/cluster: ([a-z0-9_]+)/);
    const allTypes = rest.includes("visit_types: *all_visit_types");
    const listed = rest.match(/visit_types: \[([a-z_, ]*)\]/);
    if (!name || !cluster) {
      throw new Error(`unparseable branch line: ${line}`);
    }
    branches.push({
      id: entry[1],
      nameTr: name[1],
      cluster: cluster[1],
      allTypes,
      types: listed
        ? listed[1]
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
        : [],
    });
  }
  return { clusters, branches };
}

describe("seed sync against packages/protocols/taxonomy/branches.yaml", () => {
  const yaml = parseYamlBranches();

  it("carries every cluster id", () => {
    expect(SEED_CLUSTERS.map((c) => c.id)).toEqual(yaml.clusters);
    expect(yaml.clusters).toHaveLength(9);
  });

  it("carries every branch, field for field", () => {
    expect(yaml.branches.length).toBeGreaterThan(0);
    expect(SEED_BRANCHES.map((b) => b.id)).toEqual(yaml.branches.map((b) => b.id));
    for (const [index, branch] of yaml.branches.entries()) {
      const seeded = SEED_BRANCHES[index];
      expect(seeded.nameTr, branch.id).toBe(branch.nameTr);
      expect(seeded.cluster, branch.id).toBe(branch.cluster);
      const wanted = branch.allTypes ? [...ALL_VISIT_TYPE_IDS] : branch.types;
      expect([...seeded.visitTypes], branch.id).toEqual(wanted);
    }
  });

  it("the excluded cluster binds no pack and books no intake", () => {
    const excluded = SEED_CLUSTERS.find((c) => c.id === "excluded");
    expect(excluded).toMatchObject({ pack: null, intake: false });
    const medical = SEED_CLUSTERS.find((c) => c.id === "medical");
    expect(medical).toMatchObject({ pack: "cluster.medical", intake: true });
  });
});

describe("intakeBranches", () => {
  it("excludes the non-intake cluster (Acil Tıp books no pre-visit intake)", () => {
    const bookable = intakeBranches(SEED_BRANCHES, SEED_CLUSTERS);
    expect(bookable.some((b) => b.id === "acil_tip")).toBe(false);
    expect(bookable).toHaveLength(SEED_BRANCHES.length - 1);
  });
});

describe("orderBranches (02 §3: the ten highest-volume branches first)", () => {
  it("puts the common ten first, in the 02 order, then the rest by tr name", () => {
    const ordered = orderBranches(intakeBranches(SEED_BRANCHES, SEED_CLUSTERS));
    expect(ordered.slice(0, COMMON_BRANCH_IDS.length).map((b) => b.id)).toEqual([
      ...COMMON_BRANCH_IDS,
    ]);
    const rest = ordered.slice(COMMON_BRANCH_IDS.length).map((b) => b.nameTr);
    const sorted = [...rest].sort((a, b) => a.localeCompare(b, "tr"));
    expect(rest).toEqual(sorted);
  });

  it("the common ten are İç, Çocuk, Üroloji, Göz, KBB, Ortopedi, Kardiyoloji, Nöroloji, Kadın Doğum, Dermatoloji", () => {
    expect(COMMON_BRANCH_IDS).toEqual([
      "ic_hastaliklari",
      "cocuk_sagligi_ve_hastaliklari",
      "uroloji",
      "goz_hastaliklari",
      "kulak_burun_bogaz_hastaliklari",
      "ortopedi_ve_travmatoloji",
      "kardiyoloji",
      "noroloji",
      "kadin_hastaliklari_ve_dogum",
      "deri_ve_zuhrevi_hastaliklari",
    ]);
    for (const id of COMMON_BRANCH_IDS) {
      expect(branchById(SEED_BRANCHES, id), id).toBeDefined();
    }
  });
});

describe("searchBranches (Turkish-folded, accent- and case-insensitive)", () => {
  const bookable = intakeBranches(SEED_BRANCHES, SEED_CLUSTERS);

  it("folds Turkish letters both ways", () => {
    expect(foldTr("Üroloji")).toBe("uroloji");
    expect(foldTr("İç Hastalıkları")).toBe("ic hastaliklari");
    expect(foldTr("GÖĞÜS")).toBe("gogus");
  });

  it("finds branches from ASCII-typed queries", () => {
    const uro = searchBranches(bookable, "uroloji").map((b) => b.id);
    expect(uro).toContain("uroloji");
    expect(uro).toContain("cocuk_urolojisi");
    expect(searchBranches(bookable, "goz").map((b) => b.id)).toContain("goz_hastaliklari");
  });

  it("finds branches from Turkish-typed queries", () => {
    expect(searchBranches(bookable, "İÇ HAST").map((b) => b.id)).toContain("ic_hastaliklari");
    expect(searchBranches(bookable, "kadın").map((b) => b.id)).toContain(
      "kadin_hastaliklari_ve_dogum",
    );
  });

  it("keeps the common-first ordering inside results", () => {
    const results = searchBranches(bookable, "kardiyo").map((b) => b.id);
    expect(results[0]).toBe("kardiyoloji"); // common branch outranks the yan dal
    expect(results).toContain("cocuk_kardiyolojisi");
  });

  it("returns nothing for an unknown name, never throws", () => {
    expect(searchBranches(bookable, "cildiye")).toEqual([]);
  });
});

describe("visibleBranches (the picker never renders empty)", () => {
  const bookable = intakeBranches(SEED_BRANCHES, SEED_CLUSTERS);

  it("with no query shows the ordered head of the list", () => {
    const shown = visibleBranches(bookable, "", 12);
    expect(shown).toHaveLength(12);
    expect(shown[0].id).toBe("ic_hastaliklari");
  });

  it("with a query shows every match", () => {
    const shown = visibleBranches(bookable, "çocuk", 12);
    expect(shown.length).toBeGreaterThan(12); // yan dallar — the cap is for browsing, not search
    expect(shown.every((b) => foldTr(b.nameTr).includes("cocuk"))).toBe(true);
  });
});
