/**
 * INT-136 — the typed intake surface (Detaylı): instrument items rendered
 * verbatim, low-literacy chips, progress + resume.
 *
 * WHAT THIS FILE CAN AND CANNOT PROVE, said once and up front. vitest runs on
 * `node` here with no renderer (apps/mobile/vitest.config.ts: *"Component
 * rendering is exercised via Expo tooling, not vitest"*), so nothing below
 * renders a screen. The same split `overflow.spec.ts` and `appearance.spec.ts`
 * already make: the RULES are pure functions with their own unit tests
 * (`instruments.test.ts`, `lowLiteracy.test.ts`, `questions.test.ts`), and what
 * this file holds is the WIRING — that the screen reaches the rule, that the
 * one route from a pack's `text_tr` to the screen copies nothing, and that the
 * catalogue makes no claim the licences do not support. Anything that needs an
 * eye is a screenshot in docs/evidence/INT-136.md, labelled as one.
 *
 * Two of the checks reach outside the app on purpose. The instrument licence
 * table and the emptiness of the item registry are properties of
 * `packages/protocols`, not of the app, and asserting them against a copy of
 * the strings in the app would prove only that the copy agrees with itself —
 * which is the exact failure invariant 10 exists to prevent.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { INSTRUMENT_ITEMS, INSTRUMENT_LICENCES } from "@/lib/intake/instruments";
import { allQuestions } from "@/lib/intake/questions";
import { APP_STEPS } from "@/lib/prefs/appearance";
import { scaledSize, spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const REPO = join(MOBILE, "..", "..");
const PROTOCOLS = join(REPO, "packages", "protocols");
const INTAKE_SCREEN = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const metrics = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
);

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function read(relativePath: string, root = MOBILE): string {
  const source = readFileSync(join(root, relativePath), "utf8");
  expect(source.length, `${relativePath} is empty`).toBeGreaterThan(0);
  return source;
}

/**
 * Code only, comments dropped — the same order `overflow.spec.ts` runs in, and
 * for the same reason: a module that DOCUMENTS what it must not do should not
 * be convicted by a scan for the word.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/* ------------------------------------------------------------------ */
/* 1. The licence table is the one in packages/protocols, not a copy    */
/* ------------------------------------------------------------------ */

/** `"PHQ-9": InstrumentLicence.GO,` → `{"PHQ-9": "GO"}`. */
function pythonLicenceTable(): Record<string, string> {
  const source = read(join("src", "protocols", "licences.py"), PROTOCOLS);
  const block = /INSTRUMENT_LICENCES[\s\S]*?\n\)/.exec(source);
  expect(block, "licences.py no longer declares INSTRUMENT_LICENCES as expected").not.toBeNull();
  const rows = [...block![0].matchAll(/"([^"]+)":\s*InstrumentLicence\.([A-Z_]+)/g)];
  expect(rows.length, "no licence rows parsed out of licences.py").toBeGreaterThan(0);
  return Object.fromEntries(rows.map((row) => [row[1], row[2]]));
}

describe("the app's licence table is the server's", () => {
  it("matches packages/protocols row for row", () => {
    expect({ ...INSTRUMENT_LICENCES }).toEqual(pythonLicenceTable());
  });

  it("records C-SSRS and WHO-5 as blocked, on both sides", () => {
    const python = pythonLicenceTable();
    for (const id of ["C-SSRS", "WHO-5"]) {
      expect(python[id], id).toBe("BLOCKED");
      expect(INSTRUMENT_LICENCES[id], id).toBe("BLOCKED");
    }
  });
});

/* ------------------------------------------------------------------ */
/* 2. The registry is empty because the packs are, not by assertion     */
/* ------------------------------------------------------------------ */

/**
 * Instrument ids a pack source DEFINES (the top-level `instruments:` key that
 * `ProtocolPack.instruments` reads), as opposed to the ones a section merely
 * REFERENCES through `questionnaires:`. Only a definition carries `text_tr`,
 * and only a definition can therefore be rendered.
 */
export function definedInstrumentIds(packSource: string): string[] {
  const block = /^instruments:\n([\s\S]*?)(?=^\S|\Z)/m.exec(packSource);
  if (block === null) {
    return [];
  }
  // Only the sequence entries of `instruments:` itself, at the top of the
  // block — an ITEM's own `id:` is nested two levels deeper and is not an
  // instrument. The id shape is `dsl.py InstrumentId`, which starts with a
  // capital, so a nested lowercase item id cannot be mistaken for one either.
  return [...block[1].matchAll(/^ {0,2}-\s*id:\s*"?([A-Z][A-Za-z0-9-]*)"?\s*$/gm)].map(
    (match) => match[1],
  );
}

const PACK_SOURCES = walk(PROTOCOLS)
  .filter((path) => path.endsWith(".yaml") && !path.includes(`${sep}dist${sep}`))
  .map((path) => ({ name: relative(REPO, path), source: readFileSync(path, "utf8") }));

describe("no committed pack authors an instrument item", () => {
  it("finds pack sources to scan at all", () => {
    expect(PACK_SOURCES.length).toBeGreaterThan(50);
  });

  it("defines no instrument anywhere in the protocol tree", () => {
    const defined = PACK_SOURCES.flatMap(({ name, source }) =>
      definedInstrumentIds(source).map((id) => `${name}:${id}`),
    );
    expect(defined).toEqual([]);
  });

  it("would see one if a pack authored it (negative control)", () => {
    // The scan has to be shown to discriminate. Synthetic pack source; the id
    // belongs to no validated scale.
    const authored = [
      "id: fixture.pack",
      "instruments:",
      '  - id: "FIXTURE-ORNEK"',
      "    items:",
      "      - id: ornek_1",
      '        text_tr: "Örnek madde."',
      "        allow_paraphrase: false",
      "sections: {}",
      "",
    ].join("\n");
    expect(definedInstrumentIds(authored)).toEqual(["FIXTURE-ORNEK"]);
  });

  it("ships an app registry that holds exactly what the packs define", () => {
    // Both sides are empty today, and they are empty for the SAME reason —
    // HB-C1 (nobody has signed a pack) plus HB-L2/HB-L3 (two of the four
    // instruments are licence-BLOCKED). When a pack authors one, this fails
    // until the app registry carries it.
    const defined = PACK_SOURCES.flatMap(({ source }) => definedInstrumentIds(source)).filter(
      (id) => INSTRUMENT_LICENCES[id] === "GO",
    );
    expect(Object.keys(INSTRUMENT_ITEMS).sort()).toEqual(defined.sort());
  });
});

/* ------------------------------------------------------------------ */
/* 3. There is one route from `text_tr` to the screen, and it copies    */
/*    nothing                                                           */
/* ------------------------------------------------------------------ */

describe("the instrument renderer is verbatim by construction", () => {
  const renderer = code(read("src/components/InstrumentStep.tsx"));

  it("takes the item text from the registry and not from the catalogue", () => {
    expect(renderer).toContain("item.textTr");
    // `t(` may appear for the app's OWN chrome (the refusal notice); it must
    // never appear applied to the item.
    expect(renderer).not.toMatch(/t\(\s*[^)]*textTr/);
    expect(renderer).not.toMatch(/t\(\s*[^)]*choicesTr/);
  });

  it("applies no transform to the item text on its way to the screen", () => {
    for (const transform of [
      ".trim()",
      ".normalize(",
      ".replace(",
      ".slice(",
      ".toUpperCase(",
      ".toLowerCase(",
      ".toLocaleUpperCase(",
      ".toLocaleLowerCase(",
      "textTransform",
      "numberOfLines",
      "ellipsizeMode",
      "adjustsFontSizeToFit",
    ]) {
      expect(renderer, transform).not.toContain(transform);
    }
  });

  it("says so on screen when it refuses, rather than rendering nothing", () => {
    // A refused instrument that renders `null` is invisible: the step looks
    // finished and the patient is moved past a section nobody told them was
    // unavailable. The refusal is copy, and copy has a key (invariant 5).
    expect(renderer).toContain("intake.instrument.unavailable.title");
    expect(renderer).toContain("intake.instrument.unavailable.body");
    expect(renderer).not.toMatch(/return\s+null\s*;/);
  });

  it("is reached from the typed intake screen", () => {
    const screen = code(read(INTAKE_SCREEN));
    expect(screen).toContain("InstrumentStep");
    expect(screen).toContain("question.instrument");
  });
});

/* ------------------------------------------------------------------ */
/* 4. The catalogue claims nothing the licences do not support          */
/* ------------------------------------------------------------------ */

describe("no instrument is named or claimed in patient copy", () => {
  const values = [...Object.values(tr), ...Object.values(en)];

  it("names no instrument", () => {
    const named = values.filter((value) => /\bPHQ\b|\bGAD\b|WHO-5|C-SSRS|\bHAQ\b/i.test(value));
    expect(named).toEqual([]);
  });

  it("claims no Turkish validation for anything", () => {
    // CLAUDE.md, clinical content rules: PHQ-2/GAD-2 have no Turkish
    // validation at all, and the PHQ-9 Turkish evidence is a reliability
    // study. Invariant 20 keeps every such figure out of patient copy.
    const claims = values.filter((value) =>
      /doğrulanmış ölçek|Türkçe'ye uyarlanmış|validated scale|duyarlılık|özgüllük/i.test(value),
    );
    expect(claims).toEqual([]);
  });
});

describe("the low-literacy overlay is acquired without stigma", () => {
  it("never asks the patient whether they can read", () => {
    // files/02 §3: *"never ask «okuyabiliyor musunuz?»"*. The mobile mirror of
    // tests/sim/test_scenarios.py::test_the_persona_is_never_asked_whether_they_can_read.
    const asks = [...Object.values(tr), ...Object.values(en)].filter((value) =>
      /okuyabiliyor|okuma yazma|okur musunuz|okumayı biliyor|can you read|able to read/i.test(
        value,
      ),
    );
    expect(asks).toEqual([]);
  });

  it("offers the size framing files/02 §3 names instead", () => {
    expect(tr["appearance.textSize"]).toContain("Yazı");
  });
});

/* ------------------------------------------------------------------ */
/* 5. Chips stay reachable at every step the app's own control offers   */
/* ------------------------------------------------------------------ */

/**
 * A chip in a `flexWrap: "wrap"` row sizes to its content: React Native gives a
 * wrap item no shrink, so a label wider than the row makes the CHIP wider than
 * the row, and there is no horizontal scroll to reach it. Truncating is banned
 * repo-wide (files/00 §2, held by `appearance.spec.ts`), so the only remaining
 * way for a long Turkish option label to stay reachable at the app's largest
 * text step is for the chip to be bounded and the label to wrap inside it.
 *
 * Measured rather than asserted, using INT-295's reader over the face the app
 * actually ships — the same model that agreed with an iPhone 16 Pro capture to
 * within half a point. INT-295 is also why the sweep runs over the app's OWN
 * ladder rather than at 1.0: its text step REPLACES the OS Dynamic Type value,
 * so a device sitting at the default says nothing about what the control can
 * ask for.
 */
const OPTION_CHIP_HOSTS = [INTAKE_SCREEN, "src/components/DialogueIntake.tsx"];

/**
 * INT-466: the dialogue lays its chips out in a wrap row, and each chip is
 * the stage's answer card (StageControls), so the bound lives there.
 */
const CHIP_STYLE_HOST: Record<string, string> = {
  "src/components/DialogueIntake.tsx": "src/components/stage/StageControls.tsx",
};

/** The answer card's horizontal chrome: both paddings, the gap and the check. */
const STAGE_CARD_CHROME = spacing.md + 2 + (spacing.sm + 6) + (spacing.sm + 2) + 22 + 2;

/** The narrowest iPhone still in service, and the phone INT-295 captured on. */
const PHONE_WIDTHS = [375, 402] as const;

/**
 * The chip's own horizontal chrome: `paddingHorizontal`, plus the widest thing
 * a chip adds beside its label. INT-433 made the typed chips borderless and
 * gave the selected one a check sized to the label and a gap, so that is
 * taken at the largest step; it also covers the dialogue chips' hairline.
 */
const CHIP_CHROME = 2 * spacing.md + scaledSize("label", 2.0) + spacing.xs;

/** Every chip label the packs can put on screen, in both catalogues. */
const OPTION_LABELS = [
  ...new Set(
    allQuestions.flatMap((question) =>
      (question.options ?? []).flatMap((option) => [tr[option.labelKey], en[option.labelKey]]),
    ),
  ),
];

function chipWidth(label: string, scale: number): number {
  // Chips are `role="label"` (AppText) in both hosts.
  return CHIP_CHROME + metrics.advance(label, scaledSize("label", scale));
}

describe("a pack option label is reachable at every APP_STEPS size", () => {
  it("has labels that do NOT fit a row, so the bound is load-bearing", () => {
    // The control has to be shown to be needed. Without this, `maxWidth` would
    // be a style nobody could tell from decoration.
    const row = Math.min(...PHONE_WIDTHS) - 2 * spacing.screen;
    const widest = Math.max(...OPTION_LABELS.map((label) => chipWidth(label, 2.0)));
    expect(OPTION_LABELS.length).toBeGreaterThan(50);
    expect(widest).toBeGreaterThan(row);
  });

  it("bounds every wrap-laid chip that carries a pack option label", () => {
    for (const host of OPTION_CHIP_HOSTS) {
      const source = code(read(host));
      expect(source, `${host} no longer lays chips out in a wrap row`).toContain(
        'flexWrap: "wrap"',
      );
      const styleHost = CHIP_STYLE_HOST[host];
      if (styleHost !== undefined) {
        const card = /\n\s{2}card:\s*\{[\s\S]*?\n\s{2}\}/.exec(code(read(styleHost)));
        expect(card, `${styleHost} has no \`card\` style to bound`).not.toBeNull();
        expect(card![0], styleHost).toContain('maxWidth: "100%"');
        continue;
      }
      const chip = /\n\s{2}chip:\s*\{[\s\S]*?\n\s{2}\}/.exec(source);
      expect(chip, `${host} has no \`chip\` style to bound`).not.toBeNull();
      expect(chip![0], host).toContain('maxWidth: "100%"');
    }
  });

  it("keeps the widest label inside the row once the bound wraps it", () => {
    // A bounded chip is as wide as the row at worst, and the label wraps
    // inside the space the chrome leaves. What must never happen is the
    // chrome alone exceeding the row — then no wrapping saves it.
    for (const phone of PHONE_WIDTHS) {
      const row = phone - 2 * spacing.screen;
      expect(CHIP_CHROME, `${phone}pt`).toBeLessThan(row);
      for (const scale of APP_STEPS) {
        // One glyph has to fit beside the chrome at every step, or the label
        // could never wrap into a legible column.
        const widestGlyph = Math.max(
          ...OPTION_LABELS.flatMap((label) => [...label]).map((glyph) =>
            metrics.advance(glyph, scaledSize("label", scale)),
          ),
        );
        expect(CHIP_CHROME + widestGlyph, `${phone}pt @${scale}`).toBeLessThanOrEqual(row);
        // The stage's answer card sets its label in the body role.
        const widestBodyGlyph = Math.max(
          ...OPTION_LABELS.flatMap((label) => [...label]).map((glyph) =>
            metrics.advance(glyph, scaledSize("body", scale)),
          ),
        );
        expect(
          STAGE_CARD_CHROME + widestBodyGlyph,
          `card ${phone}pt @${scale}`,
        ).toBeLessThanOrEqual(row);
      }
    }
  });

  it("truncates no chip label anywhere on the typed intake path", () => {
    for (const host of [...OPTION_CHIP_HOSTS, "src/components/InstrumentStep.tsx"]) {
      const source = code(read(host));
      for (const token of ["numberOfLines", "ellipsizeMode", "adjustsFontSizeToFit"]) {
        expect(source, `${host}/${token}`).not.toContain(token);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6. Progress and resume are the pack's, not the screen's              */
/* ------------------------------------------------------------------ */

describe("progress and resume", () => {
  const screen = code(read(INTAKE_SCREEN));

  it("resumes through the pack layer, so the rule is unit-testable", () => {
    expect(screen).toContain("resumeQuestion(");
  });

  it("counts progress through the pack layer too", () => {
    expect(screen).toContain("intakeProgress(");
  });

  it("denominates on the applicable flow, and says when it may grow", () => {
    // INT-136 printed no total, because "3 / 9" over the whole pack is a
    // promise the next answer can break. INT-433 (owner, 2 Oct 2026) asks for
    // "Soru N / M": M is the APPLICABLE count the pack layer derives on every
    // render, never the pack's length, and while a gate could still open the
    // growth line is shown with it, so the total is never a silent promise.
    const progress = code(read("src/components/QuestionProgress.tsx"));
    expect(tr["intake.progress.question"]).toBe("Soru");
    expect(screen).toMatch(/questionPosition\(applicable, question\.id, flowCanGrow\)/);
    expect(screen).not.toMatch(/intakeQuestions\.length/);
    expect(screen).not.toMatch(/\{\s*stepIndex\s*\+\s*1\s*\}\s*\/\s*/);
    expect(progress).toMatch(/position\.mayGrow \? \(/);
    expect(progress).toContain('t("intake.progress.grows")');
  });
});
