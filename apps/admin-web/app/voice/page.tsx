/**
 * INT-182 — `/voice`: per-profile metrics, each tenant's kill switch, default
 * profile and canary, and the four controls (files/08 §3 "Voice runtime").
 *
 * A server component, exactly like `/ops` and `/overview`: the loader runs here
 * with the caller's bearer forwarded to `GET /admin/voice`, where the API's
 * INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who sees
 * anything. The browser receives rendered HTML and names no datasource
 * (files/08 §0b F1). `?result=` is a code the form handler redirected back
 * with; anything that is not one of its codes is dropped.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { VoiceConsole } from "../../src/voice/console";
import { stepUpResultFrom } from "../../src/step-up/results";
import { loadVoice, resultFrom } from "../../src/voice/load";

export default async function VoicePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const lang = langFrom(params["lang"]);
  const state = await loadVoice({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return (
    <VoiceConsole
      state={state}
      lang={lang}
      result={resultFrom(params["result"])}
      stepUp={stepUpResultFrom(params["step_up"])}
    />
  );
}
