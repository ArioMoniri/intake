/**
 * INT-565 — the Cost module, rendered (INT-190; files/08 §3 "Cost", §4 J):
 * the price file and its components, cost per session by component and
 * profile for each window, and the budgets with their alerts.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * The view-model's figures are money and quantity atoms (invariant 22); its
 * sentinel words ("price not configured", "unknown") are re-worded here in the
 * page's language, and a figure is never invented for one. No `style`.
 */
import { Fragment, type ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type CostCopy } from "./copy";
import type { CostState } from "./load";
import {
  BUDGET_NOT_CONFIGURED,
  PRICE_NOT_CONFIGURED,
  VENDOR_NOT_CONFIGURED,
  type CostPresentation,
  type WindowPresentation,
} from "./module";

type C = CostCopy;

function vendor(value: string, c: C): ReactElement {
  return value === VENDOR_NOT_CONFIGURED ? (
    <span className="suppressed">{c.vendorNotConfigured}</span>
  ) : (
    <code>{value}</code>
  );
}

/** A money atom, or the page's word for why there is none. */
function money(value: string, hasFigure: boolean, c: C): ReactElement {
  if (hasFigure) return <>{value}</>;
  const word = value === PRICE_NOT_CONFIGURED ? c.priceNotConfigured : c.unknown;
  return <span className="suppressed">{word}</span>;
}

function Config({ view, c }: { view: CostPresentation; c: C }): ReactElement {
  return (
    <Tile id="config" title={c.tiles.config} state="ok" reason={null} c={c}>
      <dl className="facts">
        <dt>{c.path}</dt>
        <dd>
          <code>{view.config.path}</code>
        </dd>
        <dt>{c.digest}</dt>
        <dd>
          <code>{view.config.sha256_prefix}</code>
        </dd>
        <dt>{c.blocker}</dt>
        <dd>
          <code>{view.config.blocker}</code>
        </dd>
        <dt>{c.currency}</dt>
        <dd>{view.currency}</dd>
        <dt>{c.usageSource}</dt>
        <dd data-source-configured={view.source.configured}>
          {view.source.configured ? c.yes : c.no}
        </dd>
      </dl>
      <p className="window">{c.configNote}</p>
    </Tile>
  );
}

function Components({ view, c }: { view: CostPresentation; c: C }): ReactElement {
  return (
    <Tile id="components" title={c.tiles.components} state="ok" reason={null} c={c} wide>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.component}</th>
            <th>{c.vendor}</th>
            <th>{c.unit}</th>
            <th>{c.attribution}</th>
            <th>{c.price}</th>
          </tr>
        </thead>
        <Rows rows={view.components} columns={5} kind="components" empty={c.empties.components}>
          {(row) => (
            <tr key={row.component} data-component={row.component}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>{vendor(row.vendor, c)}</td>
              <td lang="en">{row.unit}</td>
              <td>
                <code>{row.attribution}</code>
              </td>
              <td lang={row.priceConfigured ? "en" : undefined}>
                {money(row.price, row.priceConfigured, c)}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Window({ window, c }: { window: WindowPresentation; c: C }): ReactElement {
  return (
    <Tile
      id={`window_${window.period}`}
      title={c.tiles.window[window.period] ?? window.period}
      state="ok"
      reason={null}
      c={c}
      wide
      meta={<span className="sub">{window.window}</span>}
    >
      <dl className="facts">
        {window.sessions.byProfile.map((row) => (
          <Fragment key={row.profile}>
            <dt>
              {c.sessions} · <code>{row.profile}</code>
            </dt>
            <dd>{row.count ?? <span className="cell-unknown">{c.unknown}</span>}</dd>
          </Fragment>
        ))}
      </dl>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.component}</th>
            <th>{c.profile}</th>
            <th>{c.quantity}</th>
            <th>{c.cost}</th>
          </tr>
        </thead>
        <Rows rows={window.perSession} columns={4} kind="per_session" empty={c.empties.perSession}>
          {(row) => (
            <tr key={`${row.component}:${row.profile}`} data-component={row.component}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>
                <code>{row.profile}</code>
              </td>
              <td>{row.quantity ?? <span className="cell-unknown">{c.unknown}</span>}</td>
              <td>{money(row.cost, row.hasFigure, c)}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.total}</th>
            <th>{c.cost}</th>
          </tr>
        </thead>
        <Rows rows={window.byProfile} columns={2} kind="totals" empty={c.empties.totals}>
          {(total) => (
            <tr key={total.profile} data-total={total.profile}>
              <td>
                <code>{total.profile}</code>
              </td>
              <td>
                {total.complete ? (
                  total.cost
                ) : (
                  <span className="suppressed">
                    {c.withheld}:{" "}
                    {total.missing.map((part) => (
                      <code key={part}>{part} </code>
                    ))}
                  </span>
                )}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Budgets({ view, c }: { view: CostPresentation; c: C }): ReactElement {
  return (
    <Tile id="budgets" title={c.tiles.budgets} state="ok" reason={null} c={c} wide>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.budget}</th>
            <th>{c.scope}</th>
            <th>{c.period}</th>
            <th>{c.limit}</th>
            <th>{c.spend}</th>
            <th>{c.status}</th>
          </tr>
        </thead>
        <Rows rows={view.budgets} columns={6} kind="budgets" empty={c.empties.budgets}>
          {(budget) => (
            <tr key={budget.budgetId} data-budget={budget.budgetId} data-status={budget.status}>
              <td>
                <code>{budget.budgetId}</code>
              </td>
              <td>{budget.scope === "all vendors" ? c.allVendors : <code>{budget.scope}</code>}</td>
              <td>
                <code>{budget.period}</code>
              </td>
              <td>
                {budget.limit === BUDGET_NOT_CONFIGURED ? (
                  <span className="suppressed">{c.budgetNotConfigured}</span>
                ) : (
                  <span lang="en">{budget.limit}</span>
                )}
              </td>
              <td>
                {budget.spend === "unknown" ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  <span lang="en">{budget.spend}</span>
                )}
              </td>
              <td>{c.statuses[budget.status] ?? budget.status}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function CostConsole({ state, lang }: { state: CostState; lang: Lang }): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="cost" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="cost" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="cost">
      <header className="page-head">
        <ConsoleNav current="cost" lang={lang} />
        <h1>{c.title}</h1>
      </header>
      <section className="band" aria-labelledby="band-prices">
        <h2 id="band-prices" className="band-head">
          {c.bands.prices}
        </h2>
        <div className="grid">
          <Config view={view} c={c} />
          <Components view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-sessions">
        <h2 id="band-sessions" className="band-head">
          {c.bands.sessions}
        </h2>
        <div className="grid">
          {view.windows.map((window) => (
            <Window key={window.period} window={window} c={c} />
          ))}
        </div>
      </section>
      <section className="band" aria-labelledby="band-budgets">
        <h2 id="band-budgets" className="band-head">
          {c.bands.budgets}
        </h2>
        <div className="grid">
          <Budgets view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
