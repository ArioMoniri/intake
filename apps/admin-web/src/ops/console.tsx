/**
 * INT-351 — the ops console, rendered. A synchronous, presentational tree over
 * the loader's state: the App Router page renders it on the server, and the
 * e2e spec renders the very same tree to static markup.
 *
 * No `style` attributes anywhere — the CSP has no `unsafe-inline`, so styling
 * is the bundled stylesheet only. Every tile carries `data-tile` and
 * `data-tile-state`; an unknown tile says so in words with its reason code
 * beside it, and carries no figure (invariant 17).
 */
import type { ReactElement, ReactNode } from "react";

import { COPY, type Copy, type Lang } from "./copy";
import type { OpsConsoleState } from "./load";
import type { OpsView, TileState } from "./module";

interface TileProps {
  id: string;
  title: string;
  state: TileState;
  reason: string | null;
  c: Copy;
  meta?: ReactNode;
  children?: ReactNode;
}

function Tile({ id, title, state, reason, c, meta, children }: TileProps): ReactElement {
  return (
    <section
      data-tile={id}
      data-tile-state={state}
      className={`tile tile-${state}`}
      aria-labelledby={`tile-${id}`}
    >
      <header className="tile-head">
        <h2 id={`tile-${id}`}>{title}</h2>
        {meta}
      </header>
      {state === "unknown" ? (
        <p className="unknown" data-reason={reason ?? ""}>
          <strong>{c.unknown}</strong> · {c.reasons[reason ?? ""] ?? reason} <code>{reason}</code>
        </p>
      ) : (
        children
      )}
    </section>
  );
}

function ScrollTable({ children }: { children: ReactNode }): ReactElement {
  return (
    <div className="scroll">
      <table>{children}</table>
    </div>
  );
}

function Cell({ value, c }: { value: string | null; c: Copy }): ReactElement {
  return value === null ? <span className="cell-unknown">{c.unknown}</span> : <>{value}</>;
}

function windowLabel(c: Copy, window: string): string {
  return (c.windows as Record<string, string>)[window] ?? window;
}

function Health({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const h = view.health;
  const known = h.alive !== "unknown" || h.ready !== "unknown" || h.gitSha !== "unknown";
  return (
    <Tile
      id="api_health"
      title={c.health.title}
      state={known ? "ok" : "unknown"}
      reason={known ? null : "api_unreachable"}
      c={c}
    >
      <dl className="facts">
        <dt>{c.health.alive}</dt>
        <dd data-state={h.alive}>{c.health.states[h.alive]}</dd>
        <dt>{c.health.ready}</dt>
        <dd data-state={h.ready}>{c.health.states[h.ready]}</dd>
        {h.failingChecks.length > 0 ? (
          <>
            <dt>{c.health.failing}</dt>
            <dd>{h.failingChecks.join(", ")}</dd>
          </>
        ) : null}
        <dt>{c.health.version}</dt>
        <dd>
          <code>{h.gitSha === "unknown" ? c.unknown : h.gitSha.slice(0, 12)}</code>
        </dd>
        <dt>{c.health.builtAt}</dt>
        <dd>{h.builtAt === "unknown" ? c.unknown : <time>{h.builtAt}</time>}</dd>
      </dl>
    </Tile>
  );
}

function Models({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.models;
  const meta =
    t.releaseBlocked === null ? null : (
      <p className="badge" data-state={t.releaseBlocked ? "blocked" : "open"}>
        {c.models.release}: {t.releaseBlocked ? c.models.blocked : c.models.open}
      </p>
    );
  return (
    <Tile id="models" title={c.models.title} state={t.state} reason={t.reason} c={c} meta={meta}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.models.component}</th>
            <th>{c.models.selfHostable}</th>
            <th>{c.models.selfHostedNow}</th>
            <th>{c.models.probe}</th>
            <th>{c.models.probeStatus}</th>
            <th>{c.models.licence}</th>
            <th>{c.models.severity}</th>
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row) => (
            <tr key={row.component} data-severity={row.severity}>
              <td>
                <code>{row.component}</code>
                {row.pin ? <div className="sub">{row.pin}</div> : null}
              </td>
              <td>{row.selfHostable ? c.yes : c.no}</td>
              <td>{row.selfHostedNow ? c.yes : c.no}</td>
              <td>
                <code>{row.probe}</code>
              </td>
              <td data-state={row.probeStatus}>{row.probeStatus}</td>
              <td>{row.licenceVerifiedAt ?? c.none}</td>
              <td data-state={row.severity}>{row.severity}</td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Gpu({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.gpu;
  return (
    <Tile id="gpu" title={c.gpu.title} state={t.state} reason={t.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.gpu.host}</th>
            <th>{c.gpu.index}</th>
            <th>{c.gpu.utilization}</th>
            <th>{c.gpu.memory}</th>
          </tr>
        </thead>
        <tbody>
          {t.hosts.map((host) =>
            host.up && host.gpus.length > 0 ? (
              host.gpus.map((g) => (
                <tr key={`${host.hostId}-${g.index}`}>
                  <td>
                    <code>{host.hostId}</code> <span data-state="up">{c.gpu.up}</span>
                  </td>
                  <td>{g.index}</td>
                  <td>
                    <Cell value={g.utilization} c={c} />
                  </td>
                  <td>
                    <Cell value={g.memoryUsed} c={c} /> / <Cell value={g.memoryTotal} c={c} />
                  </td>
                </tr>
              ))
            ) : (
              <tr key={host.hostId}>
                <td>
                  <code>{host.hostId}</code>{" "}
                  <span data-state={host.up ? "up" : "down"}>
                    {host.up ? c.gpu.up : c.gpu.down}
                  </span>
                </td>
                <td colSpan={3}>
                  <span className="cell-unknown">{c.unknown}</span>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Usage({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.modelUsage;
  const meta = <p className="window">{windowLabel(c, t.window)}</p>;
  return (
    <Tile
      id="model_usage"
      title={c.usage.title}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.usage.lane}</th>
            <th>{c.usage.kind}</th>
            <th>{c.usage.requests}</th>
            <th>{c.usage.p95}</th>
            <th>{c.usage.failures}</th>
          </tr>
        </thead>
        <tbody>
          {t.lanes.map((lane) => (
            <tr key={`${lane.kind}-${lane.lane}`}>
              <td>
                <code>{lane.lane}</code>
              </td>
              <td>{lane.kind}</td>
              <td>
                <Cell value={lane.requests} c={c} />
              </td>
              <td>
                <Cell value={lane.p95} c={c} />
              </td>
              <td>
                <Cell value={lane.failures} c={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Clips({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.clipCache;
  const meta = <p className="window">{windowLabel(c, t.window)}</p>;
  return (
    <Tile id="clip_cache" title={c.clips.title} state={t.state} reason={t.reason} c={c} meta={meta}>
      <dl className="facts">
        <dt>{c.clips.hit}</dt>
        <dd>
          <Cell value={t.hit} c={c} />
        </dd>
        <dt>{c.clips.miss}</dt>
        <dd>
          <Cell value={t.miss} c={c} />
        </dd>
        <dt>{c.clips.hitRatio}</dt>
        <dd>
          <Cell value={t.hitRatio} c={c} />
        </dd>
      </dl>
      {t.syntheses.length > 0 ? (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.clips.gateway}</th>
              <th>{c.clips.outcome}</th>
              <th>{c.clips.syntheses}</th>
            </tr>
          </thead>
          <tbody>
            {t.syntheses.map((s) => (
              <tr key={`${s.gateway}-${s.outcome}`}>
                <td>
                  <code>{s.gateway}</code>
                </td>
                <td>{s.outcome}</td>
                <td>
                  <Cell value={s.count} c={c} />
                </td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      ) : null}
      {t.manifests.length > 0 ? (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.clips.pack}</th>
              <th>{c.clips.locale}</th>
              <th>{c.clips.voice}</th>
              <th>{c.clips.present}</th>
              <th>{c.clips.coverage}</th>
            </tr>
          </thead>
          <tbody>
            {t.manifests.map((m) => (
              <tr key={`${m.pack}-${m.locale}-${m.voice}`}>
                <td>
                  <code>{m.pack}</code>
                </td>
                <td>{m.locale}</td>
                <td>
                  <code>{m.voice}</code>
                </td>
                <td>
                  <Cell value={m.present} c={c} /> / <Cell value={m.rows} c={c} />
                </td>
                <td>
                  <Cell value={m.coverage} c={c} />
                </td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      ) : null}
    </Tile>
  );
}

function Wait({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.waitTime;
  const meta = (
    <p className="window">
      {windowLabel(c, t.window)} · {c.kFloor} {t.kFloor} · <code>{t.metricId}</code>
    </p>
  );
  return (
    <Tile id="wait_time" title={c.wait.title} state={t.state} reason={t.reason} c={c} meta={meta}>
      <dl className="facts">
        <dt>{c.wait.n}</dt>
        <dd>
          <Cell value={t.n} c={c} />
        </dd>
        <dt>{c.wait.mean}</dt>
        <dd>
          {t.suppressed ? (
            <span className="suppressed">{c.wait.suppressed}</span>
          ) : (
            <Cell value={t.meanMin === null ? null : `${t.meanMin} ${c.wait.minutes}`} c={c} />
          )}
        </dd>
      </dl>
    </Tile>
  );
}

function Satisfaction({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.satisfaction;
  const meta = (
    <p className="window">
      {windowLabel(c, t.window)} · {c.kFloor} {t.kFloor}
    </p>
  );
  return (
    <Tile
      id="satisfaction"
      title={c.satisfaction.title}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <dl className="facts">
        <dt>{c.satisfaction.csatN}</dt>
        <dd>
          <Cell value={t.csatN} c={c} />
        </dd>
        <dt>{c.satisfaction.csatMean}</dt>
        <dd>
          {t.csatSuppressed ? (
            <span className="suppressed">{c.satisfaction.suppressed}</span>
          ) : (
            <Cell value={t.csatMean} c={c} />
          )}
        </dd>
        <dt>{c.satisfaction.nps}</dt>
        <dd>
          <Cell value={t.nps} c={c} />
        </dd>
      </dl>
    </Tile>
  );
}

function Cicd({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.cicd;
  const meta = t.branch ? (
    <p className="window">
      {c.cicd.branch}: <code>{t.branch}</code>
    </p>
  ) : null;
  return (
    <Tile id="cicd" title={c.cicd.title} state={t.state} reason={t.reason} c={c} meta={meta}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cicd.workflow}</th>
            <th>{c.cicd.status}</th>
            <th>{c.cicd.conclusion}</th>
            <th>{c.cicd.sha}</th>
            <th>{c.cicd.updated}</th>
          </tr>
        </thead>
        <tbody>
          {t.workflows.map((w) => (
            <tr key={w.workflow}>
              <td>
                <code>{w.workflow}</code>
              </td>
              <td>{w.status}</td>
              <td data-state={w.conclusion}>{w.conclusion}</td>
              <td>
                <code>{w.sha}</code>
              </td>
              <td>
                {w.updatedAt === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  <time>{w.updatedAt}</time>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

export function OpsConsole({ state, lang }: { state: OpsConsoleState; lang: Lang }): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <main lang={lang} className="ops" data-page="ops">
        <h1>{c.title}</h1>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </main>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <main lang={lang} className="ops" data-page="ops">
        <h1>{c.title}</h1>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </main>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="ops">
      <header className="page-head">
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time> · {c.prometheus}:{" "}
          <code>{view.prometheus}</code>
        </p>
      </header>
      <div className="grid">
        <Health view={view} c={c} />
        <Gpu view={view} c={c} />
        <Cicd view={view} c={c} />
        <Usage view={view} c={c} />
        <Clips view={view} c={c} />
        <Wait view={view} c={c} />
        <Satisfaction view={view} c={c} />
        <Models view={view} c={c} />
      </div>
    </main>
  );
}
