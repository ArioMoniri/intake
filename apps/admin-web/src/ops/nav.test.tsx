/**
 * INT-459 — the console shell's navigation: a grouped sidebar with a symbol per
 * page and a language switch. Server-rendered links only; the current page is
 * marked, not linked, exactly as before (INT-181), and every href is the page's
 * own path with the language carried along.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CONSOLE_PAGES, ConsoleNav, type ConsolePage } from "./nav";

type Lang = "tr" | "en";

function render(current: ConsolePage, lang: Lang): string {
  return renderToStaticMarkup(createElement(ConsoleNav, { current, lang }));
}

function navOf(html: string, label: string): string {
  const open = html.indexOf(`aria-label="${label}"`);
  expect(open, `nav labelled ${label}`).toBeGreaterThan(-1);
  return html.slice(open, html.indexOf("</nav>", open));
}

describe("the sidebar lists every console page once, grouped", () => {
  for (const lang of ["tr", "en"] as const) {
    it(`every page appears exactly once, in group order (${lang})`, () => {
      const nav = navOf(
        render("overview", lang),
        lang === "tr" ? "Konsol sayfaları" : "Console pages",
      );
      for (const page of CONSOLE_PAGES) {
        expect(nav.split(`data-page-link="${page}"`).length - 1, page).toBe(1);
      }
      const order = [...nav.matchAll(/data-page-link="([a-z-]+)"/g)].map((m) => m[1]);
      expect(order).toEqual([...CONSOLE_PAGES]);
    });
  }

  it("names its groups in tr and en", () => {
    expect(render("ops", "tr")).toMatch(/İzleme[\s\S]*Hizmetler[\s\S]*Yönetim/);
    expect(render("ops", "en")).toMatch(/Monitor[\s\S]*Services[\s\S]*Governance/);
  });

  it("each group's list is labelled by its visible group name", () => {
    const html = render("voice", "en");
    const ids = [...html.matchAll(/<ul aria-labelledby="([^"]+)"/g)].map((m) => m[1]!);
    expect(ids.length).toBe(3);
    for (const id of ids) expect(html).toContain(`id="${id}"`);
  });
});

describe("the current page is marked, not linked", () => {
  for (const page of CONSOLE_PAGES) {
    it(page, () => {
      const html = render(page, "tr");
      expect(html).toMatch(
        new RegExp(`<span[^>]*aria-current="page"[^>]*data-page-link="${page}"`),
      );
      expect(html).not.toContain(`href="/${page}"`);
      for (const other of CONSOLE_PAGES.filter((p) => p !== page)) {
        expect(html).toContain(`href="/${other}"`);
      }
    });
  }

  it("near-miss: in en every link carries the language", () => {
    const html = render("overview", "en");
    expect(html).toContain('href="/ops?lang=en"');
    expect(html).not.toContain('href="/ops"');
  });
});

describe("symbols are decoration, never the name", () => {
  it("every page entry carries one hidden, unfocusable symbol beside its text", () => {
    const html = render("access", "en");
    const entries = [...html.matchAll(/data-page-link="[a-z-]+"[^>]*>([\s\S]*?)<\/(a|span)>/g)];
    expect(entries.length).toBe(CONSOLE_PAGES.length);
    for (const [, inner] of entries) {
      expect(inner!.match(/<svg/g)?.length).toBe(1);
      expect(inner).toMatch(/<svg[^>]*aria-hidden="true"[^>]*focusable="false"/);
      expect(
        inner!
          .replace(/<svg[\s\S]*?<\/svg>/g, "")
          .replace(/<[^>]+>/g, "")
          .trim().length,
      ).toBeGreaterThan(1);
    }
  });

  it("no style attribute anywhere (the CSP has no unsafe-inline)", () => {
    for (const lang of ["tr", "en"] as const) expect(render("cicd", lang)).not.toContain("style=");
  });
});

describe("the language switch keeps the page", () => {
  it("tr: Türkçe is current; English links to the same page with ?lang=en", () => {
    const sw = navOf(render("voice", "tr"), "Dil");
    expect(sw).toMatch(/<span[^>]*aria-current="true"[^>]*>Türkçe<\/span>/);
    expect(sw).toMatch(
      /<a[^>]*href="\/voice\?lang=en"[^>]*hrefLang="en"[^>]*lang="en"[^>]*>English<\/a>/,
    );
  });

  it("en: English is current; Türkçe links to the page without the query", () => {
    const sw = navOf(render("cicd", "en"), "Language");
    expect(sw).toMatch(/<span[^>]*aria-current="true"[^>]*>English<\/span>/);
    expect(sw).toMatch(/<a[^>]*href="\/cicd"[^>]*hrefLang="tr"[^>]*lang="tr"[^>]*>Türkçe<\/a>/);
  });

  it("near-miss: the switch never links to the language already shown", () => {
    expect(navOf(render("ops", "tr"), "Dil")).not.toContain('hrefLang="tr"');
    expect(navOf(render("ops", "en"), "Language")).not.toContain('hrefLang="en"');
  });
});
