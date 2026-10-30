/**
 * INT-459 refresh — the app's palette, read from its source of truth
 * (`apps/mobile/src/lib/theme.ts`) as text. Importing the module would make
 * the admin lane resolve the app's Expo tsconfig, which only an installed app
 * workspace can, so the spec reads the literal instead: every `name: "#hex"`
 * pair inside the `light` and `dark` blocks of `export const palette`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

export const APP_THEME = join(__dirname, "..", "..", "..", "mobile", "src", "lib", "theme.ts");

export type AppTheme = Record<string, string>;

function block(source: string, scheme: "light" | "dark"): string {
  const start = source.indexOf(`\n  ${scheme}: {`);
  if (start < 0) throw new Error(`theme.ts: no ${scheme} block`);
  const end = source.indexOf("\n  },", start);
  if (end < 0) throw new Error(`theme.ts: the ${scheme} block does not close`);
  return source.slice(start, end);
}

/** The palette's two themes, each as `name -> #hex` in lower case. */
export function appPalette(source: string = readFileSync(APP_THEME, "utf8")): {
  light: AppTheme;
  dark: AppTheme;
} {
  const start = source.indexOf("export const palette = {");
  if (start < 0) throw new Error("theme.ts: no exported palette");
  const body = source.slice(start, source.indexOf("} as const;", start));
  const read = (scheme: "light" | "dark"): AppTheme =>
    Object.fromEntries(
      [...block(body, scheme).matchAll(/^\s+([a-zA-Z]+): "(#[0-9a-fA-F]{6})"/gm)].map((m) => [
        m[1]!,
        m[2]!.toLowerCase(),
      ]),
    );
  return { light: read("light"), dark: read("dark") };
}
