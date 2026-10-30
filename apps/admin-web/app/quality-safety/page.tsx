/**
 * INT-565 — `/quality-safety`: triage events, PolicyGuard blocks, the
 * false-RED review queue and note acceptance (INT-185; files/08 §3, §4 D/E).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/quality-safety`, where the API's
 * INT-180 gate decides who sees anything. The browser receives rendered HTML
 * and names no datasource (files/08 §0b F1).
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { QualitySafetyConsole } from "../../src/safety/console";
import { loadQualitySafety } from "../../src/safety/load";

export default async function QualitySafetyPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadQualitySafety({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <QualitySafetyConsole state={state} lang={lang} />;
}
