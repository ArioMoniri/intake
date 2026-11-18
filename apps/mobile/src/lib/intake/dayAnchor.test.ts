/**
 * INT-604 — a day-relative answer is anchored to the day it was given.
 *
 * Owner decision M2 (17 Nov 2026, D18 scope): use "şu sıralar" where the
 * meaning is "these days"; keep "bugün" where the clinical meaning is genuinely
 * today — onset today — and state the anchor there. The intake is answered
 * hours or days before the visit and the clinician reads the note on the visit
 * day, so a line reading "Bugün başladı" says nothing true without the day the
 * patient said it. The note therefore prints the answering day on every line of
 * a step declared `dayAnchored`.
 */
import { describe, expect, it } from "vitest";

import { tr } from "../i18n/tr";
import { formatFactDate } from "./carriedFacts";
import { buildNote, emptyNoteState, noteReducer } from "./note";
import { allQuestions } from "./questions";

const ACCOUNT = { carriedFacts: [] };
const ANSWERED_ON = "2026-11-14";

function hpi(answers: Parameters<typeof buildNote>[0]): string[] {
  return buildNote(answers, ACCOUNT).find((s) => s.id === "hpi")?.lines ?? [];
}

describe("questions whose meaning is genuinely today keep 'bugün' and declare the anchor", () => {
  it("the onset steps are day-anchored and still say bugün", () => {
    const anchored = allQuestions.filter((q) => q.dayAnchored === true).map((q) => q.id);
    expect(anchored.sort()).toEqual(["duration", "onset_today_when"]);
    expect(tr["intake.opt.today"]).toBe("Bugün başladı");
    expect(tr["intake.q.onsetTodayWhen"]).toBe("Bugün ne zaman başladı?");
  });

  it("the 'these days' question no longer says bugün", () => {
    expect(tr["intake.q.complaint"]).toBe("Şu sıralar sizi hekime getiren nedir?");
  });
});

describe("the note states the anchor", () => {
  it("records the answering day the lane passes", () => {
    const note = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "duration",
      values: ["today"],
      answeredOn: ANSWERED_ON,
    });
    expect(note.answers[0]?.answeredOn).toBe(ANSWERED_ON);
  });

  it("an anchored line carries the answering day", () => {
    const lines = hpi([{ questionId: "duration", values: ["today"], answeredOn: ANSWERED_ON }]);
    expect(lines).toEqual([
      `${tr["review.hpi.duration"]}: ${tr["intake.opt.today"]} (${tr["note.answeredOn"]}: ${formatFactDate(ANSWERED_ON)})`,
    ]);
  });

  it("near miss: a step that is not day-anchored carries no anchor", () => {
    const lines = hpi([{ questionId: "character", values: ["pressure"], answeredOn: ANSWERED_ON }]);
    expect(lines.join(" ")).not.toContain(tr["note.answeredOn"]);
  });

  it("an answer recorded before the anchor existed renders as it always did", () => {
    const lines = hpi([{ questionId: "duration", values: ["today"] }]);
    expect(lines).toEqual([`${tr["review.hpi.duration"]}: ${tr["intake.opt.today"]}`]);
  });
});
