/**
 * INT-565 — the Security module, rendered (INT-192; files/08 §3; files/10 §7,
 * §9): SIEM summaries by detector, signal and severity; egress denials over a
 * stated window; the audit chain's verdict; the pen-test findings tracker.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * An unwired feed says so per detector rather than showing 0; an egress count
 * with no scrape behind it is an unknown tile with its cause and fill; the
 * audit chain shows its verdict and never a head (HB-I12). No `style`.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type SecurityCopy } from "./copy";
import type { SecurityState } from "./load";
import type { DistributionBar, SecurityPresentation } from "./module";

type C = SecurityCopy;

function Distribution({
  bars,
  head,
  kind,
  c,
}: {
  bars: readonly DistributionBar[];
  head: string;
  kind: string;
  c: C;
}): ReactElement {
  return (
    <ScrollTable>
      <thead>
        <tr>
          <th>{head}</th>
          <th>{c.count}</th>
        </tr>
      </thead>
      <Rows rows={bars} columns={2} kind={kind} empty={c.empties.distribution}>
        {(bar) => (
          <tr key={bar.key}>
            <td>
              <code>{bar.key}</code>
            </td>
            <td>{bar.count}</td>
          </tr>
        )}
      </Rows>
    </ScrollTable>
  );
}

function Siem({ view, c }: { view: SecurityPresentation; c: C }): ReactElement {
  const siem = view.siem;
  return (
    <Tile id="siem" title={c.tiles.siem} state="ok" reason={null} c={c} wide>
      <dl className="facts">
        <dt>{c.feedConfigured}</dt>
        <dd data-feed-configured={siem.feedConfigured}>{siem.feedConfigured ? c.yes : c.no}</dd>
        <dt>{c.total}</dt>
        <dd>{siem.total ?? <span className="cell-unknown">{c.unknown}</span>}</dd>
        <dt>{c.refused}</dt>
        <dd>{siem.refused ?? <span className="cell-unknown">{c.unknown}</span>}</dd>
      </dl>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.detector}</th>
            <th>{c.configured}</th>
            <th>{c.count}</th>
            <th>{c.why}</th>
          </tr>
        </thead>
        <Rows rows={siem.detectors} columns={4} kind="detectors" empty={c.empties.detectors}>
          {(detector) => (
            <tr key={detector.detector} data-detector={detector.detector}>
              <td>
                <code>{detector.detector}</code>
              </td>
              <td>{detector.configured ? c.yes : c.no}</td>
              <td>{detector.count ?? <span className="cell-unknown">{c.unknown}</span>}</td>
              <td>
                {detector.configured
                  ? ""
                  : detector.detector === "crowdsec"
                    ? c.detectorWhy.crowdsec
                    : c.detectorWhy.stream}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      {siem.feedConfigured ? (
        <>
          <Distribution bars={siem.bySignal} head={c.signal} kind="signals" c={c} />
          <Distribution bars={siem.bySeverity} head={c.severity} kind="severities" c={c} />
        </>
      ) : null}
      <p className="window">{c.siemNote}</p>
    </Tile>
  );
}

function Egress({ view, c }: { view: SecurityPresentation; c: C }): ReactElement {
  const egress = view.egressDenials;
  return (
    <Tile
      id="egress"
      title={c.tiles.egress}
      state={egress.sourceAvailable ? "ok" : "unknown"}
      reason={egress.sourceReason}
      c={c}
      meta={
        <span className="sub">
          {c.window}: {egress.window}
        </span>
      }
    >
      <dl className="facts">
        <dt>{c.denied}</dt>
        <dd>{egress.deniedTotal}</dd>
        <dt>{c.target}</dt>
        <dd>
          <code>{egress.target}</code>
        </dd>
      </dl>
      <p className="window">{c.egressNote}</p>
    </Tile>
  );
}

function AuditChain({ view, c }: { view: SecurityPresentation; c: C }): ReactElement {
  const chain = view.auditChain;
  return (
    <Tile id="audit_chain" title={c.tiles.auditChain} state="ok" reason={null} c={c}>
      <p className="badge" data-state={chain.ok ? "ok" : "blocked"} data-outcome={chain.outcome}>
        <code>{chain.outcome}</code>
      </p>
      <p>{c.outcomes[chain.outcome] ?? chain.outcome}</p>
      <dl className="facts">
        <dt>{c.attested}</dt>
        <dd>{chain.ok ? c.yes : c.no}</dd>
        <dt>{c.anchor}</dt>
        <dd>{chain.anchorAvailable ? c.yes : c.no}</dd>
      </dl>
      <p className="window">{c.chainNote}</p>
    </Tile>
  );
}

function Pentest({ view, c }: { view: SecurityPresentation; c: C }): ReactElement {
  const pentest = view.pentest;
  return (
    <Tile id="pentest" title={c.tiles.pentest} state="ok" reason={null} c={c} wide>
      <dl className="facts">
        <dt>{c.assessment}</dt>
        <dd data-assessment={pentest.assessmentState}>
          {c.assessments[pentest.assessmentState] ?? pentest.assessmentState}
        </dd>
        <dt>{c.lastAssessment}</dt>
        <dd>
          {pentest.lastAssessment === null ? (
            <span className="cell-unknown">—</span>
          ) : (
            <time>{pentest.lastAssessment}</time>
          )}
        </dd>
      </dl>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.severity}</th>
            <th>{c.sla}</th>
          </tr>
        </thead>
        <Rows rows={pentest.slaDaysBySeverity} columns={2} kind="sla" empty={c.empties.sla}>
          {(row) => (
            <tr key={row.severity} data-severity={row.severity}>
              <td>
                <code>{row.severity}</code>
              </td>
              <td>{row.days}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.finding}</th>
            <th>{c.severity}</th>
            <th>{c.status}</th>
            <th>{c.age}</th>
            <th>{c.discovered}</th>
          </tr>
        </thead>
        <Rows rows={pentest.findings} columns={5} kind="findings" empty={c.empties.findings}>
          {(finding) => (
            <tr key={finding.findingId} data-finding={finding.findingId}>
              <td>
                <code>{finding.findingId}</code>
              </td>
              <td>
                <code>{finding.severity}</code>
              </td>
              <td>
                <code>{finding.status}</code>
              </td>
              <td>{finding.ageDays ?? "—"}</td>
              <td>
                <time>{finding.discoveredOn}</time>
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
      <p className="window">{c.pentestNote}</p>
    </Tile>
  );
}

export function SecurityConsole({
  state,
  lang,
}: {
  state: SecurityState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="security" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="security" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="security">
      <header className="page-head">
        <ConsoleNav current="security" lang={lang} />
        <h1>{c.title}</h1>
      </header>
      <section className="band" aria-labelledby="band-detection">
        <h2 id="band-detection" className="band-head">
          {c.bands.detection}
        </h2>
        <div className="grid">
          <Siem view={view} c={c} />
          <Egress view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-integrity">
        <h2 id="band-integrity" className="band-head">
          {c.bands.integrity}
        </h2>
        <div className="grid">
          <AuditChain view={view} c={c} />
          <Pentest view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
