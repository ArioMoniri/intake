/**
 * INT-351 — the admin-web App Router shell (files/08 §7: Next.js App Router;
 * audit F26 — the console was headless view-models only).
 *
 * Deliberately minimal: the console's own stylesheet, the INT-450 refresh
 * layer over it, and the INT-459 Apple-native layer last (its tokens, the
 * palette that holds every colour of both themes, its shell, its content, the
 * patterns its follow-up mined, and the refresh's layout) — bundled
 * and served from `'self'` (the CSP carries no `unsafe-inline`, so no `style`
 * attribute is used anywhere), no client component, no third-party script,
 * font or frame.
 */
import type { Metadata, Viewport } from "next";
import type { ReactElement, ReactNode } from "react";

import "./console.css";
import "./refresh.css";
import "./refresh-charts.css";
import "./native-tokens.css";
import "./palette.css";
import "./native-shell.css";
import "./native-content.css";
import "./native-patterns.css";
import "./native-layout.css";

export const metadata: Metadata = {
  title: "INTAKE admin",
  robots: { index: false, follow: false },
};

/** The browser's own chrome takes the page's background in each theme
 * (`--bg` in app/palette.css; e2e/palette.spec.ts pins the two together). */
export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf8f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0e0c" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }): ReactElement {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
