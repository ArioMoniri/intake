/**
 * INT-351 — the admin-web App Router shell (files/08 §7: Next.js App Router;
 * audit F26 — the console was headless view-models only).
 *
 * Deliberately minimal: one stylesheet, bundled and served from `'self'`
 * (the CSP carries no `unsafe-inline`, so no `style` attribute is used
 * anywhere), no client component, no third-party script, font or frame.
 */
import type { Metadata } from "next";
import type { ReactElement, ReactNode } from "react";

import "./console.css";

export const metadata: Metadata = {
  title: "INTAKE admin",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }): ReactElement {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
