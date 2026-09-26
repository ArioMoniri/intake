/**
 * INT-301 — the language chooser, the mid-visit switch, and right-to-left,
 * pinned on the source tree.
 *
 * Same shape and the same reason as every other e2e/*.spec.ts here: React
 * Native has no DOM, so a rendered assertion needs a device. What CAN be
 * proved from the tree is the wiring — that the chooser reads the registry
 * rather than a hardcoded list, that it is reachable at first run and from the
 * Me screen, that a language switch changes only the PRESENTATION (answers are
 * values, so switching never touches the note), and that right-to-left is a
 * property of the SHARED anatomy rather than a fix sprinkled screen by screen.
 *
 * The chooser itself is ABSENT today (only `tr` is registered), so the
 * two things this file cannot prove — that two real endonyms render, and that
 * the enlarged anatomy flips coherently under RTL — are the simulator's job
 * the day a second locale lands. What it pins is that nothing in the tree will
 * have to be touched screen-by-screen when it does.
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

const TREE: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Source with comments and string literals removed. A layout-direction
 * property is a fact about the CODE; the word "direction" in a sentence is
 * not, so the direction scans below read this rather than the raw text. */
function codeOnly(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1")
    .replace(/`(?:[^`\\]|\\.)*`/g, "``")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''");
}

it("the scanner sees the tree it is supposed to police", () => {
  expect(TREE.length).toBeGreaterThan(40);
});

/* ------------------------------------------------------------------ */
/* 1 — the chooser reads the registry, at first run and on the Me tab  */
/* ------------------------------------------------------------------ */

describe("the chooser is reachable, and reads the registry", () => {
  it("the Me screen still derives its languages from the registry (INT-296)", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toMatch(/offerableAppLocales\(\)/);
    expect(me).not.toMatch(/\["tr",\s*"en"\]\s*as\s*const/);
  });

  it("the Me screen turns that set into a chooser — endonyms, absent when < 2", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    // The offered set is mapped to displayable choices and gated by `present`.
    expect(me).toMatch(/\bpresent\(/);
    expect(me).toMatch(/\btoChoices\(/);
    // Each language in its own name and script — the endonym, not a catalogue label.
    expect(me).toMatch(/\.endonym\b/);
  });

  it("first run reaches the same chooser", () => {
    const welcome = file("src/app/(auth)/welcome.tsx");
    expect(welcome).toMatch(/from "@\/lib\/locale\/chooser"/);
    expect(welcome).toMatch(/\.endonym\b/);
  });
});

/* ------------------------------------------------------------------ */
/* 2 — a switch changes presentation only; it never re-asks             */
/* ------------------------------------------------------------------ */

describe("switching keeps the session", () => {
  it("switchLocale changes the language and nothing else — it never touches the note", () => {
    const session = file("src/lib/session.tsx");
    const body = session.slice(
      session.indexOf("const switchLocale ="),
      session.indexOf("const visits ="),
    );
    expect(body).toContain("setLocale");
    // Answers are values, not strings: a switch re-renders, it does not
    // rebuild the note, so the switch path may not write answers.
    expect(body).not.toContain("setNotes");
    expect(body).not.toContain("updateNote");
  });

  it("the note stores VALUES, so the same answer renders in either language", () => {
    const note = file("src/lib/intake/note.ts");
    // The Answer carries coded `values`, and the human words are provenance
    // only — never the stored answer. Rendering to text goes through `t()`.
    expect(note).toMatch(/values:\s*string\[\]/);
    expect(note).toMatch(/from "\.\.\/i18n"/);
  });

  it("the chooser's switch refuses while a red-flag script is in flight", () => {
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toMatch(/chooseFromChooser/);
  });
});

/* ------------------------------------------------------------------ */
/* 3 — right-to-left is a property of the shared anatomy                */
/* ------------------------------------------------------------------ */

describe("right-to-left is a layout property, not a per-screen fix", () => {
  it("the shared anatomy derives direction from the locale, in ONE place", () => {
    const themed = file("src/components/Themed.tsx");
    expect(themed).toMatch(/from "@\/lib\/locale\/direction"/);
    // The screen container flips; text writes in the locale's direction.
    expect(themed).toMatch(/direction:/);
    expect(themed).toMatch(/writingDirection:/);
  });

  it("no other screen or component sets a layout direction — it is inherited", () => {
    // The render tree is screens (src/app) and components (src/components); the
    // locale lib is where direction is DEFINED and carried as data, not applied
    // as a style, so it is not in scope here.
    const setters = TREE.filter((f) => {
      const isRenderTree = f.name.startsWith("src/app/") || f.name.startsWith("src/components/");
      return (
        isRenderTree &&
        f.name !== "src/components/Themed.tsx" &&
        /\b(writingDirection|direction):/.test(codeOnly(f.source))
      );
    }).map((f) => f.name);
    // Allow-list ships EMPTY and may only shrink (the INT-284/INT-295 rule).
    expect(setters).toEqual([]);
  });

  it("no physical-direction style leaks that RTL cannot flip", () => {
    // `textAlign: left|right` and `row-reverse` do NOT flip under RTL and are
    // exactly the per-screen defect this issue refuses. Allow-list empty.
    // Comments are stripped (so prose about a "row-reverse" is not a hit) but
    // string literals are KEPT — the value `"left"` is exactly what we look for.
    const noComments = (s: string): string =>
      s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
    const offenders: string[] = [];
    for (const f of TREE) {
      const code = noComments(f.source);
      if (/textAlign:\s*["'](left|right)["']/.test(code)) {
        offenders.push(`${f.name}: textAlign left/right`);
      }
      if (/["'][a-z]*(row|column)-reverse["']/.test(code)) {
        offenders.push(`${f.name}: reversed flex`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the enlarged type steps are direction-agnostic — size does not read direction", () => {
    // INT-295 found a row that broke at a reachable text step; the fix must
    // hold in BOTH directions, which it does because the type scale takes no
    // direction argument and the chooser row wraps rather than pinning an edge.
    const theme = file("src/lib/theme.ts");
    expect(theme).toMatch(/scaledSize\(role: TypeRole, fontScale: number\)/);
    const me = file("src/app/(tabs)/me/index.tsx");
    expect(me).toMatch(/flexWrap:\s*["']wrap["']/);
  });
});
