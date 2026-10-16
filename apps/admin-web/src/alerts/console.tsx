/**
 * INT-481 — the Alerts page, rendered: what Alertmanager holds right now,
 * counted by severity and then listed by id. It is a synchronous,
 * presentational tree over the loader's state. The App Router page renders it
 * on the server, and the e2e spec renders the very same tree.
 *
 * Ids only. An alert is its name, severity, state, start and the closed set of
 * labels, shown as `key=value` chips. Its annotations never reach this page,
 * so nothing here describes an alert in prose. An unknown source is rendered
 * as the word and its reason code with no figure beside it (invariant 17).
 *
 * The staff Grafana link is a plain anchor, offered only to an admitted caller
 * and only when the server env names a valid https origin (`./load`). Nothing
 * is framed or embedded, and there is no `style` attribute anywhere.
 */
import { Fragment, type ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { ScrollTable, Tile, type TileCopy } from "../ops/tiles";
import { COPY, type AlertsCopy, type Lang } from "./copy";
import type { AlertsState } from "./load";
import { SEVERITIES, type AlertsView } from "./module";

type C = AlertsCopy;

const HTTP_REASON = "alertmanager_http_";

/** The tile copy for this source: every HTTP status shares one sentence. */
function tileCopy(c: C, reason: string | null): TileCopy {
  if (reason === null || !reason.startsWith(HTTP_REASON)) return c;
  return { unknown: c.unknown, reasons: { [reason]: c.reasons["alertmanager_http"] ?? reason } };
}

function Counts({ view, c }: { view: AlertsView; c: C }): ReactElement {
  const counts = view.counts;
  return (
    <Tile
      id="alert_counts"
      title={c.tiles.counts}
      state={view.source.state}
      reason={view.source.reason}
      c={tileCopy(c, view.source.reason)}
    >
      {counts === null ? null : (
        <dl className="facts">
          {SEVERITIES.map((severity) => (
            <Fragment key={severity}>
              <dt>{c.severities[severity]}</dt>
              <dd data-count={severity}>{counts[severity]}</dd>
            </Fragment>
          ))}
          <dt>{c.withheld}</dt>
          <dd data-count="withheld">{view.withheld}</dd>
        </dl>
      )}
    </Tile>
  );
}

function List({ view, c }: { view: AlertsView; c: C }): ReactElement {
  return (
    <Tile
      id="alerts"
      title={c.tiles.alerts}
      state={view.source.state}
      reason={view.source.reason}
      c={tileCopy(c, view.source.reason)}
    >
      {view.alerts.length === 0 ? (
        <p className="window">{c.none}</p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.cols.alertname}</th>
              <th>{c.cols.severity}</th>
              <th>{c.cols.state}</th>
              <th>{c.cols.startsAt}</th>
              <th>{c.cols.labels}</th>
            </tr>
          </thead>
          <tbody>
            {view.alerts.map((alert, index) => (
              <tr
                key={`${alert.alertname}-${index}`}
                data-severity={alert.severity}
                data-alert-state={alert.state}
              >
                <td>
                  <code>{alert.alertname}</code>
                </td>
                <td>{c.severities[alert.severity]}</td>
                <td>{c.states[alert.state]}</td>
                <td>
                  <time>{alert.startsAt}</time>
                </td>
                <td>
                  {alert.labels.length === 0 ? (
                    c.none
                  ) : (
                    <span className="chips">
                      {alert.labels.map((label) => (
                        <code key={label.key} className="chip" data-label={label.key}>
                          {`${label.key}=${label.value}`}
                        </code>
                      ))}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
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
    <main lang={lang} className="ops" data-page="alerts">
      <h1>{c.title}</h1>
      {children}
    </main>
  );
}

export function AlertsConsole({
  state,
  lang,
  grafana,
}: {
  state: AlertsState;
  lang: Lang;
  grafana: string | null;
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
    <main lang={lang} className="ops" data-page="alerts">
      <header className="page-head">
        <ConsoleNav current="alerts" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time> · {c.source}: {c.alertmanager}{" "}
          <code>{view.source.state}</code>
        </p>
        {grafana === null ? null : (
          <p>
            <a href={grafana} rel="noopener noreferrer" data-link="grafana">
              {c.grafana}
            </a>
          </p>
        )}
      </header>
      <div className="grid">
        <Counts view={view} c={c} />
        <List view={view} c={c} />
      </div>
    </main>
  );
}
