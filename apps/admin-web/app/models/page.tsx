/**
 * INT-564 — `/models`: the models & self-hosting registry with the release
 * gate as its first tile (INT-183, files/08 §6).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/models`, where the API's INT-180
 * gate decides who sees anything. `?result=` is a code the benchmark form's
 * handler redirected back with; anything that is not one of its codes is
 * dropped.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { ModelsConsole } from "../../src/models/console";
import { benchmarkResultFrom, loadModels } from "../../src/models/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function ModelsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const state = await loadModels({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return (
    <ModelsConsole
      state={state}
      lang={langFrom(params["lang"])}
      result={benchmarkResultFrom(params["result"])}
    />
  );
}
