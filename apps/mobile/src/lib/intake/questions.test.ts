import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { allQuestions, optionLabelKey, packForDepartment, type IntakeQuestion } from "./questions";

/**
 * Department strings exactly as visits carry them (MHRS-style, Turkish
 * diacritics included) → a question id that only that branch's pack asks.
 * Resolution goes through foldDepartment, so each row also pins the
 * diacritic folding for that department name.
 */
const RESOLUTION: { department: string; marker: string }[] = [
  { department: "Kardiyoloji", marker: "radiation" },
  { department: "İç Hastalıkları", marker: "radiation" },
  { department: "Nöroloji", marker: "neuro_assoc" },
  { department: "Kulak Burun Boğaz", marker: "ent_assoc" },
  { department: "Ortopedi ve Travmatoloji", marker: "ortho_region" },
  { department: "Dermatoloji", marker: "derm_character" },
  { department: "Cildiye", marker: "derm_character" },
  { department: "Göğüs Hastalıkları", marker: "pulmo_character" },
  { department: "Kadın Hastalıkları ve Doğum", marker: "gyn_cycle" },
  { department: "Jinekoloji", marker: "gyn_cycle" },
  { department: "Üroloji", marker: "uro_urination" },
  { department: "Göz Hastalıkları", marker: "eye_vision" },
  { department: "Gastroenteroloji", marker: "gastro_meal" },
  { department: "Sindirim Sistemi Hastalıkları", marker: "gastro_meal" },
];

/** One pack per branch, deduped by reference (spellings share the array). */
function branchPacks(): IntakeQuestion[][] {
  return [...new Set(RESOLUTION.map((row) => packForDepartment(row.department)))];
}

describe("packForDepartment resolution", () => {
  for (const { department, marker } of RESOLUTION) {
    it(`"${department}" resolves to the pack asking ${marker}`, () => {
      const pack = packForDepartment(department);
      expect(pack.map((q) => q.id)).toContain(marker);
    });
  }

  it("unknown or missing departments fall back to the general pack", () => {
    const general = packForDepartment(undefined);
    expect(general.map((q) => q.id)).toEqual(["complaint", "duration", "extra"]);
    expect(packForDepartment("Aile Hekimliği")).toBe(general);
  });

  it("covers ten distinct branch packs", () => {
    expect(branchPacks()).toHaveLength(10);
  });
});

describe("pack shape invariants", () => {
  const packs = branchPacks();

  it("every branch pack has 6–9 steps, opens with the complaint, closes with the free note", () => {
    for (const pack of packs) {
      expect(pack.length).toBeGreaterThanOrEqual(6);
      expect(pack.length).toBeLessThanOrEqual(9);
      expect(pack[0].id).toBe("complaint");
      expect(pack[pack.length - 1].id).toBe("extra");
    }
  });

  it("every non-text question carries at least two options, all resolvable via optionLabelKey", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.kind === "text") {
          continue;
        }
        expect(q.options, q.id).toBeDefined();
        expect(q.options!.length, q.id).toBeGreaterThanOrEqual(2);
        for (const option of q.options!) {
          expect(optionLabelKey(q.id, option.id), `${q.id}/${option.id}`).toBe(option.labelKey);
        }
      }
    }
  });

  it("every dimension question carries hpiLabelKey (complaint feeds the CC section, extra the patient-note line)", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.id === "complaint" || q.id === "extra") {
          continue;
        }
        expect(q.hpiLabelKey, q.id).toBeDefined();
      }
    }
  });

  it("every chips question explains multi-select via a hint", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.kind === "chips") {
          expect(q.hintKey, q.id).toBeDefined();
        }
      }
    }
  });

  it("severity is asked in words in every branch pack", () => {
    for (const pack of packs) {
      const severity = pack.find((q) => q.id === "severity");
      expect(severity).toBeDefined();
      expect(severity!.options!.map((o) => o.id)).toEqual(["mild", "moderate", "severe"]);
    }
  });
});

describe("catalog coverage and invariant 22 (no numerals)", () => {
  function referencedKeys(): Set<string> {
    const keys = new Set<string>();
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      for (const q of pack) {
        keys.add(q.titleKey);
        if (q.hintKey) {
          keys.add(q.hintKey);
        }
        if (q.hpiLabelKey) {
          keys.add(q.hpiLabelKey);
        }
        for (const option of q.options ?? []) {
          keys.add(option.labelKey);
        }
      }
    }
    return keys;
  }

  it("every referenced key exists non-empty in tr AND en (tr is the source of truth)", () => {
    for (const key of referencedKeys()) {
      expect((tr as Record<string, string>)[key]?.trim(), `tr ${key}`).toBeTruthy();
      expect((en as Record<string, string>)[key]?.trim(), `en ${key}`).toBeTruthy();
    }
  });

  it("no numeral characters in any pack-facing string — invariant 22", () => {
    for (const key of referencedKeys()) {
      expect((tr as Record<string, string>)[key], `tr ${key}`).not.toMatch(/[0-9]/);
      expect((en as Record<string, string>)[key], `en ${key}`).not.toMatch(/[0-9]/);
    }
  });
});

describe("allQuestions ordering (the note builder renders HPI lines in this order)", () => {
  it("contains every pack question exactly once", () => {
    const ids = allQuestions.map((q) => q.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      for (const q of pack) {
        expect(ids, q.id).toContain(q.id);
      }
    }
  });

  it("preserves each pack's own question order, so HPI lines follow the interview", () => {
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      const packIds = new Set(pack.map((q) => q.id));
      const filtered = allQuestions.filter((q) => packIds.has(q.id)).map((q) => q.id);
      expect(filtered).toEqual(pack.map((q) => q.id));
    }
  });
});
