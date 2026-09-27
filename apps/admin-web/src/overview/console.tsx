/**
 * INT-181 — the overview, rendered: SLO tiles with burn rates, the synthetic
 * probe matrix and dependency health (files/08 §3 Overview, Reliability). A
 * synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 *
 * Built from the ops console's primitives (`../ops/tiles`), so every tile
 * carries `data-tile` / `data-tile-state` and an unknown tile shows the word,
 * its reason and no figure (invariant 17). No `style` attribute anywhere — the
 * CSP has no `unsafe-inline`.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { Cell, ScrollTable, Tile } from "../ops/tiles";
import { COPY, type Lang, type OverviewCopy } from "./copy";
import type { OverviewState } from "./load";
import type { Age, OverviewView, SloView } from "./module";

type C = OverviewCopy;

function ageText(value: Age | null, c: C): string | null {
  return value === null ? null : `${value.value} ${c.units[value.unit]}`;
}

function Health({ value, c }: { value: string | null; c: C }): ReactElement {
  if (value === null) return <span className="cell-unknown">{c.unknown}</span>;
  return <span data-state={value}>{c.health[value] ?? value}</span>;
}

function SloTile({ t, c }: { t: SloView; c: C }): ReactElement {
  const meta = (
    <p className="window">
      {c.slo.objective} {t.objective} · {c.slo.window} <code>{t.window}</code>
    </p>
  );
  return (
    <Tile
      id={`slo:${t.key}`}
      title={`${t.service} · ${t.slo}`}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <dl className="facts">
        <dt>{c.slo.sli}</dt>
        <dd>
          <Cell value={t.sli} c={c} />
        </dd>
        <dt>{c.slo.budget}</dt>
        <dd data-overspent={t.budgetOverspent === true ? "true" : "false"}>
          <Cell value={t.budgetRemaining} c={c} />
          {t.budgetOverspent === true ? <> · {c.slo.overspent}</> : null}
        </dd>
      </dl>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.slo.lane}</th>
            <th>{c.slo.factor}</th>
            <th>{c.slo.long}</th>
            <th>{c.slo.short}</th>
            <th>{c.slo.condition}</th>
            <th>{c.slo.severity}</th>
          </tr>
        </thead>
        <tbody>
          {t.lanes.map((lane) => {
            const condition =
              lane.conditionMet === null ? "unknown" : lane.conditionMet ? "met" : "not_met";
            return (
              <tr key={lane.lane} data-lane={lane.lane}>
                <td>{c.slo.lanes[lane.lane] ?? lane.lane}</td>
                <td>{lane.factor}</td>
                <td>
                  <code>{lane.longWindow}</code> <Cell value={lane.longBurn} c={c} />
                </td>
                <td>
                  <code>{lane.shortWindow}</code> <Cell value={lane.shortBurn} c={c} />
                </td>
                <td data-condition={condition}>
                  {condition === "unknown" ? (
                    <span className="cell-unknown">{c.unknown}</span>
                  ) : condition === "met" ? (
                    c.slo.met
                  ) : (
                    c.slo.notMet
                  )}
                </td>
                <td>{lane.severity}</td>
              </tr>
            );
          })}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Slos({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.slos;
  return (
    <section className="band" aria-labelledby="band-slos">
      <h2 id="band-slos" className="band-head">
        {c.slo.section}
      </h2>
      <p className="window">{c.slo.policy}</p>
      <div className="grid">
        {s.state === "unknown" ? (
          <Tile id="slos" title={c.slo.section} state="unknown" reason={s.reason} c={c} />
        ) : (
          s.tiles.map((t) => <SloTile key={t.key} t={t} c={c} />)
        )}
      </div>
    </section>
  );
}

function ProbeMatrix({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const m = view.probeMatrix;
  const meta = (
    <p className="window">
      {c.probes.every} {ageText(m.sweepInterval, c) ?? c.unknown} · {c.probes.staleAfter}{" "}
      {ageText(m.staleAfter, c) ?? c.unknown}
    </p>
  );
  return (
    <Tile
      id="probe_matrix"
      title={c.probes.title}
      state={m.state}
      reason={m.reason}
      c={c}
      meta={meta}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.probes.component}</th>
            <th>{c.probes.probe}</th>
            <th>{c.probes.status}</th>
            <th>{c.probes.latency}</th>
            <th>{c.probes.budget}</th>
            <th>{c.probes.checkedAt}</th>
            <th>{c.probes.age}</th>
          </tr>
        </thead>
        <tbody>
          {m.rows.map((row) => (
            <tr key={row.component} data-stale={row.stale ? "true" : "false"}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>
                <code>{row.probe}</code>
              </td>
              <td>
                <Health value={row.status} c={c} />
                {row.stale ? <span className="stale"> · {c.probes.stale}</span> : null}
              </td>
              <td>
                <Cell value={row.latency} c={c} />
              </td>
              <td>{row.budget}</td>
              <td>
                {row.checkedAt === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  <time>{row.checkedAt}</time>
                )}
              </td>
              <td>
                <Cell value={ageText(row.age, c)} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Components({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.dependencies.components;
  return (
    <Tile id="dep_components" title={c.deps.components} state={s.state} reason={s.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.deps.component}</th>
            <th>{c.deps.health}</th>
            <th>{c.deps.fallback}</th>
            <th>{c.deps.fallbackHealth}</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((row) => (
            <tr key={row.component}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>
                <Health value={row.health} c={c} />
                {row.healthReason ? (
                  <>
                    {" "}
                    <code>{row.healthReason}</code>
                  </>
                ) : null}
              </td>
              <td>
                {row.fallbackKind === "component" ? (
                  <code>{row.fallback}</code>
                ) : row.fallbackKind === "in_process" ? (
                  c.deps.inProcess
                ) : (
                  c.deps.none
                )}
              </td>
              <td>
                {row.fallbackKind === "none" ? "—" : <Health value={row.fallbackHealth} c={c} />}
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Prometheus({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.dependencies.prometheus;
  return (
    <Tile id="dep_prometheus" title={c.deps.prometheus} state={s.state} reason={s.reason} c={c}>
      <dl className="facts">
        <dt>{c.deps.prometheusHealth}</dt>
        <dd>
          <Health value={s.health} c={c} />
          {s.healthReason ? (
            <>
              {" "}
              <code>{s.healthReason}</code>
            </>
          ) : null}
        </dd>
      </dl>
    </Tile>
  );
}

function GpuHosts({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.dependencies.gpuHosts;
  return (
    <Tile id="dep_gpu_hosts" title={c.deps.gpuHosts} state={s.state} reason={s.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.deps.host}</th>
            <th>{c.deps.health}</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((row) => (
            <tr key={row.hostId}>
              <td>
                <code>{row.hostId}</code>
              </td>
              <td>
                <Health value={row.health} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Vendors({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.dependencies.vendors;
  return (
    <Tile id="dep_vendors" title={c.deps.vendors} state={s.state} reason={s.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.deps.vendor}</th>
            <th>{c.deps.breaker}</th>
            <th>{c.deps.health}</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((row) => (
            <tr key={row.component}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>
                {row.breaker === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  (c.deps.breakers[row.breaker] ?? row.breaker)
                )}
              </td>
              <td>
                <Health value={row.health} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function ApiReadiness({ view, c }: { view: OverviewView; c: C }): ReactElement {
  const s = view.dependencies.apiReadiness;
  return (
    <Tile
      id="dep_api_readiness"
      title={c.deps.apiReadiness}
      state={s.state}
      reason={s.reason}
      c={c}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.deps.check}</th>
            <th>{c.deps.health}</th>
          </tr>
        </thead>
        <tbody>
          {s.checks.map((row) => (
            <tr key={row.check}>
              <td>
                <code>{row.check}</code>
              </td>
              <td>
                <Health value={row.health} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

export function OverviewConsole({
  state,
  lang,
}: {
  state: OverviewState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <main lang={lang} className="ops" data-page="overview">
        <h1>{c.title}</h1>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </main>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <main lang={lang} className="ops" data-page="overview">
        <h1>{c.title}</h1>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </main>
    );
  }
  const view = state.view;
  const s = view.sources;
  return (
    <main lang={lang} className="ops" data-page="overview">
      <header className="page-head">
        <ConsoleNav current="overview" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time> · {c.sources}: prometheus{" "}
          <code>{s.prometheus}</code> · slo <code>{s.sloFiles}</code> · registry{" "}
          <code>{s.registry}</code> · sweep <code>{s.probeSweep}</code>
        </p>
      </header>
      <Slos view={view} c={c} />
      <section className="band" aria-labelledby="band-probes">
        <h2 id="band-probes" className="band-head">
          {c.probes.section}
        </h2>
        <div className="grid">
          <ProbeMatrix view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-deps">
        <h2 id="band-deps" className="band-head">
          {c.deps.section}
        </h2>
        <div className="grid">
          <Components view={view} c={c} />
          <ApiReadiness view={view} c={c} />
          <Prometheus view={view} c={c} />
          <GpuHosts view={view} c={c} />
          <Vendors view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
