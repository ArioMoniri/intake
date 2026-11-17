/**
 * INT-459 — axe-core over a server-rendered tree, in jsdom (the INT-450
 * harness's shape). jsdom has no layout, so colour contrast is computed from
 * the tokens elsewhere and is switched off here.
 */
import axe from "axe-core";
import { JSDOM } from "jsdom";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** One document's axe audit on a shared CI runner: the admin-web lane shares
 * the pool's host with the other lanes, and a wired overview (every table
 * answering) ran past vitest's 5 s default there (#963, run 40602198849).
 * Every axe test audits one document and takes this allowance. */
export const AXE_TIMEOUT_MS = 30_000;

export function documentFor(tree: ReactElement, lang: "tr" | "en"): string {
  const body = renderToStaticMarkup(tree);
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><title>INTAKE admin</title></head><body>${body}</body></html>`;
}

export async function violations(html: string): Promise<string[]> {
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const window = dom.window as unknown as { eval: (src: string) => void; axe: typeof axe };
  window.eval(axe.source);
  const results = await window.axe.run(dom.window.document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } },
  });
  dom.window.close();
  return results.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}
