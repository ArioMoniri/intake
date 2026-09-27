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

import { Cell, ScrollTable, Tile } from "../ops/tiles";
import type { CicdCopy } from "./copy";
import type { CicdView } from "./module";

type C = CicdCopy;

function When({ value, c }: { value: string | null; c: C }): ReactElement {
  return value === null ? <span className="cell-unknown">{c.unknown}</span> : <time>{value}</time>;
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
      title={c.tiles.pipelines}
      state={t.state}
      reason={t.reason}
      c={c}
      meta={meta}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.workflow}</th>
            <th>{c.cols.run}</th>
            <th>{c.cols.status}</th>
            <th>{c.cols.conclusion}</th>
            <th>{c.cols.commit}</th>
            <th>{c.cols.duration}</th>
            <th>{c.cols.updated}</th>
            <th>{c.cols.failedJobs}</th>
          </tr>
        </thead>
        <tbody>
          {t.workflows.flatMap((w) =>
            w.runs.map((run) => (
              <tr key={`${w.workflow}#${run.runNumber}`} data-workflow={w.workflow}>
                <td>
                  <code>{w.workflow}</code>
                </td>
                <td>{run.runNumber}</td>
                <td>{run.status}</td>
                <td data-state={run.conclusion}>{run.conclusion}</td>
                <td>
                  <code title={run.sha}>{run.shortSha}</code>
                </td>
                <td>
                  <Cell value={run.duration} c={c} />
                </td>
                <td>
                  <When value={run.updatedAt} c={c} />
                </td>
                <td data-failed-jobs={run.failedJobs.join(" ")}>
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
            )),
          )}
        </tbody>
      </ScrollTable>
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
    <Tile id="gates" title={c.tiles.gates} state={t.state} reason={t.reason} c={c} meta={meta}>
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
        <tbody>
          {t.refs.map((ref) => {
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
          })}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

export function Releases({ view, c }: { view: CicdView; c: C }): ReactElement {
  const t = view.releases;
  return (
    <Tile id="releases" title={c.tiles.releases} state={t.state} reason={t.reason} c={c}>
      {t.rows.length === 0 ? (
        <p className="window">{c.none}</p>
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
        <tbody>
          {t.rows.map((row) => (
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
          ))}
        </tbody>
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
