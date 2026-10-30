/**
 * INT-565 — the Protocols module, rendered (INT-184; files/08 §3; files/09
 * §1-4): branch coverage and the branch × maturity matrix, the proposal review
 * queue with Loop 2's closed vocabulary, and clip coverage per voice.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * The review queue shows each proposal's decision state as words, never as a
 * button: the console records proposal decisions through audited four-eyes
 * routes that do not exist yet, and a control with nowhere to post is a dead
 * end (invariant 17). No `style` attribute (the CSP has no `unsafe-inline`).
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type ProtocolsCopy } from "./copy";
import type { ProtocolsState } from "./load";
import type { MatrixRow, ProtocolsPresentation } from "./module";

type C = ProtocolsCopy;

function maturityOf(row: MatrixRow, c: C): string {
  if (row.servedMaturity !== null) return `${row.servedMaturity} · ${c.served}`;
  if (row.status === "EXCLUDED") return c.excluded;
  if (row.draftMaturity !== null) return `${row.draftMaturity} · ${c.draft}`;
  return c.noPack;
}

function Coverage({ view, c }: { view: ProtocolsPresentation; c: C }): ReactElement {
  const { summary, rows } = view.matrix;
  return (
    <>
      <Tile id="coverage" title={c.tiles.summary} state="ok" reason={null} c={c}>
        <dl className="facts">
          <dt>{c.total}</dt>
          <dd>{summary.total}</dd>
          <dt>{c.statuses.DIRECT}</dt>
          <dd>{summary.direct}</dd>
          <dt>{c.statuses.CLUSTER}</dt>
          <dd>{summary.cluster}</dd>
          <dt>{c.statuses.MISSING}</dt>
          <dd data-state={summary.missing > 0 ? "missing" : "ok"}>{summary.missing}</dd>
          <dt>{c.statuses.EXCLUDED}</dt>
          <dd>{summary.excluded}</dd>
        </dl>
        <p className="window">{c.coverageNote}</p>
      </Tile>
      <Tile id="matrix" title={c.tiles.matrix} state="ok" reason={null} c={c} wide>
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.branch}</th>
              <th>{c.cluster}</th>
              <th>{c.status}</th>
              <th>{c.maturity}</th>
            </tr>
          </thead>
          <Rows rows={rows} columns={4} kind="matrix" empty={c.empties.matrix}>
            {(row) => (
              <tr key={row.branchId} data-branch={row.branchId} data-servable={row.servable}>
                <td lang="tr">
                  {row.nameTr} <span className="sub">{row.branchId}</span>
                </td>
                <td>
                  <code>{row.cluster}</code>
                </td>
                <td data-status={row.status}>{c.statuses[row.status]}</td>
                <td>{maturityOf(row, c)}</td>
              </tr>
            )}
          </Rows>
        </ScrollTable>
      </Tile>
    </>
  );
}

/** A decision's state as words; the view-model's refusal reason is English. */
function ControlState({
  name,
  enabled,
  word,
  reason,
}: {
  name: string;
  enabled: boolean;
  word: string;
  reason: string | null;
}): ReactElement {
  return (
    <span data-control={name} data-enabled={enabled} lang={enabled ? undefined : "en"}>
      {enabled ? word : reason}
    </span>
  );
}

function Review({ view, c }: { view: ProtocolsPresentation; c: C }): ReactElement {
  const queue = view.reviewQueue;
  return (
    <>
      <Tile id="review" title={c.tiles.review} state="ok" reason={null} c={c} wide>
        <p className="window">{c.reviewNote}</p>
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.proposal}</th>
              <th>{c.target}</th>
              <th>{c.pack}</th>
              <th>{c.evidence}</th>
              <th>{c.decision}</th>
            </tr>
          </thead>
          <Rows rows={queue.rows} columns={5} kind="review" empty={c.empties.review}>
            {(row) => (
              <tr key={row.proposalId} data-proposal={row.proposalId}>
                <td>
                  <code>{row.proposalId}</code>
                </td>
                <td>
                  <code>{row.target}</code>
                </td>
                <td>
                  <code>{row.packId}</code> <span className="sub">{row.slotId}</span>
                </td>
                <td>{row.evidenceComplete ? c.complete : row.unmetChecks.join(", ")}</td>
                <td>
                  <ControlState
                    name="approve"
                    enabled={row.approveControl.enabled}
                    word={c.approvable}
                    reason={row.approveControl.disabledReason}
                  />
                  {" · "}
                  <ControlState
                    name="reject"
                    enabled={row.rejectControl.enabled}
                    word={c.rejectable}
                    reason={row.rejectControl.disabledReason}
                  />
                </td>
              </tr>
            )}
          </Rows>
        </ScrollTable>
      </Tile>
      <Tile id="vocabulary" title={c.tiles.vocabulary} state="ok" reason={null} c={c}>
        <dl className="facts">
          <dt>{c.allowedTargets}</dt>
          <dd>
            {queue.allowedTargets.map((target) => (
              <code key={target} data-target={target}>
                {target}{" "}
              </code>
            ))}
          </dd>
          <dt>{c.unmetChecks}</dt>
          <dd>
            {queue.unmetCheckNames.map((check) => (
              <code key={check} data-check={check}>
                {check}{" "}
              </code>
            ))}
          </dd>
        </dl>
      </Tile>
    </>
  );
}

function Clips({ view, c }: { view: ProtocolsPresentation; c: C }): ReactElement {
  const clips = view.clipCoverage;
  return (
    <Tile id="clips" title={c.tiles.clips} state="ok" reason={null} c={c} wide>
      <p className="window">{c.clipsNote}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.voice}</th>
            <th>{c.role}</th>
            <th>{c.required}</th>
            <th>{c.cached}</th>
            <th>{c.missing}</th>
          </tr>
        </thead>
        <Rows rows={clips.voices} columns={5} kind="clips" empty={c.empties.clips}>
          {(voice) => (
            <tr key={voice.voiceId} data-voice={voice.voiceId}>
              <td>
                <code>{voice.voiceId}</code>
              </td>
              <td lang="en">{voice.role}</td>
              {voice.cells.map((cell) => (
                <td key={cell.label}>{cell.value}</td>
              ))}
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function ProtocolsConsole({
  state,
  lang,
}: {
  state: ProtocolsState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="protocols" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="protocols" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="protocols">
      <header className="page-head">
        <ConsoleNav current="protocols" lang={lang} />
        <h1>{c.title}</h1>
      </header>
      <section className="band" aria-labelledby="band-coverage">
        <h2 id="band-coverage" className="band-head">
          {c.bands.coverage}
        </h2>
        <div className="grid">
          <Coverage view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-review">
        <h2 id="band-review" className="band-head">
          {c.bands.review}
        </h2>
        <div className="grid">
          <Review view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-clips">
        <h2 id="band-clips" className="band-head">
          {c.bands.clips}
        </h2>
        <div className="grid">
          <Clips view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
