/**
 * INT-565 — `/protocols`: branch coverage, the proposal review queue and clip
 * coverage (INT-184; files/08 §3; files/09 §1-4).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/protocols`, where the API's INT-180
 * gate decides who sees anything. The browser receives rendered HTML and names
 * no datasource (files/08 §0b F1).
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { ProtocolsConsole } from "../../src/protocols/console";
import { loadProtocols } from "../../src/protocols/load";

export default async function ProtocolsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadProtocols({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <ProtocolsConsole state={state} lang={lang} />;
}
