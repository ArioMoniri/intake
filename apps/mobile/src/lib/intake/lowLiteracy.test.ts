/**
 * INT-136 — `overlay.low_literacy` on the typed surface (files/04 §2.3
 * *"chips + slow pace"*), read against the promise files/02 §3 makes:
 *
 *   "full operation **without reading**. Every chip label is spoken and
 *    selectable by voice; severity is **numeracy-free, using 3–4 ordinal
 *    spoken anchors** (Cowan 2010 … not the 7±2 folklore); **no free text
 *    anywhere on the critical path**."
 *
 * The runtime half of this already exists and is where the vocabulary comes
 * from: `tests/sim/driver.py free_text_critical_path_steps` and scenario
 * IM-10. These are the same claims against the mobile pack, and the same
 * discipline as files/04 §2.3 imposes — *"overlays … may only add/tighten
 * red flags or change delivery; they never remove questions"* — so nothing
 * here drops a step, re-scales one, or re-words one. Every rule is a
 * DELIVERY rule, and where the pack cannot satisfy one the function NAMES
 * the step rather than quietly excusing it.
 */
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { MAX_SPOKEN_OPTION_HINTS } from "../dialogue/speech";
import {
  ORDINAL_ANCHOR_MAX,
  ORDINAL_ANCHOR_MIN,
  lowLiteracyReadiness,
  numeralAnchoredSteps,
  ordinalAnchorOffenders,
  typingOnlySteps,
  unspeakableChipLabels,
} from "./lowLiteracy";
import { allQuestions, packForVisit, type IntakeQuestion } from "./questions";

/** Every shipped pack, in both modes — the whole surface the overlay meets. */
const DEPARTMENTS = [undefined, "kardiyoloji", "noroloji", "kbb", "dermatoloji"] as const;
const PACKS = DEPARTMENTS.flatMap((department) => [
  { name: `${department ?? "genel"}/hizli`, pack: packForVisit(department, { mode: "hizli" }) },
  { name: `${department ?? "genel"}/detayli`, pack: packForVisit(department, { mode: "detayli" }) },
]);

describe("the ordinal anchor bound is three to four, and it is enforced", () => {
  it("states Cowan's bound rather than the 7±2 folklore files/13 §5.3 debunks", () => {
    expect(ORDINAL_ANCHOR_MIN).toBe(3);
    expect(ORDINAL_ANCHOR_MAX).toBe(4);
  });

  it("shares its upper end with the spoken lane rather than restating it", () => {
    // One published finding, one constant. `dialogue/speech.ts` reached the
    // same bound first, for enumeration; a second literal 4 here is how the
    // two would silently disagree after someone revisits one of them.
    expect(ORDINAL_ANCHOR_MAX).toBe(MAX_SPOKEN_OPTION_HINTS);
  });

  it("no shipped ordinal step is outside the bound", () => {
    for (const { name, pack } of PACKS) {
      expect(ordinalAnchorOffenders(pack), name).toEqual([]);
    }
  });

  it("at least one shipped step declares itself ordinal, so the gate has a subject", () => {
    expect(allQuestions.some((q) => q.ordinal === true)).toBe(true);
  });

  it("names a step whose anchor set is too long", () => {
    const tooMany: IntakeQuestion = {
      id: "fixture_five_anchors",
      kind: "single",
      ask: "closed",
      ordinal: true,
      titleKey: "intake.q.severity",
      options: [
        { id: "a", labelKey: "intake.opt.mild" },
        { id: "b", labelKey: "intake.opt.moderate" },
        { id: "c", labelKey: "intake.opt.severe" },
        { id: "d", labelKey: "intake.opt.yes" },
        { id: "e", labelKey: "intake.opt.no" },
      ],
    };
    expect(ordinalAnchorOffenders([tooMany])).toEqual(["fixture_five_anchors"]);
  });

  it("names a step whose anchor set is too short", () => {
    const tooFew: IntakeQuestion = {
      id: "fixture_two_anchors",
      kind: "single",
      ask: "closed",
      ordinal: true,
      titleKey: "intake.q.severity",
      options: [
        { id: "a", labelKey: "intake.opt.mild" },
        { id: "b", labelKey: "intake.opt.severe" },
      ],
    };
    expect(ordinalAnchorOffenders([tooFew])).toEqual(["fixture_two_anchors"]);
  });
});

describe("no step on the critical path can only be answered by typing", () => {
  it("every shipped pack is clean", () => {
    for (const { name, pack } of PACKS) {
      expect(typingOnlySteps(pack), name).toEqual([]);
    }
  });

  it("names an option-bearing step whose option list is empty", () => {
    // The shape that degrades to a bare keyboard: the chips grid is the
    // fallback under an open ask, so an empty grid leaves the free field as
    // the only control. This is also what an instrument step looks like when
    // its verbatim choices did not resolve.
    const empty = {
      id: "fixture_no_options",
      kind: "chips",
      ask: "open",
      titleKey: "intake.q.extra",
      options: [],
    } as unknown as IntakeQuestion;
    expect(typingOnlySteps([empty])).toEqual(["fixture_no_options"]);
  });

  it("a free-note step is not on the critical path — it commits empty", () => {
    const note = allQuestions.find((q) => q.kind === "text");
    expect(note).toBeDefined();
    expect(typingOnlySteps([note!])).toEqual([]);
  });
});

describe("no chip label can carry a numeral into a speech model", () => {
  it("is clean on every shipped pack", () => {
    for (const { name, pack } of PACKS) {
      expect(unspeakableChipLabels(pack), name).toEqual([]);
    }
  });

  it("keeps every numeral in `inline`, where nothing speaks it", () => {
    const painScore = allQuestions.find((q) => q.id === "pain_score");
    expect(painScore?.options?.[0].inline).toBe("0");
    for (const option of painScore!.options!) {
      expect(/\p{Nd}/u.test(option.inline ?? ""), option.id).toBe(true);
      expect(/\p{Nd}/u.test(t(option.labelKey, "tr")), option.id).toBe(false);
    }
  });

  it("does not hold a text_only step to a speech rule", () => {
    // files/13 §13: no clip, no speech_tr, ever — so `spokenPack` drops it and
    // its labels are not on a speech path to be judged.
    const painScore = allQuestions.find((q) => q.id === "pain_score");
    expect(painScore?.delivery).toBe("text_only");
    expect(unspeakableChipLabels([painScore!])).toEqual([]);
  });

  it("names a spoken step whose label carries a digit", () => {
    expect(
      unspeakableChipLabels([
        {
          id: "fixture_digit",
          kind: "single",
          ask: "closed",
          titleKey: "intake.q.severity",
          // "Başında 05 ile yazın, örneğin 0532 111 44 55." — a real catalogue
          // string that carries digits, borrowed here only as a numeral source.
          options: [{ id: "x", labelKey: "auth.phone.hint" }],
        },
      ]),
    ).toEqual(["fixture_digit"]);
  });
});

describe("the overlay reports what it cannot yet deliver", () => {
  it("names the numeral-anchored step files/02 §3 has no ordinal wording for", () => {
    const detayli = packForVisit(undefined, { mode: "detayli" });
    // The 0–10 pain score is `text_only` and its options are authored words,
    // so nothing speaks a digit — but eleven anchors is not "3–4 ordinal
    // spoken anchors", and no Turkish anchor wording for it is authored
    // anywhere (baseLayer.ts says so in its own header). Recoding it is a
    // clinical judgement, so the overlay names it instead of inventing one.
    expect(numeralAnchoredSteps(detayli)).toEqual(["pain_score"]);
  });

  it("finds no numeral-anchored step in the fast mode", () => {
    expect(numeralAnchoredSteps(packForVisit(undefined, { mode: "hizli" }))).toEqual([]);
  });

  it("is not ready in the detailed mode, and says exactly why", () => {
    const readiness = lowLiteracyReadiness(packForVisit(undefined, { mode: "detayli" }));
    expect(readiness.ready).toBe(false);
    expect(readiness.unmet).toEqual(["numeral_anchored:pain_score"]);
  });

  it("is ready in the fast mode", () => {
    const readiness = lowLiteracyReadiness(packForVisit(undefined, { mode: "hizli" }));
    expect(readiness.ready).toBe(true);
    expect(readiness.unmet).toEqual([]);
  });
});
