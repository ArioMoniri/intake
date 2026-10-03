/**
 * INT-459 — reading the console's Content-Security-Policy the way a browser
 * does, for the one question the loading state raises: is this inline style
 * applied or refused?
 *
 * CSP Level 3, "Does element match source list for type and source?":
 * - a style attribute is checked against `style-src-attr`, then `style-src`,
 *   then `default-src`; a `<style>` element against `style-src-elem`, then
 *   `style-src`, then `default-src`. The first directive present decides.
 * - `'unsafe-inline'` admits everything, unless the list also carries a nonce
 *   or a hash, which switches it off.
 * - A hash admits a `<style>` element whose text matches. It admits an
 *   attribute only when the same list also carries `'unsafe-hashes'`.
 * - A nonce admits an element that carries it. An attribute cannot carry one.
 *
 * Hashes are derived here from the value, never written out (a spec that
 * names a literal it checks for trips the scanners it is guarding).
 */
import { createHash } from "node:crypto";

/** Each directive's source list, by lower-cased name; the first one wins. */
export function directivesOf(policy: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const part of policy.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name === undefined || name === "") continue;
    const key = name.toLowerCase();
    if (!out.has(key)) out.set(key, sources);
  }
  return out;
}

/** The CSP hash source for an inline value: sha256 over its UTF-8, base64. */
export function hashSource(value: string): string {
  return `'sha256-${createHash("sha256").update(value, "utf8").digest("base64")}'`;
}

/** Every `unsafe-*` keyword in a policy, named with its directive. */
export function unsafeSources(policy: string): string[] {
  return [...directivesOf(policy)].flatMap(([name, sources]) =>
    sources.filter((s) => /unsafe-/i.test(s)).map((s) => `${name} ${s}`),
  );
}

const NONCE_OR_HASH = /^'(nonce-|sha(256|384|512)-)/i;

function governing(policy: string, chain: readonly string[]): string[] | undefined {
  const directives = directivesOf(policy);
  for (const name of chain) {
    const list = directives.get(name);
    if (list !== undefined) return list;
  }
  return undefined;
}

function unsafeInline(list: readonly string[]): boolean {
  return list.includes("'unsafe-inline'") && !list.some((s) => NONCE_OR_HASH.test(s));
}

/** Would the browser apply `style="<value>"` from the markup? */
export function admitsStyleAttribute(policy: string, value: string): boolean {
  const list = governing(policy, ["style-src-attr", "style-src", "default-src"]);
  if (list === undefined || unsafeInline(list)) return true;
  return list.includes("'unsafe-hashes'") && list.includes(hashSource(value));
}

/** Would the browser apply `<style nonce="<nonce>">text</style>`? */
export function admitsStyleElement(policy: string, text: string, nonce?: string): boolean {
  const list = governing(policy, ["style-src-elem", "style-src", "default-src"]);
  if (list === undefined || unsafeInline(list)) return true;
  if (nonce !== undefined && list.includes(`'nonce-${nonce}'`)) return true;
  return list.includes(hashSource(text));
}
