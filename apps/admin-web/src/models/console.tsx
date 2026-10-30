/**
 * INT-564 — the Models & self-hosting registry, rendered (INT-183, files/08
 * §6): the release gate first ("the console renders this as the first tile"),
 * then every registry row in registry order with its licence, probe, budget,
 * fallback, findings and the two benchmark lanes.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * A lane the API enables is a plain form posting to `/models/action`; a lane
 * it disables is a disabled button that says why. No `style` attribute.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { BENCHMARK_KINDS, type BenchmarkResult } from "./actions";
import { COPY, type ModelsCopy } from "./copy";
import type { ModelsState } from "./load";
import type { ModelsPresentation, RowPresentation } from "./module";

type C = ModelsCopy;

function cell(row: RowPresentation, label: string): string {
  return row.cells.find((item) => item.label === label)?.value ?? "";
}

function yesNo(value: string, c: C): string {
  return value === "yes" ? c.yes : value === "no" ? c.no : value;
}

function Release({ view, c }: { view: ModelsPresentation; c: C }): ReactElement {
  const tile = view.releaseTile;
  return (
    <article
      data-tile="release"
      data-release-blocked={tile.blocked}
      className="tile tile-ok tile-wide"
      aria-labelledby="tile-release"
    >
      <header className="tile-head">
        <h2 id="tile-release">{c.tiles.release}</h2>
      </header>
      <p className={tile.blocked ? "refusal" : "window"}>{tile.blocked ? c.blocked : c.clear}</p>
      {tile.reasons.length === 0 ? null : (
        <ul className="inspector">
          {tile.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <p className="window" data-probe-results={view.probeResults.state}>
        {view.probeResults.state === "ok" ? c.sweepOk : c.sweepUnknown}
        {view.probeResults.reason === null ? null : (
          <>
            {" "}
            <code>{view.probeResults.reason}</code>
          </>
        )}
      </p>
    </article>
  );
}

function Lane({
  row,
  kind,
  lang,
  c,
}: {
  row: RowPresentation;
  kind: (typeof BENCHMARK_KINDS)[number];
  lang: Lang;
  c: C;
}): ReactElement {
  const lane = row.benchmark.lanes[kind];
  if (!lane.enabled) {
    return (
      <button type="button" disabled data-lane={kind} title={lane.disabledReason ?? undefined}>
        {c.lanes[kind]}
      </button>
    );
  }
  return (
    <form method="post" action="/models/action" className="inline-form" data-lane={kind}>
      <input type="hidden" name="component" value={row.component} />
      <input type="hidden" name="kind" value={kind} />
      {lang === "en" ? <input type="hidden" name="lang" value="en" /> : null}
      <button type="submit">{c.lanes[kind]}</button>
    </form>
  );
}

function Registry({ view, lang, c }: { view: ModelsPresentation; lang: Lang; c: C }): ReactElement {
  return (
    <Tile id="registry" title={c.tiles.registry} state="ok" reason={null} c={c} wide>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.component}</th>
            <th>{c.cols.severity}</th>
            <th>{c.cols.phiPath}</th>
            <th>{c.cols.selfHosted}</th>
            <th>{c.cols.licence}</th>
            <th>{c.cols.probe}</th>
            <th>{c.cols.budget}</th>
            <th>{c.cols.fallback}</th>
            <th>{c.cols.findings}</th>
            <th>{c.cols.benchmark}</th>
          </tr>
        </thead>
        <Rows rows={view.rows} columns={10} kind="registry" empty={c.empties.registry}>
          {(row) => (
            <tr key={row.component} data-component={row.component} data-severity={row.severity}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>{c.severity[row.severity]}</td>
              <td>{yesNo(cell(row, "PHI path"), c)}</td>
              <td>{yesNo(cell(row, "self-hosted now"), c)}</td>
              <td>{cell(row, "licence")}</td>
              <td>
                <code>{cell(row, "probe")}</code>
              </td>
              <td>{cell(row, "budget")}</td>
              <td>
                <code>{cell(row, "fallback")}</code>
              </td>
              <td>
                {row.findings.length === 0 ? (
                  c.none
                ) : (
                  <ul className="inspector">
                    {row.findings.map((finding) => (
                      <li key={finding}>{finding}</li>
                    ))}
                  </ul>
                )}
                {row.measurements.map((measurement) => (
                  <p key={measurement} className="window">
                    {measurement}
                  </p>
                ))}
              </td>
              <td>
                {BENCHMARK_KINDS.map((kind) => (
                  <Lane key={kind} row={row} kind={kind} lang={lang} c={c} />
                ))}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function ModelsConsole({
  state,
  lang,
  result,
}: {
  state: ModelsState;
  lang: Lang;
  result: BenchmarkResult | null;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="models" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="models" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="models">
      <header className="page-head">
        <ConsoleNav current="models" lang={lang} />
        <h1>{c.title}</h1>
        {result === null ? null : (
          <p className="result" data-result={result} role="status">
            {c.results[result]}
          </p>
        )}
      </header>
      <section className="band" aria-labelledby="band-release">
        <h2 id="band-release" className="band-head">
          {c.tiles.release}
        </h2>
        <div className="grid">
          <Release view={view} c={c} />
          <Registry view={view} lang={lang} c={c} />
        </div>
      </section>
    </main>
  );
}
