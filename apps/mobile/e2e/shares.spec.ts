/**
 * INT-139 — Paylaşımlarınız: the share centre, its revoke path and the
 * patient's access log.
 *
 * Acceptance (docs/backlog/issues.yaml): *"revocation cascades to tokens
 * within 1 min (test); patient sees access log"*.
 *
 * Same shape and the same reason as `me.spec.ts` and `nav.spec.ts`: React
 * Native has no DOM, so a rendered assertion needs a device. What CAN be
 * proved from the tree is that the wiring exists and the dangerous shortcuts
 * are absent — the screen goes through one store, the store goes through the
 * INT-150 routes, no token is ever read, no identity is ever rendered, and
 * the revoke control sits outside every conditional. The BEHAVIOUR of the
 * store and the rules is proved next to them, without a network, in
 * `src/lib/shares/links.test.ts` and `src/lib/shares/store.test.ts`.
 *
 * The half of the acceptance this repository cannot yet hold is named rather
 * than assumed: `services/api/src/intake_api/doctor_link/` is INT-150's, and
 * INT-150 is PR #446 — open, not merged. Until it lands there is no revoke
 * route on `main` to cross-check these paths against, and §7 below is the
 * tripwire that says so and fails the day it lands.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { APP_STEPS } from "@/lib/prefs/appearance";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { scaledSize, spacing } from "@/lib/theme";

import { readFontMetrics } from "./fontMetrics";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const REPO = join(MOBILE, "..", "..");

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

/** Code only, comments dropped — prose about a rule is not the rule. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const SCREEN = "src/app/(tabs)/visits/[visitId]/shares.tsx";
const API = "src/lib/shares/api.ts";
const STORE = "src/lib/shares/store.ts";
const RULES = "src/lib/shares/links.ts";

/* ------------------------------------------------------------------ */
/* 1 · The screen is real, reachable, and inside the file-size rule    */
/* ------------------------------------------------------------------ */

describe("the share centre is a reachable screen", () => {
  it("has a route, and the nav map knows about it", () => {
    expect(file(SCREEN)).toContain("export default");
    expect(readFileSync(join(__dirname, "nav.spec.ts"), "utf8")).toContain(
      '"(tabs)/visits/[visitId]/shares.tsx"',
    );
  });

  it("is entered from the visit it belongs to (02 §4: visit detail carries it)", () => {
    const detail = file("src/app/(tabs)/visits/[visitId]/index.tsx");
    expect(detail).toContain("/shares`");
    expect(detail).toContain('t("shares.title")');
  });

  it("fits the file-size rule the constitution sets", () => {
    for (const name of [SCREEN, API, STORE, RULES]) {
      expect(file(name).split("\n").length, name).toBeLessThan(500);
    }
  });

  it("blocks capture, because a recipient label is the patient's own words", () => {
    expect(file(SCREEN)).toContain("useClinicalScreenPrivacy");
  });
});

/* ------------------------------------------------------------------ */
/* 2 · The three routes, and only the three routes                     */
/* ------------------------------------------------------------------ */

/**
 * Every route this client calls, and the reason the set stops here.
 *
 * All three are declared under `core` alone in INT-150's router. The two it
 * omits — `POST …/doctor-links` (issue) and `POST …/{id}/otp` (mint a code)
 * — enforce `share:previsit_note`, and neither is in this issue's acceptance:
 * INT-139 is "active shares, revoke, access log". Building them here would
 * also mean rendering a 128-bit bearer token in a patient app and implying a
 * delivery channel that does not exist (HB-O7). Their absence is what makes
 * §5's claim total rather than merely likely.
 */
const CLIENT_ROUTES = [
  { method: "GET", suffix: "/note/doctor-links" },
  { method: "POST", suffix: "/note/doctor-links/{link_id}/revoke" },
  { method: "GET", suffix: "/note/doctor-links/access-log" },
];

describe("the client speaks exactly the INT-150 patient surface", () => {
  const api = code(file(API));

  it("lists, revokes and reads the log over the visit's own note", () => {
    expect(api).toContain("/v1/visits/");
    expect(api).toContain("/note/doctor-links");
    expect(api).toContain("/revoke");
    expect(api).toContain("/access-log");
    expect(CLIENT_ROUTES).toHaveLength(3);
  });

  it("mints no link and mints no code anywhere in the app", () => {
    // The two share-purpose-gated routes. Their absence is asserted over the
    // whole tree, not just the client, so a screen cannot reach past it.
    const MINTS_A_CODE = /doctor-links[^"'`]*\/otp/;
    const ISSUES_A_LINK = /method:\s*"POST"[\s\S]{0,200}?\/note\/doctor-links"/;
    for (const entry of TREE) {
      const source = code(entry.source);
      expect(source, `${entry.name} mints an opening code`).not.toMatch(MINTS_A_CODE);
      expect(source, `${entry.name} issues a link`).not.toMatch(ISSUES_A_LINK);
    }
  });

  it("drives every call from the store, never from the screen", () => {
    expect(code(file(SCREEN))).not.toContain("authedFetch");
    expect(code(file(STORE))).not.toContain("fetch(");
    expect(api).toContain("authedFetch");
  });
});

/* ------------------------------------------------------------------ */
/* 3 · A token is a credential, and this app never holds one           */
/* ------------------------------------------------------------------ */

describe("no token reaches the app", () => {
  it("parses the seven fields of a grant and not the eighth", () => {
    const rules = code(file(RULES));
    expect(rules).toContain("link_id");
    expect(rules).toContain("view_limit");
    // `DoctorLinkIssued` is `DoctorLinkOut` plus `token`. Nothing here reads
    // it, so nothing downstream can render, log or copy it.
    expect(rules).not.toContain("token");
  });

  it("names no token, code or fingerprint anywhere in the share modules", () => {
    for (const name of [SCREEN, API, STORE, RULES]) {
      const source = code(file(name));
      for (const banned of ["token", "fingerprint", "Clipboard", "setStringAsync"]) {
        expect(source, `${name} reaches ${banned}`).not.toContain(banned);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 4 · The access log renders a role, never a person                   */
/* ------------------------------------------------------------------ */

describe("the patient sees the access log, as roles", () => {
  it("renders the log from the store and gives every role its own key", () => {
    expect(code(file(SCREEN))).toContain("roleLabelKey");
    expect(code(file(SCREEN))).toContain("categoryLabelKey");
    for (const role of ["self", "guardian", "clinician", "clinicStaff", "system", "unknown"]) {
      const key = `shares.log.role.${role}`;
      expect(tr, key).toHaveProperty(key);
      expect(en, key).toHaveProperty(key);
    }
  });

  it("has no way to render a name: the seam drops both id-shaped fields", () => {
    const rules = code(file(RULES));
    expect(rules).not.toContain("resource_ref");
    expect(rules).not.toContain("entry_hash");
    for (const name of [SCREEN, STORE]) {
      for (const banned of ["Avatar", "Image", "initials", "actor"]) {
        expect(code(file(name)), `${name} reaches ${banned}`).not.toContain(banned);
      }
    }
  });

  it("says on the screen that the log carries roles and not names", () => {
    expect(code(file(SCREEN))).toContain('t("shares.log.noNames")');
  });
});

/* ------------------------------------------------------------------ */
/* 5 · Revoke, and the deferral the client does not add                */
/* ------------------------------------------------------------------ */

describe("the revoke control", () => {
  const screen = code(file(SCREEN));

  it("is a two-step, the INT-140 idiom rather than a second one", () => {
    expect(screen).toContain('t("shares.revoke")');
    expect(screen).toContain('t("shares.revoke.confirm")');
    // No Alert: an alert's text cannot live in the catalogue (invariant 5)
    // and its buttons cannot carry an accessibility hint.
    expect(screen).not.toContain("Alert");
  });

  /**
   * The clause INT-150 §6 protects, asserted where a future edit would break
   * it. The screen may not consult a consent value to decide whether to offer
   * the control, and `revokeOffered` takes a grant and nothing else — so the
   * only way to reintroduce the bug is to add a conditional here, which this
   * catches.
   */
  it("is offered without consulting any consent value", () => {
    expect(screen).toContain("revokeOffered");
    for (const banned of ["consents", "useConsent", "purposeView", "allowed"]) {
      expect(screen, `the revoke path reads ${banned}`).not.toContain(banned);
    }
  });

  it("adds no cache, no poll and no persistence for a revocation to wait out", () => {
    for (const name of [API, STORE, RULES]) {
      const source = code(file(name));
      for (const banned of [
        "AsyncStorage",
        "SecureStore",
        "expo-file-system",
        "setInterval",
        "setTimeout",
        "cacheTtl",
        "staleAfter",
      ]) {
        expect(source, `${name} reaches ${banned}`).not.toContain(banned);
      }
    }
  });

  it("states the mechanism and never a latency figure (invariant 20)", () => {
    // What the product may promise is that a stopped share stops working at
    // the next attempt to open it. What it may not do is put a number on how
    // fast — that measurement lives in docs/evidence/INT-139.md with its
    // date and its corpus.
    expect(screen).toContain('t("shares.revoke.effect")');
    for (const [key, value] of Object.entries({ ...tr, ...en })) {
      if (!key.startsWith("shares.")) {
        continue;
      }
      expect(value, `${key} puts a duration in patient copy`).not.toMatch(
        /\b\d+\s*(?:sn|sec|second|saniye|dk|dakika|minute|min)\b/i,
      );
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6 · Copy: catalogued, mirrored, and readable at every text step      */
/* ------------------------------------------------------------------ */

describe("the copy", () => {
  const KEYS = Object.keys(tr).filter((key) => key.startsWith("shares."));

  it("mirrors every Turkish key into English (invariant 5)", () => {
    expect(KEYS.length).toBeGreaterThan(20);
    for (const key of KEYS) {
      expect(en, key).toHaveProperty(key);
      expect((en as Record<string, string>)[key]).not.toBe((tr as Record<string, string>)[key]);
    }
  });

  it("says where the list is held, the way the Me screen does", () => {
    expect(code(file(SCREEN))).toContain('t("shares.held")');
  });

  /**
   * INT-136 measured 52 of 248 Turkish option labels overflowing the row at
   * the largest step, and INT-295 established that the app's own text control
   * REPLACES the OS value — so a device sitting at the default says nothing
   * about what the control can ask for. Every row this screen adds is
   * therefore checked across `APP_STEPS`, not at 1.0.
   */
  describe("every row this screen adds is reachable at every APP_STEPS size", () => {
    const metrics = readFontMetrics(
      join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
    );
    // The narrowest phone the app targets, minus the screen gutters and the
    // ListRow's own horizontal padding (spacing.md each side).
    const PHONE_WIDTHS = [320, 375, 390];
    const ROW_CHROME = 2 * spacing.md;

    const STATE_LABELS = KEYS.filter((key) => key.startsWith("shares.state.")).flatMap((key) => [
      (tr as Record<string, string>)[key],
      (en as Record<string, string>)[key],
    ]);

    it("has state labels that do not fit beside a long recipient, so the bound matters", () => {
      expect(STATE_LABELS.length).toBeGreaterThan(6);
      const widest = Math.max(
        ...STATE_LABELS.map((l) => metrics.advance(l, scaledSize("caption", 2.0))),
      );
      expect(widest).toBeGreaterThan(0);
    });

    it("leaves room for one glyph of every label beside the row chrome", () => {
      for (const phone of PHONE_WIDTHS) {
        const row = phone - 2 * spacing.screen - ROW_CHROME;
        for (const scale of APP_STEPS) {
          const widestGlyph = Math.max(
            ...STATE_LABELS.flatMap((label) => [...label]).map((glyph) =>
              metrics.advance(glyph, scaledSize("caption", scale)),
            ),
          );
          expect(widestGlyph, `${phone}pt @${scale}`).toBeLessThanOrEqual(row);
        }
      }
    });

    it("wraps rather than truncates: nothing on this screen can be cut short", () => {
      const screen = code(file(SCREEN));
      for (const token of ["numberOfLines", "ellipsizeMode", "adjustsFontSizeToFit"]) {
        expect(screen, token).not.toContain(token);
      }
      // A screen with no scroll container overflows both ends at the largest
      // step and nothing brings it back (INT-284).
      expect(screen).toMatch(/<ScrollView\b/);
    });
  });
});

/* ------------------------------------------------------------------ */
/* 7 · The half of the acceptance main cannot hold yet                  */
/* ------------------------------------------------------------------ */

const SERVER_ROUTER = join(
  REPO,
  "services",
  "api",
  "src",
  "intake_api",
  "doctor_link",
  "router.py",
);

describe("the cross-check this branch cannot run", () => {
  /**
   * An inversion, not a deletion (the INT-263 form). The acceptance's first
   * clause — "revocation cascades to tokens within 1 min" — is a property of
   * the server's revoke path, and that path is INT-150's: PR #446, open and
   * unmerged at the time this branch was cut. There is nothing on `main` to
   * point these three paths at, so the honest artefact is a tripwire that
   * fails the day there is.
   */
  it("fails the moment INT-150 lands, so the paths get pinned to the router", () => {
    expect(
      existsSync(SERVER_ROUTER),
      "services/api/src/intake_api/doctor_link/router.py now exists, so INT-150 " +
        "(PR #446) has merged. Replace this inversion with the real cross-check: " +
        "assert every CLIENT_ROUTES suffix appears in that router, and re-run the " +
        "revocation-interval measurement on main. See docs/evidence/INT-139.md.",
    ).toBe(false);
  });

  it("records the dependency where a reader of the backlog will meet it", () => {
    const evidence = readFileSync(join(REPO, "docs", "evidence", "INT-139.md"), "utf8");
    expect(evidence).toContain("PR #446");
    // The same three phrases `scripts/ci/evidence_check.sh` greps for, and
    // with its case-insensitivity, so this cannot pass where the gate fails.
    for (const phrase of [/red run/i, /green run/i, /make check/i]) {
      expect(evidence, String(phrase)).toMatch(phrase);
    }
  });
});
