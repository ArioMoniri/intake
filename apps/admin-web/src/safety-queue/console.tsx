/**
 * INT-562 — the Safety queue, rendered (files/08 §3 "Safety queue"): the
 * clinic's inbox as one table in the inbox's order, a count of what waits
 * and what is past its SLA, and one acknowledgement form per open entry. A
 * synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the spec renders the very same tree.
 *
 * Ids and clocks only (invariant 6). No `style` attribute anywhere.
 */
import { Fragment, type ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { withUnit } from "../ops/guards";
import { RefusedPage } from "../ui/states";
import type { ResultCode } from "./actions";
import { COPY, type Lang, type SafetyQueueCopy } from "./copy";
import type { SafetyQueueState } from "./load";
import type { QueueRowView, SafetyQueueView } from "./module";

type C = SafetyQueueCopy;

const COLUMNS = 9;

function Acknowledge({ row, lang, c }: { row: QueueRowView; lang: Lang; c: C }): ReactElement {
  return (
    <form action="/safety-queue/action" method="post" autoComplete="off">
      <input type="hidden" name="entry_id" value={row.entryId} />
      <input type="hidden" name="lang" value={lang} />
      <button type="submit">{c.acknowledge}</button>
    </form>
  );
}

function Row({ row, lang, c }: { row: QueueRowView; lang: Lang; c: C }): ReactElement {
  const age = `${withUnit(row.elapsedMinutes, c.minutes)} · ${c.sla} ${withUnit(row.slaMinutes, c.minutes)}`;
  return (
    <tr
      data-entry={row.entryId}
      data-kind={row.kind}
      data-age-band={row.ageBand ?? ""}
      data-acknowledged={String(row.acknowledged)}
    >
      <td data-col="entry">
        <code>{row.entryId}</code>
      </td>
      <td data-col="session">
        <code>{row.sessionId}</code>
      </td>
      <td
        data-col="kind"
        data-state={row.kind === "red" || row.kind === "red_on_site" ? "red" : "attention"}
      >
        {c.kinds[row.kind]}
      </td>
      <td data-col="rules">
        {row.ruleIds.map((rule, i) => (
          <Fragment key={rule}>
            {i > 0 ? " " : null}
            <code>{rule}</code>
          </Fragment>
        ))}
      </td>
      <td data-col="register">{row.register === null ? c.none : c.registers[row.register]}</td>
      <td data-col="created">
        <time>{row.createdAt}</time>
      </td>
      <td data-col="age" data-state={row.ageBand === "past_sla" ? "blocked" : "ok"}>
        {age}
        {row.ageBand === null ? null : <span className="sub"> · {c.bands[row.ageBand]}</span>}
      </td>
      <td data-col="acknowledged">
        {row.acknowledged ? (
          <>
            <code>{row.acknowledgedBy}</code> · <time>{row.acknowledgedAt}</time>
          </>
        ) : (
          c.none
        )}
      </td>
      <td data-col="action">
        {row.acknowledged ? c.none : <Acknowledge row={row} lang={lang} c={c} />}
      </td>
    </tr>
  );
}

function Queue({ view, lang, c }: { view: SafetyQueueView; lang: Lang; c: C }): ReactElement {
  return (
    <Tile id="queue" title={c.tile} state="ok" reason={null} c={c} wide>
      <p className="window">{c.whoMayAcknowledge}</p>
      <p className="status-summary">
        {view.open} {c.summary.open} · {view.pastSla} {c.summary.pastSla}
      </p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.entry}</th>
            <th>{c.cols.session}</th>
            <th>{c.cols.kind}</th>
            <th>{c.cols.rules}</th>
            <th>{c.cols.register}</th>
            <th>{c.cols.created}</th>
            <th>{c.cols.age}</th>
            <th>{c.cols.acknowledged}</th>
            <th>{c.cols.action}</th>
          </tr>
        </thead>
        <Rows rows={view.rows} columns={COLUMNS} kind="safetyQueue" empty={c.empties.safetyQueue}>
          {(row) => <Row key={row.entryId} row={row} lang={lang} c={c} />}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function SafetyQueueConsole({
  state,
  lang,
  result,
}: {
  state: SafetyQueueState;
  lang: Lang;
  result: ResultCode | null;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="safety-queue" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="safety-queue" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "inbox_unavailable") {
    return (
      <RefusedPage page="safety-queue" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.inboxUnavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="safety-queue">
      <header className="page-head">
        <ConsoleNav current="safety-queue" lang={lang} />
        <h1>{c.title}</h1>
        <p>{c.intro}</p>
        {result === null ? null : (
          <p className="result" data-result={result} role="status">
            {c.results[result]}
          </p>
        )}
      </header>
      <div className="grid">
        <Queue view={view} lang={lang} c={c} />
      </div>
    </main>
  );
}
