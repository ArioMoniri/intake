/**
 * INT-497 — the short acknowledgement said while a late question is still
 * being made, so the patient is never left in dead silence after answering.
 *
 * It is the delivery deck's own acknowledgement, never new copy, and it obeys
 * every rule the composer does (delivery.ts): nothing around RED, nothing
 * inside an instrument, less rather than more after a barge-in, never the
 * same line twice in a row — and it is only ever a line whose clip is
 * already made, because a filler that has to be synthesised first is a second
 * wait, not an answer to the first.
 */
import { describe, expect, it } from "vitest";

import type { Utterance } from "./delivery";
import { DELIVERY_DECK, deliveryTextTr, type DeliveryKey } from "./deliveryDeck";
import { HOLDING_AFTER_MS, holdingLine, withHolding, type HoldingInput } from "./holdingLine";

const THANKS: readonly DeliveryKey[] = DELIVERY_DECK.thanks;

const QUESTION: Utterance = {
  kind: "question",
  key: "intake.q.onset.title",
  text: "Şikayetiniz ne zaman başladı?",
  deliveryContext: "routine",
};

function input(over: Partial<HoldingInput> = {}): HoldingInput {
  return {
    plan: [QUESTION],
    questionContext: "routine",
    cue: "none",
    afterRed: false,
    previousLineKey: null,
    lastHoldingKey: null,
    sessionSeed: "visit-1",
    turnIndex: 3,
    isReady: () => true,
    ...over,
  };
}

describe("HOLDING_AFTER_MS — a warm turn never waits for it", () => {
  it("is a small slice of the 800 ms first-audio target", () => {
    expect(HOLDING_AFTER_MS).toBeGreaterThan(0);
    expect(HOLDING_AFTER_MS).toBeLessThanOrEqual(200);
  });
});

describe("holdingLine — what it says", () => {
  it("is an acknowledgement from the deck, in the acknowledgement voice", () => {
    const line = holdingLine(input())!;
    expect(line.kind).toBe("acknowledgement");
    expect(THANKS).toContain(line.key);
    expect(line.text).toBe(deliveryTextTr(line.key as DeliveryKey));
    expect(line.deliveryContext).toBe("acknowledgement");
  });

  it("acknowledges a 'don't know' and a correction in their own words", () => {
    expect(DELIVERY_DECK.hesitant).toContain(holdingLine(input({ cue: "hesitant" }))!.key);
    expect(DELIVERY_DECK.revised).toContain(holdingLine(input({ cue: "revised" }))!.key);
  });

  it("is the same line for the same visit and turn — the transcript can replay it", () => {
    expect(holdingLine(input())).toEqual(holdingLine(input()));
  });
});

describe("holdingLine — when it says nothing", () => {
  it.each([["red"], ["instrument"], ["sensitive"]] as const)(
    "says nothing before a %s question",
    (questionContext) => {
      expect(holdingLine(input({ questionContext }))).toBeNull();
    },
  );

  it("says nothing right after a RED-adjacent turn", () => {
    expect(holdingLine(input({ afterRed: true }))).toBeNull();
  });

  it("says nothing after a barge-in or before a repeat — they wanted less", () => {
    expect(holdingLine(input({ cue: "barge_in" }))).toBeNull();
    expect(holdingLine(input({ cue: "repeat_request" }))).toBeNull();
  });

  it("says nothing when the turn already opens with a line of its own", () => {
    const lead: Utterance = {
      kind: "lead_in",
      key: "dialogue.delivery.lead.a",
      text: deliveryTextTr("dialogue.delivery.lead.a"),
      deliveryContext: "routine",
    };
    expect(holdingLine(input({ plan: [lead, QUESTION] }))).toBeNull();
  });

  it("holds in place of the turn's own line when that line's clip is not made yet", () => {
    const lead: Utterance = {
      kind: "lead_in",
      key: "dialogue.delivery.lead.a",
      text: deliveryTextTr("dialogue.delivery.lead.a"),
      deliveryContext: "routine",
    };
    const line = holdingLine(
      input({ plan: [lead, QUESTION], isReady: (key) => key !== "dialogue.delivery.lead.a" }),
    );
    expect(THANKS).toContain(line?.key);
    // …and the transcript then shows the holding line, not the unsaid lead.
    expect(withHolding([lead, QUESTION], line)).toEqual([line, QUESTION]);
  });

  it("says nothing on the opening, which waits for its own welcome", () => {
    const welcome: Utterance = {
      kind: "lead_in",
      key: "dialogue.delivery.welcome.a",
      text: deliveryTextTr("dialogue.delivery.welcome.a"),
      deliveryContext: "welcome",
    };
    expect(holdingLine(input({ plan: [welcome, QUESTION], isReady: () => false }))).toBeNull();
  });

  it("says nothing whose clip is not already made", () => {
    expect(holdingLine(input({ isReady: () => false }))).toBeNull();
  });
});

describe("holdingLine — it never repeats back to back", () => {
  it("never says the line the previous turn ended on", () => {
    for (const previous of THANKS) {
      for (let turnIndex = 0; turnIndex < 12; turnIndex += 1) {
        expect(holdingLine(input({ previousLineKey: previous, turnIndex }))?.key).not.toBe(
          previous,
        );
      }
    }
  });

  it("never says the last holding line again", () => {
    for (const last of THANKS) {
      for (let turnIndex = 0; turnIndex < 12; turnIndex += 1) {
        expect(holdingLine(input({ lastHoldingKey: last, turnIndex }))?.key).not.toBe(last);
      }
    }
  });

  it("picks among what is ready rather than giving up on the first miss", () => {
    const only = THANKS[THANKS.length - 1];
    const line = holdingLine(input({ isReady: (key) => key === only }));
    expect(line?.key).toBe(only);
  });

  it("says nothing when the only ready line would be a repeat", () => {
    const only = THANKS[0];
    expect(
      holdingLine(input({ isReady: (key) => key === only, previousLineKey: only })),
    ).toBeNull();
  });
});

describe("withHolding — the transcript shows exactly what the voice said", () => {
  it("puts the holding line before the question, and the question last", () => {
    const line = holdingLine(input())!;
    expect(withHolding([QUESTION], line)).toEqual([line, QUESTION]);
  });

  it("is the plan itself when nothing was held", () => {
    const plan = [QUESTION];
    expect(withHolding(plan, null)).toBe(plan);
  });
});
