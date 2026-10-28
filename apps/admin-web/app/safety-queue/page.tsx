/**
 * INT-562 — `/safety-queue`: the clinic's safety inbox (files/08 §3 "Safety
 * queue"): every RED, its on-site notification and the transitions of a RED
 * visit, in the inbox's order, with one acknowledgement per open entry.
 *
 * A server component, exactly like `/ops` and `/voice`: the loader runs here
 * with the caller's bearer forwarded to `GET /admin/safety-queue`, where the
 * API's INT-180 gate decides who sees anything. The browser receives rendered
 * HTML and names no datasource (files/08 §0b F1). `?result=` is a code the
 * form handler redirected back with; anything else is dropped.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { SafetyQueueConsole } from "../../src/safety-queue/console";
import { loadSafetyQueue, resultFrom } from "../../src/safety-queue/load";

export default async function SafetyQueuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const lang = langFrom(params["lang"]);
  const state = await loadSafetyQueue({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <SafetyQueueConsole state={state} lang={lang} result={resultFrom(params["result"])} />;
}
