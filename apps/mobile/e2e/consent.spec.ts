/**
 * Consent UI acceptance (INT-132), pinned as source facts — the same
 * technique as auth.spec.ts: the purpose registry, the reducer and the
 * screens ARE the KVKK m.6 consent-quality posture, so a pre-ticked switch,
 * a bundled purpose or a silently re-granted version bump fails here before
 * any device run would notice.
 *
 * Pins (issue acceptance, verbatim): "texts loaded from docs/legal with
 * hash binding; unbundled toggles; withdrawal instant; re-prompt on version
 * change; Turkish primary".
 *
 * The consent TEXTS themselves do not exist yet (docs/legal/consents is
 * INT-210, owner+counsel). The UI therefore fails closed: a purpose without
 * a loaded text renders the calm pending state and CANNOT be granted —
 * matching the server, which refuses grants without texts. Fixture texts
 * live only inside test files, never in docs/legal and never in the app.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import { visibleTabs } from "../src/lib/session";
import {
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  viewOf,
  withdraw,
  type TextEntry,
} from "../src/lib/consent/ledger";
import { PURPOSES, purposeDef } from "../src/lib/consent/purposes";

const APP = join(__dirname, "..", "src", "app");
const SRC = join(__dirname, "..", "src");
const REPO = join(__dirname, "..", "..", "..");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const loaded = (version: string, hash: string): TextEntry => ({
  status: "loaded",
  text: { version, textHash: hash, body: "Deneme metni — yalnızca test." },
});

describe("routes: İzinleriniz from Profilim + first-run after onboarding (02 §4)", () => {
  it.each([
    "(auth)/consent.tsx",
    "(tabs)/me/consents/index.tsx",
    "(tabs)/me/consents/[purpose].tsx",
  ])("%s exists", (route) => {
    expect(() => read(APP, route)).not.toThrow();
  });

  it("otp verify routes the fresh account to the consent first-run, not the shell", () => {
    const otp = read(APP, "(auth)/otp.tsx");
    expect(otp).toContain("/(auth)/consent");
  });

  it("first-run continues into the shell without granting anything", () => {
    const firstRun = read(APP, "(auth)/consent.tsx");
    expect(firstRun).toContain("/(tabs)/today");
    // the continue CTA never blocks on a consent decision
    expect(firstRun).toContain('t("consent.firstRun.continue")');
  });

  it("Profilim links to İzinleriniz", () => {
    const me = read(APP, "(tabs)/me/index.tsx");
    expect(me).toContain("/(tabs)/me/consents");
  });

  it("both consent screens are registered in the tabs shell", () => {
    const layout = read(APP, "(tabs)/_layout.tsx");
    expect(layout).toContain('name="me/consents/index"');
    expect(layout).toContain('name="me/consents/[purpose]"');
  });
});

describe("06 §2 purpose structure — closed list, registry order", () => {
  it("purposes are exactly the 06 §2 togglable set, in 06 §2 order", () => {
    // `share` is deliberately absent: a share consent is parameterised per
    // visit ({recipient, visit, sections, expiry}, asked in Review & send);
    // a bare share toggle here would be the bundled consent 06 §2 forbids.
    expect(PURPOSES.map((p) => p.id)).toEqual([
      "core",
      "voice",
      "wellbeing",
      "lane:affect",
      "lane:linguistic",
      "documents",
      "learning:personal",
      "learning:service_improvement",
      "satisfaction",
      "research",
    ]);
  });

  it("lane:acoustic is not a purpose (06 §2.4: an ICF, not a toggle)", () => {
    expect(purposeDef("lane:acoustic")).toBeNull();
    expect(Object.keys(tr).some((key) => key.includes("acoustic"))).toBe(false);
  });

  it("core is an açık rıza toggle like the others, on its explicit basis (INT-537)", () => {
    // the server registry makes core açık rıza and visits + notes require it,
    // so it is granted against its text and withdrawn in one tap — never a
    // piece of information the patient cannot act on
    const core = purposeDef("core")!;
    expect(core.ui).toBe("toggle");
    expect(core.basis).toBe("explicit_consent");
    expect(core.basisKey).toBe("consent.basis.explicit");
    expect(core.defaultGranted).toBe(false);
    // no text, no grant; with its text, a hash-bound grant
    const state = freshLedger();
    expect(grant(state, "core", "2026-10-16T00:00:00Z").flipped).toEqual([]);
    const texted = applyTexts(state, { core: loaded("v1", "c".repeat(64)) });
    const granted = grant(texted, "core", "2026-10-16T00:00:00Z");
    expect(granted.flipped).toEqual(["core"]);
    expect(granted.state.records.core.boundHash).toBe("c".repeat(64));
    expect(withdraw(granted.state, "core", "2026-10-16T00:01:00Z").flipped).toEqual(["core"]);
  });

  it("core withdrawal cascades to every other purpose — the server's dependents_of(core)", () => {
    // packages/intake_platform consent/registry.py: "core reaches every other
    // purpose — a withdrawn service consent leaves nothing to ride on"
    expect(purposeDef("core")!.cascadeChildren).toEqual(
      PURPOSES.filter((p) => p.id !== "core").map((p) => p.id),
    );
  });

  it("no purpose is information-only any more, and its chrome is gone", () => {
    expect(PURPOSES.map((p) => p.ui).filter((ui) => ui !== "toggle" && ui !== "optout")).toEqual(
      [],
    );
    expect(Object.keys(tr)).not.toContain("consent.basis.service");
    expect(Object.keys(tr)).not.toContain("consent.state.service");
    for (const file of [
      join(SRC, "components", "ConsentList.tsx"),
      join(APP, "(auth)", "consent.tsx"),
      join(APP, "(tabs)", "me", "consents", "index.tsx"),
      join(APP, "(tabs)", "me", "consents", "[purpose].tsx"),
    ]) {
      expect(read(file), file).not.toContain('"info"');
    }
  });

  it("the consent screens mirror a core change into the session like any other", () => {
    for (const file of [
      join(APP, "(auth)", "consent.tsx"),
      join(APP, "(tabs)", "me", "consents", "index.tsx"),
      join(APP, "(tabs)", "me", "consents", "[purpose].tsx"),
    ]) {
      expect(read(file), file).not.toContain('key !== "core"');
    }
  });

  it("lane sub-toggles nest under voice; lane:linguistic stays independent", () => {
    expect(purposeDef("lane:affect")!.parent).toBe("voice");
    expect(purposeDef("lane:linguistic")!.parent).toBe("voice"); // UI nesting only
    expect(purposeDef("voice")!.cascadeChildren).toEqual(["lane:affect"]);
    expect(purposeDef("voice")!.cascadeChildren).not.toContain("lane:linguistic");
  });

  it("learning purposes are default-on OPT-OUT with their honest non-consent bases", () => {
    const personal = purposeDef("learning:personal")!;
    const service = purposeDef("learning:service_improvement")!;
    expect(personal.ui).toBe("optout");
    expect(personal.basis).toBe("service_performance");
    expect(personal.defaultGranted).toBe(true);
    expect(service.ui).toBe("optout");
    expect(service.basis).toBe("deidentified_optout");
    expect(service.defaultGranted).toBe(true);
  });
});

describe("no pre-ticking anywhere (KVKK m.6 unbundling)", () => {
  it("every explicit-consent purpose defaults OFF — no representable pre-tick", () => {
    for (const purpose of PURPOSES) {
      if (purpose.basis === "explicit_consent") {
        expect(purpose.defaultGranted, purpose.id).toBe(false);
      }
    }
  });

  it("exactly the two learning purposes are default-on", () => {
    const defaultOn = PURPOSES.filter((p) => p.defaultGranted).map((p) => p.id);
    expect(defaultOn).toEqual(["learning:personal", "learning:service_improvement"]);
  });

  it("a fresh account starts with every explicit purpose off and an empty queue", () => {
    const state = freshLedger();
    for (const view of viewOf(state)) {
      if (view.basis === "explicit_consent") {
        expect(view.allowed, view.id).toBe(false);
      }
    }
    expect(state.queue).toEqual([]);
  });

  it("seeding never enqueues server ops (seeds are state, not decisions)", () => {
    const seeded = seedFromSession({
      core: true,
      voice: true,
      wellbeing: true,
      documents: true,
      health: false,
    });
    expect(seeded.queue).toEqual([]);
  });
});

describe("missing text fails closed (invariant 18: no text, no grant)", () => {
  it("granting a purpose whose text is missing changes nothing", () => {
    const state = freshLedger();
    const result = grant(state, "wellbeing", "2026-08-28T00:00:00Z");
    expect(result.flipped).toEqual([]);
    expect(result.state).toBe(state);
    expect(result.state.queue).toEqual([]);
  });

  it("the pending state is a real tr string used by the screens", () => {
    expect(tr["consent.state.pending"]).toBe("Metin hazırlanıyor");
    const list = read(SRC, "components", "ConsentList.tsx");
    expect(list).toContain("pending_text");
    const detail = read(APP, "(tabs)/me/consents/[purpose].tsx");
    expect(detail).toContain('t("consent.pending.body")');
  });

  it("no consent text is bundled into the app — texts arrive from the loader only", () => {
    for (const file of walk(SRC)) {
      if (!/\.(ts|tsx)$/.test(file)) continue;
      expect(read(file), file).not.toContain("consent_text_version");
    }
    // the legal tree is INT-210's human deliverable; the app must not ship one
    expect(existsSync(join(REPO, "docs", "legal", "consents"))).toBe(false);
  });

  it("the detail screen renders the loader payload body, never catalog copy", () => {
    const detail = read(APP, "(tabs)/me/consents/[purpose].tsx");
    expect(detail).toContain(".body");
    expect(detail).toContain(".version");
    expect(detail).toContain(".textHash");
  });
});

describe("versioning: stale grant → yeniden onay gerekli, never a silent re-grant", () => {
  const granted = () => {
    const withText = applyTexts(freshLedger(), {
      wellbeing: loaded("v1", "a".repeat(64)),
    });
    return grant(withText, "wellbeing", "2026-08-28T00:00:00Z").state;
  };

  it("a version bump flips the purpose to stale and stops honouring it", () => {
    const bumped = applyTexts(granted(), { wellbeing: loaded("v2", "b".repeat(64)) });
    const view = viewOf(bumped).find((v) => v.id === "wellbeing")!;
    expect(view.allowed).toBe(false);
    expect(view.display).toBe("stale");
  });

  it("a version bump alone never re-grants: only an explicit grant rebinds", () => {
    const bumped = applyTexts(granted(), { wellbeing: loaded("v2", "b".repeat(64)) });
    // no action → still stale; explicit grant → bound to the NEW version
    const regranted = grant(bumped, "wellbeing", "2026-08-28T00:01:00Z").state;
    expect(viewOf(regranted).find((v) => v.id === "wellbeing")!.allowed).toBe(true);
    expect(regranted.records["wellbeing"].boundVersion).toBe("v2");
  });

  it("the stale state is a real tr string and the detail screen re-prompts", () => {
    expect(tr["consent.state.stale"]).toBe("Yeniden onay gerekli");
    const detail = read(APP, "(tabs)/me/consents/[purpose].tsx");
    expect(detail).toContain('t("consent.stale.body")');
  });
});

describe("withdrawal: instant, cascading, mirrored into the session gate", () => {
  it("withdrawing voice drags lane:affect down in the same pass; linguistic survives", () => {
    let state = applyTexts(freshLedger(), {
      voice: loaded("v1", "1".repeat(64)),
      "lane:affect": loaded("v1", "2".repeat(64)),
      "lane:linguistic": loaded("v1", "3".repeat(64)),
    });
    state = grant(state, "voice", "2026-08-28T00:00:00Z").state;
    state = grant(state, "lane:affect", "2026-08-28T00:00:01Z").state;
    state = grant(state, "lane:linguistic", "2026-08-28T00:00:02Z").state;
    const result = withdraw(state, "voice", "2026-08-28T00:01:00Z");
    expect(result.flipped).toEqual(["voice", "lane:affect"]);
    const views = viewOf(result.state);
    expect(views.find((v) => v.id === "lane:affect")!.allowed).toBe(false);
    expect(views.find((v) => v.id === "lane:linguistic")!.allowed).toBe(true);
  });

  it("the İzinleriniz screen flips the session consents in the same handler", () => {
    const screen = read(APP, "(tabs)/me/consents/index.tsx");
    expect(screen).toContain("withdrawLocal");
    expect(screen).toContain("setConsent(");
  });

  it("the detail screen states that withdrawal takes effect immediately", () => {
    const detail = read(APP, "(tabs)/me/consents/[purpose].tsx");
    expect(detail).toContain('t("consent.detail.withdrawNote")');
    expect(tr["consent.detail.withdrawNote"]).toContain("hemen");
  });
});

describe("optional purposes never gate core flows (02 §7)", () => {
  it("today/visits/records/me stand with every consent off", () => {
    const tabs = visibleTabs({
      core: false,
      voice: false,
      wellbeing: false,
      documents: false,
      health: false,
    });
    expect(tabs).toEqual(["today", "visits", "records", "me"]);
  });

  it("the existing intake and review flows do not import the consent ledger", () => {
    for (const route of [
      "(tabs)/visits/[visitId]/intake.tsx",
      "(tabs)/visits/[visitId]/review.tsx",
      "(tabs)/today.tsx",
    ]) {
      expect(read(APP, route), route).not.toContain("lib/consent");
    }
  });
});

describe("Turkish primary; en mirror; NO legal copy in the catalogs", () => {
  const consentKeys = Object.keys(tr).filter((key) => key.startsWith("consent.")) as MessageKey[];

  it("every consent key exists in both catalogs (tr is the source of truth)", () => {
    expect(consentKeys.length).toBeGreaterThan(20);
    for (const key of consentKeys) {
      expect(tr[key].trim().length, key).toBeGreaterThan(0);
      expect(en[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("catalog strings are UI chrome, never consent-text bodies", () => {
    // legal texts are paragraphs citing the statute; chrome is short and
    // never names the law — the text itself arrives from docs/legal only
    for (const key of Object.keys(tr) as MessageKey[]) {
      expect(tr[key], key).not.toMatch(/6698|KVKK/);
      expect(en[key], key).not.toMatch(/6698|KVKK/);
    }
    for (const key of consentKeys) {
      expect(tr[key].length, key).toBeLessThanOrEqual(240);
    }
  });

  it("the purpose rows resolve label, who-sees-what and basis through tr keys", () => {
    for (const purpose of PURPOSES) {
      expect(tr[purpose.labelKey], purpose.id).toBeTruthy();
      expect(tr[purpose.whoKey], purpose.id).toBeTruthy();
      expect(tr[purpose.basisKey], purpose.id).toBeTruthy();
    }
  });
});
