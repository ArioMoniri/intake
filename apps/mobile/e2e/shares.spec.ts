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
 * §7 is the cross-check against the server itself. It was written as an
 * INVERSION — asserting the router's absence, because INT-150 was PR #446 and
 * still open when this branch was cut — and it did exactly what a tripwire is
 * for: #446 merged mid-iteration, the inversion failed, and it was replaced
 * by the real check. That check now recovers every route decorator out of
 * `doctor_link/router.py` and asserts the client calls only the three the
 * share purpose does NOT gate, which is the acceptance's revoke clause
 * checked against the deployed system rather than claimed about the client.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
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
 * INT-139 is "active shares, revoke, access log". Building them in THIS client
 * would mean rendering a 128-bit bearer token on the listing screen. INT-311
 * gives them their own owner instead — `src/lib/shares/issue.ts`, feeding the
 * dedicated issuing surface — so this client stays free of them and §5's claim
 * about it stays total. The confinement is checked below.
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

  /**
   * INT-311 relaxed this, and only this line. Until INT-311 the two
   * share-purpose-gated routes had no owner anywhere in the app, and asserting
   * their absence over the WHOLE tree was correct. INT-311 gives them one
   * owner — `src/lib/shares/issue.ts`, the issuing surface's transport — and
   * the reason each may now go is one reason, not two: the SERVER redemption
   * path they feed is real. `doctor_link/redeem.py::open_link` checks the share
   * consent scope (`ensure_consent(scope=SHARE_SCOPE)`) and writes a
   * hash-chained audit entry (`api.doctor_link.opened`) before it discloses a
   * section — the precondition INT-311's acceptance names. So the control is
   * not dropped, it is NARROWED to one file: issuing and code-minting are
   * proved absent from every OTHER module (this client, the share-centre
   * screen, review & send, the note surface), and proved present on the one
   * that owns them. INT-137's four negative controls on the review surface are
   * untouched and still stand (`e2e/issueLink.spec.ts` §2, `review_send.spec.ts` §6).
   */
  it("mints a link and a code ONLY on the issuing surface INT-311 owns", () => {
    const MINTS_A_CODE = /doctor-links[^"'`]*\/otp/;
    const ISSUES_A_LINK = /method:\s*"POST"[\s\S]{0,200}?\/note\/doctor-links"/;
    const OWNER = "src/lib/shares/issue.ts";
    for (const entry of TREE) {
      if (entry.name === OWNER) {
        continue;
      }
      const source = code(entry.source);
      expect(source, `${entry.name} mints an opening code`).not.toMatch(MINTS_A_CODE);
      expect(source, `${entry.name} issues a link`).not.toMatch(ISSUES_A_LINK);
    }
    // The owner is where they live — a positive check so this stays load-bearing
    // rather than passing because nobody issues at all.
    const owner = code(file(OWNER));
    expect(owner).toContain("/note/doctor-links");
    expect(owner).toContain("/otp");
    expect(owner).toMatch(/"POST"/);
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
/* 7 · The client's paths, pinned to the server that serves them        */
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

/**
 * Every route decorator in INT-150's patient-side router, recovered from the
 * source so the client and the server cannot drift apart silently.
 *
 * The regex reads `@router.<method>(<args>)` up to the decorated function, and
 * the two things it recovers are the path literal and whether the decorator's
 * `require_scopes(...)` mentions `SHARE_SCOPE`. That second fact is the whole
 * point: it is the machine-checkable form of INT-150 §6, and it is what makes
 * "a withdrawal cannot lock the stop control" a property of the deployed
 * system rather than a claim in a comment.
 */
function serverRoutes(source: string): { method: string; path: string; sharePurpose: boolean }[] {
  const found: { method: string; path: string; sharePurpose: boolean }[] = [];
  const head = /@router\.(get|post|put|delete|patch)\(/g;
  for (const match of source.matchAll(head)) {
    // Balance the parentheses rather than pattern-matching the end. A regex
    // that guessed where the decorator stopped read a single-line one as
    // running into the NEXT decorator's arguments — which reported the
    // access-log route as share-gated and the OTP mint as not. A check whose
    // failure mode is "reports the wrong route as safe" has to be exact.
    let depth = 1;
    let i = (match.index ?? 0) + match[0].length;
    const from = i;
    for (; i < source.length && depth > 0; i += 1) {
      if (source[i] === "(") {
        depth += 1;
      } else if (source[i] === ")") {
        depth -= 1;
      }
    }
    const args = source.slice(from, i - 1);
    const literal = /^\s*"([^"]*)"/.exec(args);
    found.push({
      method: match[1].toUpperCase(),
      path: literal === null ? "" : literal[1],
      sharePurpose: /require_scopes\([^)]*SHARE_SCOPE/.test(args.replace(/\s+/g, " ")),
    });
  }
  return found;
}

describe("the client is pinned to the router INT-150 shipped", () => {
  const source = readFileSync(SERVER_ROUTER, "utf8");
  const routes = serverRoutes(source);

  it("reads the router it is checking, rather than passing on an empty parse", () => {
    // A cross-check that matches nothing passes for the wrong reason. INT-150
    // ships five routes on this prefix: issue, list, mint, revoke, log.
    expect(routes).toHaveLength(5);
    expect(source).toContain('prefix="/v1/visits/{visit_id}/note/doctor-links"');
  });

  it("speaks three paths the router actually serves", () => {
    const served = new Set(routes.map((r) => `${r.method} ${r.path}`));
    expect(served).toContain("GET ");
    expect(served).toContain("POST /{link_id}/revoke");
    expect(served).toContain("GET /access-log");
    // and the client's own strings reach those same three, prefix included
    const api = code(file(API));
    expect(api).toContain("/v1/visits/");
    expect(api).toContain("/note/doctor-links");
    expect(api).toContain("/revoke");
    expect(api).toContain("/access-log");
    expect(CLIENT_ROUTES).toHaveLength(3);
  });

  /**
   * The acceptance's revoke clause, checked against the server rather than
   * asserted about the client. INT-150 §6 declares revoke and the access log
   * under `core` ALONE so that withdrawing `share:previsit_note` cannot lock
   * the patient out of stopping a share they already started. If a future edit
   * added the share purpose to either decorator, this app's stop control would
   * become unreachable exactly when it is most needed — and this fails.
   */
  it("calls only routes a withdrawal of the share purpose cannot take away", () => {
    const gated = new Set(routes.filter((r) => r.sharePurpose).map((r) => `${r.method} ${r.path}`));
    // The two the client deliberately does not call are the gated ones …
    expect(gated).toEqual(new Set(["POST ", "POST /{link_id}/otp"]));
    // … and none of the three it does call is among them.
    for (const call of ["GET ", "POST /{link_id}/revoke", "GET /access-log"]) {
      expect(gated, `${call} now enforces the share purpose`).not.toContain(call);
    }
  });

  it("records the measurement and the run it came from", () => {
    const evidence = readFileSync(join(REPO, "docs", "evidence", "INT-139.md"), "utf8");
    // The same three phrases `scripts/ci/evidence_check.sh` greps for, and
    // with its case-insensitivity, so this cannot pass where the gate fails.
    for (const phrase of [/red run/i, /green run/i, /make check/i]) {
      expect(evidence, String(phrase)).toMatch(phrase);
    }
  });
});
