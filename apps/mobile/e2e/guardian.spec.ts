/**
 * Guardian, companion and proxy acceptance (INT-133), pinned as source facts
 * plus live reducer behaviour — the nav.spec.ts technique.
 *
 * Pins (issue acceptance, verbatim): "under-18 only via guardian account
 * with guardian consent; adolescent private-section policy implemented per
 * 06 §6; proxy-reported flag on every record".
 *
 * The load-bearing negatives are as important as the positives here, so they
 * are pinned too: the device never decides an age band, the client never
 * sends `proxy_reported`, no self-consent or emancipation affordance exists
 * for a minor, and the HB-L20 policy-row ids never reach the screen — a
 * refusal that printed `adolescent_self_consent` would tell a waiting room
 * that this patient is fourteen.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  attributionBody,
  ATTRIBUTIONS,
  resolveAttribution,
  SELF_ALONE,
} from "../src/lib/profile/attribution";
import type { AttributionInput } from "../src/lib/profile/attribution";
import {
  isTerminalRefusal,
  parseProfile,
  PROFILE_FALLBACK,
  refusalCopyKey,
  refusalOf,
} from "../src/lib/profile/refusals";
import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const SRC = join(__dirname, "..", "src");
const APP = join(SRC, "app");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const companion = (over: Partial<AttributionInput> = {}): AttributionInput => ({
  role: "companion",
  speaker: "companion",
  acknowledged: true,
  thirdPartyPresent: false,
  ...over,
});

describe("attribution: the three 02 §3 values, derived not asserted", () => {
  it("exposes exactly the three values, in copy order", () => {
    expect([...ATTRIBUTIONS]).toEqual(["self_report", "proxy_report", "assisted_self_report"]);
  });

  it("the default session is the patient, alone, self-reported", () => {
    const outcome = resolveAttribution(SELF_ALONE);
    expect(outcome.attribution).toBe("self_report");
    expect(outcome.proxyReported).toBe(false);
    expect(outcome.safeguardingAsked).toBe(true);
    expect(outcome.ready).toBe(true);
  });

  it("a companion answering is proxy-reported (06 §6)", () => {
    expect(resolveAttribution(companion()).proxyReported).toBe(true);
  });

  it("the patient answering on a companion device is assisted, not proxy", () => {
    const outcome = resolveAttribution(companion({ speaker: "patient" }));
    expect(outcome.attribution).toBe("assisted_self_report");
    expect(outcome.proxyReported).toBe(false);
    // 02 §3: a third party is present BY DEFINITION
    expect(outcome.thirdPartyPresent).toBe(true);
  });

  it("a companion session is not ready until the role is acknowledged", () => {
    expect(resolveAttribution(companion({ acknowledged: false })).ready).toBe(false);
    expect(resolveAttribution(companion()).ready).toBe(true);
  });

  it("the wire body carries the facts and NOT the conclusion", () => {
    const body = attributionBody(companion());
    expect(Object.keys(body).sort()).toEqual([
      "acknowledged",
      "role",
      "speaker",
      "third_party_present",
    ]);
    // a client-settable proxy flag would be a client-clearable one
    expect(JSON.stringify(body)).not.toContain("proxy_reported");
  });
});

describe("13 §13: a third party is a confound, not a feature", () => {
  it("a declared third party sends sensitive sections to text and stops safeguarding", () => {
    const outcome = resolveAttribution({ ...SELF_ALONE, thirdPartyPresent: true });
    expect(outcome.sensitiveTextOnly).toBe(true);
    expect(outcome.safeguardingAsked).toBe(false);
  });

  it("safeguarding is never asked of a proxy, declared third party or not", () => {
    expect(resolveAttribution(companion()).safeguardingAsked).toBe(false);
    expect(resolveAttribution(companion({ thirdPartyPresent: true })).safeguardingAsked).toBe(
      false,
    );
  });

  it("no companion path ever leaves safeguarding on", () => {
    for (const speaker of ["patient", "companion"] as const) {
      for (const thirdPartyPresent of [true, false]) {
        const outcome = resolveAttribution(companion({ speaker, thirdPartyPresent }));
        expect(outcome.safeguardingAsked).toBe(false);
        expect(outcome.sensitiveTextOnly).toBe(true);
      }
    }
  });
});

describe("under-18 runs through a guardian account, and that door is shut", () => {
  it("the companion screen offers no guardian flow, only the closed door", () => {
    const screen = read(APP, "(tabs)/me/companion.tsx");
    expect(screen).toContain('t("companion.guardian.unavailable")');
    expect(screen).toContain('t("companion.guardian.body")');
    // no form, no start button, no route to one
    expect(screen).not.toMatch(/router\.push\([^)]*guardian/i);
  });

  it("the guardian refusal is terminal on the device; only the ack is recoverable", () => {
    expect(isTerminalRefusal("guardian_consent_required")).toBe(true);
    expect(isTerminalRefusal("dob_unverified")).toBe(true);
    expect(isTerminalRefusal("jurisdiction_unsupported")).toBe(true);
    expect(isTerminalRefusal("proxy_acknowledgement_required")).toBe(false);
  });

  it("every age-gate refusal code maps to copy that exists in both catalogues", () => {
    for (const code of [
      "guardian_consent_required",
      "dob_unverified",
      "jurisdiction_unsupported",
      "proxy_acknowledgement_required",
    ] as const) {
      const refusal = refusalOf({ error: code, scope: "core" });
      expect(refusal).toBe(code);
      const key = refusalCopyKey(code);
      expect(tr[key]).toBeTruthy();
      expect(en[key]).toBeTruthy();
    }
  });

  it("an unknown refusal is not guessed at", () => {
    expect(refusalOf({ error: "something_new", scope: "core" })).toBeNull();
    expect(refusalOf(null)).toBeNull();
    expect(refusalOf("consent_required")).toBeNull();
  });

  it("an unreachable profile route falls back closed", () => {
    expect(PROFILE_FALLBACK.guardianFlowAvailable).toBe(false);
    expect(PROFILE_FALLBACK.proxyAcknowledgementRequired).toBe(true);
  });

  it("a served profile body is parsed conservatively", () => {
    expect(
      parseProfile({
        attributions: ["self_report", "proxy_report", "assisted_self_report"],
        proxy_acknowledgement_required: true,
        guardian_flow_available: false,
      })?.guardianFlowAvailable,
    ).toBe(false);
    // absent fields read as the closed answer, never the permissive one
    const sparse = parseProfile({ attributions: ["self_report"] });
    expect(sparse?.proxyAcknowledgementRequired).toBe(true);
    expect(sparse?.guardianFlowAvailable).toBe(false);
    // an attribution this build cannot explain is dropped, not rendered
    expect(parseProfile({ attributions: ["self_report", "something_new"] })?.attributions).toEqual([
      "self_report",
    ]);
    // and a body with nothing usable is not a capability set
    expect(parseProfile({ attributions: [] })).toBeNull();
    expect(parseProfile(null)).toBeNull();
    expect(parseProfile("profile")).toBeNull();
  });
});

describe("the device decides nothing about age, and leaks nothing about it", () => {
  it("no screen or profile module computes an age band or reads a date of birth", () => {
    const suspects = walk(SRC).filter(
      (path) =>
        (path.endsWith(".ts") || path.endsWith(".tsx")) &&
        (path.includes(join("lib", "profile")) || path.includes(join("me", "companion"))),
    );
    expect(suspects.length).toBeGreaterThan(0);
    for (const path of suspects) {
      const source = readFileSync(path, "utf8");
      expect(source).not.toMatch(/date_of_birth|birthDate|dateOfBirth|ageYears|getFullYear/);
      // the bands themselves are server vocabulary
      expect(source).not.toMatch(/"(child|adolescent|adult)"/);
    }
  });

  it("no HB-L20 policy-row id ever reaches the copy catalogues", () => {
    for (const catalogue of [tr, en]) {
      const blob = JSON.stringify(catalogue);
      for (const row of [
        "adolescent_self_consent",
        "emancipation",
        "guardian_link_basis",
        "guardian_relationship_proof",
        "unverified_dob",
        "jurisdiction_tr_only",
        "adolescent_private_guardian_default",
        "dob_collection_mandatory",
      ]) {
        expect(blob).not.toContain(row);
      }
    }
  });

  it("no self-consent or emancipation affordance exists anywhere in the app", () => {
    for (const path of walk(SRC).filter((p) => p.endsWith(".ts") || p.endsWith(".tsx"))) {
      const source = readFileSync(path, "utf8");
      expect(source).not.toMatch(/ergin\s*kıl|emancipat|selfConsent|self_consent/i);
    }
  });
});

describe("06 §6: the adolescent-private section is stated, not silently withheld", () => {
  it("the screen carries the clinic-policy rule and the withhold default", () => {
    const screen = read(APP, "(tabs)/me/companion.tsx");
    expect(screen).toContain('t("companion.private.body")');
    const body = tr["companion.private.body"];
    // delivered to the clinician; guardian visibility follows the clinic's
    // written policy; no recorded policy means not shown
    expect(body).toContain("hekime");
    expect(body).toContain("politika");
    expect(body).toMatch(/gösterilmez/);
  });
});

describe("the proxy acknowledgement is an acknowledgement of role, never of representation", () => {
  it("the copy says so in both languages", () => {
    expect(tr["companion.ack.notProof"]).toMatch(/karar verme hakkınız olduğu anlamına gelmez/);
    expect(en["companion.ack.notProof"]).toMatch(/does not mean you may decide/);
  });

  it("changing the role clears any standing acknowledgement", async () => {
    const store = await import("../src/lib/profile/store");
    store.resetCompanionDeclaration();
    // two taps, as the screen does them: pick the role, then acknowledge —
    // a role change always lands on an unacknowledged state
    store.setCompanionDeclaration({ role: "companion" });
    expect(store.companionDeclaration().acknowledged).toBe(false);
    store.setCompanionDeclaration({ acknowledged: true });
    expect(store.companionDeclaration().acknowledged).toBe(true);
    store.setCompanionDeclaration({ role: "self" });
    expect(store.companionDeclaration().acknowledged).toBe(false);
    // and a self role can never carry a companion speaker
    expect(store.companionDeclaration().speaker).toBe("patient");
    store.resetCompanionDeclaration();
  });

  it("the declaration is session-only: nothing writes it to the device", () => {
    const source = read(SRC, "lib", "profile", "store.ts");
    expect(source).not.toMatch(/AsyncStorage|SecureStore|expo-file-system|localStorage/);
  });
});

describe("the proxy flag is on the record, and the copy explains it before the session", () => {
  it("the note-facing consequence is stated up front", () => {
    // INT-588: the screen lists the effects through the build-aware helper, so
    // a release build (no spoken questions) does not list the text-only one.
    const screen = read(APP, "(tabs)/me/companion.tsx");
    expect(screen).toContain("companionEffectKeys(outcome, currentBuildMode())");
    const helper = read(SRC, "lib", "buildCopy.ts");
    expect(helper).toContain('"companion.effect.proxy"');
    expect(helper).toContain('"companion.effect.textOnly"');
    expect(helper).toContain('"companion.effect.noSafeguarding"');
  });

  it("the entry row exists on Profilim", () => {
    const me = read(APP, "(tabs)/me/index.tsx");
    expect(me).toContain('t("me.companion")');
    expect(me).toContain('router.push("/(tabs)/me/companion")');
  });
});
