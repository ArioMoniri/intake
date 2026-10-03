/**
 * The RED screen model and store (INT-446; CLAUDE.md invariants 10, 21;
 * files/02 §5.3). Every register × location × location-answer combination is
 * enumerated over the catalog the real route serves (the recorded
 * tests/fixtures/triage_hop/red_catalog.json, pinned to the route by
 * tests/api/test_triage_hop.py), each with its near-miss control.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import type { Answer } from "../intake/note";
import { GENERIC_RED_SCRIPT_IDS, type RedLocation, type RedRegister } from "../livekit/red";
import type { RedTrigger } from "../livekit/types";
import { RED_LOCATIONS, RED_MOTION, RED_REGISTERS, type LocationAnswer } from "../motion/red";
import {
  decodeRedCatalog,
  evaluateBoundAnswers,
  scriptIdFor,
  triageRequest,
  type PrePositionedRed,
} from "./hop";
import { deriveRedLocation } from "./location";
import {
  createRedStore,
  dialogueFrozenAt,
  dialogueShown,
  intakeLive,
  RedCatalogIncomplete,
  redCoversNavigator,
  redScreen,
  redStopsDialogue,
  UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS,
  type RedState,
} from "./store";

const FIXTURES = join(__dirname, "..", "..", "..", "..", "..", "tests", "fixtures", "triage_hop");
const CATALOG_BYTES = new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json")));
const CATALOG = decodeRedCatalog(CATALOG_BYTES) as PrePositionedRed;
const RAW = JSON.parse(new TextDecoder().decode(CATALOG_BYTES)) as {
  scripts: Record<string, { actionTr: string; show112: boolean }>;
  questions: Record<string, { askTr: string }>;
};
const RULE = "rf.sentetik_yasamsal";

function trigger(register: RedRegister, location: RedLocation): RedTrigger {
  return {
    kind: "red_trigger",
    ruleId: RULE,
    register,
    location,
    scriptId: scriptIdFor(RULE, location),
  };
}

function state(register: RedRegister, location: RedLocation, answer: LocationAnswer): RedState {
  return { trigger: trigger(register, location), catalog: CATALOG, answer, elapsedMs: null };
}

const ANSWERS: readonly LocationAnswer[] = [
  "unanswered",
  "inHospital",
  "notInHospital",
  "noAnswer",
];

describe("RED screen — every register × location × answer", () => {
  it("the recorded catalog decodes: every rule id is a scriptIdFor id, and the generic RED is pre-positioned", () => {
    expect(CATALOG).not.toBeNull();
    const ids = [...Object.keys(CATALOG.scripts), ...Object.keys(CATALOG.questions)].sort();
    expect(ids).toEqual(
      [
        ...RED_LOCATIONS.map((l) => scriptIdFor(RULE, l)),
        ...Object.values(GENERIC_RED_SCRIPT_IDS),
      ].sort(),
    );
  });

  for (const register of RED_REGISTERS) {
    for (const location of RED_LOCATIONS) {
      for (const answer of ANSWERS) {
        it(`${register} × ${location} × ${answer}`, () => {
          const screen = redScreen(state(register, location, answer));
          if (register === "DEFERRED_CLINICIAN") {
            // Patient screen unchanged — and the dialogue is not stopped.
            expect(screen).toEqual({ kind: "none" });
            expect(redStopsDialogue(state(register, location, answer))).toBe(false);
            return;
          }
          const mode = register === "SILENT" ? "inFlow" : "rootLayer";
          expect(redStopsDialogue(state(register, location, answer))).toBe(true);
          if (location === "UNKNOWN" && answer === "unanswered") {
            // The one question, verbatim, and nothing else: no 112 mounts yet.
            expect(screen).toEqual({
              kind: "ask",
              mode,
              register,
              askTr: RAW.questions[scriptIdFor(RULE, "UNKNOWN")].askTr,
              motion: RED_MOTION,
            });
            return;
          }
          const resolved: RedLocation =
            location === "UNKNOWN" ? (answer === "inHospital" ? "ON_SITE" : "REMOTE") : location;
          const raw = RAW.scripts[scriptIdFor(RULE, resolved)];
          expect(screen.kind).toBe("act");
          if (screen.kind !== "act") {
            return;
          }
          expect(screen.mode).toBe(mode);
          expect(screen.location).toBe(resolved);
          expect(screen.actionTr).toBe(raw.actionTr); // verbatim, invariant 10
          expect(screen.motion).toBe(RED_MOTION);
          // 112: absent under ON_SITE; under REMOTE exactly what the pack authorises.
          expect(screen.call112).toBe(resolved === "REMOTE" && raw.show112);
          // LD-05: only a no-answer branch keeps the question open, after the action.
          expect(screen.lateAskTr).toBe(
            location === "UNKNOWN" && answer === "noAnswer"
              ? RAW.questions[scriptIdFor(RULE, "UNKNOWN")].askTr
              : null,
          );
        });
      }
    }
  }

  it("ON_SITE never mounts 112, even if a catalog entry claimed it (near miss)", () => {
    const forged: PrePositionedRed = {
      ...CATALOG,
      scripts: {
        ...CATALOG.scripts,
        [scriptIdFor(RULE, "ON_SITE")]: {
          ...CATALOG.scripts[scriptIdFor(RULE, "ON_SITE")],
          show112: true,
        },
      },
    };
    for (const register of ["ALERT", "CALM", "SILENT"] as const) {
      const screen = redScreen({ ...state(register, "ON_SITE", "unanswered"), catalog: forged });
      expect(screen.kind === "act" && screen.call112).toBe(false);
    }
    // …and the control: the same script under REMOTE does show it.
    const remote = redScreen(state("ALERT", "REMOTE", "unanswered"));
    expect(remote.kind === "act" && remote.call112).toBe(true);
  });

  // INT-453 / CD-24: a RED whose script is missing still shows the generic
  // RED, in the trigger's OWN register (carry_engine_register, never a fixed
  // ALERT), at the trigger's own location, with CD-24's generic copy.
  const generic: PrePositionedRed = {
    scripts: {
      [GENERIC_RED_SCRIPT_IDS.REMOTE]: CATALOG.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE],
      [GENERIC_RED_SCRIPT_IDS.ON_SITE]: CATALOG.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE],
    },
    questions: {
      [GENERIC_RED_SCRIPT_IDS.UNKNOWN]: CATALOG.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN],
    },
  };
  const MODE = { ALERT: "rootLayer", CALM: "rootLayer", SILENT: "inFlow" } as const;

  for (const register of ["ALERT", "CALM", "SILENT"] as const) {
    for (const location of RED_LOCATIONS) {
      it(`generic RED: ${register} × ${location} keeps its register, location and affordance`, () => {
        const store = createRedStore();
        store.present({ ...trigger(register, location), scriptId: "rf.not.on.device" }, generic);
        const mode = MODE[register];
        if (location === "UNKNOWN") {
          // CD-24's verdict: ask first; no 112 before the answer.
          expect(redScreen(store.getSnapshot())).toEqual({
            kind: "ask",
            mode,
            register,
            askTr: RAW.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN].askTr,
            motion: RED_MOTION,
          });
          store.answerLocation("notInHospital");
        }
        const resolved = location === "UNKNOWN" ? "REMOTE" : location;
        const raw = RAW.scripts[GENERIC_RED_SCRIPT_IDS[resolved]];
        expect(redScreen(store.getSnapshot())).toMatchObject({
          kind: "act",
          mode,
          register,
          location: resolved,
          actionTr: raw.actionTr, // CD-24's copy, verbatim
          call112: resolved === "REMOTE", // never under ON_SITE
        });
        // The patient is shown a RED (SILENT included), so the dialogue stops.
        expect(redStopsDialogue(store.getSnapshot())).toBe(true);
      });
    }
  }

  it("near miss: a clinician-only RED shows nothing", () => {
    for (const location of RED_LOCATIONS) {
      const deferred: RedState = {
        ...state("DEFERRED_CLINICIAN", location, "unanswered"),
        catalog: generic,
      };
      expect(redScreen(deferred)).toEqual({ kind: "none" });
    }
  });

  // INT-465, review round 2: a wordless generic is a failure, never a pass.
  it("CD-24 generic_red_silent_is_never_wordless: a SILENT generic with no copy fails at every location", () => {
    const empty: PrePositionedRed = { scripts: {}, questions: {} };
    const wordless: PrePositionedRed = {
      ...generic,
      scripts: {
        ...generic.scripts,
        [GENERIC_RED_SCRIPT_IDS.REMOTE]: {
          ...generic.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE],
          actionTr: "",
        },
      },
    };
    for (const catalog of [empty, wordless]) {
      for (const location of RED_LOCATIONS) {
        const store = createRedStore();
        const missing = { ...trigger("SILENT", location), scriptId: "rf.not.on.device" };
        expect(() => store.present(missing, catalog)).toThrow(RedCatalogIncomplete);
        expect(store.getSnapshot()).toBeNull();
        const bare: RedState = { trigger: missing, catalog, answer: "noAnswer", elapsedMs: null };
        expect(() => redScreen(bare)).toThrow(RedCatalogIncomplete);
      }
    }
    // Near miss: with CD-24's copy the same SILENT generic shows words, in the flow.
    for (const location of ["REMOTE", "ON_SITE"] as const) {
      const store = createRedStore();
      store.present({ ...trigger("SILENT", location), scriptId: "rf.not.on.device" }, generic);
      const screen = redScreen(store.getSnapshot());
      expect(screen.kind === "act" && screen.mode).toBe("inFlow");
      expect(screen.kind === "act" && screen.actionTr.length > 0).toBe(true);
    }
  });

  it("CD-24 generic_red_unknown_asks_before_112: the question first, no 112 control", () => {
    for (const register of ["ALERT", "CALM", "SILENT"] as const) {
      const store = createRedStore();
      store.present({ ...trigger(register, "UNKNOWN"), scriptId: "rf.not.on.device" }, generic);
      const screen = redScreen(store.getSnapshot());
      expect(screen.kind).toBe("ask");
      expect("call112" in screen).toBe(false);
    }
  });

  it("CD-24 generic_red_unknown_no_answer_goes_remote: no answer drives the store to REMOTE with 112", () => {
    for (const register of ["ALERT", "CALM", "SILENT"] as const) {
      const store = createRedStore();
      store.present({ ...trigger(register, "UNKNOWN"), scriptId: "rf.not.on.device" }, generic);
      store.answerLocation("noAnswer");
      expect(redScreen(store.getSnapshot())).toMatchObject({
        kind: "act",
        register,
        location: "REMOTE",
        actionTr: RAW.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE].actionTr,
        call112: true,
      });
      // Near miss: "evet" goes ON_SITE, which has words and no 112.
      const yes = createRedStore();
      yes.present({ ...trigger(register, "UNKNOWN"), scriptId: "rf.not.on.device" }, generic);
      yes.answerLocation("inHospital");
      expect(redScreen(yes.getSnapshot())).toMatchObject({
        kind: "act",
        location: "ON_SITE",
        actionTr: RAW.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE].actionTr,
        call112: false,
      });
    }
    // The rule's own question takes its own on_no_answer branch, too.
    const own = createRedStore();
    own.present(trigger("ALERT", "UNKNOWN"), CATALOG);
    own.answerLocation("noAnswer");
    const screen = redScreen(own.getSnapshot());
    expect(screen.kind === "act" && [screen.location, screen.call112]).toEqual(["REMOTE", true]);
  });

  it("the device's no-answer wait is a named, unsigned engineering value (CD-24 no_answer_wait is draft)", () => {
    // Recorded as unsigned, never as a clinical value: CD-24 fail_closed_while_draft.
    expect(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS).toBeGreaterThan(0);
    expect(Number.isInteger(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS)).toBe(true);
  });

  it("CD-24 generic_red_stops_intake: no lane may ask or commit a question while a RED stands", () => {
    for (const location of RED_LOCATIONS) {
      for (const register of ["ALERT", "CALM", "SILENT"] as const) {
        expect(intakeLive(state(register, location, "unanswered")), `${register} ${location}`).toBe(
          false,
        );
      }
      // Near miss: a clinician-only RED keeps the step live.
      expect(intakeLive(state("DEFERRED_CLINICIAN", location, "unanswered"))).toBe(true);
    }
    expect(intakeLive(null)).toBe(true);
  });

  it("the root RED layer hides the navigator from assistive technology; SILENT and none do not", () => {
    for (const register of ["ALERT", "CALM"] as const) {
      expect(redCoversNavigator(redScreen(state(register, "REMOTE", "unanswered")))).toBe(true);
      expect(redCoversNavigator(redScreen(state(register, "UNKNOWN", "unanswered")))).toBe(true);
    }
    // Near misses: SILENT is in the flow, and a clinician-only RED shows nothing.
    expect(redCoversNavigator(redScreen(state("SILENT", "REMOTE", "unanswered")))).toBe(false);
    expect(redCoversNavigator(redScreen(state("DEFERRED_CLINICIAN", "REMOTE", "unanswered")))).toBe(
      false,
    );
    expect(redCoversNavigator(redScreen(null))).toBe(false);
  });

  it("CD-24 generic_red_stops_intake: a question that arrives after the RED is not shown", () => {
    const before = ["q1", "a1"];
    const red: RedState = {
      trigger: { ...trigger("SILENT", "REMOTE"), scriptId: "rf.not.on.device" },
      catalog: generic,
      answer: "unanswered",
      elapsedMs: null,
    };
    // The RED lands while the stream has two entries; the agent's next question
    // arrives after it.
    const frozen = dialogueFrozenAt(null, redStopsDialogue(red), before.length);
    expect(frozen).toBe(2);
    const after = [...before, "q2: Ateşiniz var mı?"];
    expect(
      dialogueShown(after, dialogueFrozenAt(frozen, redStopsDialogue(red), after.length)),
    ).toEqual(before);
    // Near miss: with no RED, or a clinician-only one, the question shows.
    expect(dialogueFrozenAt(null, redStopsDialogue(null), after.length)).toBeNull();
    expect(dialogueShown(after, null)).toEqual(after);
    const deferred: RedState = {
      ...red,
      trigger: { ...red.trigger, register: "DEFERRED_CLINICIAN" },
    };
    expect(
      dialogueShown(after, dialogueFrozenAt(null, redStopsDialogue(deferred), after.length)),
    ).toEqual(after);
  });
});

describe("RED store — escalation only", () => {
  it("a RED the patient sees stays; a later RED does not replace it", () => {
    const store = createRedStore();
    let emitted = 0;
    store.subscribe(() => {
      emitted += 1;
    });
    store.present(trigger("CALM", "REMOTE"), CATALOG, 5);
    store.present(trigger("ALERT", "REMOTE"), CATALOG, 1);
    expect(store.getSnapshot()?.trigger.register).toBe("CALM");
    expect(store.getSnapshot()?.elapsedMs).toBe(5);
    expect(emitted).toBe(1);
  });

  it("a clinician-only RED yields to one the patient must see, and not the reverse", () => {
    const store = createRedStore();
    store.present(trigger("DEFERRED_CLINICIAN", "REMOTE"), CATALOG);
    store.present(trigger("DEFERRED_CLINICIAN", "ON_SITE"), CATALOG);
    expect(store.getSnapshot()?.trigger.location).toBe("REMOTE");
    store.present(trigger("SILENT", "REMOTE"), CATALOG);
    expect(store.getSnapshot()?.trigger.register).toBe("SILENT");
    store.present(trigger("DEFERRED_CLINICIAN", "REMOTE"), CATALOG);
    expect(store.getSnapshot()?.trigger.register).toBe("SILENT");
  });

  it("the location question is answered once, and only under UNKNOWN", () => {
    const store = createRedStore();
    store.present(trigger("ALERT", "REMOTE"), CATALOG);
    store.answerLocation("inHospital");
    expect(store.getSnapshot()?.answer).toBe("unanswered"); // near miss: REMOTE is known
    const unknown = createRedStore();
    unknown.present(trigger("ALERT", "UNKNOWN"), CATALOG);
    unknown.answerLocation("notInHospital");
    unknown.answerLocation("inHospital");
    expect(unknown.getSnapshot()?.answer).toBe("notInHospital");
    const screen = redScreen(unknown.getSnapshot());
    expect(screen.kind === "act" && screen.location).toBe("REMOTE");
  });

  // INT-465 round 3; LD-05 (INT-471, #800). The WCAG 2.2.1 Essential Exception for
  // the unsigned no-answer wait holds only if the patient's own answer, given after
  // the wait took the no-answer branch, is honoured. The wait never removes it.
  describe("a late location answer, after the wait took the no-answer branch (LD-05)", () => {
    const setups = [
      [
        "the rule's own question",
        (r: RedRegister) => trigger(r, "UNKNOWN"),
        CATALOG,
        RAW.questions[scriptIdFor(RULE, "UNKNOWN")].askTr,
      ],
      [
        "the generic question",
        // A rule whose question is not on the device asks CD-24's generic one.
        (r: RedRegister) => ({ ...trigger(r, "UNKNOWN"), scriptId: "rf.not.on.device" }),
        CATALOG,
        RAW.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN].askTr,
      ],
    ] as const;

    for (const [name, make, catalog, askTr] of setups) {
      for (const register of ["ALERT", "CALM", "SILENT"] as const) {
        it(`${name}, ${register}: a late "evet" moves the RED to ON_SITE, and 112 goes`, () => {
          const store = createRedStore();
          store.present(make(register), catalog);
          store.answerLocation("noAnswer");
          expect(redScreen(store.getSnapshot())).toMatchObject({
            kind: "act",
            location: "REMOTE",
            call112: true,
          });
          store.answerLocation("inHospital");
          expect(store.getSnapshot()?.answer).toBe("inHospital");
          expect(redScreen(store.getSnapshot())).toMatchObject({
            kind: "act",
            register,
            location: "ON_SITE",
            call112: false, // invariant 21: absent under ON_SITE
            lateAskTr: null, // answered: the question is closed
          });
        });

        it(`${name}, ${register}: a late "hayır" keeps REMOTE with 112`, () => {
          const store = createRedStore();
          store.present(make(register), catalog);
          store.answerLocation("noAnswer");
          store.answerLocation("notInHospital");
          expect(store.getSnapshot()?.answer).toBe("notInHospital");
          expect(redScreen(store.getSnapshot())).toMatchObject({
            kind: "act",
            location: "REMOTE",
            call112: true,
            lateAskTr: null,
          });
        });

        it(`${name}, ${register}: near miss: with no late answer it stays REMOTE with 112, question still open`, () => {
          const store = createRedStore();
          store.present(make(register), catalog);
          store.answerLocation("noAnswer");
          store.answerLocation("noAnswer"); // a second expiry is not an answer
          expect(store.getSnapshot()?.answer).toBe("noAnswer");
          const screen = redScreen(store.getSnapshot());
          expect(screen).toMatchObject({ kind: "act", location: "REMOTE", call112: true });
          // The question stays open, after the action and 112 (RedLayer).
          expect(screen.kind === "act" && screen.lateAskTr).toBe(askTr);
        });
      }
    }

    it("the patient's own answer is final: nothing moves it afterwards", () => {
      const store = createRedStore();
      store.present(trigger("ALERT", "UNKNOWN"), CATALOG);
      store.answerLocation("noAnswer");
      store.answerLocation("inHospital");
      store.answerLocation("notInHospital");
      store.answerLocation("noAnswer");
      expect(store.getSnapshot()?.answer).toBe("inHospital");
    });
  });
});

describe("the hop's request and decoding", () => {
  const answers: Answer[] = [
    { questionId: "complaint", values: ["pain", "fever"], words: "başım ağrıyor" },
    { questionId: "extra", values: ["serbest metin"] },
    { questionId: "duration", values: [" "] },
  ];

  it("sends bound values only — never the patient's words — and drops an empty answer", () => {
    const request = triageRequest(answers, "REMOTE", new Date("2026-08-29T07:00:00.000Z"));
    expect(request).toEqual({
      location: "REMOTE",
      reference_time: "2026-08-29T07:00:00.000Z",
      answers: { complaint: ["pain", "fever"], extra: "serbest metin" },
    });
    expect(JSON.stringify(request)).not.toContain("başım");
  });

  it("a refused trigger is unevaluated, never coerced to GREEN or RED", async () => {
    const reply =
      (body: unknown, status = 200) =>
      async () => ({
        status,
        bytes: new TextEncoder().encode(JSON.stringify(body)),
      });
    const request = triageRequest(answers, "REMOTE", new Date(0));
    const noRegister = {
      kind: "red_trigger",
      ruleId: RULE,
      location: "REMOTE",
      scriptId: "x.remote",
    };
    expect(await evaluateBoundAnswers(reply(noRegister), request)).toEqual({ kind: "unevaluated" });
    expect(
      await evaluateBoundAnswers(reply({ kind: "triage_level", level: "RED" }), request),
    ).toEqual({ kind: "unevaluated" });
    expect(
      await evaluateBoundAnswers(reply({ error: "triage_unconfigured" }, 503), request),
    ).toEqual({ kind: "unevaluated" });
    expect(
      await evaluateBoundAnswers(async () => {
        throw new Error("offline");
      }, request),
    ).toEqual({ kind: "unevaluated" });
    expect(
      await evaluateBoundAnswers(reply({ kind: "triage_level", level: "YELLOW" }), request),
    ).toEqual({ kind: "level", level: "YELLOW" });
  });

  it("the catalog is all or nothing: one malformed entry refuses it", () => {
    const raw = JSON.parse(new TextDecoder().decode(CATALOG_BYTES)) as Record<string, unknown>;
    const broken = structuredClone(raw) as { scripts: Record<string, Record<string, unknown>> };
    broken.scripts[scriptIdFor(RULE, "REMOTE")].actionTr = "";
    expect(decodeRedCatalog(new TextEncoder().encode(JSON.stringify(broken)))).toBeNull();
    const question = structuredClone(raw) as { questions: Record<string, Record<string, unknown>> };
    question.questions[scriptIdFor(RULE, "UNKNOWN")].onYes = "UNKNOWN";
    expect(decodeRedCatalog(new TextEncoder().encode(JSON.stringify(question)))).toBeNull();
    expect(decodeRedCatalog(new TextEncoder().encode("not json"))).toBeNull();
  });
});

describe("the location axis (files/02 §5.3 Axis 3)", () => {
  const today = "2026-08-29";
  it("REMOTE only for Hızlı on a visit planned for a later day or not yet booked", () => {
    expect(deriveRedLocation({ mode: "hizli", visitDate: "2026-09-02", today, kiosk: false })).toBe(
      "REMOTE",
    );
    expect(deriveRedLocation({ mode: "hizli", visitDate: null, today, kiosk: false })).toBe(
      "REMOTE",
    );
  });
  it("UNKNOWN on the visit day, in Detaylı without a check-in, and on a kiosk (near misses)", () => {
    expect(deriveRedLocation({ mode: "hizli", visitDate: today, today, kiosk: false })).toBe(
      "UNKNOWN",
    );
    expect(
      deriveRedLocation({ mode: "detayli", visitDate: "2026-09-02", today, kiosk: false }),
    ).toBe("UNKNOWN");
    expect(deriveRedLocation({ mode: "hizli", visitDate: "2026-09-02", today, kiosk: true })).toBe(
      "UNKNOWN",
    );
  });
});
