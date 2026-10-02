/**
 * INT-414 — conversational delivery around a question, never inside it.
 *
 * The owner asked for questions that open warm and welcoming, stay
 * professional and not robot-like, and follow the patient's state and the
 * question's context. Everything that answers that request lives in the
 * DELIVERY layer: a welcome, lead-ins, section transitions, acknowledgements
 * and a closing. What this suite holds is the boundary around it:
 *
 *   - every question, instrument item and RED script comes out BYTE-EQUAL
 *     (invariant 10; "conversational delivery may paraphrase the lead-in,
 *     never the item");
 *   - a RED gets nothing before, after or around it (invariant 21);
 *   - no delivery string asks anything, carries a numeral or makes a
 *     clinical claim (invariants 2 and 22);
 *   - variation is deterministic, never repeats back to back, and does not
 *     decorate every turn;
 *   - a cue that is missing, stalled or malformed changes nothing, and the
 *     composer never waits for one (invariant 11).
 *
 * The real PolicyGuard is Python; tests/release/test_delivery_copy.py runs
 * every string here through it. The lexical checks below are this lane's own
 * floor under that gate, not a copy of it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { INSTRUMENT_ITEMS, type InstrumentItem } from "../intake/instruments";
import { allQuestions, packForDepartment, packForVisit } from "../intake/questions";
import {
  composeDelivery,
  DELIVERY_CUES,
  DELIVERY_TOPICS,
  QUESTION_CONTEXTS,
  readCue,
  SESSION_PHASES,
  type DeliveryInput,
  type Utterance,
  type VerbatimItem,
} from "./delivery";
import { DELIVERY_CONTEXTS } from "./deliveryContext";
import {
  ACKNOWLEDGEMENT_SLOTS,
  DELIVERY_DECK,
  DELIVERY_KEYS,
  deliveryTextTr,
  type DeliveryKey,
} from "./deliveryDeck";
import { instrumentItem, questionItem, redItem } from "./deliveryPlan";
import { questionSpeechTr } from "./speech";

const REPO = join(__dirname, "..", "..", "..", "..", "..");

const SEEDS = ["visit-1", "visit-2", "v-ç", "", "a-long-visit-identifier-0042"];
const LANES = ["voice", "typed"] as const;

function base(item: VerbatimItem | null, overrides: Partial<DeliveryInput> = {}): DeliveryInput {
  return {
    phase: "mid",
    questionContext: "routine",
    cue: "none",
    turnIndex: 3,
    sessionSeed: "visit-1",
    previousKey: null,
    lane: "voice",
    topic: "hpi",
    previousTopic: "hpi",
    previousContext: "routine",
    item,
    ...overrides,
  };
}

/** Every input shape the composer can be handed for one item. */
function* everyInput(item: VerbatimItem, dense = true): Generator<DeliveryInput> {
  for (const phase of SESSION_PHASES) {
    if (phase === "closing") {
      continue; // the closing turn carries no item
    }
    for (const questionContext of QUESTION_CONTEXTS) {
      for (const [c, cue] of DELIVERY_CUES.entries()) {
        // The sparse form still visits every phase × context × cue, taking
        // one lane and one turn position per cell in rotation.
        const lanes = dense ? LANES : [LANES[c % LANES.length]];
        for (const lane of lanes) {
          for (const turnIndex of dense ? [0, 1, 2, 7] : [c]) {
            yield base(item, {
              phase,
              questionContext,
              cue,
              lane,
              turnIndex,
              sessionSeed: SEEDS[turnIndex % SEEDS.length],
              topic: DELIVERY_TOPICS[turnIndex % DELIVERY_TOPICS.length],
              previousTopic: "hpi",
            });
          }
        }
      }
    }
  }
}

function questionsOf(utterances: readonly Utterance[]): Utterance[] {
  return utterances.filter((u) => u.kind === "question");
}

// --- the RED scripts, read from the committed pack --------------------------------------

/**
 * Every patient-facing RED string in the life-threat pack: `action_tr`, each
 * `do_nots_tr` line, `why_tr` and the UNKNOWN location's `ask_one_tr`. Read
 * with a deliberately small reader for the three shapes the file uses — an
 * inline double-quoted scalar, a folded `>-` block and a list of quoted
 * items — so the test does not need a YAML dependency the app does not have.
 * `test_the_red_reader_is_not_vacuous` holds it to the file's real size.
 */
function redScriptsFromPack(): string[] {
  const lines = readFileSync(
    join(REPO, "files", "protocols", "base.life_threat.yaml"),
    "utf8",
  ).split("\n");
  const indent = (line: string) => line.length - line.trimStart().length;
  const scripts: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    if (!/^\s*(action_tr|do_nots_tr|why_tr|ask_one_tr):\s*$/.test(lines[i])) {
      continue;
    }
    const trLine = lines[i + 1] ?? "";
    const match = /^(\s*)tr:\s*(.*)$/.exec(trLine);
    if (match === null) {
      continue;
    }
    const at = match[1].length;
    const rest = match[2].trim();
    if (rest.startsWith('"')) {
      scripts.push(JSON.parse(rest) as string);
    } else if (rest === ">-") {
      const body: string[] = [];
      for (
        let j = i + 2;
        j < lines.length && lines[j].trim() !== "" && indent(lines[j]) > at;
        j += 1
      ) {
        body.push(lines[j].trim());
      }
      scripts.push(body.join(" "));
    } else if (rest === "") {
      for (let j = i + 2; j < lines.length && /^\s*-\s*"/.test(lines[j]); j += 1) {
        scripts.push(JSON.parse(lines[j].trim().slice(1).trim()) as string);
      }
    }
  }
  return scripts;
}

const RED_SCRIPTS = redScriptsFromPack();

// --- invariant 10: the item is never altered --------------------------------------------

describe("the question is byte-equal to its scripted composition", () => {
  it("holds for every shipped question, in every phase, context, cue, lane and seed", () => {
    for (const question of allQuestions) {
      const item = questionItem(question);
      const speech = questionSpeechTr(question);
      expect(Object.is(item.text, speech)).toBe(true);
      for (const input of everyInput(item, false)) {
        const asked = questionsOf(composeDelivery(input));
        if (
          asked.length !== 1 ||
          !Object.is(asked[0].text, speech) ||
          asked[0].key !== question.titleKey
        ) {
          expect.fail(`${question.id} / ${input.phase} / ${input.questionContext} / ${input.cue}`);
        }
      }
    }
  });

  it("holds for every pack a visit can run, and the question is always last", () => {
    const departments = [undefined, "Kardiyoloji", "Nöroloji", "KBB", "Ortopedi", "Dermatoloji"];
    const more = [
      "Göğüs Hastalıkları",
      "Kadın Hastalıkları ve Doğum",
      "Üroloji",
      "Göz",
      "Gastroenteroloji",
    ];
    for (const department of [...departments, ...more]) {
      for (const mode of ["hizli", "detayli"] as const) {
        for (const question of packForVisit(department, { mode })) {
          const out = composeDelivery(base(questionItem(question), { turnIndex: 4 }));
          expect(out.at(-1)?.kind).toBe("question");
          expect(Object.is(out.at(-1)?.text, questionSpeechTr(question))).toBe(true);
        }
      }
    }
  });

  it("never mutates the item it was handed", () => {
    const question = packForDepartment("Kardiyoloji")[0];
    const item = Object.freeze({ ...questionItem(question) });
    expect(() => composeDelivery(base(item, { phase: "opening", turnIndex: 0 }))).not.toThrow();
    expect(item.text).toBe(questionSpeechTr(question));
  });
});

describe("a validated instrument item is byte-equal, and its options are untouched", () => {
  /** A synthetic, test-only item: INSTRUMENT_ITEMS is empty by design (HB-C1,
   * HB-L2, HB-L3), so the property is proven on a frozen stand-in AND on every
   * row the registry will ever hold. */
  const SYNTHETIC: InstrumentItem = Object.freeze({
    id: "item_a",
    textTr: "Deneme maddesi, yalnızca bu test için yazıldı.",
    allowParaphrase: false,
    choicesTr: Object.freeze(["Birinci seçenek", "İkinci seçenek"]),
  });

  const registryItems = Object.entries(INSTRUMENT_ITEMS).flatMap(([instrumentId, items]) =>
    items.map((item) => ({ instrumentId, item })),
  );

  it("comes out as the item text itself, for the synthetic item and every registry row", () => {
    for (const { instrumentId, item } of [
      { instrumentId: "TEST-INSTRUMENT", item: SYNTHETIC },
      ...registryItems,
    ]) {
      const choices = item.choicesTr;
      const verbatim = instrumentItem(instrumentId, item);
      expect(Object.is(verbatim.text, item.textTr)).toBe(true);
      for (const input of everyInput(verbatim)) {
        const out = composeDelivery({ ...input, questionContext: "instrument" });
        const asked = questionsOf(out);
        expect(asked).toHaveLength(1);
        expect(Object.is(asked[0].text, item.textTr)).toBe(true);
        expect(asked[0].deliveryContext).toBe("instrument");
      }
      expect(item.choicesTr).toBe(choices);
      expect(item.choicesTr).toEqual(choices);
    }
  });

  it("gets no acknowledgement or cadence line between items — standardised administration", () => {
    const verbatim = instrumentItem("TEST-INSTRUMENT", SYNTHETIC);
    // Every cue, the repeat request included: a re-asked item is asked again
    // exactly as it was, with nothing said in front of it (the clinical
    // review's point — "between items" has no exception).
    for (const cue of DELIVERY_CUES) {
      for (let turnIndex = 1; turnIndex < 40; turnIndex += 1) {
        const out = composeDelivery(
          base(verbatim, {
            questionContext: "instrument",
            previousContext: "instrument",
            cue,
            turnIndex,
          }),
        );
        expect(out).toHaveLength(1);
      }
    }
  });

  it("says nothing in front of a re-asked item, in any phase, lane or seed", () => {
    const verbatim = instrumentItem("TEST-INSTRUMENT", SYNTHETIC);
    for (const input of everyInput(verbatim, false)) {
      const out = composeDelivery({
        ...input,
        phase: "mid",
        questionContext: "instrument",
        previousContext: "instrument",
        cue: "repeat_request",
      });
      expect(out, `${input.sessionSeed}@${input.turnIndex}`).toHaveLength(1);
      expect(Object.is(out[0].text, SYNTHETIC.textTr)).toBe(true);
    }
  });

  it("introduces the instrument, not a repair line, when its first item is re-asked", () => {
    const out = composeDelivery(
      base(instrumentItem("TEST-INSTRUMENT", SYNTHETIC), {
        questionContext: "instrument",
        previousContext: "routine",
        cue: "repeat_request",
      }),
    );
    expect(out).toHaveLength(2);
    expect(DELIVERY_DECK.instrument).toContain(out[0].key);
    expect(DELIVERY_DECK.repair as readonly string[]).not.toContain(out[0].key);
  });

  it("is introduced once, in the instrument's own delivery context", () => {
    const out = composeDelivery(
      base(instrumentItem("TEST-INSTRUMENT", SYNTHETIC), {
        questionContext: "instrument",
        previousContext: "routine",
      }),
    );
    expect(out).toHaveLength(2);
    expect(out[0].kind).toBe("lead_in");
    expect(out[0].deliveryContext).toBe("instrument");
    expect(DELIVERY_DECK.instrument).toContain(out[0].key);
  });
});

describe("RED: the script, the whole script and nothing but the script", () => {
  it("reads every RED string the life-threat pack carries", () => {
    // test_the_red_reader_is_not_vacuous — three rules with scripts, each
    // with REMOTE and ON_SITE actions, do-not lists, explanations and the
    // UNKNOWN location's single question.
    expect(RED_SCRIPTS.length).toBeGreaterThan(20);
    expect(RED_SCRIPTS).toContain("Hemen **112**'yi arayın.");
    expect(RED_SCRIPTS).toContain("Şu anda hastanede misiniz?");
  });

  it("passes every RED script through alone, in every phase, cue, lane and seed", () => {
    for (const [index, script] of RED_SCRIPTS.entries()) {
      const item = redItem(`rf.script_${index}`, script);
      for (const input of everyInput(item)) {
        const out = composeDelivery(input);
        const [only] = out;
        const bare =
          out.length === 1 &&
          only.kind === "question" &&
          only.key === item.key &&
          Object.is(only.text, script) &&
          only.deliveryContext === "red";
        if (!bare) {
          expect.fail(`${item.key} / ${input.phase} / ${input.cue}: ${JSON.stringify(out)}`);
        }
      }
    }
    // One full structural comparison, so the shape itself is asserted too.
    const item = redItem("rf.shape", RED_SCRIPTS[0]);
    expect(composeDelivery(base(item, { phase: "opening", turnIndex: 0 }))).toEqual([
      { kind: "question", key: "rf.shape", text: RED_SCRIPTS[0], deliveryContext: "red" },
    ]);
  });

  it("adds nothing to a RED-adjacent question either", () => {
    const question = allQuestions[0];
    for (const cue of DELIVERY_CUES) {
      const out = composeDelivery(
        base(questionItem(question), {
          questionContext: "red",
          phase: "opening",
          cue,
          turnIndex: 0,
        }),
      );
      expect(out).toEqual([
        {
          kind: "question",
          key: question.titleKey,
          text: questionSpeechTr(question),
          deliveryContext: "red",
        },
      ]);
    }
  });

  it("keeps the bare imperative plural: a RED script is never softened by a lead-in", () => {
    const out = composeDelivery(
      base(redItem("rf.x", "Tutun. Arayın. Bakmayın."), { cue: "hesitant" }),
    );
    expect(out.map((u) => u.text)).toEqual(["Tutun. Arayın. Bakmayın."]);
  });
});

// --- invariant 2: one question per turn, no clinical claims -----------------------------

/** The mı/mi/mu/mü clitic as a whole token, bare or with a person/tense tail. */
const QUESTION_PARTICLE =
  /^m[ıiuü](?:s[ıiuü]n(?:[ıiuü]z)?|y[ıiuü][mz]|yd[ıiuü]|ym[ıiuü]ş|d[ıiuü]r)?$/u;

/** Outcome reassurance, minimising and alarm — none of it belongs to delivery. */
const CLINICAL_CLAIM =
  /(geçecek|geçer\b|düzel(?:ir|ecek|iyor)|iyileş|ciddi|normaldir|endişelen|merak etmeyin|korkmayın|tehlike|önemli bir şey|tanı|teşhis|tedavi|ilacınızı|acil)/iu;

function tokens(text: string): string[] {
  return text
    .split(/\s+/u)
    .map((token) => token.replace(/^[^\p{L}]+|[^\p{L}]+$/gu, "").toLocaleLowerCase("tr-TR"))
    .filter((token) => token.length > 0);
}

function sentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/u)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);
}

describe("every delivery string is speakable, question-free and claim-free", () => {
  it("covers a real deck: every slot has at least two variants except the one repair it extends", () => {
    for (const [slot, keys] of Object.entries(DELIVERY_DECK)) {
      expect(keys.length, slot).toBeGreaterThanOrEqual(2);
      expect(new Set(keys).size, slot).toBe(keys.length);
    }
    expect(DELIVERY_KEYS.length).toBeGreaterThan(40);
  });

  it("exists in tr and in its en mirror", () => {
    for (const key of DELIVERY_KEYS) {
      expect(tr[key], key).toBeTruthy();
      expect(en[key], key).toBeTruthy();
      expect(en[key], key).not.toBe(tr[key]);
      expect(deliveryTextTr(key)).toBe(tr[key]);
    }
  });

  it("asks nothing: no question mark and no mı/mi/mu/mü particle", () => {
    for (const key of DELIVERY_KEYS) {
      const text = tr[key];
      expect(text, key).not.toContain("?");
      for (const token of tokens(text)) {
        expect(QUESTION_PARTICLE.test(token), `${key}: ${token}`).toBe(false);
      }
    }
  });

  it("carries no numeral, in tr or en (invariant 22)", () => {
    for (const key of DELIVERY_KEYS) {
      expect(/\p{Nd}/u.test(tr[key]), key).toBe(false);
      expect(/\p{Nd}/u.test(en[key]), key).toBe(false);
    }
  });

  it("makes no diagnosis, treatment, prognosis, reassurance or alarm", () => {
    for (const key of DELIVERY_KEYS) {
      expect(CLINICAL_CLAIM.test(tr[key]), `${key}: ${tr[key]}`).toBe(false);
    }
  });

  it("stays short: at most two sentences, fifteen words each; acknowledgements five words", () => {
    for (const key of DELIVERY_KEYS) {
      const parts = sentences(tr[key]);
      expect(parts.length, key).toBeLessThanOrEqual(2);
      for (const part of parts) {
        expect(part.split(/\s+/u).length, `${key}: ${part}`).toBeLessThanOrEqual(15);
      }
    }
    for (const slot of ACKNOWLEDGEMENT_SLOTS) {
      for (const key of DELIVERY_DECK[slot]) {
        expect(tr[key].split(/\s+/u).length, key).toBeLessThanOrEqual(5);
      }
    }
  });

  it("stays in siz: no sen form and no doubled-polite imperative", () => {
    const sen = /\b(?:sen|sana|seni|senin|sende|senden|seninle)\b/iu;
    const doubled = /(?:ediniz|giriniz|veriniz|seçiniz|açınız|yazınız|okuyunuz|dokununuz)\b/iu;
    for (const key of DELIVERY_KEYS) {
      expect(sen.test(tr[key]), key).toBe(false);
      expect(doubled.test(tr[key]), key).toBe(false);
    }
  });

  it("never claims what the product does not do: no doctor-sharing line, no repeat command", () => {
    // docs/legal/strings.yaml does not exist, so no sentence may say where
    // the answers go; and the dev dialogue has no spoken repeat command yet.
    for (const key of DELIVERY_KEYS) {
      expect(tr[key], key).not.toMatch(/hekim|doktor|paylaş|iletil|gönderil/iu);
      expect(tr[key], key).not.toMatch(/tekrar/iu);
    }
  });
});

describe("tags", () => {
  it("every utterance carries one of the shared delivery contexts", () => {
    const question = allQuestions[1];
    for (const input of everyInput(questionItem(question))) {
      for (const utterance of composeDelivery(input)) {
        expect(DELIVERY_CONTEXTS).toContain(utterance.deliveryContext);
      }
    }
  });

  it("opens with the welcome context and closes with the closing context", () => {
    const opening = composeDelivery(
      base(questionItem(allQuestions[0]), { phase: "opening", turnIndex: 0 }),
    );
    expect(opening.slice(0, 2).map((u) => u.deliveryContext)).toEqual(["welcome", "welcome"]);
    expect(opening.map((u) => u.kind)).toEqual(["lead_in", "transition", "question"]);
    const closing = composeDelivery(base(null, { phase: "closing" }));
    expect(closing.length).toBeGreaterThan(0);
    expect(closing.every((u) => u.deliveryContext === "closing" && u.kind !== "question")).toBe(
      true,
    );
  });

  it("tags acknowledgements as acknowledgements", () => {
    for (const cue of ["hesitant", "revised"] as const) {
      const out = composeDelivery(base(questionItem(allQuestions[2]), { cue }));
      expect(out[0].kind).toBe("acknowledgement");
      expect(out[0].deliveryContext).toBe("acknowledgement");
    }
  });

  it("speaks a sensitive question and its framing in the sensitive context", () => {
    const out = composeDelivery(
      base(questionItem(allQuestions[3]), {
        phase: "sensitive",
        questionContext: "sensitive",
        previousContext: "routine",
      }),
    );
    expect(out.map((u) => u.deliveryContext)).toEqual(["sensitive", "sensitive"]);
  });
});

// --- invariant 11: cues are read, never awaited -----------------------------------------

describe("cues are read-only and never awaited", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("a missing, throwing, stalled or malformed source reads as no cue", () => {
    expect(readCue(null)).toBe("none");
    expect(readCue(undefined)).toBe("none");
    expect(readCue(() => undefined)).toBe("none");
    expect(
      readCue(() => {
        throw new Error("lane down");
      }),
    ).toBe("none");
    expect(readCue(() => new Promise(() => undefined))).toBe("none");
    expect(readCue(() => "grief")).toBe("none");
    expect(readCue(() => ({ cue: "hesitant" }))).toBe("none");
    expect(readCue(() => "hesitant")).toBe("hesitant");
  });

  it("a stalled source leaves the output and its latency unchanged", () => {
    vi.useFakeTimers();
    // An observer lane that will not answer for thirty seconds: its value is
    // a promise that settles only on the fake clock.
    const stalled = () =>
      new Promise<string>((resolve) => {
        setTimeout(() => resolve("hesitant"), 30_000);
      });
    const item = questionItem(allQuestions[4]);
    for (let turnIndex = 1; turnIndex < 25; turnIndex += 1) {
      const neutral = composeDelivery(base(item, { turnIndex, cue: "none" }));
      const started = Date.now();
      const withStall = composeDelivery(base(item, { turnIndex, cue: readCue(stalled) }));
      // Synchronous: an array, not a thenable, and no fake time had to pass.
      expect(Array.isArray(withStall)).toBe(true);
      expect(Date.now() - started).toBe(0);
      expect(withStall).toEqual(neutral);
    }
    // The stalled source only ever scheduled its own timers; the composer none.
    vi.advanceTimersByTime(30_000);
  });
});

// --- variation: deterministic, never back to back, never every turn ---------------------

function deliveryKeys(out: readonly Utterance[]): string[] {
  return out.filter((u) => u.kind !== "question").map((u) => u.key);
}

describe("variation", () => {
  it("is deterministic and never touches Math.random", () => {
    const random = vi.spyOn(Math, "random").mockImplementation(() => {
      throw new Error("Math.random is not a variation source");
    });
    try {
      const item = questionItem(allQuestions[5]);
      for (const input of everyInput(item)) {
        expect(composeDelivery(input)).toEqual(composeDelivery({ ...input }));
      }
    } finally {
      random.mockRestore();
    }
  });

  it("varies across sessions: the opening is not the same sentence for everyone", () => {
    const item = questionItem(allQuestions[0]);
    const openings = new Set(
      Array.from(
        { length: 40 },
        (_, i) =>
          composeDelivery(
            base(item, { phase: "opening", turnIndex: 0, sessionSeed: `visit-${i}` }),
          )[0].key,
      ),
    );
    expect(openings.size).toBe(DELIVERY_DECK.welcome.length);
  });

  it("never repeats the previous turn's line", () => {
    const item = questionItem(allQuestions[6]);
    const offenders: string[] = [];
    // Every pool the composer draws from is reached: each cue, each topic
    // change, the sensitive entry, the resume line and every context.
    const shapes: Partial<DeliveryInput>[] = [
      ...DELIVERY_CUES.map((cue) => ({ cue })),
      ...DELIVERY_TOPICS.map((topic) => ({ topic, previousTopic: "hpi" as const })),
      { phase: "sensitive" as const, questionContext: "sensitive" as const },
      {
        phase: "sensitive" as const,
        questionContext: "sensitive" as const,
        topic: "family" as const,
      },
      { phase: "first" as const },
      { questionContext: "pain" as const },
      { questionContext: "instrument" as const },
      { questionContext: "sensitive" as const, previousContext: "sensitive" as const },
    ];
    for (const seed of SEEDS) {
      for (let turnIndex = 1; turnIndex < 16; turnIndex += 1) {
        for (const shape of shapes) {
          for (const previousKey of DELIVERY_KEYS) {
            const out = composeDelivery(
              base(item, { ...shape, sessionSeed: seed, turnIndex, previousKey }),
            );
            if (deliveryKeys(out).includes(previousKey)) {
              offenders.push(`${seed}@${turnIndex} ${JSON.stringify(shape)}: ${previousKey}`);
            }
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("does not decorate every turn: no cadence line straight after another line", () => {
    const item = questionItem(allQuestions[7]);
    for (const seed of SEEDS) {
      for (let turnIndex = 1; turnIndex < 80; turnIndex += 1) {
        const out = composeDelivery(
          base(item, { sessionSeed: seed, turnIndex, previousKey: "dialogue.delivery.lead.a" }),
        );
        expect(out).toHaveLength(1);
      }
    }
  });

  it("decorates some quiet turns and leaves others bare", () => {
    const item = questionItem(allQuestions[8]);
    const decorated = Array.from(
      { length: 200 },
      (_, turnIndex) =>
        deliveryKeys(composeDelivery(base(item, { turnIndex: turnIndex + 1 }))).length,
    );
    expect(decorated.filter((n) => n > 0).length).toBeGreaterThan(40);
    expect(decorated.filter((n) => n === 0).length).toBeGreaterThan(40);
  });
});

// --- patient words never reach speech ---------------------------------------------------

describe("patient words are never composed", () => {
  it("every text the composer emits is a deck string or the item it was handed", () => {
    const deck = new Set<string>(DELIVERY_KEYS.map((key: DeliveryKey) => tr[key]));
    const item = questionItem(allQuestions[9]);
    for (const input of everyInput(item)) {
      for (const utterance of composeDelivery(input)) {
        if (utterance.kind === "question") {
          expect(utterance.text).toBe(item.text);
        } else {
          expect(deck.has(utterance.text), utterance.key).toBe(true);
        }
      }
    }
  });

  it("has no input that could carry a patient's words into a delivery line", () => {
    // The input type has no free-text field besides the scripted item: the
    // cue is a closed vocabulary, and anything else reads as "none".
    expect(readCue(() => "Göğsüm ağrıyor")).toBe("none");
  });
});
