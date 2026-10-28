/**
 * INT-428 — the Model lanes module, rendered (files/08 §3; ADR-035): the
 * deployment's data class with a banner when hosted lanes are not part of it,
 * when it carries real patient data or when its classes disagree; each lane
 * and configured role with its configured route and model and what serves it
 * now; latency and cost per route and provider; each lane's model options;
 * the hosted providers and their keys; the ceremonies awaiting a second key;
 * and the controls. A synchronous, presentational tree over the loader's
 * state; the App Router page renders it on the server and the e2e spec
 * renders the very same tree. No `style` attribute anywhere.
 *
 * After a key-set request the page shows "staged · …last4" — the API's last
 * four, carried back in a one-shot HttpOnly cookie, never the key and never
 * the query string.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { RefusedPage } from "../ui/states";
import type { ResultCode, StagedKey } from "./actions";
import { StepUpBanner } from "../step-up/form";
import type { StepUpResult } from "../step-up/results";
import { ControlForms, PendingTile } from "./controls";
import { COPY, type Lang, type ModelLanesCopy } from "./copy";
import type { ModelLanesState } from "./load";
import { DeploymentTile, LanesTile, OptionsTiles, ProvidersTile, UsageTile } from "./tiles";

type C = ModelLanesCopy;

function Result({
  result,
  staged,
  c,
}: {
  result: ResultCode;
  staged: StagedKey | null;
  c: C;
}): ReactElement {
  return (
    <p className="result" data-result={result} role="status">
      {c.results[result]}
      {result === "staged" && staged !== null ? (
        <>
          {" "}
          <span data-staged={staged.provider}>
            {staged.provider} · {c.staged} · …<code>{staged.last4}</code>
          </span>
        </>
      ) : null}
    </p>
  );
}

export function ModelLanesConsole({
  state,
  lang,
  result,
  staged = null,
  stepUp = null,
}: {
  state: ModelLanesState;
  lang: Lang;
  result: ResultCode | null;
  stepUp?: StepUpResult | null;
  staged?: StagedKey | null;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="model-lanes" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="model-lanes" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="model-lanes">
      <header className="page-head">
        <ConsoleNav current="model-lanes" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time>
        </p>
        {result === null ? null : <Result result={result} staged={staged} c={c} />}
        <StepUpBanner result={stepUp} lang={lang} />
      </header>
      {view.banners.map((banner) => (
        <p key={banner} className="refusal" data-banner={banner} role="note">
          {c.banners[banner]}
        </p>
      ))}
      <section className="band" aria-labelledby="band-lanes">
        <h2 id="band-lanes" className="band-head">
          {c.tiles.lanes}
        </h2>
        <div className="grid">
          <DeploymentTile view={view} c={c} />
          <PendingTile view={view} lang={lang} c={c} />
          <LanesTile view={view} c={c} />
          <UsageTile view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-options">
        <h2 id="band-options" className="band-head">
          {c.tiles.options}
        </h2>
        <div className="grid">
          <OptionsTiles view={view} c={c} />
          <ProvidersTile view={view} c={c} />
        </div>
      </section>
      <ControlForms view={view} lang={lang} c={c} />
    </main>
  );
}
