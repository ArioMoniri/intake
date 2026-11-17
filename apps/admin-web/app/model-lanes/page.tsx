/**
 * INT-428 — `/model-lanes`: which backend serves the llm, asr and tts lanes
 * and every configured role, what each costs and how fast it answers, the
 * selectable models, the hosted providers' keys, and the controls (files/08
 * §3; ADR-035).
 *
 * A server component, exactly like `/cicd` and `/voice`: the loader runs here
 * with the caller's bearer forwarded to `GET /admin/model-lanes`, where the
 * API's INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who
 * sees anything. The browser receives rendered HTML and names no datasource
 * (files/08 §0b F1). `?result=` is a code the form handler redirected back
 * with; anything that is not one of its codes is dropped. A staged key's last
 * four arrive in the handler's one-shot cookie, and only in that shape.
 */
import type { ReactElement } from "react";
import { cookies, headers } from "next/headers";

import { STAGED_COOKIE } from "../../src/model-lanes/actions";
import { ModelLanesConsole } from "../../src/model-lanes/console";
import { loadModelLanes, resultFrom, stagedFrom } from "../../src/model-lanes/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function ModelLanesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const jar = await cookies();
  const params = await searchParams;
  const lang = langFrom(params["lang"]);
  const state = await loadModelLanes({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return (
    <ModelLanesConsole
      state={state}
      lang={lang}
      result={resultFrom(params["result"])}
      staged={stagedFrom(jar.get(STAGED_COOKIE)?.value)}
    />
  );
}
