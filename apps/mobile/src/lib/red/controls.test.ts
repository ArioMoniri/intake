/**
 * INT-602 — the RED layer's controls (CLAUDE.md invariants 9, 10, 21; files/02
 * §5.3; docs/design/audit-2026-11 Part B R1–R6).
 *
 * Every acceptance item has its test here, each with a near-miss control:
 * 1. the 112 control is the strongest control on the layer, gives instant
 *    pressed feedback, and a dialer that cannot open falls back to the number;
 * 2. under CALM its boundary clears 3:1 against the wash, in both themes;
 * 3. under ON_SITE there is no 112 and always a staff control, never nothing;
 * 4. the layer pads every edge by its safe-area inset;
 * 5. RED chrome copy is the bare imperative plural.
 * The source half (what RedLayer.tsx renders) is in e2e/red.spec.ts.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "../a11y/target";
import { t } from "../i18n";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { GENERIC_RED_SCRIPT_IDS, type RedLocation, type RedRegister } from "../livekit/red";
import type { RedTrigger } from "../livekit/types";
import { RED_MOTION, type LocationAnswer } from "../motion/red";
import { CTA_MIN_HEIGHT } from "../prefs/appearance";
import { motion, palette, spacing, typeScale, type ColorScheme } from "../theme";
import {
  callOrShowNumber,
  RED_SECONDARY_CONTROL,
  redControlBoundary,
  redLayerFrame,
  redPressedOpacity,
  redPrimaryControl,
  redWash,
  staffCallLine,
} from "./controls";
import { decodeRedCatalog, scriptIdFor, type PrePositionedRed, type RedOrigin } from "./hop";
import {
  createLocationReporter,
  createStaffCaller,
  LOCATION_PATH,
  LOCATION_REPORT_MAX_ATTEMPTS,
  STAFF_CALL_PATH,
  staffCallFor,
  staffCallPhase,
} from "./locationReport";
import { createRedStore, redScreen } from "./store";

const ROOT = join(__dirname, "..", "..", "..", "..", "..");
const FIXTURES = join(ROOT, "tests", "fixtures", "triage_hop");
const CATALOG_BYTES = new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json")));
const CATALOG = decodeRedCatalog(CATALOG_BYTES) as PrePositionedRed;
const RULE = "rf.sentetik_yasamsal";
const ORIGIN: RedOrigin = { sessionId: "visit-1", visitId: "visit-1" };
const SCHEMES: readonly ColorScheme[] = ["light", "dark"];
/** The registers the patient is shown: DEFERRED_CLINICIAN changes nothing on screen. */
const SHOWN = ["ALERT", "CALM", "SILENT"] as const satisfies readonly RedRegister[];

function trigger(register: RedRegister, location: RedLocation): RedTrigger {
  return {
    kind: "red_trigger",
    ruleId: RULE,
    register,
    location,
    scriptId: scriptIdFor(RULE, location),
  };
}

/** The same catalog with the rule's own located scripts gone (pack drift → generic RED). */
function withoutRuleScripts(): PrePositionedRed {
  const scripts = Object.fromEntries(
    Object.entries(CATALOG.scripts).filter(([id]) => !id.startsWith(`${RULE}.`)),
  );
  return { scripts, questions: CATALOG.questions };
}

// --- the staff caller's rig (INT-602 clinical review round 1) ---

const STAFF_BODY = { session_id: "visit-1", visit_id: "visit-1", rule_id: RULE };
const NEVER_EXPIRES = () => ({
  expired: new Promise<void>(() => undefined),
  cancel: () => undefined,
});
const FAST = { sleep: async () => undefined, jitter: () => 0.5, timeout: NEVER_EXPIRES };

function json(body: unknown): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(body));
}

/** A server answering each request with the next status (the last repeats). */
function staffRig(statuses: readonly number[], body: unknown) {
  const sent: { path: string; body: unknown }[] = [];
  const caller = createStaffCaller({
    ...FAST,
    transport: async (path, raw) => {
      sent.push({ path, body: JSON.parse(raw ?? "null") as unknown });
      const status = statuses[Math.min(sent.length, statuses.length) - 1] ?? 500;
      return { status, bytes: json(status < 300 ? body : { error: "refused" }) };
    },
  });
  return { sent, caller };
}

function onSiteStore() {
  const store = createRedStore();
  store.present(trigger("ALERT", "ON_SITE"), CATALOG, ORIGIN);
  return store;
}

async function settle(rounds = 200): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await Promise.resolve();
  }
}

// WCAG 2.x relative luminance and contrast ratio (the same formula as theme.test.ts).
function channel(v: number): number {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("INT-602 (1) — the 112 control is the strongest control on the RED layer", () => {
  it.each(SHOWN)("%s: at least the primary CTA's height, with a label no smaller than its", (r) => {
    for (const scheme of SCHEMES) {
      const look = redPrimaryControl(r, palette[scheme]);
      // components/Themed.tsx PrimaryButton: minHeight CTA_MIN_HEIGHT, body role, weight 600.
      expect(look.minHeight).toBeGreaterThanOrEqual(CTA_MIN_HEIGHT);
      expect(typeScale[look.labelRole]).toBeGreaterThanOrEqual(typeScale.body);
      expect(Number(look.labelWeight)).toBeGreaterThanOrEqual(600);
      // …and no other control on the layer outranks it.
      expect(look.minHeight).toBeGreaterThan(RED_SECONDARY_CONTROL.minHeight);
      expect(typeScale[look.labelRole]).toBeGreaterThan(typeScale[RED_SECONDARY_CONTROL.labelRole]);
    }
  });

  it("near miss: the pre-INT-602 look (44 pt, 15 pt label) is below the CTA floor", () => {
    expect(MIN_TAP).toBeLessThan(CTA_MIN_HEIGHT);
    expect(typeScale.label).toBeLessThan(typeScale.body);
    // The secondary answers (Evet / Hayır) keep that look: still a 44 pt target.
    expect(RED_SECONDARY_CONTROL.minHeight).toBe(MIN_TAP);
  });

  it("gives immediate pressed feedback: the INT-341 opacity step, which is not motion", () => {
    expect(redPressedOpacity(true)).toBe(motion.press.opacity);
    expect(redPressedOpacity(true)).toBeLessThan(1);
    // Near miss: unpressed, the control is drawn at full strength.
    expect(redPressedOpacity(false)).toBe(1);
    // Committed on press with 0 ms feedback, and still no haptic (ADR-033 Q2).
    expect(RED_MOTION.actions).toEqual({ commitOn: "press", feedbackMs: 0, longPress: false });
    expect(RED_MOTION.haptic).toBe(false);
  });

  it("a dialer that cannot open falls back to showing the number", async () => {
    const shown: string[] = [];
    callOrShowNumber(
      () => Promise.reject(new Error("no dialer")),
      () => shown.push("rejected"),
    );
    callOrShowNumber(
      () => {
        throw new Error("no handler");
      },
      () => shown.push("threw"),
    );
    await Promise.resolve();
    await Promise.resolve();
    expect(shown.sort()).toEqual(["rejected", "threw"]);
    // Near miss: a dialer that opens shows no fallback.
    const opened: string[] = [];
    callOrShowNumber(
      () => Promise.resolve(true),
      () => opened.push("fallback"),
    );
    await Promise.resolve();
    await Promise.resolve();
    expect(opened).toEqual([]);
  });

  it("the fallback copy exists in tr and en and says to dial from the phone", () => {
    expect(tr["red.call112Failed"]).toMatch(/arayın\.$/u);
    expect(en["red.call112Failed"].length).toBeGreaterThan(0);
  });
});

describe("INT-602 (2) — under CALM the 112 control has a visible boundary (WCAG 1.4.11)", () => {
  it.each(SCHEMES)("%s: the boundary clears 3:1 against the CALM wash", (scheme) => {
    const colors = palette[scheme];
    const look = redPrimaryControl("CALM", colors);
    expect(contrast(redControlBoundary(look), redWash("CALM", colors))).toBeGreaterThanOrEqual(3);
  });

  it.each(SCHEMES)("%s: ALERT and SILENT clear 3:1 against their own ground too", (scheme) => {
    const colors = palette[scheme];
    for (const register of ["ALERT", "SILENT"] as const) {
      const look = redPrimaryControl(register, colors);
      expect(
        contrast(redControlBoundary(look), redWash(register, colors)),
        register,
      ).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(SCHEMES)(
    "near miss (%s): the pre-INT-602 CALM fill on the wash is below 3:1",
    (scheme) => {
      const colors = palette[scheme];
      expect(contrast(colors.surfaceRaised, redWash("CALM", colors))).toBeLessThan(3);
    },
  );

  it("CALM keeps its register: no emergency colour on the control (files/02 §5.3)", () => {
    for (const scheme of SCHEMES) {
      const colors = palette[scheme];
      const calm = redPrimaryControl("CALM", colors);
      expect(calm.backgroundColor).not.toBe(colors.emergency);
      expect(redControlBoundary(calm)).not.toBe(colors.emergency);
      // Near miss: ALERT is the one register that carries the emergency colour.
      expect(redPrimaryControl("ALERT", colors).backgroundColor).toBe(colors.emergency);
    }
  });
});

describe("INT-602 (3) — under ON_SITE: no 112, and never control-less", () => {
  /** Every path to an ON_SITE action: known, answered "evet", and a late "evet". */
  const ON_SITE_PATHS: readonly (readonly [string, RedLocation, readonly LocationAnswer[]])[] = [
    ["known ON_SITE", "ON_SITE", []],
    ["UNKNOWN answered evet", "UNKNOWN", ["inHospital"]],
    ["UNKNOWN, late evet after the no-answer wait", "UNKNOWN", ["noAnswer", "inHospital"]],
  ];

  for (const [name, catalog] of [
    ["the rule's own script", CATALOG],
    ["the generic RED (rule script missing)", withoutRuleScripts()],
  ] as const) {
    for (const register of SHOWN) {
      for (const [path, location, answers] of ON_SITE_PATHS) {
        it(`${register} · ${path} · ${name}: a staff control, and no 112`, () => {
          const store = createRedStore();
          store.present(trigger(register, location), catalog, ORIGIN);
          for (const answer of answers) {
            store.answerLocation(answer as Exclude<LocationAnswer, "unanswered">);
          }
          const screen = redScreen(store.getSnapshot());
          expect(screen).toMatchObject({ kind: "act", location: "ON_SITE" });
          if (screen.kind !== "act") {
            return;
          }
          expect(screen.call112).toBe(false); // invariant 21: absent
          expect(screen.callStaff).toBe(true); // never control-less
          expect(screen.actionTr.trim().length).toBeGreaterThan(0); // the guidance text
        });
      }
    }
  }

  it("fails closed: an ON_SITE script whose pack action says nothing of staff still gets the control", () => {
    const quiet: PrePositionedRed = {
      ...CATALOG,
      scripts: {
        ...CATALOG.scripts,
        [`${RULE}.on_site`]: {
          primary: "GO_TO_IN_HOUSE_ACIL",
          show112: false,
          actionTr: "Acil Servis'e gidin.",
          doNotsTr: [],
          whyTr: null,
        },
      },
    };
    const store = createRedStore();
    store.present(trigger("ALERT", "ON_SITE"), quiet, ORIGIN);
    expect(redScreen(store.getSnapshot())).toMatchObject({ call112: false, callStaff: true });
  });

  it.each(SHOWN)("near miss (%s): REMOTE shows 112 and no staff control", (register) => {
    const store = createRedStore();
    store.present(trigger(register, "REMOTE"), CATALOG, ORIGIN);
    expect(redScreen(store.getSnapshot())).toMatchObject({
      kind: "act",
      call112: true,
      callStaff: false,
    });
    // …and UNKNOWN answered hayır, and the no-answer branch, are REMOTE too.
    for (const answers of [["notInHospital"], ["noAnswer"]] as const) {
      const unknown = createRedStore();
      unknown.present(trigger(register, "UNKNOWN"), CATALOG, ORIGIN);
      for (const answer of answers) {
        unknown.answerLocation(answer);
      }
      expect(redScreen(unknown.getSnapshot())).toMatchObject({ call112: true, callStaff: false });
    }
  });

  it("the staff control's words are a non-clinical UI affordance, in tr first with an en mirror", () => {
    expect(tr["red.callStaff"]).toBe("Görevlilere haber verin");
    expect(en["red.callStaff"]).toBe("Notify staff");
    expect(tr["red.callStaff.sent"]).toBe("Görevlilere haber gönderildi.");
    expect(tr["red.callStaff.failed"]).toContain("Bir görevliden yardım isteyin");
    expect(tr["red.callStaff.failed"]).toContain("Acil Servis'e gidin");
    const keys = [
      "red.callStaff",
      "red.callStaff.hint",
      "red.callStaff.sending",
      "red.callStaff.sent",
      "red.callStaff.failed",
    ] as const;
    for (const key of keys) {
      expect(en[key].length, key).toBeGreaterThan(0);
      // Near miss (invariant 21): nothing about the staff control names 112.
      expect(tr[key]).not.toMatch(/112|ambulans/iu);
      expect(en[key]).not.toMatch(/112|ambulance/iu);
      // It never promises that a person will come: one inbox entry is written.
      expect(tr[key], key).not.toMatch(/geliyor|gelecek|çağır/iu);
      expect(en[key], key).not.toMatch(/\bcom(e|ing)\b|\bcall\b|on (the|their) way/iu);
    }
    // The detector is not vacuous: the round-0 label is caught.
    expect("Görevli çağırın").toMatch(/geliyor|gelecek|çağır/iu);
    expect("Call staff").toMatch(/\bcall\b/iu);
  });

  it("pressing it posts this RED's ids to the staff-call route, never as a location answer", async () => {
    const { sent, caller } = staffRig([202], { staffNotified: true });
    const store = onSiteStore();
    expect(staffCallFor(store.getSnapshot())).toEqual(STAFF_BODY);
    caller.call(store.getSnapshot());
    caller.call(store.getSnapshot()); // a second press while the first is in flight: one request
    await settle();
    expect(sent).toEqual([{ path: STAFF_CALL_PATH, body: STAFF_BODY }]);
    // Near miss (invariant 4): it is not the location route, and carries no location.
    expect(sent[0]?.path).not.toBe(LOCATION_PATH);
    expect(Object.keys(STAFF_BODY)).not.toContain("location");
  });

  it("sent shows only after the server confirms staffNotified, never before", async () => {
    let release: (() => void) | null = null;
    const sent: string[] = [];
    const caller = createStaffCaller({
      ...FAST,
      transport: (path) =>
        new Promise((resolve) => {
          sent.push(path);
          release = () => resolve({ status: 202, bytes: json({ staffNotified: true }) });
        }),
    });
    const store = onSiteStore();
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("idle");
    caller.call(store.getSnapshot());
    await settle();
    // The request is out and unanswered: sending, not sent.
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("sending");
    expect(sent).toHaveLength(1);
    (release as (() => void) | null)?.();
    await settle();
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("sent");
  });

  it("near miss: a 2xx that does not say staff were notified is not sent", async () => {
    for (const body of [{ staffNotified: false }, {}, null] as const) {
      const { caller } = staffRig([202], body);
      const store = onSiteStore();
      caller.call(store.getSnapshot());
      await settle();
      expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot()), JSON.stringify(body)).toBe(
        "failed",
      );
    }
  });

  it.each([401, 403, 422])(
    "a %i refusal is the visible failed state, after one request",
    async (status) => {
      const { sent, caller } = staffRig([status], { error: "rule_not_served" });
      const store = onSiteStore();
      caller.call(store.getSnapshot());
      await settle();
      expect(sent).toHaveLength(1); // not retriable
      expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("failed");
    },
  );

  it("retries that run out are the visible failed state", async () => {
    const { sent, caller } = staffRig([503], { error: "safety_inbox_unconfigured" });
    const store = onSiteStore();
    caller.call(store.getSnapshot());
    await settle(4000);
    expect(sent).toHaveLength(LOCATION_REPORT_MAX_ATTEMPTS);
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("failed");
    // Near miss: a network that throws on every try fails the same way.
    const down = createStaffCaller({
      ...FAST,
      transport: async () => {
        throw new Error("network down");
      },
    });
    down.call(store.getSnapshot());
    await settle(4000);
    expect(staffCallPhase(down.getSnapshot(), store.getSnapshot())).toBe("failed");
  });

  it("after a failure the patient can press again; after a confirmed send a repeat re-shows sent", async () => {
    const { sent, caller } = staffRig([422, 202], { staffNotified: true });
    const store = onSiteStore();
    caller.call(store.getSnapshot());
    await settle();
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("failed");
    caller.call(store.getSnapshot());
    await settle();
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("sent");
    expect(sent).toHaveLength(2);
    // A repeat press after a confirmed send pages nobody: no request, still sent.
    caller.call(store.getSnapshot());
    await settle();
    expect(sent).toHaveLength(2);
    expect(staffCallPhase(caller.getSnapshot(), store.getSnapshot())).toBe("sent");
  });

  it("near miss: another RED's press shows nothing on this one", async () => {
    const { caller } = staffRig([202], { staffNotified: true });
    caller.call(onSiteStore().getSnapshot());
    await settle();
    const other = createRedStore();
    other.present({ ...trigger("ALERT", "ON_SITE"), ruleId: "rf.baska_kural" }, CATALOG, ORIGIN);
    expect(staffCallPhase(caller.getSnapshot(), other.getSnapshot())).toBe("idle");
    expect(staffCallPhase(caller.getSnapshot(), null)).toBe("idle");
  });

  it("each phase has its line; sent is the only one that says staff were told", () => {
    expect(staffCallLine("idle")).toBeNull();
    expect(staffCallLine("sending")).toEqual({ key: "red.callStaff.sending", tone: "status" });
    expect(staffCallLine("sent")).toEqual({ key: "red.callStaff.sent", tone: "status" });
    expect(staffCallLine("failed")).toEqual({ key: "red.callStaff.failed", tone: "error" });
    // Near miss: no line before confirmation reads as done.
    for (const phase of ["idle", "sending", "failed"] as const) {
      const line = staffCallLine(phase);
      expect(line === null ? "" : tr[line.key], phase).not.toMatch(/gönderildi/u);
    }
  });

  it.each(["ON_SITE", "REMOTE", "UNKNOWN"] as const)(
    "near miss: DEFERRED_CLINICIAN × %s shows no staff control and no 112",
    (location) => {
      const store = createRedStore();
      store.present(trigger("DEFERRED_CLINICIAN", location), CATALOG, ORIGIN);
      expect(redScreen(store.getSnapshot())).toEqual({ kind: "none" });
      expect(staffCallFor(store.getSnapshot())).toBeNull();
    },
  );

  it("near miss: a REMOTE RED, an unanswered question and no RED owe no staff call", () => {
    const remote = createRedStore();
    remote.present(trigger("ALERT", "REMOTE"), CATALOG, ORIGIN);
    expect(staffCallFor(remote.getSnapshot())).toBeNull();
    const asked = createRedStore();
    asked.present(trigger("ALERT", "UNKNOWN"), CATALOG, ORIGIN);
    expect(staffCallFor(asked.getSnapshot())).toBeNull();
    expect(staffCallFor(null)).toBeNull();
    // The answer reporter is unchanged: a known ON_SITE RED asked nothing.
    const sent: string[] = [];
    const reporter = createLocationReporter({
      transport: async (path) => {
        sent.push(path);
        return { status: 202, bytes: new Uint8Array() };
      },
    });
    const onSite = createRedStore();
    onSite.present(trigger("ALERT", "ON_SITE"), CATALOG, ORIGIN);
    reporter.observe(onSite.getSnapshot());
    expect(sent).toEqual([]);
  });

  it("the generic RED's ON_SITE script is on the device, so the generic path has guidance", () => {
    expect(CATALOG.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE]?.show112).toBe(false);
  });
});

describe("INT-602 (4) — the RED layer respects safe-area insets on every edge", () => {
  const CASES = [
    ["portrait, Dynamic Island", { top: 59, right: 0, bottom: 34, left: 0 }],
    ["landscape, sensor housing left and right", { top: 0, right: 59, bottom: 21, left: 59 }],
    ["Android, cutout and gesture bar", { top: 48, right: 0, bottom: 24, left: 0 }],
  ] as const;

  it.each(CASES)("%s: every edge clears its inset", (_name, insets) => {
    const frame = redLayerFrame(insets);
    expect(frame.bandHeight).toBeGreaterThanOrEqual(insets.top + spacing.md);
    expect(frame.padding.left).toBeGreaterThanOrEqual(insets.left + spacing.screen);
    expect(frame.padding.right).toBeGreaterThanOrEqual(insets.right + spacing.screen);
    expect(frame.padding.bottom).toBeGreaterThanOrEqual(insets.bottom + spacing.screen);
    expect(frame.padding.top).toBeGreaterThanOrEqual(spacing.xl);
  });

  it("near miss: with no insets the layer keeps its pre-INT-602 geometry", () => {
    expect(redLayerFrame({ top: 0, right: 0, bottom: 0, left: 0 })).toEqual({
      bandHeight: spacing.xl * 2,
      padding: {
        top: spacing.xl,
        right: spacing.screen,
        bottom: spacing.screen,
        left: spacing.screen,
      },
    });
  });
});

describe("INT-602 (5) — RED copy is the bare imperative plural", () => {
  it('the do-not heading is "Yapmayın", not "Lütfen yapmayın"', () => {
    expect(t("red.doNots", "tr")).toBe("Yapmayın");
    expect(t("red.doNots", "en")).toBe("Do not");
  });

  it("near miss: no RED chrome string softens with Lütfen / Please", () => {
    const keys = (Object.keys(tr) as (keyof typeof tr)[]).filter((k) => k.startsWith("red."));
    expect(keys.length).toBeGreaterThanOrEqual(7);
    for (const key of keys) {
      expect(tr[key], key).not.toMatch(/\blütfen\b/iu);
      expect(en[key], key).not.toMatch(/\bplease\b/iu);
    }
    // The detector is not vacuous.
    expect("Lütfen yapmayın").toMatch(/\blütfen\b/iu);
  });

  it("the service claim the audit flags is checked against its committed snapshot", () => {
    const snapshot = readFileSync(
      join(ROOT, "packages", "protocols", "sources", "TR-EK4-2022.txt"),
      "utf8",
    );
    const generic = readFileSync(
      join(ROOT, "packages", "protocols", "generic", "generic_red.yaml"),
      "utf8",
    );
    const claim =
      "112 ambulansıyla getirilen hastalar, acil serviste ayrıca öncelik sırası için bekletilmez.";
    // The line is pack text (invariant 10) and is not rewritten here.
    expect(generic).toContain(claim);
    // What the cited source supports: no separate triage for a 112 ambulance arrival…
    expect(snapshot).toContain(
      "(5) 112 acil ambulanslarıyla sağlık tesisine getirilen hastalara ayrıca triyaj uygulaması yapılmaz.",
    );
    // …and what it does not state: that such a patient is not kept waiting. The
    // snapshot's only "bekletilmeksizin" in MADDE 8(5) is about the ambulance.
    expect(snapshot).not.toMatch(/hastalar[^.]*bekletilmez/u);
    // So the line goes to clinical review, recorded in blockers.md for INT-602.
    const blockers = readFileSync(join(ROOT, "docs", "backlog", "blockers.md"), "utf8");
    const at = blockers.indexOf("## INT-602");
    expect(at).toBeGreaterThan(-1);
    expect(blockers.slice(at)).toContain("öncelik sırası için bekletilmez");
  });
});
