/**
 * INT-321 — the intake asks its MODE up front, and the clinic-interruptible
 * checkpoint is a single "Bitirdim" (I am done), not a "Sıranız geldi" chip.
 *
 * The defect the owner photographed: the "Hastanedeyim" switch and the
 * "Sıranız geldi" chip sat on TOP of every typed question, so a patient met a
 * mode switch, a checkpoint chip and the question's own CTA at once and could
 * not tell what to press or when. INT-295 had already fought the same row for
 * overflow; the fix here is to stop having the row at all.
 *
 * The redesign:
 *   - the mode (Hastanedeyim = ayrıntılı, or kısa) is a ONE-TIME choice shown
 *     before the questions, recorded on the note as `modeChosen`;
 *   - the per-question ModeBar is gone (the component and its spec with it);
 *   - the "called in, give me my note now" affordance survives, relabelled to
 *     the plain first-person "Bitirdim" and reachable once the flow has begun.
 *
 * These are source-slice assertions (the tree cannot be rendered under the
 * node test runner), same technique the retired modeBar.spec.ts used: they
 * prove the wiring exists and the old wiring is gone.
 */
import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const INTAKE = readFileSync(join(MOBILE, "src/app/(tabs)/visits/[visitId]/intake.tsx"), "utf8");

describe("INT-321: the mode is asked up front, not on every question", () => {
  it("the per-question ModeBar is gone from the intake screen and the tree", () => {
    expect(INTAKE).not.toContain("ModeBar");
    expect(INTAKE).not.toContain("components/ModeBar");
    expect(
      existsSync(join(MOBILE, "src/components/ModeBar.tsx")),
      "ModeBar.tsx should be deleted, not orphaned",
    ).toBe(false);
    expect(
      existsSync(join(MOBILE, "e2e/modeBar.spec.ts")),
      "modeBar.spec.ts covered a component that no longer exists",
    ).toBe(false);
  });

  it("the mode chooser is wired before the questions and records the choice", () => {
    // The chooser is gated on the note's `modeChosen`, so it shows once.
    expect(INTAKE).toContain("modeChosen");
    // Its two doors carry the new catalogue keys.
    expect(INTAKE).toContain("intake.mode.q");
    expect(INTAKE).toContain("intake.mode.hospital");
    expect(INTAKE).toContain("intake.mode.brief");
  });

  it("the checkpoint is a single 'Bitirdim', and 'Sıranız geldi' is gone", () => {
    expect(INTAKE).toContain("intake.finishNow");
    expect(INTAKE).not.toContain("intake.queue.called");
    expect(INTAKE).not.toContain("onQueueCalled");
  });
});

describe("INT-321 copy: tr source of truth + en mirror (invariant 5)", () => {
  const added = [
    "intake.mode.q",
    "intake.mode.hospital",
    "intake.mode.hospitalSub",
    "intake.mode.brief",
    "intake.mode.briefSub",
    "intake.finishNow",
  ] as const;

  const removed = [
    "intake.mode.hastanedeyim",
    "intake.mode.detayliOn",
    "intake.queue.called",
  ] as const;

  it("every new key exists non-empty in tr and in the en mirror", () => {
    for (const key of added) {
      expect((tr as Record<string, string>)[key]?.trim().length, key).toBeGreaterThan(0);
      expect((en as Record<string, string>)[key]?.trim().length, key).toBeGreaterThan(0);
    }
  });

  it("the retired mode-row keys are gone from both catalogues", () => {
    for (const key of removed) {
      expect((tr as Record<string, string>)[key], key).toBeUndefined();
      expect((en as Record<string, string>)[key], key).toBeUndefined();
    }
  });

  it("no numeral reaches the mode copy (invariant 22 posture)", () => {
    for (const key of added) {
      expect((tr as Record<string, string>)[key], key).not.toMatch(/[0-9]/u);
      expect((en as Record<string, string>)[key], key).not.toMatch(/[0-9]/u);
    }
  });

  it("the mode copy addresses the patient as siz, never sen (invariant 2)", () => {
    for (const key of added) {
      expect((tr as Record<string, string>)[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });

  it("the finish action is the plain first-person 'Bitirdim'", () => {
    expect(tr["intake.finishNow" as keyof typeof tr]).toBe("Bitirdim");
  });
});
