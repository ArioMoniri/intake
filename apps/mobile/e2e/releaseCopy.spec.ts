/**
 * INT-588 — the screens resolve their build-aware copy through one module.
 *
 * `src/lib/buildCopy.test.ts` proves what each choice resolves to in a release
 * build. What only the source can show is that the screens actually make the
 * choice — that no screen renders a dev-only line directly — and that the
 * open-answer hint is chosen on the same two facts that decide whether the
 * dictation button exists at all (`__DEV__` and the voice consent), so the
 * hint can never promise a button the screen does not draw.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test.") && !p.includes(`${sep}i18n${sep}`))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Code only, comments dropped — prose about a rule is not the rule. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const APPEARANCE = "src/app/(tabs)/me/appearance.tsx";
const COMPANION = "src/app/(tabs)/me/companion.tsx";
const BUILD_COPY = "src/lib/buildCopy.ts";

describe("the open-answer hint", () => {
  const intake = code(file(INTAKE));

  it("is chosen through the build-aware helper, at both places it is read", () => {
    expect(intake.split("openAnswerHintKey(").length - 1).toBe(2);
    expect(intake).not.toContain('t("intake.open.hint")');
  });

  it("on the same facts that draw the dictation button — at EVERY call", () => {
    expect(intake).toMatch(/__DEV__ && consents\?\.voice === true \? \(\s*<VoiceNote/);
    // whitespace-free, so a reflowed call still counts; every call must be the
    // canonical one, so a literal "dev" or a hard-coded consent at either
    // place fails (a single match would let the other drift)
    const flat = intake.replace(/\s+/g, "");
    const canonical = "openAnswerHintKey(currentBuildMode(),consents?.voice===true)";
    expect(flat.split(canonical).length - 1).toBe(flat.split("openAnswerHintKey(").length - 1);
    expect(code(file(BUILD_COPY))).toMatch(/__DEV__/);
  });

  it("the voice variant is named only by the helper", () => {
    for (const entry of TREE) {
      if (entry.name === BUILD_COPY) continue;
      expect(code(entry.source), entry.name).not.toContain('"intake.open.hintVoice"');
    }
  });
});

describe("the start-mode chooser", () => {
  it("is drawn only where a voice start exists", () => {
    const screen = code(file(APPEARANCE));
    expect(screen).toMatch(/startModeOffered\(currentBuildMode\(\)\) \? \(/);
  });
});

describe("the companion effects", () => {
  it("are listed through the build-aware helper", () => {
    const screen = code(file(COMPANION));
    expect(screen).toContain("companionEffectKeys(outcome, currentBuildMode())");
    // the text-only effect is still a catalogue line, named by the helper
    expect(code(file(BUILD_COPY))).toContain('"companion.effect.textOnly"');
  });
});
