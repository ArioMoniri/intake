/**
 * INT-565 — Clinical quality & safety, rendered (INT-185; files/08 §3, §4
 * D/E): the RED/YELLOW/GREEN distribution and who produced it, PolicyGuard
 * blocks by violation class, the false-RED review queue and note acceptance by
 * specialty.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * PolicyGuard blocks with no scrape behind them are an unknown tile with its
 * cause and what fills it — never a column of zeros (invariant 17). The
 * false-RED queue shows pointers only and offers no control: the annotation
 * routes are INT-175's, and a staff read of the content is refused (HB-L6).
 * No `style` attribute.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type QualitySafetyCopy } from "./copy";
import type { QualitySafetyState } from "./load";
import type { QualitySafetyPresentation } from "./module";

type C = QualitySafetyCopy;

function Triage({ view, c }: { view: QualitySafetyPresentation; c: C }): ReactElement {
  const triage = view.triageEvents;
  return (
    <Tile id="triage" title={c.tiles.triage} state="ok" reason={null} c={c}>
      <dl className="facts">
        <dt>{c.metric}</dt>
        <dd>
          <code>{triage.metricId}</code>
        </dd>
        <dt>{c.status}</dt>
        <dd>
          <code>{triage.metricStatus}</code>
        </dd>
        <dt>{c.candidateCap}</dt>
        <dd>
          <code>{triage.candidateFlagCap}</code>
        </dd>
      </dl>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.level}</th>
            <th>{c.count}</th>
            <th>{c.producedBy}</th>
          </tr>
        </thead>
        <Rows rows={triage.levels} columns={3} kind="levels" empty={c.empties.levels}>
          {(row) => (
            <tr key={row.level} data-level={row.level}>
              <td>{row.level}</td>
              <td>{row.count}</td>
              <td>
                <code>{row.producedBy}</code>
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      <p className="window">{c.triageNote}</p>
    </Tile>
  );
}

function PolicyGuard({ view, c }: { view: QualitySafetyPresentation; c: C }): ReactElement {
  const guard = view.policyGuardClasses;
  return (
    <Tile
      id="policyguard"
      title={c.tiles.policyguard}
      state={guard.sourceAvailable ? "ok" : "unknown"}
      reason={guard.sourceReason}
      c={c}
      meta={
        <span className="sub">
          {c.window}: {guard.window}
        </span>
      }
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.className}</th>
            <th>{c.count}</th>
          </tr>
        </thead>
        <Rows rows={guard.classes} columns={2} kind="classes" empty={c.empties.classes}>
          {(row) => (
            <tr key={row.className} data-class={row.className}>
              <td>
                <code>{row.className}</code>
              </td>
              <td>{row.count ?? <span className="cell-unknown">{c.unknown}</span>}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      <p className="window">{c.policyNote}</p>
    </Tile>
  );
}

function FalseRed({ view, c }: { view: QualitySafetyPresentation; c: C }): ReactElement {
  const queue = view.falseRedQueue;
  return (
    <Tile id="false_red" title={c.tiles.falseRed} state="ok" reason={null} c={c} wide>
      <dl className="facts">
        <dt>{c.queue}</dt>
        <dd>
          <code>{queue.queueId}</code>
        </dd>
        <dt>{c.enqueueScope}</dt>
        <dd>
          <code>{queue.enqueueScope}</code>
        </dd>
        <dt>{c.reviewers}</dt>
        <dd>
          {queue.reviewerRoles.map((role) => (
            <code key={role}>{role} </code>
          ))}
        </dd>
        <dt>{c.contentRead}</dt>
        <dd data-content-read={queue.contentReadState}>
          {c.contentRefused} · {c.blocker} <code>{queue.contentBlocker}</code>
        </dd>
      </dl>
      <p className="window">{c.falseRedNote}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.item}</th>
            <th>{c.rule}</th>
            <th>{c.branch}</th>
            <th>{c.created}</th>
            <th>{c.review}</th>
          </tr>
        </thead>
        <Rows rows={queue.items} columns={5} kind="items" empty={c.empties.items}>
          {(item) => (
            <tr key={item.itemId} data-item={item.itemId}>
              <td>
                <code>{item.itemId}</code>
              </td>
              <td>
                <code>{item.ruleId}</code>
              </td>
              <td>
                <code>{item.branchId}</code>
              </td>
              <td>
                <time>{item.createdAt}</time>
              </td>
              <td>
                {item.review === null ? (
                  "—"
                ) : (
                  <code>
                    {item.review.label} · {item.review.sectionReason}
                  </code>
                )}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Acceptance({ view, c }: { view: QualitySafetyPresentation; c: C }): ReactElement {
  const acceptance = view.acceptanceBySpecialty;
  return (
    <Tile id="acceptance" title={c.tiles.acceptance} state="ok" reason={null} c={c} wide>
      <p className="window">{c.acceptanceNote}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.branch}</th>
            <th>{c.delivered}</th>
            <th>{c.accepted}</th>
            <th>{c.rate}</th>
          </tr>
        </thead>
        <Rows rows={acceptance.rows} columns={4} kind="acceptance" empty={c.empties.acceptance}>
          {(row) => (
            <tr key={row.branchId} data-branch={row.branchId}>
              <td lang="tr">
                {row.nameTr} <span className="sub">{row.branchId}</span>
              </td>
              {row.cells.map((cell) => (
                <td key={cell.label}>{cell.value}</td>
              ))}
              <td>{row.rate ?? <span className="suppressed">{c.noMeasurement}</span>}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function QualitySafetyConsole({
  state,
  lang,
}: {
  state: QualitySafetyState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="quality-safety" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="quality-safety" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="quality-safety">
      <header className="page-head">
        <ConsoleNav current="quality-safety" lang={lang} />
        <h1>{c.title}</h1>
      </header>
      <section className="band" aria-labelledby="band-routing">
        <h2 id="band-routing" className="band-head">
          {c.bands.routing}
        </h2>
        <div className="grid">
          <Triage view={view} c={c} />
          <PolicyGuard view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-review">
        <h2 id="band-review" className="band-head">
          {c.bands.review}
        </h2>
        <div className="grid">
          <FalseRed view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-notes">
        <h2 id="band-notes" className="band-head">
          {c.bands.notes}
        </h2>
        <div className="grid">
          <Acceptance view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
