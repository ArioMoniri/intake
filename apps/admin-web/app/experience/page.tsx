/**
 * INT-564 — `/experience`: CSAT, NPS, the clinician pulse and the SDS-01
 * wait-time export for one stated window (INT-186, INT-241; files/08 §3).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/experience`, where the API's INT-180
 * gate decides who sees anything and the tenant comes from the caller's claim.
 * `?from=` and `?to=` choose the window; anything else falls back to the 30
 * days before today, and the page says which window it shows.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { ExperienceConsole } from "../../src/experience/console";
import { loadExperience, windowFrom } from "../../src/experience/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function ExperiencePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const state = await loadExperience({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
    window: windowFrom({ from: params["from"], to: params["to"] }, new Date()),
  });
  return <ExperienceConsole state={state} lang={langFrom(params["lang"])} />;
}
