/**
 * INT-182 — the Voice module, rendered (files/08 §3 "Voice runtime"): per-profile
 * metrics, each tenant's kill switch / default profile / canary, the requests
 * awaiting a second key, and the four controls. A synchronous, presentational
 * tree over the loader's state; the App Router page renders it on the server
 * and the e2e spec renders the very same tree.
 *
 * Built from the ops console's primitives (`../ops/tiles`), so every tile
 * carries `data-tile` / `data-tile-state` and an unknown tile shows the word,
 * its reason and no figure (invariant 17). No `style` attribute anywhere — the
 * CSP has no `unsafe-inline`.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { Cell, ScrollTable, Tile } from "../ops/tiles";
import type { ResultCode } from "./actions";
import { ControlForms, ControlsTile, PendingTile } from "./controls";
import { COPY, type Lang, type VoiceCopy } from "./copy";
import type { VoiceState } from "./load";
import type { VoiceView } from "./module";

type C = VoiceCopy;

function Window({ value, c }: { value: string; c: C }): ReactElement {
  return <p className="window">{c.windows[value] ?? value}</p>;
}

function Sessions({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.sessions;
  return (
    <Tile
      id="sessions"
      title={c.tiles.sessions}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={<Window value={t.window} c={c} />}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.profile}</th>
            <th>{c.cols.reason}</th>
            <th>{c.cols.sessions}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={`${row.profile}:${row.reason}`} data-profile={row.profile}>
              <td>
                <code>{row.profile}</code>
              </td>
              <td>{c.routeReasons[row.reason] ?? row.reason}</td>
              <td>
                <Cell value={row.sessions} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function KillSwitchActivity({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.killSwitchActivity;
  return (
    <Tile
      id="kill_switch_activity"
      title={c.tiles.killSwitch}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={<Window value={t.window} c={c} />}
    >
      <dl className="facts">
        <dt>{c.cols.inflight}</dt>
        {t.inflight.map((row) => (
          <dd key={row.outcome}>
            {c.flipOutcomes[row.outcome] ?? row.outcome}: <Cell value={row.count} c={c} />
          </dd>
        ))}
        <dt>{c.cols.readFailures}</dt>
        {t.readFailures.map((row) => (
          <dd key={row.phase}>
            {c.readPhases[row.phase] ?? row.phase}: <Cell value={row.count} c={c} />
          </dd>
        ))}
      </dl>
    </Tile>
  );
}

function TurnLatency({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.turnLatency;
  const meta = (
    <p className="window">
      {c.cols.metric} <code>{t.metricId}</code> · {c.windows[t.window] ?? t.window}
    </p>
  );
  return (
    <Tile
      id="turn_latency"
      title={c.tiles.latency}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.profile}</th>
            <th>{c.cols.p50}</th>
            <th>{c.cols.p95}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={row.profile} data-profile={row.profile}>
              <td>
                <code>{row.profile}</code>
              </td>
              <td>
                <Cell value={row.p50} c={c} />
              </td>
              <td>
                <Cell value={row.p95} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function SpeechErrors({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.speechErrors;
  return (
    <Tile
      id="speech_errors"
      title={c.tiles.speech}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={<Window value={t.window} c={c} />}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.component}</th>
            <th>{c.cols.kind}</th>
            <th>{c.cols.calls}</th>
            <th>{c.cols.failures}</th>
            <th>{c.cols.errorRatio}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={`${row.component}:${row.kind}`}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>{row.kind}</td>
              <td>{row.calls}</td>
              <td>{row.failures}</td>
              <td>
                <Cell value={row.errorRatio} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Failovers({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.failovers;
  return (
    <Tile
      id="failovers"
      title={c.tiles.failovers}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={<Window value={t.window} c={c} />}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.from}</th>
            <th>{c.cols.to}</th>
            <th>{c.cols.count}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={`${row.from}>${row.to}`}>
              <td>
                <code>{row.from}</code>
              </td>
              <td>
                <code>{row.to}</code>
              </td>
              <td>
                <Cell value={row.count} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Breakers({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.breakers;
  return (
    <Tile id="breakers" title={c.tiles.breakers} state={t.state} reason={t.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.component}</th>
            <th>{c.cols.state}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={row.component} data-breaker={row.state ?? "unknown"}>
              <td>
                <code>{row.component}</code>
              </td>
              <td>
                {row.state === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  (c.breakerStates[row.state] ?? row.state)
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Refused({
  lang,
  c,
  children,
}: {
  lang: Lang;
  c: C;
  children: ReactElement;
}): ReactElement {
  return (
    <main lang={lang} className="ops" data-page="voice">
      <h1>{c.title}</h1>
      {children}
    </main>
  );
}

export function VoiceConsole({
  state,
  lang,
  result,
}: {
  state: VoiceState;
  lang: Lang;
  result: ResultCode | null;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <Refused lang={lang} c={c}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </Refused>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <Refused lang={lang} c={c}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </Refused>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="voice">
      <header className="page-head">
        <ConsoleNav current="voice" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time> · {c.sources}: prometheus{" "}
          <code>{view.sources.prometheus}</code> · controls <code>{view.sources.controls}</code>
        </p>
        {result === null ? null : (
          <p className="result" data-result={result} role="status">
            {c.results[result]}
          </p>
        )}
      </header>
      <section className="band" aria-labelledby="band-tenants">
        <h2 id="band-tenants" className="band-head">
          {c.tiles.controls}
        </h2>
        <div className="grid">
          <ControlsTile view={view} c={c} />
          <PendingTile view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-profiles">
        <h2 id="band-profiles" className="band-head">
          {c.tiles.sessions}
        </h2>
        <div className="grid">
          <Sessions view={view} c={c} />
          <TurnLatency view={view} c={c} />
          <SpeechErrors view={view} c={c} />
          <Failovers view={view} c={c} />
          <Breakers view={view} c={c} />
          <KillSwitchActivity view={view} c={c} />
        </div>
      </section>
      <ControlForms view={view} lang={lang} c={c} />
    </main>
  );
}
