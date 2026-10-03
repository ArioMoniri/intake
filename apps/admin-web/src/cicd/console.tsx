/**
 * INT-187 — the CI/CD & releases module, rendered (files/08 §3 "CI/CD &
 * releases"): workflow runs, required gates, releases, deploy state, the
 * deploy freeze with the error budget and the gate they decide, the requests
 * awaiting a second key, and the two freeze controls. A synchronous,
 * presentational tree over the loader's state; the App Router page renders it
 * on the server and the e2e spec renders the very same tree.
 *
 * Tier and the roles who may request and approve are read off the payload's
 * control catalogue — the server's `DangerousAction` registry — never from a
 * list kept here. There is no approve form (approval needs a fresh single-use
 * WebAuthn assertion, which a script-free page cannot mint) and no rollback
 * form (there is no deploy controller to command): both buttons are present,
 * disabled, and say why. No `style` attribute anywhere.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { Cell, ScrollTable, Tile } from "../ops/tiles";
import type { ResultCode } from "./actions";
import { COPY, type CicdCopy, type Lang } from "./copy";
import type { CicdState } from "./load";
import type { CicdView, ControlView } from "./module";
import { Deployments, Gates, NotDeployed, Pipelines, Releases } from "./tiles";

type C = CicdCopy;

function Freeze({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.freeze;
  const state = t.engaged === null ? "unknown" : t.engaged ? "engaged" : "open";
  return (
    <Tile id="freeze" title={c.tiles.freeze} state={t.state} reason={t.reason} c={c}>
      <dl className="facts" data-freeze={state}>
        <dt>{c.cols.engaged}</dt>
        <dd data-state={t.engaged ? "blocked" : "ok"}>{t.engaged ? c.yes : c.no}</dd>
        <dt>{c.cols.revision}</dt>
        <dd>
          <Cell value={t.revision} c={c} />
        </dd>
        <dt>{c.cols.lastChange}</dt>
        <dd>{t.lastChange === null ? c.none : (c.forms.names[t.lastChange] ?? t.lastChange)}</dd>
        <dt>{c.cols.changedBy}</dt>
        <dd>{t.changedBy === null ? c.none : <code>{t.changedBy}</code>}</dd>
        <dt>{c.cols.changedAt}</dt>
        <dd>{t.changedAt === null ? c.none : <time>{t.changedAt}</time>}</dd>
        <dt>{c.cols.approvedBy}</dt>
        <dd>{t.approvedBy === null ? c.none : <code>{t.approvedBy}</code>}</dd>
        <dt>{c.cols.reasonClass}</dt>
        <dd>{t.reasonClass === null ? c.none : <code>{t.reasonClass}</code>}</dd>
      </dl>
    </Tile>
  );
}

function ErrorBudget({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.errorBudget;
  return (
    <Tile id="error_budget" title={c.tiles.errorBudget} state={t.state} reason={t.reason} c={c}>
      <dl className="facts">
        <dt>{c.cols.exhausted}</dt>
        {t.exhausted.length === 0 ? (
          <dd>{c.none}</dd>
        ) : (
          t.exhausted.map((name) => (
            <dd key={name} data-state="blocked">
              <code>{name}</code>
            </dd>
          ))
        )}
        <dt>{c.cols.unmeasured}</dt>
        {t.unmeasured.length === 0 ? (
          <dd>{c.none}</dd>
        ) : (
          t.unmeasured.map((name) => (
            <dd key={name} className="cell-unknown">
              <code>{name}</code>
            </dd>
          ))
        )}
      </dl>
    </Tile>
  );
}

function DeployGate({ view, c }: { view: CicdView; c: C }): ReactElement {
  const g = view.deployGate;
  const verdict = g.allowed ? "allowed" : "refused";
  return (
    <Tile id="deploy_gate" title={c.tiles.deployGate} state="ok" reason={null} c={c}>
      <p className="badge" data-verdict={verdict} data-state={g.allowed ? "ok" : "blocked"}>
        {c.cols.allowed}: {c.gate[verdict]}
      </p>
      <dl className="facts">
        <dt>{c.cols.refusals}</dt>
        {g.refusals.length === 0 ? (
          <dd>{c.none}</dd>
        ) : (
          g.refusals.map((code) => (
            <dd key={code} data-refusal={code}>
              {c.gate.codes[code] ?? code} <code>{code}</code>
            </dd>
          ))
        )}
        <dt>{c.cols.notes}</dt>
        {g.notes.length === 0 ? (
          <dd>{c.none}</dd>
        ) : (
          g.notes.map((code) => (
            <dd key={code} data-note={code}>
              {c.gate.codes[code] ?? code} <code>{code}</code>
            </dd>
          ))
        )}
        <dt>{c.cols.enforcement}</dt>
        {g.enforcement.map((row) => (
          <dd key={row.point} data-enforcement={row.status}>
            <code>{row.point}</code> · {c.gate.enforcement[row.status] ?? row.status}
          </dd>
        ))}
      </dl>
    </Tile>
  );
}

function Pending({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.pending;
  return (
    <Tile id="pending" title={c.tiles.pending} state={t.state} reason={t.reason} c={c}>
      <p className="window">{c.approveNeedsStepUp}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.action}</th>
            <th>{c.cols.control}</th>
            <th>{c.cols.baseRevision}</th>
            <th>{c.cols.requestedRole}</th>
            <th>{c.cols.expiresAt}</th>
            <th>{c.approve}</th>
          </tr>
        </thead>
        <tbody>
          {t.actions.map((row) => (
            <tr key={row.actionId} data-action={row.actionId}>
              <td>
                <code>{row.actionId}</code>
              </td>
              <td>{c.forms.names[row.control] ?? row.control}</td>
              <td>{row.baseRevision}</td>
              <td>
                <code>{row.requestedRole}</code>
              </td>
              <td>
                <time>{row.expiresAt}</time>
              </td>
              <td>
                <button type="button" disabled data-reason="step_up_unwired">
                  {c.approve}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function ControlForm({
  control,
  view,
  lang,
  c,
}: {
  control: ControlView;
  view: CicdView;
  lang: Lang;
  c: C;
}): ReactElement {
  const oneKey = control.tier === 1;
  return (
    <form
      action="/cicd/action"
      method="post"
      data-control={control.control}
      data-tier={String(control.tier)}
      className="tile"
      autoComplete="off"
    >
      <header className="tile-head">
        <h2>{c.forms.names[control.control] ?? control.control}</h2>
      </header>
      <p className="window">
        {oneKey ? c.forms.tier1 : c.forms.tier2} · <code>{control.route}</code>
      </p>
      <dl className="facts">
        <dt>{c.forms.requesters}</dt>
        <dd>{control.actorRoles.join(", ")}</dd>
        <dt>{c.forms.approvers}</dt>
        <dd>{control.approverRoles.length === 0 ? c.none : control.approverRoles.join(", ")}</dd>
      </dl>
      <input type="hidden" name="action" value={control.control} />
      <input type="hidden" name="lang" value={lang} />
      <label>
        {c.forms.reasonClass}{" "}
        <select name="reason_class" required>
          {view.reasonClasses.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label>
        {c.forms.justification}{" "}
        <textarea name="justification" required minLength={12} maxLength={2000} rows={2} />
      </label>
      <button type="submit">{oneKey ? c.forms.engage : c.forms.request}</button>
    </form>
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
    <main lang={lang} className="ops" data-page="cicd">
      <h1>{c.title}</h1>
      {children}
    </main>
  );
}

export function CicdConsole({
  state,
  lang,
  result,
}: {
  state: CicdState;
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
    <main lang={lang} className="ops" data-page="cicd">
      <header className="page-head">
        <ConsoleNav current="cicd" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time> · {c.sources}: prometheus{" "}
          <code>{view.sources.prometheus}</code> · freeze <code>{view.sources.freezeStore}</code> ·
          slo <code>{view.sources.sloFiles}</code>
        </p>
        {result === null ? null : (
          <p className="result" data-result={result} role="status">
            {c.results[result]}
          </p>
        )}
      </header>
      <section className="band" aria-labelledby="band-release">
        <h2 id="band-release" className="band-head">
          {c.tiles.deployGate}
        </h2>
        <div className="grid">
          <DeployGate view={view} c={c} />
          <Freeze view={view} c={c} />
          <ErrorBudget view={view} c={c} />
          <Pending view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-ci">
        <h2 id="band-ci" className="band-head">
          {c.tiles.pipelines}
        </h2>
        <div className="grid">
          <Pipelines view={view} c={c} />
          <Gates view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-cd">
        <h2 id="band-cd" className="band-head">
          {c.tiles.deployments}
        </h2>
        <div className="grid">
          <Releases view={view} c={c} />
          <Deployments view={view} c={c} />
          <NotDeployed view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-controls">
        <h2 id="band-controls" className="band-head">
          {c.forms.section}
        </h2>
        <p className="window">{c.forms.policy}</p>
        <div className="grid">
          {view.catalogue.map((control) => (
            <ControlForm key={control.control} control={control} view={view} lang={lang} c={c} />
          ))}
        </div>
      </section>
    </main>
  );
}
