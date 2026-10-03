/**
 * INT-459 — reading the console's own stylesheets in a spec: a small rule
 * parser (selectors, declarations, enclosing at-rules) and the WCAG 2.x
 * contrast arithmetic. Comments are stripped first, because the stylesheets'
 * headers are prose that names what they forbid.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const APP = join(__dirname, "..", "..", "app");

/** The INT-459 Apple-native layer: its tokens, its shell, its content. */
export const NATIVE_SHEETS = [
  "native-tokens.css",
  "native-shell.css",
  "native-content.css",
] as const;

/** The console's stylesheets, in the order the layout imports them. */
export const SHEETS = ["console.css", "refresh.css", ...NATIVE_SHEETS] as const;

export function sheet(name: string): string {
  return readFileSync(join(APP, name), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

export interface Rule {
  sheet: string;
  selector: string;
  decls: Record<string, string>;
  /** Enclosing at-rule preludes, outermost first (`@media …`, `@supports …`). */
  at: string[];
}

function declsOf(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of body.split(";")) {
    const colon = part.indexOf(":");
    if (colon < 0) continue;
    out[part.slice(0, colon).trim()] = part.slice(colon + 1).trim();
  }
  return out;
}

/** Every style rule of a stylesheet; keyframe steps are left out. */
export function rulesOf(name: string, css: string = sheet(name)): Rule[] {
  const out: Rule[] = [];
  const stack: { prelude: string; start: number }[] = [];
  let prelude = "";
  for (let i = 0; i < css.length; i += 1) {
    const ch = css[i]!;
    if (ch === "{") {
      stack.push({ prelude: prelude.trim(), start: i + 1 });
      prelude = "";
    } else if (ch === "}") {
      const top = stack.pop();
      if (top === undefined) throw new Error(`${name}: unbalanced '}' at ${i}`);
      const at = stack.map((s) => s.prelude);
      if (!top.prelude.startsWith("@") && !at.some((a) => a.startsWith("@keyframes"))) {
        out.push({
          sheet: name,
          selector: top.prelude,
          decls: declsOf(css.slice(top.start, i)),
          at,
        });
      }
      prelude = "";
    } else if (ch === ";" && stack.length === 0) {
      prelude = "";
    } else {
      prelude += ch;
    }
  }
  if (stack.length !== 0) throw new Error(`${name}: unclosed block`);
  return out;
}

export function allRules(): Rule[] {
  return SHEETS.flatMap((name) => rulesOf(name));
}

export function nativeRules(): Rule[] {
  return NATIVE_SHEETS.flatMap((name) => rulesOf(name));
}

export function selectorsOf(rule: Rule): string[] {
  return rule.selector
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// --- colour -----------------------------------------------------------------

function channel(hex: string, i: number): number {
  return parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
}

/** `fg` laid over `bg` at `alpha` (0..1), as sRGB hex. */
export function blend(fg: string, bg: string, alpha: number): string {
  const mix = [0, 1, 2].map((i) =>
    Math.round(channel(fg, i) * alpha + channel(bg, i) * (1 - alpha)),
  );
  return `#${mix.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = [0, 1, 2].map((i) => {
    const s = channel(hex, i) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

/** WCAG 2.x contrast ratio of two opaque sRGB hex colours. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}
