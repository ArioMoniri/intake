/**
 * INT-414 — the planners that feed the composer, and the seams that carry its
 * output to the patient.
 *
 * `delivery.test.ts` holds the composer to the boundary (items verbatim, RED
 * bare, nothing asked, nothing claimed). This suite holds what sits either side
 * of it:
 *
 *   - which question counts as sensitive, pain, instrument or routine, and
 *     which note topic it opens — read from what the pack DECLARES, never
 *     guessed from wording;
 *   - whole sessions, voice and typed, folded turn by turn: the opening once,
 *     a transition where the topic changes, no line twice in a row;
 *   - the voice seam: a lead-in clip that is not ready is dropped rather than
 *     waited for, so the question is never late because of its lead-in;
 *   - the vendor seam: a delivery line is mintable as `ScriptedTr` only from
 *     its resource key, and the server's allow-list mirrors exactly the lines
 *     the voice lane can speak.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { tr } from "../i18n/tr";
import {
  allQuestions,
  packForDepartment,
  packForVisit,
  spokenPack,
  type IntakeQuestion,
} from "../intake/questions";
import { composeDelivery, DELIVERY_CUES, DELIVERY_TOPICS, type Utterance } from "./delivery";
import { DELIVERY_CONTEXTS, type DeliveryContext } from "./deliveryContext";
import {
  DELIVERY_DECK,
  DELIVERY_KEYS,
  prewarmContextOf,
  slotOf,
  VOICE_DELIVERY_KEYS,
} from "./deliveryDeck";
import { deliveryClipName, settleTurnClips } from "./deliveryClips";
import {
  closingDelivery,
  deliveryTopicOf,
  planDelivery,
  planDialogueDelivery,
  questionContextOf,
  questionDeliveryContextOf,
  questionItem,
  stepFor,
  typedStepDelivery,
} from "./deliveryPlan";
import { requireScriptedDeliveryTr, scriptedDeliveryTr } from "./georgeClip";
import { questionSpeechTr } from "./speech";
import type { StreamEntry } from "./stream";
import { clipName, createClipStore, type ClipFs } from "./tts";

const REPO = join(__dirname, "..", "..", "..", "..", "..");
const SRC = join(__dirname, "..", "..");

const byId = (id: string): IntakeQuestion => {
  const found = allQuestions.find((q) => q.id === id);
  if (found === undefined) {
    throw new Error(`no question ${id}`);
  }
  return found;
};

function deliveryKeys(out: readonly Utterance[]): string[] {
  return out.filter((u) => u.kind !== "question").map((u) => u.key);
}

/** A deterministic PRNG for cue sequences — the suite never uses Math.random. */
function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

const DEPARTMENTS = [
  undefined,
  "Kardiyoloji",
  "Nöroloji",
  "KBB",
  "Ortopedi",
  "Dermatoloji",
  "Göğüs Hastalıkları",
  "Kadın Hastalıkları ve Doğum",
  "Üroloji",
  "Göz",
  "Gastroenteroloji",
];

// --- classification ------------------------------------------------------------------

describe("question context is read from what the pack declares", () => {
  it("pain is exactly the questions gated on the patient having named pain", () => {
    const pain = allQuestions.filter((q) => questionContextOf(q) === "pain").map((q) => q.id);
    const gatedOnPain = allQuestions
      .filter((q) => q.askIf?.includesAny.includes("pain") === true)
      .map((q) => q.id);
    expect(pain).toEqual(gatedOnPain);
    expect(pain).toEqual(
      expect.arrayContaining([
        "pain_character",
        "ent_pain_where",
        "gyn_pain_where",
        "eye_pain_move",
      ]),
    );
  });

  it("sensitive is a deferrable section or a text-first step (files/13 §13, 02 §33)", () => {
    for (const q of allQuestions) {
      const declared = q.deferrableAs !== undefined || q.delivery === "text_first";
      expect(questionContextOf(q) === "sensitive", q.id).toBe(declared);
    }
    expect(questionContextOf(byId("fh_known"))).toBe("sensitive");
    expect(questionContextOf(byId("substance"))).toBe("sensitive");
  });

  it("an instrument step is the instrument context, whatever else it declares", () => {
    // Test-only: no shipped step carries an instrument (HB-C1, HB-L2, HB-L3).
    // It also declares a deferral, which the instrument context outranks.
    const item: IntakeQuestion = {
      id: "test_instrument_step",
      titleKey: "intake.q.severity",
      kind: "single",
      ask: "closed",
      options: [{ id: "a", labelKey: "intake.opt.yes" }],
      instrument: { instrumentId: "PHQ-9", itemId: "item_1" },
      deferrableAs: "wellbeing",
    };
    expect(questionContextOf(item)).toBe("instrument");
  });

  it("everything else is routine", () => {
    expect(questionContextOf(byId("complaint"))).toBe("routine");
    expect(questionContextOf(byId("duration"))).toBe("routine");
  });
});

describe("the topic a question opens is its note section", () => {
  it("maps the history block, the base layer and the closing step", () => {
    expect(deliveryTopicOf(byId("complaint"))).toBe("hpi");
    expect(deliveryTopicOf(byId("allergy_known"))).toBe("allergies");
    expect(deliveryTopicOf(byId("meds_other"))).toBe("medications");
    expect(deliveryTopicOf(byId("pmh_known"))).toBe("pmh");
    expect(deliveryTopicOf(byId("fh_known"))).toBe("family");
    expect(deliveryTopicOf(byId("smoking"))).toBe("social");
    expect(deliveryTopicOf(byId("extra"))).toBe("wrapup");
    const measure = packForVisit(undefined, { mode: "detayli" }).find((q) => q.kind === "measure");
    expect(measure).toBeDefined();
    expect(deliveryTopicOf(measure!)).toBe("measurements");
  });
});

// --- whole sessions ------------------------------------------------------------------

describe("a whole voice session, folded turn by turn", () => {
  const pack = spokenPack(packForVisit("Kardiyoloji", { mode: "detayli" }));
  const neutral = planDelivery(
    pack.map((q) => stepFor(q, "none")),
    { sessionSeed: "visit-7", lane: "voice", start: "opening" },
  );

  it("opens once, with a welcome and the voice orientation", () => {
    expect(deliveryKeys(neutral[0])).toHaveLength(2);
    expect(DELIVERY_DECK.welcome).toContain(neutral[0][0].key);
    expect(DELIVERY_DECK.orientVoice).toContain(neutral[0][1].key);
    for (const turn of neutral.slice(1)) {
      for (const key of deliveryKeys(turn)) {
        expect(DELIVERY_DECK.welcome as readonly string[]).not.toContain(key);
      }
    }
  });

  it("asks every question verbatim and last", () => {
    neutral.forEach((turn, i) => {
      expect(turn.at(-1)?.kind).toBe("question");
      expect(Object.is(turn.at(-1)?.text, questionSpeechTr(pack[i]))).toBe(true);
      expect(turn.filter((u) => u.kind === "question")).toHaveLength(1);
    });
  });

  it("announces a new topic where the pack changes section", () => {
    const firstAllergy = pack.findIndex((q) => q.id === "allergy_known");
    const firstFamily = pack.findIndex((q) => q.id === "fh_known");
    const wrapup = pack.findIndex((q) => q.id === "extra");
    expect(DELIVERY_DECK.topicAllergies).toContain(neutral[firstAllergy][0].key);
    expect(DELIVERY_DECK.topicFamily).toContain(neutral[firstFamily][0].key);
    expect(neutral[firstFamily][0].deliveryContext).toBe("sensitive");
    expect(DELIVERY_DECK.topicWrapup).toContain(neutral[wrapup][0].key);
  });

  it("carries at most one line per turn after the opening, and never the same line twice running", () => {
    const offenders: string[] = [];
    for (const department of DEPARTMENTS) {
      for (const mode of ["hizli", "detayli"] as const) {
        const questions = spokenPack(packForVisit(department, { mode }));
        for (let s = 0; s < 12; s += 1) {
          const random = lcg(s + 1);
          const cues = [
            "none",
            "hesitant",
            "revised",
            "long_silence",
            "barge_in",
            "repeat_request",
          ] as const;
          const plan = planDelivery(
            questions.map((q) => stepFor(q, cues[Math.floor(random() * cues.length)])),
            { sessionSeed: `s-${s}`, lane: "voice", start: s % 2 === 0 ? "opening" : "first" },
          );
          plan.forEach((turn, i) => {
            const keys = deliveryKeys(turn);
            if (keys.length > (i === 0 ? 2 : 1)) {
              offenders.push(`${department}/${mode}/${s}@${i}: ${keys.length} lines`);
            }
            const before = i > 0 ? new Set(deliveryKeys(plan[i - 1])) : new Set<string>();
            for (const key of keys) {
              if (before.has(key)) {
                offenders.push(`${department}/${mode}/${s}@${i}: ${key} twice running`);
              }
            }
          });
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("is quieter than it is decorated over a routine stretch", () => {
    const plan = planDelivery(
      pack.map((q) => stepFor(q, "none")),
      { sessionSeed: "visit-9", lane: "voice", start: "first" },
    );
    const bare = plan.filter((turn) => deliveryKeys(turn).length === 0).length;
    expect(bare).toBeGreaterThan(plan.length / 3);
  });

  it("gets brief after a barge-in: no acknowledgement, no cadence line", () => {
    const steps = pack.slice(0, 3).map((q) => stepFor(q, "barge_in"));
    for (let s = 0; s < 50; s += 1) {
      const plan = planDelivery(steps, { sessionSeed: `b-${s}`, lane: "voice", start: "first" });
      for (const turn of plan.slice(1)) {
        expect(deliveryKeys(turn)).toEqual([]);
      }
    }
  });
});

describe("the dialogue stream plan", () => {
  const pack = spokenPack(packForDepartment("Kardiyoloji"));
  const [first, second] = pack;
  const stream: StreamEntry[] = [
    { kind: "agent_question", questionId: first.id },
    { kind: "patient", workId: 1, status: "text", text: "Başım ağrıyor" },
    { kind: "agent_question", questionId: second.id },
    { kind: "agent_confirm", questionId: first.id, values: ["headache"] },
    { kind: "agent_unclear", questionId: second.id },
    { kind: "agent_question", questionId: second.id },
  ];

  it("plans the question entries only, and opens the first", () => {
    const plan = planDialogueDelivery(pack, stream, new Map(), "visit-3");
    expect([...plan.keys()]).toEqual([0, 2, 5]);
    expect(DELIVERY_DECK.welcome).toContain(plan.get(0)![0].key);
  });

  it("explains a re-ask with the repair line the reducer's unclear entry stands for", () => {
    const plan = planDialogueDelivery(pack, stream, new Map(), "visit-3");
    expect(DELIVERY_DECK.repair).toContain(plan.get(5)![0].key);
    expect(Object.is(plan.get(5)!.at(-1)!.text, questionSpeechTr(second))).toBe(true);
  });

  it("answers a recorded cue on the entry it was recorded for", () => {
    const plan = planDialogueDelivery(pack, stream, new Map([[2, "hesitant" as const]]), "visit-3");
    expect(DELIVERY_DECK.hesitant).toContain(plan.get(2)![0].key);
  });

  it("never lets a patient's words reach the plan", () => {
    const plan = planDialogueDelivery(pack, stream, new Map(), "visit-3");
    for (const turn of plan.values()) {
      for (const utterance of turn) {
        expect(utterance.text).not.toContain("Başım ağrıyor");
      }
    }
  });
});

describe("the typed lane", () => {
  const applicable = packForVisit("Kardiyoloji", { mode: "hizli" });

  it("welcomes a fresh intake with the typed orientation, never the spoken one", () => {
    const lines = typedStepDelivery({
      applicable,
      answers: [],
      currentId: applicable[0].id,
      startId: applicable[0].id,
      fresh: true,
      sessionSeed: "visit-5",
    });
    expect(lines.map((u) => u.kind)).toEqual(["lead_in", "transition"]);
    expect(DELIVERY_DECK.orientTyped).toContain(lines[1].key);
  });

  it("picks a resumed intake up where it left off", () => {
    const lines = typedStepDelivery({
      applicable,
      answers: [{ questionId: applicable[0].id, values: ["headache"] }],
      currentId: applicable[1].id,
      startId: applicable[1].id,
      fresh: false,
      sessionSeed: "visit-5",
    });
    expect(lines).toHaveLength(1);
    expect(DELIVERY_DECK.resume).toContain(lines[0].key);
  });

  it("acknowledges a don't-know answer on the next step", () => {
    const allergyKnown = applicable.findIndex((q) => q.id === "allergy_known");
    const next = applicable[allergyKnown + 1];
    const answers = applicable
      .slice(0, allergyKnown + 1)
      .map((q) => ({ questionId: q.id, values: q.id === "allergy_known" ? ["not_sure"] : ["x"] }));
    const lines = typedStepDelivery({
      applicable,
      answers,
      currentId: next.id,
      startId: applicable[0].id,
      fresh: true,
      sessionSeed: "visit-5",
    });
    // A new topic outranks the acknowledgement; on a same-topic step the
    // acknowledgement is what is said.
    const expected =
      next.noteSection === "allergies" ? DELIVERY_DECK.hesitant : DELIVERY_DECK.topicMedications;
    expect(expected as readonly string[]).toContain(lines[0].key);
  });

  it("is the same line on every render of the same step", () => {
    const input = {
      applicable,
      answers: [{ questionId: applicable[0].id, values: ["headache"] }],
      currentId: applicable[1].id,
      startId: applicable[0].id,
      fresh: true,
      sessionSeed: "visit-5",
    };
    expect(typedStepDelivery(input)).toEqual(typedStepDelivery(input));
  });
});

describe("the closing", () => {
  it("thanks the patient in the closing context, and is stable for one visit", () => {
    const lines = closingDelivery("visit-8", 12);
    expect(lines).toHaveLength(1);
    expect(DELIVERY_DECK.closing).toContain(lines[0].key);
    expect(lines[0].deliveryContext).toBe("closing");
    expect(closingDelivery("visit-8", 12)).toEqual(lines);
  });
});

// --- the voice seam ------------------------------------------------------------------

describe("delivery clips", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("names every delivery clip safely and uniquely, per key AND context, apart from question clips", () => {
    // A line said in two contexts is two clips (INT-415 profiles differ), so
    // the context is part of the name and a cache hit is never the wrong voice.
    const names = DELIVERY_KEYS.flatMap((key) =>
      DELIVERY_CONTEXTS.map((context) => deliveryClipName(key, context)),
    );
    expect(new Set(names).size).toBe(names.length);
    for (const name of names) {
      expect(name).toMatch(/^l_[a-z0-9_]+\.wav$/);
    }
    expect(names).not.toContain(clipName("question", "complaint"));
  });

  it("drops a lead-in that is not ready: the question is never late for it", async () => {
    const stalled = new Promise<string>(() => undefined);
    const turn = await settleTurnClips(Promise.resolve("q.wav"), [stalled], {
      awaitLeads: false,
      deadlineMs: 60_000,
    });
    expect(turn).toEqual({ leads: [], question: "q.wav" });
  });

  it("always keeps a lead-in already synthesised this session — no race with a cache hit", async () => {
    const turn = await settleTurnClips(Promise.resolve("q.wav"), ["ready.wav"], {
      awaitLeads: false,
      deadlineMs: 60_000,
    });
    expect(turn).toEqual({ leads: ["ready.wav"], question: "q.wav" });
  });

  it("keeps a ready lead-in, in order, and skips one that failed", async () => {
    const turn = await settleTurnClips(
      new Promise<string>((resolve) => setTimeout(() => resolve("q.wav"), 5)),
      [
        Promise.resolve("a.wav"),
        Promise.reject(new Error("tts_unavailable")),
        Promise.resolve("c.wav"),
      ],
      { awaitLeads: false, deadlineMs: 60_000 },
    );
    expect(turn).toEqual({ leads: ["a.wav", "c.wav"], question: "q.wav" });
  });

  it("waits for the opening's own clips, but never past the clip deadline", async () => {
    vi.useFakeTimers();
    const pending = settleTurnClips(
      Promise.resolve("q.wav"),
      [
        new Promise<string>(() => undefined),
        new Promise<string>((r) => setTimeout(() => r("b.wav"), 10)),
      ],
      { awaitLeads: true, deadlineMs: 1_000 },
    );
    await vi.advanceTimersByTimeAsync(1_000);
    await expect(pending).resolves.toEqual({ leads: ["b.wav"], question: "q.wav" });
  });

  it("fails the turn's speech only when the QUESTION clip fails", async () => {
    await expect(
      settleTurnClips(Promise.reject(new Error("tts_deadline")), [Promise.resolve("a.wav")], {
        awaitLeads: false,
        deadlineMs: 1_000,
      }),
    ).rejects.toThrow("tts_deadline");
  });
});

// --- the delivery context reaches the voice lane (INT-415 contract) ------------------

describe("each utterance's delivery context travels with its clip", () => {
  it("a question is spoken in its own context — sensitive, instrument, or routine", () => {
    expect(questionDeliveryContextOf(byId("fh_known"))).toBe("sensitive");
    expect(questionDeliveryContextOf(byId("substance"))).toBe("sensitive");
    expect(questionDeliveryContextOf(byId("pain_character"))).toBe("routine");
    expect(questionDeliveryContextOf(byId("complaint"))).toBe("routine");
    for (const question of allQuestions) {
      // the context the plan tags the question with is the one its clip is made in
      const [asked] = composeDelivery({
        phase: "mid",
        questionContext: questionContextOf(question),
        cue: "none",
        turnIndex: 1,
        sessionSeed: "s",
        previousKey: "dialogue.delivery.lead.a",
        lane: "voice",
        topic: "hpi",
        previousTopic: "hpi",
        previousContext: questionContextOf(question),
        item: questionItem(question),
      }).filter((u) => u.kind === "question");
      expect(asked.deliveryContext, question.id).toBe(questionDeliveryContextOf(question));
      expect(asked.deliveryContext).not.toBe("red");
    }
  });

  it("every fixed-slot line is tagged with its slot's context; repair and silence follow the question", () => {
    const offenders: string[] = [];
    for (const [c, questionContext] of (
      ["routine", "pain", "sensitive", "instrument"] as const
    ).entries()) {
      for (const cue of DELIVERY_CUES) {
        for (const topic of DELIVERY_TOPICS) {
          for (let turnIndex = 0; turnIndex < 6; turnIndex += 1) {
            for (const phase of ["opening", "first", "mid", "sensitive"] as const) {
              const out = composeDelivery({
                phase,
                questionContext,
                cue,
                turnIndex,
                sessionSeed: `s-${c}`,
                previousKey: null,
                lane: "voice",
                topic,
                previousTopic: "hpi",
                previousContext: "routine",
                item: questionItem(allQuestions[0]),
              });
              for (const utterance of out.filter((u) => u.kind !== "question")) {
                const slot = slotOf(utterance.key);
                const expected: DeliveryContext =
                  slot === "repair" || slot === "silence"
                    ? questionContext === "pain"
                      ? "routine"
                      : questionContext
                    : prewarmContextOf(utterance.key);
                if (utterance.deliveryContext !== expected) {
                  offenders.push(
                    `${utterance.key} in ${utterance.deliveryContext}, not ${expected}`,
                  );
                }
              }
            }
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the clip store forwards the context to the synthesizer", async () => {
    const files = new Map<string, string>();
    const fs: ClipFs = {
      exists: async (path) => files.has(path),
      mkdirp: async () => undefined,
      writeBase64: async (path, base64) => {
        files.set(path, base64);
      },
      removeDir: async () => undefined,
    };
    const seen: (DeliveryContext | undefined)[] = [];
    const store = createClipStore("cache/dialogue/", fs, async (_text, context) => {
      seen.push(context);
      return new Uint8Array([1, 2, 3]);
    });
    await store.ensure("l_welcome_x.wav", tr["dialogue.delivery.welcome.a"], "welcome");
    await store.ensure("q_complaint.wav", "Bugün sizi buraya getiren nedir");
    expect(seen).toEqual(["welcome", undefined]);
  });

  it("the voice lane hands every clip its context, and George receives it", () => {
    const read = (...parts: string[]) => readFileSync(join(SRC, ...parts), "utf8");
    const clips = read("lib", "dialogue", "clips.ts");
    expect(clips).toContain("prefer(text as ScriptedTr, context)");
    const hook = read("lib", "dialogue", "useDialogueSession.ts");
    expect(hook).toContain("deliveryClipName(key, context)");
    expect(hook).toContain("store.ensure(name, scriptedDeliveryTr(key), context)");
    expect(hook).toContain("utterance.deliveryContext");
    expect(hook).toContain("prewarmContextOf(key)");
    expect(hook).toMatch(/store\.ensure\(name, speech, questionContext\)/);
    // every question-clip ensure in the hook carries a context
    /** The top-level argument count of the call whose `(` is at `open`. */
    const argumentCount = (source: string, open: number): number => {
      let depth = 0;
      let commas = 0;
      for (let i = open; i < source.length; i += 1) {
        const ch = source[i];
        if (ch === "(" || ch === "[" || ch === "{") {
          depth += 1;
        } else if (ch === ")" || ch === "]" || ch === "}") {
          depth -= 1;
          if (depth === 0) {
            const inner = source
              .slice(open + 1, i)
              .trim()
              .replace(/,$/, "");
            return inner.length === 0 ? 0 : commas + 1;
          }
        } else if (ch === "," && depth === 1) {
          commas += 1;
        }
      }
      return -1;
    };
    const calls = [...hook.matchAll(/store\.ensure\(/g)];
    expect(calls.length).toBeGreaterThan(3);
    for (const call of calls) {
      const open = call.index + call[0].length - 1;
      expect(argumentCount(hook, open), hook.slice(call.index, call.index + 80)).toBe(3);
    }
  });
});

// --- the vendor seam -----------------------------------------------------------------

describe("a delivery line is scripted text, mintable only from its key", () => {
  it("mints the catalogue string for a deck key", () => {
    for (const key of DELIVERY_KEYS) {
      expect(scriptedDeliveryTr(key)).toBe(tr[key]);
    }
  });

  it("refuses anything that is not exactly that key's catalogue string", () => {
    const key = DELIVERY_DECK.thanks[0];
    expect(requireScriptedDeliveryTr(tr[key], key)).toBe(tr[key]);
    expect(() => requireScriptedDeliveryTr("Göğsüm sıkışıyor", key)).toThrow("george_not_scripted");
    expect(() => requireScriptedDeliveryTr(`${tr[key]} `, key)).toThrow("george_not_scripted");
  });

  it("has no string-typed door", () => {
    // @ts-expect-error — a free string is not a deck key, so it cannot be minted
    expect(() => scriptedDeliveryTr("Göğsüm sıkışıyor")).toThrow();
  });

  it("the server allow-list mirrors exactly the lines the voice lane can speak", () => {
    const mirror = readFileSync(
      join(REPO, "services", "api", "src", "intake_api", "dev_voice_delivery.py"),
      "utf8",
    );
    const keys = [...mirror.matchAll(/^\s+"(dialogue\.[A-Za-z0-9_.]+)":/gm)].map((m) => m[1]);
    expect([...keys].sort()).toEqual([...VOICE_DELIVERY_KEYS].sort());
    for (const key of VOICE_DELIVERY_KEYS) {
      expect(mirror, key).toContain(JSON.stringify(tr[key]));
    }
  });

  it("keeps the display-only lines off the voice lane", () => {
    for (const key of [...DELIVERY_DECK.orientTyped, ...DELIVERY_DECK.closing]) {
      expect(VOICE_DELIVERY_KEYS as readonly string[]).not.toContain(key);
    }
  });
});

// --- the screens ---------------------------------------------------------------------

describe("wiring", () => {
  const read = (...parts: string[]) => readFileSync(join(SRC, ...parts), "utf8");

  it("the typed step renders its question heading whatever the delivery says", () => {
    const screen = read("app", "(tabs)", "visits", "[visitId]", "intake.tsx");
    expect(screen).toContain("typedStepDelivery(");
    // The heading line itself carries no condition on the delivery lines.
    const heading = screen.indexOf("{t(question.titleKey)}");
    expect(heading).toBeGreaterThan(-1);
    const lead = screen.indexOf("deliveryLines.map(");
    expect(lead).toBeGreaterThan(-1);
    expect(lead).toBeLessThan(heading);
  });

  it("the dialogue speaks the planned turn and settles its lead-ins without waiting on them", () => {
    const hook = read("lib", "dialogue", "useDialogueSession.ts");
    expect(hook).toContain("planDialogueDelivery(");
    expect(hook).toContain("settleTurnClips(");
    expect(hook).toContain("scriptedDeliveryTr(");
  });

  it("the transcript shows the planned lines as their own bubbles, ahead of the question", () => {
    const surface = read("components", "DialogueIntake.tsx");
    expect(surface).toContain("renderDeliveryBubble");
    // The repair line now travels with the re-asked question, so the reducer's
    // unclear entry no longer renders a second copy of it.
    expect(surface).not.toContain('t("dialogue.notUnderstood")');
  });
});
