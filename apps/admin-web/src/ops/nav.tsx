/**
 * The link between the rendered console pages (INT-181): the overview, the
 * ops console, the Voice module (INT-182) and the CI/CD module (INT-187). Plain
 * links, server-rendered, the language carried along; the current page is
 * marked, not linked. `tr` is the source of truth (invariant 5).
 */
import type { ReactElement } from "react";

import type { Lang } from "./copy";

export type ConsolePage = "overview" | "ops" | "voice" | "cicd";

const LABELS: Record<Lang, { label: string; pages: Record<ConsolePage, string> }> = {
  tr: {
    label: "Konsol sayfaları",
    pages: { overview: "Genel bakış", ops: "Operasyon", voice: "Ses", cicd: "CI/CD" },
  },
  en: {
    label: "Console pages",
    pages: { overview: "Overview", ops: "Operations", voice: "Voice", cicd: "CI/CD" },
  },
};

const ORDER: readonly ConsolePage[] = ["overview", "ops", "voice", "cicd"];

export function ConsoleNav({ current, lang }: { current: ConsolePage; lang: Lang }): ReactElement {
  const copy = LABELS[lang];
  const suffix = lang === "en" ? "?lang=en" : "";
  return (
    <nav className="console-nav" aria-label={copy.label}>
      {ORDER.map((page) =>
        page === current ? (
          <span key={page} aria-current="page">
            {copy.pages[page]}
          </span>
        ) : (
          <a key={page} href={`/${page}${suffix}`}>
            {copy.pages[page]}
          </a>
        ),
      )}
    </nav>
  );
}
