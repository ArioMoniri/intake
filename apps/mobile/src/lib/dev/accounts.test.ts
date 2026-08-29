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

  /** Modules that import a VALUE (not just a type) out of lib/dev/accounts. */
  const valueImporters = walk(src).filter((file) => {
    if (file.endsWith(join("lib", "dev", "accounts.ts"))) {
      return false;
    }
    const text = readFileSync(file, "utf8");
    const importLine = text.match(/^import\s+(?!type\s)[^;]*?from\s+"[^"]*dev\/accounts";/ms);
    if (importLine === null) {
      return false;
    }
    // `import { type X, type Y } from` is a type-only import in disguise.
    const named = importLine[0].match(/\{([^}]*)\}/);
    if (named === null) {
      return true;
    }
    return named[1]
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .some((s) => !s.startsWith("type "));
  });

  it("exactly one screen imports the fixtures, and it is the welcome screen", () => {
    expect(valueImporters.map((f) => f.slice(src.length + 1))).toEqual([
      join("app", "(auth)", "welcome.tsx"),
    ]);
  });

  it("that screen renders them behind __DEV__, so release builds drop them", () => {
    const welcome = readFileSync(join(src, "app", "(auth)", "welcome.tsx"), "utf8");
    const guarded = welcome.slice(welcome.indexOf("__DEV__"));
    expect(welcome).toContain("__DEV__");
    expect(guarded).toContain("testAccounts.map");
    // the fixtures are never touched before the guard
    expect(welcome.slice(0, welcome.indexOf("__DEV__"))).not.toContain("testAccounts.map");
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
