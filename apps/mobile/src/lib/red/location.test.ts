/**
 * INT-604 — the visit-mode question asks one thing, and a location reaches the
 * RED axis only from an unambiguous answer (files/02 §5.3 Axis 3, "never
 * guess"; CLAUDE.md invariant 21).
 *
 * Owner decision M3 (17 Nov 2026, D18 scope): only an explicit "I am at the
 * hospital now" answer sets ON_SITE; a preference never does; anything
 * ambiguous stays UNKNOWN. On the device that explicit answer is the RED's own
 * question ("Şu anda hastanede misiniz?", asked at RED time, store.ts): the
 * up-front answer can be hours old, and ON_SITE removes the 112 affordance, so
 * an up-front "Evet, hastanedeyim" yields UNKNOWN and the RED asks again.
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { emptyNoteState, modeChoiceNeeded, noteReducer } from "../intake/note";
import { deriveRedLocation, MODE_CHOICES } from "./location";

const TODAY = "2026-08-29";
const VISIT_DATES = [null, "2026-08-28", TODAY, "2026-09-02"];

describe("the up-front question asks where the patient is, and nothing else", () => {
  it("is the location question, verbatim from files/02 §5.3", () => {
    expect(tr["intake.mode.q"]).toBe("Şu anda hastanede misiniz?");
  });

  it("each option is a location answer, not a preference", () => {
    expect(MODE_CHOICES.map((choice) => [choice.labelKey, choice.mode])).toEqual([
      ["intake.mode.hospital", "detayli"],
      ["intake.mode.away", "hizli"],
    ]);
    expect(tr["intake.mode.hospital"]).toBe("Evet, hastanedeyim");
    expect(tr["intake.mode.away"]).toBe("Hayır, hastanede değilim");
    // Near miss: the old preference label is gone from both catalogues.
    expect(Object.values(tr)).not.toContain("Kısa tutalım");
    expect("intake.mode.brief" in en).toBe(false);
  });
});

describe("golden: no answer on the device can set ON_SITE", () => {
  it("over every mode, visit date and kiosk state", () => {
    for (const mode of ["hizli", "detayli"] as const) {
      for (const visitDate of VISIT_DATES) {
        for (const kiosk of [false, true]) {
          expect(deriveRedLocation({ mode, visitDate, today: TODAY, kiosk })).not.toBe("ON_SITE");
        }
      }
    }
  });

  it("'Hayır, hastanede değilim' on a later-day visit is REMOTE", () => {
    expect(
      deriveRedLocation({ mode: "hizli", visitDate: "2026-09-02", today: TODAY, kiosk: false }),
    ).toBe("REMOTE");
  });

  it("near miss: the same answer on the visit day is UNKNOWN (it may be stale)", () => {
    expect(deriveRedLocation({ mode: "hizli", visitDate: TODAY, today: TODAY, kiosk: false })).toBe(
      "UNKNOWN",
    );
  });

  it("'Evet, hastanedeyim' is UNKNOWN, so the RED asks again at RED time", () => {
    for (const visitDate of VISIT_DATES) {
      expect(deriveRedLocation({ mode: "detayli", visitDate, today: TODAY, kiosk: false })).toBe(
        "UNKNOWN",
      );
    }
  });
});

describe("no answer is never read as an answer", () => {
  it("the chooser shows until the patient answers, also on an edit", () => {
    expect(modeChoiceNeeded(undefined)).toBe(true);
    const fresh = emptyNoteState();
    expect(modeChoiceNeeded(fresh)).toBe(true);
    // An answer that arrived without the question (an edit route on a fresh
    // note) does not stand in for it: the default `hizli` is a fallback, and
    // the chooser still shows before anything else.
    const answered = noteReducer(fresh, { type: "answer", questionId: "extra", values: ["x"] });
    expect(modeChoiceNeeded(answered)).toBe(true);
    expect(modeChoiceNeeded(noteReducer(fresh, { type: "mode", mode: "hizli" }))).toBe(false);
  });
});
