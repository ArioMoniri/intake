/**
 * INT-187 — the CI/CD page's read-only tiles: workflow runs, required gates,
 * releases, this deployment's `/version`, and Argo CD / the deploy canary.
 *
 * Built from the ops console's primitives (`../ops/tiles`), so every tile
 * carries `data-tile` / `data-tile-state` and an unknown tile shows the word,
 * its reason and no figure (invariant 17). GitHub's conclusions are shown as
 * the codes they are, coloured by `data-state`. No `style` attribute anywhere.
 */
import type { ReactElement } from "react";

import { Cell, Rows, ScrollTable, Tile } from "../ops/tiles";
import { EmptyRow, EmptyState } from "../ui/states";
import { GatePass, RunDurations } from "./charts";
import type { CicdCopy } from "./copy";
import type { CicdView } from "./module";

type C = CicdCopy;

function When({ value, c }: { value: string | null; c: C }): ReactElement {
  return value === null ? <span className="cell-unknown">{c.unknown}</span> : <time>{value}</time>;
}

/** The runs table's columns, in order: the header and each cell's label. */
function runColumns(c: C): string[] {
  return [
    c.cols.workflow,
    c.cols.run,
    c.cols.status,
    c.cols.conclusion,
    c.cols.commit,
    c.cols.duration,
    c.cols.updated,
    c.cols.failedJobs,
  ];
}

/** "6 runs · 4 failure · 2 success": a workflow's runs counted by conclusion,
 * first-seen order, GitHub's codes as they are. Nominal, never a verdict. */
function groupCounts(runs: CicdView["pipelines"]["workflows"][number]["runs"], c: C): string {
  const codes = [...new Set(runs.map((r) => r.conclusion))];
  return [
    `${runs.length} ${c.groups.runs}`,
    ...codes.map((code) => `${runs.filter((r) => r.conclusion === code).length} ${code}`),
  ].join(" · ");
}

/**
 * INT-459 — the runs, one row group per workflow headed by its name and its
 * counts, rebuilt from grouped tables (nothing copied). Under 40rem of card
 * the table folds into one small card per run, each value under its column's
 * name (`data-label`, app/native-patterns.css). The roles are explicit,
 * because some engines drop a table's semantics once its display changes.
 */
function RunsTable({ view, c }: { view: CicdView; c: C }): ReactElement {
  const columns = runColumns(c);
  const label = (i: number): string => columns[i]!;
  return (
    <div className="scroll fold">
      <table role="table">
        <thead role="rowgroup">
          <tr role="row">
            {columns.map((name) => (
              <th key={name} role="columnheader">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        {view.pipelines.workflows.every((w) => w.runs.length === 0) ? (
          <tbody role="rowgroup">
            <EmptyRow
              columns={columns.length}
              kind="runs"
              title={c.empties.runs.title}
              why={c.empties.runs.why}
            />
          </tbody>
        ) : null}
        {view.pipelines.workflows
          .filter((w) => w.runs.length > 0)
          .map((w) => (
            <tbody key={w.workflow} role="rowgroup" data-group={w.workflow}>
              <tr className="group-head" role="row">
                <th scope="rowgroup" colSpan={columns.length} role="rowheader">
                  <code>{w.workflow}</code> <span className="sub">· {groupCounts(w.runs, c)}</span>
                </th>
              </tr>
              {w.runs.map((run) => (
                <tr key={`${w.workflow}#${run.runNumber}`} role="row" data-workflow={w.workflow}>
                  <td role="cell" data-label={label(0)}>
                    <code>{w.workflow}</code>
                  </td>
                  <td role="cell" data-label={label(1)}>
                    {run.runNumber}
                  </td>
                  <td role="cell" data-label={label(2)}>
                    {run.status}
                  </td>
                  <td role="cell" data-label={label(3)} data-state={run.conclusion}>
                    {run.conclusion}
                  </td>
                  <td role="cell" data-label={label(4)}>
                    <code title={run.sha}>{run.shortSha}</code>
                  </td>
                  <td role="cell" data-label={label(5)}>
                    <Cell value={run.duration} c={c} />
                  </td>
                  <td role="cell" data-label={label(6)}>
                    <When value={run.updatedAt} c={c} />
                  </td>
                  <td role="cell" data-label={label(7)} data-failed-jobs={run.failedJobs.join(" ")}>
                    {run.failedJobs.length === 0 && run.unnamedFailures === null ? (
                      c.none
                    ) : (
                      <>
                        {run.failedJobs.map((job) => (
                          <code key={job}>{job} </code>
                        ))}
                        {run.unnamedFailures === null ? null : (
                          <span className="sub">
                            +{run.unnamedFailures} {c.cols.unnamed}
                          </span>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
      </table>
    </div>
  );
}

export function Pipelines({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.pipelines;
  const meta =
    t.branch === null ? null : (
      <p className="window">
        <code>{t.branch}</code>
      </p>
    );
  return (
    <Tile
      id="pipelines"
      wide
      title={c.tiles.pipelines}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <RunDurations view={view} c={c} />
      <RunsTable view={view} c={c} />
    </Tile>
  );
}

export function Gates({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.gates;
  const meta =
    t.checksEnforced === null ? null : (
      <p className="window" data-checks-enforced={String(t.checksEnforced)}>
        {t.checksEnforced ? c.checksEnforced.true : c.checksEnforced.false}
      </p>
    );
  return (
    <Tile id="gates" title={c.tiles.gates} state={t.state} reason={t.reason} c={c} meta={meta} wide>
      <GatePass view={view} c={c} />
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.ref}</th>
            <th>{c.cols.passing}</th>
            {t.required.map((g) => (
              <th key={`${g.workflow}/${g.gate}`}>
                <code>{g.gate}</code>
              </th>
            ))}
          </tr>
        </thead>
        <Rows rows={t.refs} columns={2 + t.required.length} kind="refs" empty={c.empties.refs}>
          {(ref) => {
            const by = new Map(ref.results.map((r) => [`${r.workflow}/${r.gate}`, r.conclusion]));
            return (
              <tr key={`${ref.kind}:${ref.ref}`} data-ref={`${ref.kind}:${ref.ref}`}>
                <td>
                  {c.refKinds[ref.kind] ?? ref.kind} <code>{ref.ref}</code>
                </td>
                <td>
                  {ref.passing}/{ref.total}
                </td>
                {t.required.map((g) => {
                  const conclusion = by.get(`${g.workflow}/${g.gate}`) ?? null;
                  return (
                    <td key={`${g.workflow}/${g.gate}`} data-state={conclusion ?? "unknown"}>
                      {conclusion ?? <span className="cell-unknown">{c.unknown}</span>}
                    </td>
                  );
                })}
              </tr>
            );
          }}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function Releases({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.releases;
  return (
    <Tile id="releases" title={c.tiles.releases} state={t.state} reason={t.reason} c={c}>
      {t.rows.length === 0 ? (
        <EmptyState kind="releases" title={c.empty.releases.title} why={c.empty.releases.why} />
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.cols.tag}</th>
              <th>{c.cols.commit}</th>
              <th>{c.cols.published}</th>
              <th>{c.cols.signing}</th>
              <th>{c.cols.deployedHere}</th>
            </tr>
          </thead>
          <tbody>
            {t.rows.map((row) => (
              <tr key={row.tag} data-tag={row.tag}>
                <td>
                  <code>{row.tag}</code>
                </td>
                <td>
                  <code title={row.sha}>{row.shortSha}</code>
                </td>
                <td>
                  <When value={row.publishedAt} c={c} />
                </td>
                <td data-state={row.signing ?? "unknown"}>
                  {row.signing === null ? (
                    <span className="cell-unknown">{c.unknown}</span>
                  ) : (
                    (c.signing[row.signing] ?? row.signing)
                  )}
                </td>
                <td>{row.deployedHere ? c.yes : c.no}</td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
    </Tile>
  );
}

export function Deployments({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.deployments;
  return (
    <Tile id="deployments" title={c.tiles.deployments} state={t.state} reason={t.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.environment}</th>
            <th>{c.cols.source}</th>
            <th>{c.cols.commit}</th>
            <th>{c.cols.builtAt}</th>
            <th>{c.cols.sbom}</th>
            <th>{c.cols.stamped}</th>
          </tr>
        </thead>
        <Rows rows={t.rows} columns={6} kind="deployments" empty={c.empties.deployments}>
          {(row) => (
            <tr key={row.environment} data-environment={row.environment}>
              <td>
                <code>{row.environment}</code>
              </td>
              <td>
                <code>{row.source}</code>
              </td>
              <td>
                {row.sha === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  <code title={row.sha}>{row.shortSha}</code>
                )}
              </td>
              <td>
                <When value={row.builtAt} c={c} />
              </td>
              <td>
                {row.sbomDigest === null ? (
                  <span className="cell-unknown">{c.unknown}</span>
                ) : (
                  <code className="sub">{row.sbomDigest}</code>
                )}
              </td>
              <td data-state={row.stamped ? "ok" : "attention"}>{row.stamped ? c.yes : c.no}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

/** Argo CD and the deploy canary: a statement of absence, with the rollback
 * button present, disabled, and saying why — there is nothing to roll back. */
export function NotDeployed({ view, c }: { view: CicdView; c: C }): ReactElement {
  return (
    <>
      <Tile id="argo_cd" title={c.tiles.argoCd} state="ok" reason={null} c={c}>
        <p className="window" data-deployed="false" data-basis={view.argoCd.basis}>
          {c.notDeployed[view.argoCd.basis] ?? view.argoCd.basis}
        </p>
        <p className="window">{c.rollbackUnavailable}</p>
        <button type="button" disabled data-reason="no_deploy_controller">
          {c.rollback}
        </button>
      </Tile>
      <Tile id="canary" title={c.tiles.canary} state="ok" reason={null} c={c}>
        <p className="window" data-deployed="false" data-basis={view.canary.basis}>
          {c.notDeployed[view.canary.basis] ?? view.canary.basis}
        </p>
      </Tile>
    </>
  );
}
