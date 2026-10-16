/**
 * INT-490 — the Analytics page, rendered: the research and improvement release
 * for one closed ISO week (LD-06). A synchronous, presentational tree over the
 * loader's state; the App Router page renders it on the server and the e2e
 * spec renders the very same tree.
 *
 * A withheld table shows the `<k` mark and the reason class in words — never
 * a figure, and never which of its cells was the small one. Bars are native
 * `<meter>` elements, so nothing is styled by attribute (the CSP has no
 * `unsafe-inline`). Every table carries `data-tile` and `data-view-state`.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { ScrollTable } from "../ops/tiles";
import { COPY, type AnalyticsCopy, type Lang } from "./copy";
import type { AnalyticsState } from "./load";
import { KINDS, type AnalyticsView, type FamilyView, type TableView } from "./module";

type C = AnalyticsCopy;

function label(value: string, c: C): string {
  return c.values[value] ?? value;
}

function Table({
  t,
  k,
  id,
  c,
  title,
}: {
  t: TableView;
  k: number;
  id: string;
  c: C;
  title: string;
}): ReactElement {
  return (
    <section
      data-tile={id}
      data-view-state={t.state}
      className={`tile tile-${t.state === "shown" ? "ok" : "withheld"}`}
      aria-labelledby={`tile-${id}`}
    >
      <header className="tile-head">
        <h2 id={`tile-${id}`}>{title}</h2>
        {t.population === null ? null : (
          <p className="window">
            {c.columns.population}: {t.population}
          </p>
        )}
      </header>
      {t.state === "withheld" ? (
        <p className="suppressed" data-reason={t.reason ?? ""}>
          <strong className="lt-k">&lt;{k}</strong> ·{" "}
          {t.reason === "cross_view" ? c.withheld.cross_view(k) : c.withheld.below_k(k)}{" "}
          <code>{t.reason}</code>
        </p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.columns.value}</th>
              <th>{t.kind === "funnel" ? c.columns.reached : c.columns.people}</th>
              <th>{c.columns.share}</th>
              {t.kind === "funnel" ? <th>{c.columns.dropOff}</th> : null}
            </tr>
          </thead>
          <tbody>
            {t.rows.map((row) => (
              <tr key={row.value} data-value={row.value}>
                <td>{label(row.value, c)}</td>
                <td>{row.people}</td>
                <td className="share">
                  <meter
                    min={0}
                    max={row.meter.max}
                    value={row.meter.value}
                    aria-label={`${label(row.value, c)}: ${row.share ?? ""}`}
                  />{" "}
                  {row.share}
                </td>
                {t.kind === "funnel" ? <td>{row.dropOff ?? "—"}</td> : null}
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
    </section>
  );
}

function Family({ f, k, c }: { f: FamilyView; k: number; c: C }): ReactElement {
  const key = `${f.protocol}:${f.version}`;
  return (
    <section className="band" aria-labelledby={`family-${key}`}>
      <h2 id={`family-${key}`} className="band-head">
        {c.family.protocol} <code>{f.protocol}</code> · {c.family.version} <code>{f.version}</code>
      </h2>
      <div className="grid">
        {f.tables.map((t) => (
          <Table key={t.kind} t={t} k={k} id={`${t.kind}:${key}`} c={c} title={c.views[t.kind]} />
        ))}
      </div>
      {f.questions.length === 0 ? null : (
        <>
          <h3 className="band-sub">{c.questions}</h3>
          {f.questions.map((q) => (
            <div key={q.question} className="question" data-question={q.question}>
              <h4>
                {c.family.question} <code>{q.question}</code>
              </h4>
              <div className="grid">
                {q.tables.map((t) => (
                  <Table
                    key={t.kind}
                    t={t}
                    k={k}
                    id={`${t.kind}:${key}:${q.question}`}
                    c={c}
                    title={c.views[t.kind]}
                  />
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </section>
  );
}

function Release({ view, c }: { view: AnalyticsView; c: C }): ReactElement {
  const r = view.retention;
  const retention = (state: typeof r.aggregates): string =>
    state.state === "undecided" ? c.retention.undecided : c.retention.days(state.days);
  return (
    <section data-tile="release" className="tile tile-ok" aria-labelledby="tile-release">
      <header className="tile-head">
        <h2 id="tile-release">{c.scope}</h2>
      </header>
      <dl className="facts">
        {view.tenants.state === "unconfigured" ? (
          <>
            <dt>{c.tenants.title}</dt>
            <dd data-state="unconfigured">{c.tenants.unconfigured}</dd>
          </>
        ) : (
          <>
            <dt>{c.tenants.admitted}</dt>
            <dd>{view.tenants.admitted}</dd>
            <dt>{c.tenants.refused}</dt>
            <dd>{view.tenants.refused}</dd>
          </>
        )}
        <dt>
          {c.retention.title} · {c.retention.aggregates}
        </dt>
        <dd data-retention={r.aggregates.state}>{retention(r.aggregates)}</dd>
        <dt>
          {c.retention.title} · {c.retention.rawTelemetry}
        </dt>
        <dd data-retention={r.rawTelemetry.state}>{retention(r.rawTelemetry)}</dd>
      </dl>
    </section>
  );
}

function NotCollected({ view, c }: { view: AnalyticsView; c: C }): ReactElement | null {
  if (view.notCollected.length === 0) return null;
  return (
    <section className="band" aria-labelledby="band-not-collected">
      <h2 id="band-not-collected" className="band-head">
        {c.notCollected.title}
      </h2>
      <p className="window">{c.notCollected.lede}</p>
      <div className="grid">
        <section
          data-tile="not_collected"
          className="tile tile-unknown"
          aria-label={c.notCollected.title}
        >
          <ScrollTable>
            <tbody>
              {view.notCollected.map((item) => (
                <tr key={item.kind} data-kind={item.kind}>
                  <td>
                    {KINDS[item.kind].scope === "question" ? `${c.questions} · ` : ""}
                    {c.views[item.kind]}
                  </td>
                  <td className="wrap">
                    {c.notCollected.reasons[item.reason] ?? item.reason} <code>{item.reason}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </section>
      </div>
    </section>
  );
}

export function AnalyticsConsole({
  state,
  lang,
}: {
  state: AnalyticsState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <main lang={lang} className="ops" data-page="analytics">
        <h1>{c.title}</h1>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </main>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <main lang={lang} className="ops" data-page="analytics">
        <h1>{c.title}</h1>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </main>
    );
  }
  const view = state.view;
  const suffix = lang === "en" ? "&lang=en" : "";
  const p = view.period;
  return (
    <main lang={lang} className="ops" data-page="analytics">
      <header className="page-head">
        <ConsoleNav current="analytics" lang={lang} />
        <h1>{c.title}</h1>
        <p>{c.lede}</p>
        <p>{c.floor(view.k)}</p>
        <p>
          {c.measurement} {c.kept} {c.generatedAt}: <time>{view.generatedAt}</time>
        </p>
      </header>
      <nav className="period-nav" aria-label={c.week} data-period={p.id}>
        <a href={`/analytics?period=${p.previous}${suffix}`}>← {c.previousWeek}</a>
        <strong>
          {c.week} <code>{p.id}</code>
        </strong>
        <span className="window">
          <time>{p.start}</time> – <time>{p.end}</time> · {c.weekRange}
        </span>
        {p.following === null ? null : (
          <a href={`/analytics?period=${p.following}${suffix}`}>{c.nextWeek} →</a>
        )}
      </nav>
      <div className="grid">
        <Release view={view} c={c} />
      </div>
      {view.families.length === 0 ? (
        <p className="empty" data-empty="true">
          {c.empty(view.k)}
        </p>
      ) : (
        view.families.map((f) => (
          <Family key={`${f.protocol}:${f.version}`} f={f} k={view.k} c={c} />
        ))
      )}
      <NotCollected view={view} c={c} />
    </main>
  );
}
