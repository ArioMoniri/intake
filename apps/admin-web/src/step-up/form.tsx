/**
 * INT-563 (ADR-043) — the **Onayla** form every pending row carries, the banner
 * a page shows when a step-up comes back, and the `/step-up` page for an
 * action no module page lists (break-glass, the access-review countersign).
 *
 * Plain HTML: the form posts to this app's own `/step-up/start` with the
 * pending action's id and the page it came from — nothing else, and no
 * script (the CSP has no `unsafe-inline`). The banner shows a code's
 * sentence, never a submitted value.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { ACTION_ID, type Page } from "./approvals";
import { COPY } from "./copy";
import type { StepUpResult } from "./results";

export function ApproveForm({
  actionId,
  from,
  lang,
  label,
}: {
  actionId: string;
  from: Page;
  lang: Lang;
  label?: string;
}): ReactElement {
  return (
    <form method="post" action="/step-up/start" className="inline-form" data-step-up={actionId}>
      <input type="hidden" name="action_id" value={actionId} />
      <input type="hidden" name="from" value={from} />
      {lang === "en" ? <input type="hidden" name="lang" value="en" /> : null}
      <button type="submit">{label ?? COPY[lang].approve}</button>
    </form>
  );
}

export function StepUpBanner({
  result,
  lang,
}: {
  result: StepUpResult | null;
  lang: Lang;
}): ReactElement | null {
  if (result === null) return null;
  return (
    <p className="result" data-step-up-result={result} role="status">
      {COPY[lang].results[result]}
    </p>
  );
}

/** `/step-up?action_id=<id>`: one action, one button. */
export function StepUpPage({
  actionId,
  result,
  lang,
}: {
  actionId: string | null;
  result: StepUpResult | null;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  const id = actionId !== null && ACTION_ID.test(actionId) ? actionId : null;
  return (
    <main lang={lang} className="ops" data-page="step-up">
      <header className="page-head">
        <ConsoleNav current="access" lang={lang} />
        <h1>{c.title}</h1>
        <StepUpBanner result={result} lang={lang} />
      </header>
      <section className="tile" aria-labelledby="step-up-action">
        <header className="tile-head">
          <h2 id="step-up-action">{c.actionId}</h2>
        </header>
        {id === null ? (
          <p className="window" data-step-up-empty="">
            {c.noAction}
          </p>
        ) : (
          <>
            <p className="window">{c.explain}</p>
            <p>
              <code>{id}</code>
            </p>
            <ApproveForm actionId={id} from="step-up" lang={lang} />
          </>
        )}
      </section>
    </main>
  );
}
