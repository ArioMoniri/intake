/**
 * INT-140 — Profilim: the data-subject surface and the learned-fact ledger.
 *
 * Acceptance (docs/backlog/issues.yaml): *"export/delete flows wired to DSAR;
 * learned facts editable/deletable with provenance"*.
 *
 * Same shape and the same reason as nav.spec.ts and appearance.spec.ts:
 * React Native has no DOM, so a rendered assertion needs a device. What CAN
 * be proved from the tree is that the wiring exists and that the dangerous
 * shortcuts are absent — the screens go through the two stores, the stores
 * go through the DSAR and overlay routes, the export document is never
 * fetched, and no fact value reaches a log. The behaviour of those stores is
 * proved next to them, in `src/lib/dsar/*.test.ts` and
 * `src/lib/learned/*.test.ts`; this file is the acceptance the backlog names.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

const DATA_SCREEN = "src/app/(tabs)/me/data.tsx";
const LEARNED_SCREEN = "src/app/(tabs)/me/learned.tsx";
const LEDGER = "src/components/LearnedLedger.tsx";

/* ------------------------------------------------------------------ */
/* Verileriniz is a real, reachable screen                            */
/* ------------------------------------------------------------------ */

describe("Verileriniz is reachable from Profilim", () => {
  it("has a route, registered in the tabs layout and in the nav map", () => {
    expect(file(DATA_SCREEN)).toContain("export default");
    expect(file("src/app/(tabs)/_layout.tsx")).toContain('name="me/data"');
    expect(readFileSync(join(__dirname, "nav.spec.ts"), "utf8")).toContain('"(tabs)/me/data.tsx"');
  });

  it("Profilim carries the entry row", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toContain('router.push("/(tabs)/me/data")');
    expect(me).toContain('t("me.data")');
  });

  it("fits the file-size rule the constitution sets", () => {
    for (const name of [DATA_SCREEN, LEARNED_SCREEN, LEDGER]) {
      expect(file(name).split("\n").length, name).toBeLessThan(500);
    }
  });
});

/* ------------------------------------------------------------------ */
/* Export / delete are wired to the DSAR routes                       */
/* ------------------------------------------------------------------ */

describe("the export and erasure flows are wired to DSAR", () => {
  const api = file("src/lib/dsar/api.ts");

  it("files an access request and an erasure against the m.11 routes", () => {
    expect(api).toContain('"/v1/me/dsar/export"');
    expect(api).toContain('"/v1/me/dsar/delete"');
    expect(api).toContain("/v1/me/dsar/delete/");
    expect(api).toContain('"/v1/me/dsar/requests"');
  });

  it("drives both from the screen through the store, never from the screen's own fetch", () => {
    const screen = file(DATA_SCREEN);
    expect(screen).toContain("fileExport");
    expect(screen).toContain("fileErasure");
    expect(screen).toContain("withdrawErasure");
    expect(screen).not.toContain("authedFetch");
  });

  it("makes erasure a two-step: arming it is not filing it", () => {
    const screen = file(DATA_SCREEN);
    expect(screen).toContain('t("data.delete.confirm")');
  });

  it("offers the withdrawal the grace exists for", () => {
    expect(file(DATA_SCREEN)).toContain("canWithdrawErasure");
  });

  /**
   * `GET /v1/me/dsar/export/{id}` marks the KVKK m.13 obligation ANSWERED at
   * the moment of delivery. This app cannot deliver: `docs/legal/strings.yaml`
   * does not exist (INT-210), so the server refuses to render the document at
   * all, and the app has no path that hands a file to the patient. Calling the
   * route would therefore record an answer nobody received. The absence is the
   * control, so it is asserted rather than assumed.
   */
  it("never fetches the export document", () => {
    for (const entry of TREE) {
      expect(entry.source, entry.name).not.toMatch(/dsar\/export\/\$\{/);
      expect(entry.source, entry.name).not.toMatch(/dsar\/export\/[a-z]/);
    }
  });

  it("says so on the screen instead of implying a copy is waiting", () => {
    expect(file(DATA_SCREEN)).toContain('t("data.export.notYet")');
  });
});

/* ------------------------------------------------------------------ */
/* Learned facts: editable, deletable, with provenance                */
/* ------------------------------------------------------------------ */

describe("the learned-fact ledger", () => {
  it("reads the overlay route, and edits and deletes per field", () => {
    const api = file("src/lib/learned/api.ts");
    expect(api).toContain('"/v1/me/learned"');
    expect(api).toContain('method: "PATCH"');
    expect(api).toContain('method: "DELETE"');
  });

  it("renders from the ledger store rather than straight off the account fixture", () => {
    const screen = file(LEARNED_SCREEN);
    expect(screen).toContain("useLearnedLedger");
    expect(screen).toContain("loadLearnedLedger");
    expect(screen).toContain("seedLearnedLedger");
  });

  it("shows where every fact came from, and when", () => {
    const ledger = file(LEDGER);
    expect(ledger).toContain("factSourceKey");
    expect(ledger).toContain('t("carried.recordedOn")');
  });

  it("says where each fact is held — the record, or this phone", () => {
    const ledger = file(LEDGER);
    expect(ledger).toContain('t("learned.origin.record")');
    expect(ledger).toContain('t("learned.origin.device")');
  });

  it("carries the per-field share scope and the delete control", () => {
    const ledger = file(LEDGER);
    expect(ledger).toContain('t("learned.shareLabel")');
    expect(ledger).toContain('t("learned.forget")');
    expect(ledger).toContain('t("learned.forget.confirm")');
  });

  it("points re-confirmation at the visit that can answer it, and answers none itself", () => {
    const ledger = file(LEDGER);
    expect(ledger).toContain('t("learned.reconfirm.footer")');
    // Invariant 12: this screen may not mint a confirmation. The overlay's
    // POST needs an origin and an observed instant the ledger does not hold,
    // and inventing either would be inventing a provenance.
    expect(file("src/lib/learned/api.ts")).not.toContain('method: "POST"');
  });

  it("never prints an internal fact key to the patient", () => {
    // `oyku.belirti_var` is a slot ref, not Turkish. It may key a list and
    // address a route; it may not be read out as if it were the fact.
    const ledger = file(LEDGER);
    const rendered = [...ledger.matchAll(/<AppText[^>]*>([\s\S]*?)<\/AppText>/g)].map((m) => m[1]);
    expect(rendered.length).toBeGreaterThan(2);
    expect(rendered.filter((body) => body.includes("fact.id"))).toEqual([]);
    expect(ledger).toContain('t("learned.value.unreadable")');
  });
});

/* ------------------------------------------------------------------ */
/* Invariant 6 — nothing here reaches a log                           */
/* ------------------------------------------------------------------ */

describe("no fact, request or identifier reaches a log", () => {
  it.each([
    "src/lib/dsar/api.ts",
    "src/lib/dsar/store.ts",
    "src/lib/dsar/requests.ts",
    "src/lib/learned/api.ts",
    "src/lib/learned/store.ts",
    "src/lib/learned/facts.ts",
    DATA_SCREEN,
    LEARNED_SCREEN,
    LEDGER,
  ])("%s writes nothing to the console and reports no server narrative", (name) => {
    const source = file(name);
    expect(source).not.toMatch(/\bconsole\.\w+/);
    expect(source).not.toContain("captureEvent");
  });
});

/* ------------------------------------------------------------------ */
/* Invariant 5 — every new string has a tr key, and en mirrors it     */
/* ------------------------------------------------------------------ */

describe("the copy this screen introduces", () => {
  const KEYS = [
    "me.data",
    "data.entry.sub",
    "data.guide.kicker",
    "data.guide.title",
    "data.guide.body",
    "data.export",
    "data.export.notYet",
    "data.due",
    "data.delete",
    "data.delete.confirm",
    "data.delete.withdraw",
    "data.delete.graceEnds",
    "data.delete.sharesCancelled",
    "data.requests",
    "data.kind.export",
    "data.kind.delete",
    "data.kind.rectify",
    "data.status.received",
    "data.status.scheduled",
    "data.status.completed",
    "data.status.cancelled",
    "data.status.overdue",
    "data.empty",
    "data.unsent",
    "data.deviceOnly",
    "learned.shareLabel",
    "learned.origin.record",
    "learned.origin.device",
    "learned.forget",
    "learned.forget.confirm",
    "learned.value.unreadable",
    "learned.reconfirm.footer",
    "learned.unsaved",
  ] as const;

  it.each(KEYS)("%s exists in tr and in en", (key) => {
    expect(tr[key], `tr is missing ${key}`).toBeTruthy();
    expect(en[key], `en is missing ${key}`).toBeTruthy();
  });

  it("says nothing in the sen register, and shouts nowhere", () => {
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/\b(?:sen|sana|senin)\b/iu);
      expect(tr[key], key).not.toBe(tr[key].toLocaleUpperCase("tr-TR"));
    }
  });

  /**
   * Invariant 18: consent and legal texts render only from `docs/legal/` with
   * hash binding. This screen governs the CONTROLS, so its copy names what a
   * button does and never states a right, a period or an obligation — the
   * m.11 notice itself is INT-210's, rendered from the legal tree.
   */
  it("states no legal period or obligation of its own", () => {
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/KVKK|kanun|madde|\b\d+\s*gün\b/iu);
    }
  });
});
