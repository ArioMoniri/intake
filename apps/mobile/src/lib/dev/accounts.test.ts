import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { getTestAccount, testAccounts } from "./accounts";

describe("synthetic test accounts", () => {
  it("exist for both consent postures", () => {
    const wellbeingStates = new Set(testAccounts.map((a) => a.consents.wellbeing));
    expect(wellbeingStates).toEqual(new Set([true, false]));
  });

  it("carry no TCKN-shaped data anywhere (synthetic-only guarantee)", () => {
    const serialized = JSON.stringify(testAccounts);
    // A Turkish national id is 11 consecutive digits; nothing in the
    // fixtures may even look like one.
    expect(serialized).not.toMatch(/\d{11}/);
  });

  it("visit dates are ISO dates and statuses are from the 02 §5.1 ladder", () => {
    const ladder = new Set(["draft", "sent", "viewed", "filed"]);
    for (const account of testAccounts) {
      for (const visit of account.visits) {
        expect(visit.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        if (visit.noteStatus !== null) {
          expect(ladder.has(visit.noteStatus), visit.id).toBe(true);
        }
      }
    }
  });

  it("looks up by id and misses safely", () => {
    expect(getTestAccount("ayse")?.name).toBe("Ayşe Yılmaz");
    expect(getTestAccount("nobody")).toBeUndefined();
  });
});

// ---- INT-247 defect 1: the synthetic seed may never reach a real account ----

describe("the synthetic seed is dev-only and cannot leak into a real session", () => {
  const src = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");

  function walk(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        return walk(full);
      }
      return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
    });
  }

  const shipped = walk(src).filter((file) => !file.endsWith(join("lib", "dev", "accounts.ts")));
  const relativeTo = (file: string) => file.slice(src.length + 1);

  // INT-410 (audit F30). Metro does not tree-shake: a static import of the
  // seed, even one only a __DEV__ branch reads, puts every account in the
  // release bundle. tests/release/test_release_bundle_has_no_fixtures.py
  // proves the artefact; these two pin the source shape that produces it.
  it("no shipped module imports the seed statically, not even for a type", () => {
    const staticImporters = shipped.filter((file) =>
      /^\s*(?:import|export)\b[^;]*?\bfrom\s+["'][^"']*dev\/accounts["']/m.test(
        readFileSync(file, "utf8"),
      ),
    );
    expect(staticImporters.map(relativeTo)).toEqual([]);
  });

  it("the one way in is a lazy import() on the welcome screen", () => {
    const lazy = /\b(?:import|require)\(\s*["'][^"']*dev\/accounts["']\s*\)/g;
    const references = shipped.flatMap((file) =>
      (readFileSync(file, "utf8").match(lazy) ?? []).map(() => relativeTo(file)),
    );
    expect(references).toEqual([join("app", "(auth)", "welcome.tsx")]);
  });

  it("a real (otp) account starts with nothing carried forward", () => {
    // Pinned here rather than in session.test.ts so the seed and its
    // containment live in one file: the OTP path never reads a fixture.
    const session = readFileSync(join(src, "lib", "session.tsx"), "utf8");
    const otp = session.slice(session.indexOf("const signInOtp"));
    expect(otp.slice(0, otp.indexOf("}, []);"))).toContain("carriedFacts: []");
    expect(otp.slice(0, otp.indexOf("}, []);"))).not.toContain("getTestAccount");
  });

  it("every seeded carried fact declares its provenance and a source visit", () => {
    for (const account of testAccounts) {
      const visitIds = new Set(account.visits.map((v) => v.id));
      for (const fact of account.carriedFacts) {
        expect(fact.assertedAt, fact.id).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(fact.text.trim().length, fact.id).toBeGreaterThan(0);
        // no orphan provenance: the fact points at a visit the fixture has
        expect(fact.sourceVisitId === null || visitIds.has(fact.sourceVisitId), fact.id).toBe(true);
      }
    }
  });
});
