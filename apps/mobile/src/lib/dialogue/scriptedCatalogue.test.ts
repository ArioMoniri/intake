/**
 * INT-443: the committed scripted catalogue is exactly what the app speaks.
 *
 * `scriptedCatalogue.tr.json` is what the server admits to the George route
 * (services/api dev_voice_guard.py). A question or tr string that changes
 * without regenerating it fails here, so the server can never admit a text
 * the app no longer says, nor refuse one it now does. Regenerate with
 * `pnpm --filter mobile exec vitest run -u src/lib/dialogue/scriptedCatalogue.test.ts`.
 */
import { describe, expect, it } from "vitest";

import { allQuestions } from "../intake/questions";
import { buildScriptedCatalogue, serialiseScriptedCatalogue } from "./scriptedCatalogue";
import { confirmSpeechTr, questionSpeechTr } from "./speech";

const catalogue = buildScriptedCatalogue();
const texts = new Set(catalogue.rows.map((row) => row.text_tr));

describe("the scripted catalogue the server admits (INT-443)", () => {
  it("is committed exactly as the composition builds it", async () => {
    await expect(serialiseScriptedCatalogue(catalogue)).toMatchFileSnapshot(
      "./scriptedCatalogue.tr.json",
    );
  });

  it("lists every speakable question the dialogue asks", () => {
    const complaint = allQuestions.find((q) => q.id === "complaint")!;
    expect(texts.has(questionSpeechTr(complaint))).toBe(true);
    expect(catalogue.rows.length).toBeGreaterThan(50);
  });

  it("holds no numeral, no markup and no empty text", () => {
    for (const row of catalogue.rows) {
      expect(row.text_tr.trim().length).toBeGreaterThan(0);
      expect(/[\p{N}<>[\]]/u.test(row.text_tr)).toBe(false);
    }
  });

  it("pins only instrument items, and never RED", () => {
    const contexts = new Set(catalogue.rows.map((row) => row.delivery_context));
    expect([...contexts].every((c) => c === "routine" || c === "instrument")).toBe(true);
    for (const row of catalogue.rows) {
      if (row.delivery_context === "instrument") {
        const question = allQuestions.find((q) => `question.${q.id}` === row.subject);
        expect(question?.instrument).toBeDefined();
      }
    }
  });

  it("never lists a confirmation naming two options (near miss: one option is listed)", () => {
    const multi = allQuestions.find((q) => q.kind === "chips" && (q.options?.length ?? 0) >= 2)!;
    const [a, b] = multi.options!;
    expect(texts.has(confirmSpeechTr(multi, [a.id]))).toBe(true);
    expect(texts.has(confirmSpeechTr(multi, [a.id, b.id]))).toBe(false);
  });

  it("lists each text once", () => {
    expect(texts.size).toBe(catalogue.rows.length);
  });
});
