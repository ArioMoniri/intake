/**
 * INT-564 — the Experience module, rendered (INT-186, INT-241; files/08 §3,
 * §4 F/G): the measurement window, CSAT, NPS and the clinician pulse, the
 * filters (each unavailable, and why), and the SDS-01 wait-time export.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * Below the k ≥ 10 floor a surface shows its count and says why nothing else
 * is shown. The window is a plain GET form on the page itself. No `style`.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type ExperienceCopy } from "./copy";
import type { DayWindow, ExperienceState } from "./load";
import type { CohortPresentation, DistributionBar, ExperiencePresentation } from "./module";

type C = ExperienceCopy;

function WindowTile({ window, lang, c }: { window: DayWindow; lang: Lang; c: C }): ReactElement {
  return (
    <form method="get" action="/experience" className="tile" data-tile="window">
      <header className="tile-head">
        <h2>{c.tiles.window}</h2>
      </header>
      {lang === "en" ? <input type="hidden" name="lang" value="en" /> : null}
      <label>
        {c.windowFrom} <input type="date" name="from" defaultValue={window.from} required />
      </label>
      <label>
        {c.windowTo} <input type="date" name="to" defaultValue={window.to} required />
      </label>
      <button type="submit">{c.windowApply}</button>
    </form>
  );
}

function Facts({
  n,
  cohort,
  extra,
  c,
}: {
  n: string;
  cohort: CohortPresentation;
  extra: Array<[string, string]>;
  c: C;
}): ReactElement {
  return (
    <dl className="facts">
      <dt>{c.window}</dt>
      <dd>
        <time>{cohort.windowStart}</time> – <time>{cohort.windowEnd}</time>
      </dd>
      <dt>{c.n}</dt>
      <dd>{n}</dd>
      {extra.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
      <dt>{c.measuredAt}</dt>
      <dd>
        <time>{cohort.measuredAt}</time>
      </dd>
    </dl>
  );
}

function Bars({
  bars,
  head,
  labels,
  c,
}: {
  bars: readonly DistributionBar[];
  head: string;
  labels?: Record<string, string>;
  c: C;
}): ReactElement {
  return (
    <ScrollTable>
      <thead>
        <tr>
          <th>{head}</th>
          <th>{c.count}</th>
        </tr>
      </thead>
      <Rows rows={bars} columns={2} kind="scores" empty={c.empties.scores}>
        {(bar) => (
          <tr key={bar.key}>
            <td>{labels?.[bar.key] ?? <code>{bar.key}</code>}</td>
            <td>{bar.count}</td>
          </tr>
        )}
      </Rows>
    </ScrollTable>
  );
}

function Surveys({ view, c }: { view: ExperiencePresentation; c: C }): ReactElement {
  const { csat, nps, pulse } = view;
  return (
    <>
      <Tile id="csat" title={c.tiles.csat} state="ok" reason={null} c={c}>
        <Facts
          n={csat.n}
          cohort={csat.cohort}
          extra={csat.meanScore === null ? [] : [[c.mean, csat.meanScore]]}
          c={c}
        />
        {csat.suppressed ? (
          <p className="window">{c.suppressed}</p>
        ) : (
          <>
            <Bars bars={csat.scores} head={c.score} c={c} />
            <Bars bars={csat.reasons} head={c.reason} c={c} />
          </>
        )}
      </Tile>
      <Tile id="nps" title={c.tiles.nps} state="ok" reason={null} c={c}>
        <Facts
          n={nps.n}
          cohort={nps.cohort}
          extra={nps.nps === null ? [] : [[c.nps, nps.nps]]}
          c={c}
        />
        {nps.suppressed ? (
          <p className="window">{c.suppressed}</p>
        ) : (
          <Bars
            bars={nps.cells.map((cell) => ({ key: cell.label, count: cell.value }))}
            head={c.score}
            labels={c.splitLabels}
            c={c}
          />
        )}
      </Tile>
      <Tile id="pulse" title={c.tiles.pulse} state="ok" reason={null} c={c}>
        <Facts
          n={pulse.n}
          cohort={pulse.cohort}
          extra={pulse.meanScore === null ? [] : [[c.mean, pulse.meanScore]]}
          c={c}
        />
        {pulse.suppressed ? (
          <p className="window">{c.suppressed}</p>
        ) : (
          <Bars bars={pulse.scores} head={c.score} c={c} />
        )}
      </Tile>
    </>
  );
}

function Filters({
  view,
  lang,
  c,
}: {
  view: ExperiencePresentation;
  lang: Lang;
  c: C;
}): ReactElement {
  return (
    <Tile id="filters" title={c.tiles.filters} state="ok" reason={null} c={c}>
      <p className="window">{c.filtersNote}</p>
      <ul className="inspector">
        {view.filters.dimensions.map((dimension) => (
          <li key={dimension.id} data-dimension={dimension.id} data-available={dimension.available}>
            {lang === "en" ? dimension.labelEn : dimension.labelTr} · {c.unavailableFilter}
          </li>
        ))}
      </ul>
    </Tile>
  );
}

function Sds01({ view, c }: { view: ExperiencePresentation; c: C }): ReactElement {
  const table = view.sds01Export;
  return (
    <Tile id="sds01" title={c.tiles.sds01} state="ok" reason={null} c={c} wide>
      <p className="window">{c.sds01Note}</p>
      <ScrollTable>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column}>
                <code>{column}</code>
              </th>
            ))}
          </tr>
        </thead>
        <Rows rows={table.rows} columns={table.columns.length} kind="sds01" empty={c.empties.sds01}>
          {(row) => (
            <tr key={row.join("|")}>
              {row.map((value, index) => (
                <td key={table.columns[index] ?? index}>{value}</td>
              ))}
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function ExperienceConsole({
  state,
  lang,
}: {
  state: ExperienceState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="experience" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="experience" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="experience">
      <header className="page-head">
        <ConsoleNav current="experience" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.window}: <time>{state.window.from}</time> – <time>{state.window.to}</time>
        </p>
      </header>
      <section className="band" aria-labelledby="band-surveys">
        <h2 id="band-surveys" className="band-head">
          {c.tiles.csat}
        </h2>
        <div className="grid">
          <WindowTile window={state.window} lang={lang} c={c} />
          <Surveys view={view} c={c} />
          <Filters view={view} lang={lang} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-waits">
        <h2 id="band-waits" className="band-head">
          {c.tiles.sds01}
        </h2>
        <div className="grid">
          <Sds01 view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
