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
import { createRedStore, redScreen, redStopsDialogue, type RedState } from "./store";

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

const ANSWERS: readonly LocationAnswer[] = ["unanswered", "inHospital", "notInHospital"];

describe("RED screen — every register × location × answer", () => {
  it("the recorded catalog decodes and every id it holds is a scriptIdFor id", () => {
    expect(CATALOG).not.toBeNull();
    const ids = [...Object.keys(CATALOG.scripts), ...Object.keys(CATALOG.questions)].sort();
    expect(ids).toEqual(RED_LOCATIONS.map((l) => scriptIdFor(RULE, l)).sort());
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

  // INT-453: a RED whose script is missing still shows the generic RED, the
  // ALERT root layer at the trigger's own location, and invents no words.
  it.each([
    ["REMOTE", true],
    ["ON_SITE", false],
    ["UNKNOWN", false],
  ] as const)(
    "a RED with a missing script shows the generic RED (%s → 112 %s)",
    (location, call112) => {
      const empty: PrePositionedRed = { scripts: {}, questions: {} };
      for (const register of ["ALERT", "CALM", "SILENT"] as const) {
        const s: RedState = { ...state(register, location, "unanswered"), catalog: empty };
        expect(redScreen(s)).toEqual({
          kind: "act",
          mode: "rootLayer",
          register: "ALERT",
          location,
          actionTr: "",
          doNotsTr: [],
          whyTr: null,
          call112,
          motion: RED_MOTION,
        });
        // The patient is shown a RED, so the dialogue stops.
        expect(redStopsDialogue(s)).toBe(true);
      }
      // Near miss: a clinician-only RED still changes nothing on the patient's screen.
      const deferred: RedState = {
        ...state("DEFERRED_CLINICIAN", location, "unanswered"),
        catalog: empty,
      };
      expect(redScreen(deferred)).toEqual({ kind: "none" });
    },
  );

  it("a generic RED under UNKNOWN asks the generic question first, when one is on the device", () => {
    const generic = {
      scripts: {
        [GENERIC_RED_SCRIPT_IDS.REMOTE]: CATALOG.scripts[scriptIdFor(RULE, "REMOTE")],
        [GENERIC_RED_SCRIPT_IDS.ON_SITE]: CATALOG.scripts[scriptIdFor(RULE, "ON_SITE")],
      },
      questions: {
        [GENERIC_RED_SCRIPT_IDS.UNKNOWN]: CATALOG.questions[scriptIdFor(RULE, "UNKNOWN")],
      },
    };
    const store = createRedStore();
    store.present({ ...trigger("CALM", "UNKNOWN"), scriptId: "rf.not.on.device.unknown" }, generic);
    expect(redScreen(store.getSnapshot())).toMatchObject({
      kind: "ask",
      register: "ALERT",
      askTr: RAW.questions[scriptIdFor(RULE, "UNKNOWN")].askTr,
    });
    store.answerLocation("notInHospital");
    // The generic script's own words, verbatim, and 112 once the answer allows it.
    expect(redScreen(store.getSnapshot())).toMatchObject({
      kind: "act",
      location: "REMOTE",
      actionTr: RAW.scripts[scriptIdFor(RULE, "REMOTE")].actionTr,
      call112: true,
    });
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
