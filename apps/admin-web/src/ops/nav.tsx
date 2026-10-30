/**
 * The link between the rendered console pages (INT-181): the overview, the
 * ops console, the Voice module (INT-182), the access review (INT-366), the
 * CI/CD module (INT-187) and the Model lanes module (INT-428). Plain links,
 * server-rendered, the language carried along; the current page is marked,
 * not linked. `tr` is the source of truth (invariant 5).
 *
 * INT-459 — rendered as the console's sidebar: the mark, the pages grouped
 * under a visible name with a symbol beside each, and a language switch that
 * keeps the page. On a narrow screen the same markup becomes a floating tab
 * bar (app/native-shell.css). A new page is one entry in each of `CONSOLE_PAGES`,
 * `GROUP_OF`, `GLYPH_OF` and the two label tables; the Model lanes page
 * (INT-428) sits under Services with the `chip` symbol.
 */
import type { ReactElement } from "react";

import { Glyph, type GlyphName } from "../ui/glyphs";
import type { Lang } from "./copy";

export type ConsolePage =
  | "overview"
  | "ops"
  | "experience"
  | "voice"
  | "model-lanes"
  | "models"
  | "access"
  | "compliance"
  | "cicd";

/** Every console page, in the order the sidebar lists them. */
export const CONSOLE_PAGES: readonly ConsolePage[] = [
  "overview",
  "ops",
  "experience",
  "voice",
  "model-lanes",
  "models",
  "access",
  "compliance",
  "cicd",
];

type Group = "monitor" | "services" | "govern";

const GROUPS: readonly Group[] = ["monitor", "services", "govern"];

const GROUP_OF: Record<ConsolePage, Group> = {
  overview: "monitor",
  ops: "monitor",
  experience: "monitor",
  voice: "services",
  "model-lanes": "services",
  models: "services",
  access: "govern",
  compliance: "govern",
  cicd: "govern",
};

const GLYPH_OF: Record<ConsolePage, GlyphName> = {
  overview: "grid",
  ops: "gauge",
  voice: "waveform",
  "model-lanes": "chip",
  models: "cube",
  experience: "chart",
  access: "key",
  compliance: "shield",
  cicd: "branch",
};

interface NavCopy {
  label: string;
  brand: string;
  brandSub: string;
  groups: Record<Group, string>;
  pages: Record<ConsolePage, string>;
  langLabel: string;
}

const LABELS: Record<Lang, NavCopy> = {
  tr: {
    label: "Konsol sayfaları",
    brand: "INTAKE",
    brandSub: "Yönetim konsolu",
    groups: { monitor: "İzleme", services: "Hizmetler", govern: "Yönetim" },
    pages: {
      overview: "Genel bakış",
      ops: "Operasyon",
      voice: "Ses",
      access: "Erişim",
      cicd: "CI/CD",
      "model-lanes": "Model hatları",
      models: "Modeller",
      experience: "Deneyim",
      compliance: "Uyum",
    },
    langLabel: "Dil",
  },
  en: {
    label: "Console pages",
    brand: "INTAKE",
    brandSub: "Admin console",
    groups: { monitor: "Monitor", services: "Services", govern: "Governance" },
    pages: {
      overview: "Overview",
      ops: "Operations",
      voice: "Voice",
      access: "Access",
      cicd: "CI/CD",
      "model-lanes": "Model lanes",
      models: "Models",
      experience: "Experience",
      compliance: "Compliance",
    },
    langLabel: "Language",
  },
};

/** Each language names itself, in itself. */
const LANG_NAMES: Record<Lang, string> = { tr: "Türkçe", en: "English" };
const LANGS: readonly Lang[] = ["tr", "en"];

function hrefOf(page: ConsolePage, lang: Lang): string {
  return `/${page}${lang === "en" ? "?lang=en" : ""}`;
}

function PageEntry({
  page,
  current,
  lang,
  copy,
}: {
  page: ConsolePage;
  current: ConsolePage;
  lang: Lang;
  copy: NavCopy;
}): ReactElement {
  const inner = (
    <>
      <Glyph name={GLYPH_OF[page]} />
      <span className="nav-text">{copy.pages[page]}</span>
    </>
  );
  return (
    <li>
      {page === current ? (
        <span aria-current="page" data-page-link={page}>
          {inner}
        </span>
      ) : (
        <a href={hrefOf(page, lang)} data-page-link={page}>
          {inner}
        </a>
      )}
    </li>
  );
}

export function ConsoleNav({ current, lang }: { current: ConsolePage; lang: Lang }): ReactElement {
  const copy = LABELS[lang];
  return (
    <>
      <nav className="console-nav" aria-label={copy.label}>
        <p className="nav-brand">
          <Glyph name="mark" size={28} />
          <span className="nav-brand-text">
            <strong>{copy.brand}</strong>
            <span>{copy.brandSub}</span>
          </span>
        </p>
        {GROUPS.map((group) => (
          <div key={group} className="nav-group">
            <p id={`nav-group-${group}`} className="nav-group-label">
              {copy.groups[group]}
            </p>
            <ul aria-labelledby={`nav-group-${group}`}>
              {CONSOLE_PAGES.filter((page) => GROUP_OF[page] === group).map((page) => (
                <PageEntry key={page} page={page} current={current} lang={lang} copy={copy} />
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <nav className="console-lang" aria-label={copy.langLabel}>
        {LANGS.map((option) =>
          option === lang ? (
            <span key={option} aria-current="true" lang={option}>
              {LANG_NAMES[option]}
            </span>
          ) : (
            <a key={option} href={hrefOf(current, option)} hrefLang={option} lang={option}>
              {LANG_NAMES[option]}
            </a>
          ),
        )}
      </nav>
    </>
  );
}
