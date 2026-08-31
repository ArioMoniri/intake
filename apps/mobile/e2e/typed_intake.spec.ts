/**
 * INT-136 — typed intake UI (Detaylı) + chips + instruments verbatim.
 *
 * Acceptance, verbatim from docs/backlog/issues.yaml:
 *   "instrument items rendered verbatim; low-literacy chips; progress + resume"
 *
 * WHAT THIS FILE IS AIMED AT, and what it deliberately is not.
 *
 * Two of the three acceptance clauses were already standing when this issue
 * opened. INT-179 built the one-question-per-screen typed flow with chips,
 * single-select cards and free text; INT-236/239 made the flow adaptive and
 * made the progress row honest about a length the answers decide; INT-256
 * composed the universal history block into it. So "low-literacy chips" and
 * "progress + resume" are pinned here rather than built — the value this
 * file adds to them is that the PROPERTIES 02 §3 names are now assertions
 * instead of prose, and the resume rule is a pack-layer function a node test
 * can drive rather than an expression inlined in a screen.
 *
 * The third clause had nothing behind it at all. No instrument surface, no
 * licence gate and no item text existed anywhere in apps/mobile, and none
 * exists anywhere in the repository: packages/protocols/base/intake.yaml
 * states in its own comment that "Instrument ITEM text is not authored here"
 * and leaves the verbatim Turkish to INT-116. That absence is the point of
 * §1 and §2 below — the mechanism is built, the gate is wired, it fails
 * closed, and the content is left empty (HUMAN_BLOCKERS Rule 2).
 *
 * WHAT THIS ENVIRONMENT CANNOT VERIFY, stated once and not softened
 * anywhere below. There is no simulator, no emulator and no Docker daemon in
 * this container, Expo cannot start, and the vitest lane runs on `node` with
 * no renderer — react-native ships Flow source this lane cannot import, and
 * neither react-test-renderer nor @testing-library/react-native is a
 * dependency of this app. So NOTHING here was seen rendered. Every claim is
 * either (a) a real call into a real module, or (b) a statement about what
 * the shipped SOURCE declares, which is the same technique a11y.spec.ts,
 * askAhead.spec.ts and large-text-overflow.spec.ts use for the same reason.
 * A source assertion cannot prove a pixel; it can prove that the one place
 * an instrument item becomes a rendered string does not transform it, and
 * that is the property invariant 10 is about.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { assertSpeakableTr } from "../src/lib/dialogue/tts";
import { t } from "../src/lib/i18n";
import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import {
  FreeNumericEntryRefused,
  NUMERIC_SLOT_TYPES,
  SLOT_TYPES,
  affordanceForQuestion,
  numericStepsWithoutChoices,
  typedAffordance,
} from "../src/lib/intake/affordance";
import {
  INSTRUMENT_ITEMS,
  INSTRUMENT_LICENCES,
  InstrumentUnavailable,
  instrumentLicence,
  instrumentOffer,
  resolveInstrument,
  type InstrumentId,
  type InstrumentItem,
} from "../src/lib/intake/instruments";
import {
  ORDINAL_ANCHOR_MAX,
  ORDINAL_ANCHOR_MIN,
  allQuestions,
  applicableQuestions,
  nextApplicableQuestion,
  packForVisit,
  resumeQuestion,
  type AnsweredValues,
  type IntakeQuestion,
} from "../src/lib/intake/questions";

const MOBILE = join(__dirname, "..");
const REPO = join(MOBILE, "..", "..");

const INSTRUMENTS_TS = join(MOBILE, "src", "lib", "intake", "instruments.ts");
const INSTRUMENT_VIEW = join(MOBILE, "src", "components", "InstrumentItems.tsx");
const INTAKE_SCREEN = join(MOBILE, "src", "app", "(tabs)", "visits", "[visitId]", "intake.tsx");
const WELLBEING_SCREEN = join(MOBILE, "src", "app", "(tabs)", "wellbeing.tsx");

const LICENCES_PY = join(REPO, "packages", "protocols", "src", "protocols", "licences.py");
const TYPES_PY = join(REPO, "packages", "protocols", "src", "protocols", "types.py");
const AFFORDANCE_PY = join(
  REPO,
  "services",
  "voice-runtime",
  "src",
  "intake_voice_runtime",
  "typed",
  "affordance.py",
);

function read(path: string): string {
  const source = readFileSync(path, "utf8");
  expect(source.length, `${path} is empty — this spec needs re-aiming`).toBeGreaterThan(0);
  return source;
}

/**
 * A file with its comments removed.
 *
 * The assertions below are about what the CODE does, and these modules carry
 * long headers that name the very things the code must not do — "no scoring",
 * "never `numberOfLines`". Matching the raw file would convict a module for
 * explaining itself, and the fix would be to delete the explanation, which is
 * the wrong direction. Strings are left intact: a literal is code.
 */
function code(path: string): string {
  return read(path)
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^[ \t]*\/\/.*$/gm, " ");
}

/* ------------------------------------------------------------------ */
/* §1 — the licence gate, mirrored from its Python source              */
/* ------------------------------------------------------------------ */

/** `INSTRUMENT_LICENCES` as `packages/protocols` spells it, parsed. */
function pythonLicenceTable(): Record<string, string> {
  const source = read(LICENCES_PY);
  const table: Record<string, string> = {};
  for (const match of source.matchAll(/"([A-Za-z0-9-]+)":\s*InstrumentLicence\.([A-Z_]+),/g)) {
    table[match[1]] = match[2];
  }
  return table;
}

describe("§1 the licence gate is the protocol package's, not a second opinion", () => {
  it("mirrors packages/protocols/src/protocols/licences.py row for row", () => {
    // Two copies of a licence verdict is how one of them ends up stale, and
    // the stale one would be the one deciding what a patient is shown. The
    // mobile table is a MIRROR and this test is what makes that word mean
    // something.
    expect(INSTRUMENT_LICENCES).toEqual(pythonLicenceTable());
  });

  it("names C-SSRS and WHO-5 BLOCKED (HB-L2, HB-L3) and HAQ-DI NEEDS_PERMISSION", () => {
    expect(instrumentLicence("C-SSRS")).toBe("BLOCKED");
    expect(instrumentLicence("WHO-5")).toBe("BLOCKED");
    expect(instrumentLicence("HAQ-DI")).toBe("NEEDS_PERMISSION");
  });

  it("fails closed: an instrument the registry never recorded is UNKNOWN", () => {
    expect(instrumentLicence("PHQ-4")).toBe("UNKNOWN");
    expect(instrumentLicence("")).toBe("UNKNOWN");
  });
});

/** A synthetic instrument body — fixture text, never clinical content. */
const SYNTHETIC_ITEMS: readonly InstrumentItem[] = [
  {
    id: "sentetik_1",
    // Deliberately diacritic-bearing: the NFD near-miss below needs a
    // string that HAS a decomposed form, and pure ASCII does not.
    textTr: "Sentetik ölçek maddesi: hiç, birkaç gün, çoğu gün.",
    allowParaphrase: false,
    choicesTr: ["Sentetik yanıt bir", "Sentetik yanıt iki"],
  },
];

describe("§1 a non-GO instrument cannot be rendered, authored items or not", () => {
  for (const blocked of ["C-SSRS", "WHO-5", "HAQ-DI"] as const) {
    it(`refuses ${blocked} even when items are handed to it`, () => {
      // The negative control that matters: the refusal is the LICENCE, so
      // handing the resolver a full item list must not open the gate.
      const items = { [blocked]: SYNTHETIC_ITEMS };
      expect(() => resolveInstrument(blocked, { items })).toThrow(InstrumentUnavailable);
      try {
        resolveInstrument(blocked, { items });
      } catch (error) {
        expect((error as InstrumentUnavailable).reason).toBe("licence_not_go");
      }
      expect(instrumentOffer(blocked, { items })).toBeNull();
    });
  }

  it("refuses an instrument nobody recorded, for the same reason", () => {
    expect(() =>
      resolveInstrument("PHQ-4" as InstrumentId, { items: { "PHQ-4": SYNTHETIC_ITEMS } }),
    ).toThrow(InstrumentUnavailable);
  });
});

describe("§1 no instrument has authored items today, and the gate says so", () => {
  it("ships an empty item registry", () => {
    // packages/protocols/base/intake.yaml, in its own words: "Instrument
    // ITEM text is not authored here: the verbatim Turkish items belong to
    // the instrument engine (INT-116)". Nothing in this app invents them.
    expect(Object.keys(INSTRUMENT_ITEMS)).toEqual([]);
  });

  it("offers nothing for any registered instrument", () => {
    for (const id of Object.keys(INSTRUMENT_LICENCES) as InstrumentId[]) {
      expect(instrumentOffer(id), id).toBeNull();
    }
  });

  it("gives the GO instruments the honest reason — content, not licence", () => {
    for (const id of ["PHQ-9", "PHQ-2", "GAD-7", "GAD-2"] as const) {
      expect(instrumentLicence(id), id).toBe("GO");
      try {
        resolveInstrument(id);
        expect.unreachable(`${id} resolved with no authored items`);
      } catch (error) {
        expect((error as InstrumentUnavailable).reason, id).toBe("items_not_authored");
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* §2 — verbatim: byte-identity, not similarity (invariant 10)         */
/* ------------------------------------------------------------------ */

describe("§2 an item reaches the screen byte for byte", () => {
  const items = { "PHQ-9": SYNTHETIC_ITEMS };

  it("returns the authored objects themselves — nothing copies or rewrites", () => {
    const resolved = resolveInstrument("PHQ-9", { items });
    expect(resolved).toHaveLength(SYNTHETIC_ITEMS.length);
    resolved.forEach((item, index) => {
      // Identity, not deep equality: a resolver that rebuilt the record
      // would pass `toEqual` while being free to trim, re-case or normalise
      // on the way.
      expect(item).toBe(SYNTHETIC_ITEMS[index]);
      expect(item.textTr).toBe(SYNTHETIC_ITEMS[index].textTr);
      expect(item.choicesTr).toBe(SYNTHETIC_ITEMS[index].choicesTr);
    });
  });

  it("discriminates a near-miss: the same text in NFD is not the same text", () => {
    // The negative control for the assertion above. "Sentetik madde metni
    // bir." decomposed is visually identical and byte-different, which is
    // exactly the class of change a paraphrase gate on similarity would
    // wave through.
    const decomposed = SYNTHETIC_ITEMS[0].textTr.normalize("NFD");
    expect(decomposed).not.toBe(SYNTHETIC_ITEMS[0].textTr);
    const nearMiss = { "PHQ-9": [{ ...SYNTHETIC_ITEMS[0], textTr: decomposed }] };
    expect(resolveInstrument("PHQ-9", { items: nearMiss })[0].textTr).not.toBe(
      SYNTHETIC_ITEMS[0].textTr,
    );
  });

  it("never routes item text through the i18n catalog", () => {
    // A catalog key would give the item an `en` mirror, and an item
    // translated by this app is not the instrument its validation refers
    // to (files/04 header, instrument fidelity). It would also make the
    // text paraphrasable copy, which invariant 10 forbids outright.
    const source = code(INSTRUMENTS_TS);
    expect(source).not.toMatch(/\bfrom "(\.\.\/)+i18n/);
    expect(source).not.toMatch(/\bt\(/);
    for (const key of Object.keys(tr) as MessageKey[]) {
      expect(key.startsWith("instrument.item"), key).toBe(false);
    }
  });

  it("renders the item text untransformed, in one place", () => {
    const view = code(INSTRUMENT_VIEW);
    expect(view).toContain("{item.textTr}");
    expect(view).toContain("{choice}");
    // Every way a renderer silently changes an authored string.
    for (const transform of [
      ".trim()",
      ".normalize(",
      ".toLocaleUpperCase(",
      ".toUpperCase(",
      ".toLocaleLowerCase(",
      ".slice(",
      ".replace(",
      "numberOfLines",
      "ellipsizeMode",
      "textTransform",
    ]) {
      expect(view, transform).not.toContain(transform);
    }
  });

  it("computes no score and prints no cut-off", () => {
    // files/04 header: an LLM may not infer a score from narrative, and
    // invariant 20 keeps every measurement out of patient copy. The app
    // does not score at all — the instrument engine (INT-116) does.
    const both = code(INSTRUMENTS_TS) + code(INSTRUMENT_VIEW);
    expect(both).not.toMatch(/\bscore\b/i);
    expect(both).not.toMatch(/cut-?off/i);
    expect(both).not.toMatch(/\bpuan\b/i);
    expect(both).not.toMatch(/kesme değeri/i);
  });

  it("makes no validation claim about PHQ-2 or GAD-2 in any catalog string", () => {
    // CLAUDE.md, in its own words: do not describe PHQ-2/GAD-2 as
    // "Turkish-validated" — they have no Turkish validation at all.
    for (const catalog of [tr, en]) {
      for (const [key, value] of Object.entries(catalog)) {
        expect(value, key).not.toMatch(/turkish-validated|türkçe.{0,12}doğrulanmış/i);
        expect(value, key).not.toMatch(/\bPHQ\b|\bGAD\b|\bWHO-5\b|\bC-SSRS\b|\bHAQ\b/);
      }
    }
  });

  it("is wired into the wellbeing surface and refused there", () => {
    // 02 §4 / wellbeing.tsx: this screen IS the WHO-5-family space, and
    // WHO-5 is licence-BLOCKED (HB-L3). The gate is wired rather than the
    // screen being left to remember, so the refusal is structural.
    const screen = read(WELLBEING_SCREEN);
    expect(screen).toContain("InstrumentItems");
    expect(screen).toMatch(/WHO-5/);
    expect(instrumentOffer("WHO-5")).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* §3 — low-literacy chips (files/02 §3)                               */
/* ------------------------------------------------------------------ */

/** Every department string the pack table routes, plus the general case. */
const DEPARTMENTS: readonly (string | undefined)[] = [
  undefined,
  "Kardiyoloji",
  "İç Hastalıkları",
  "Nöroloji",
  "Kulak Burun Boğaz",
  "Ortopedi ve Travmatoloji",
  "Dermatoloji",
  "Göğüs Hastalıkları",
  "Kadın Hastalıkları ve Doğum",
  "Üroloji",
  "Göz Hastalıkları",
  "Gastroenteroloji",
];

const PROFILES = [{ mode: "hizli" as const }, { mode: "detayli" as const }];

function everyPackQuestion(): IntakeQuestion[] {
  const seen = new Map<string, IntakeQuestion>();
  for (const department of DEPARTMENTS) {
    for (const profile of PROFILES) {
      for (const question of packForVisit(department, profile)) {
        seen.set(question.id, question);
      }
    }
  }
  return [...seen.values()];
}

describe("§3 every chip label can be spoken (02 §3: operation without reading)", () => {
  it("covers the whole authored pack, not a sample", () => {
    expect(everyPackQuestion().length).toBeGreaterThan(40);
    expect(allQuestions.length).toBeGreaterThanOrEqual(everyPackQuestion().length);
  });

  it("no option label carries a numeral", () => {
    // Invariant 22's first clause: no numeral reaches any TTS. A chip a
    // patient must be able to HEAR is therefore a chip whose label the
    // synthesiser will accept — the same guard the dialogue lane runs.
    for (const question of allQuestions) {
      for (const option of question.options ?? []) {
        expect(() => assertSpeakableTr(t(option.labelKey, "tr")), option.labelKey).not.toThrow();
      }
    }
  });

  it("no question title carries a numeral either", () => {
    for (const question of allQuestions) {
      expect(() => assertSpeakableTr(t(question.titleKey, "tr")), question.titleKey).not.toThrow();
    }
  });

  it("an ordinal scale uses three or four spoken anchors, never a number", () => {
    // 02 §3: "severity is numeracy-free, using 3–4 ordinal spoken anchors
    // (Cowan 2010 on working-memory capacity — not the 7±2 folklore)".
    const ordinal = allQuestions.filter((q) => q.ordinal === true);
    expect(ordinal.length).toBeGreaterThan(0);
    for (const question of ordinal) {
      const options = question.options ?? [];
      expect(options.length, question.id).toBeGreaterThanOrEqual(ORDINAL_ANCHOR_MIN);
      expect(options.length, question.id).toBeLessThanOrEqual(ORDINAL_ANCHOR_MAX);
    }
    expect(ORDINAL_ANCHOR_MIN).toBe(3);
    expect(ORDINAL_ANCHOR_MAX).toBe(4);
  });

  it("the patient is never asked whether they can read", () => {
    // 02 §3: acquisition must be non-stigmatising — "never ask
    // 'okuyabiliyor musunuz?'". The same assertion tests/sim makes of the
    // spoken lane, made here of every string this app can render.
    for (const catalog of [tr, en]) {
      for (const [key, value] of Object.entries(catalog)) {
        expect(value, key).not.toMatch(/okuyabiliyor|okuma ?yazma|okur ?-? ?yazar|can you read/i);
      }
    }
  });
});

describe("§3 the flow finishes without typing a word", () => {
  for (const department of DEPARTMENTS) {
    it(`completes from chips alone — ${department ?? "genel"}`, () => {
      const pack = packForVisit(department, { mode: "detayli" });
      const answers: AnsweredValues[] = [];
      let current: IntakeQuestion | null = pack[0];
      let guard = 0;
      while (current !== null) {
        guard += 1;
        expect(guard, "the flow did not terminate").toBeLessThan(pack.length + 5);
        if (current.kind !== "text") {
          const options = current.options ?? [];
          expect(options.length, current.id).toBeGreaterThan(0);
          answers.push({ questionId: current.id, values: [options[0].id] });
        }
        // A text step is passed WITHOUT typing: the flow's own skip.
        current = nextApplicableQuestion(pack, answers, current.id);
      }
      const unanswered = applicableQuestions(pack, answers).filter(
        (q) => q.kind !== "text" && !answers.some((a) => a.questionId === q.id),
      );
      expect(unanswered.map((q) => q.id)).toEqual([]);
    });
  }

  it("the free-text step's CTA is never disabled, so it can always be passed", () => {
    const screen = read(INTAKE_SCREEN);
    const at = screen.lastIndexOf('question.kind === "text" ? (');
    expect(at).toBeGreaterThan(-1);
    const bar = screen.slice(at, at + 400);
    expect(bar).toContain("PrimaryButton");
    expect(bar).not.toContain("disabled");
  });
});

describe("§3 invariant 22 — no free numeric entry, and the refusal is surfaced", () => {
  it("mirrors NUMERIC_SLOT_TYPES from services/voice-runtime typed/affordance.py", () => {
    const source = read(AFFORDANCE_PY);
    const block = /NUMERIC_SLOT_TYPES[\s\S]*?frozenset\(\s*\{([^}]*)\}/.exec(source);
    expect(block, "NUMERIC_SLOT_TYPES not found in affordance.py").not.toBeNull();
    const names = [...block![1].matchAll(/SlotType\.([A-Z_]+)/g)].map((m) =>
      m[1].toLowerCase(),
    );
    expect([...NUMERIC_SLOT_TYPES].sort()).toEqual(names.sort());
  });

  it("mirrors SlotType from packages/protocols types.py", () => {
    const source = read(TYPES_PY);
    const at = source.indexOf("class SlotType(enum.StrEnum):");
    expect(at).toBeGreaterThan(-1);
    const body = source.slice(at, source.indexOf("\nclass ", at + 1));
    const members = [...body.matchAll(/^ {4}[A-Z_]+ = "([a-z_]+)"$/gm)].map((m) => m[1]);
    expect(members.length).toBe(8);
    expect([...SLOT_TYPES].sort()).toEqual(members.sort());
  });

  it("refuses a numeric slot that has no authored choices", () => {
    // INT-096's contract, held on this side of the wire: the outcome is a
    // refusal the developer sees, never a text box the patient sees.
    for (const slotType of NUMERIC_SLOT_TYPES) {
      expect(() =>
        typedAffordance({ stepId: `sentetik.${slotType}`, slotType, choicesTr: [] }),
      ).toThrow(FreeNumericEntryRefused);
    }
  });

  it("answers a numeric slot that HAS choices with a chip, not a field", () => {
    expect(
      typedAffordance({
        stepId: "sentetik.doz",
        slotType: "quantity",
        choicesTr: ["tam", "yarım", "çeyrek"],
      }),
    ).toBe("choice");
  });

  it("leaves a non-numeric slot with no choices as free text", () => {
    expect(typedAffordance({ stepId: "sentetik.not", slotType: "string", choicesTr: [] })).toBe(
      "free_text",
    );
  });

  it("no question in any pack needs a numeric field", () => {
    for (const department of DEPARTMENTS) {
      for (const profile of PROFILES) {
        const pack = packForVisit(department, profile);
        expect(numericStepsWithoutChoices(pack), `${department}/${profile.mode}`).toEqual([]);
        for (const question of pack) {
          expect(() => affordanceForQuestion(question), question.id).not.toThrow();
        }
      }
    }
  });

  it("the intake screen offers no numeric keyboard at all", () => {
    const screen = read(INTAKE_SCREEN);
    expect(screen).not.toContain("keyboardType");
  });
});

/* ------------------------------------------------------------------ */
/* §4 — progress + resume (INT-179/236/239, pinned here)               */
/* ------------------------------------------------------------------ */

describe("§4 progress counts what is answered, never a total it cannot know", () => {
  it("the counter is the answered count and the caption says the flow can grow", () => {
    const screen = read(INTAKE_SCREEN);
    expect(screen).toContain("answeredCount");
    expect(screen).toContain('t("intake.progress.answered")');
    expect(screen).toContain('t("intake.progress.grows")');
    // "x / 9" against a denominator the next answer changes is the defect
    // INT-239 removed; nothing may print a slash between two counts again.
    expect(screen).not.toMatch(/\{answeredCount\}\s*\/\s*\{/);
  });

  it("the applicable set really does grow with an answer (adaptive denominator)", () => {
    const pack = packForVisit("Kardiyoloji", { mode: "detayli" });
    const gated = pack.filter((q) => q.askIf !== undefined);
    expect(gated.length).toBeGreaterThan(0);
    const before = applicableQuestions(pack, []).length;
    const opener = gated[0].askIf!;
    const after = applicableQuestions(pack, [
      { questionId: opener.questionId, values: [...opener.includesAny] },
    ]).length;
    expect(after).toBeGreaterThan(before);
  });
});

describe("§4 resume lands on the first unanswered applicable question", () => {
  const pack = packForVisit("Nöroloji", { mode: "detayli" });

  it("resumes at the first unanswered question, in pack order", () => {
    const first = applicableQuestions(pack, [])[0];
    expect(resumeQuestion(pack, []).id).toBe(first.id);
    const answers: AnsweredValues[] = [{ questionId: first.id, values: ["x"] }];
    const next = applicableQuestions(pack, answers).find((q) => q.id !== first.id)!;
    expect(resumeQuestion(pack, answers).id).toBe(next.id);
  });

  it("an edit request wins over the resume point", () => {
    const target = pack[pack.length - 1];
    expect(resumeQuestion(pack, [], target.id).id).toBe(target.id);
  });

  it("never returns null — a finished flow lands on its last question, not a blank", () => {
    const answers: AnsweredValues[] = applicableQuestions(pack, []).map((q) => ({
      questionId: q.id,
      values: ["x"],
    }));
    const resumed = resumeQuestion(pack, answers);
    expect(resumed).not.toBeNull();
    expect(applicableQuestions(pack, answers).map((q) => q.id)).toContain(resumed.id);
  });

  it("the screen uses the pack-layer rule rather than re-deriving it", () => {
    const screen = read(INTAKE_SCREEN);
    expect(screen).toContain("resumeQuestion(");
  });
});
