/**
 * INT-564 — the Compliance module, rendered (INT-189, files/08 §4): the data
 * transfer register with each row's lawful basis and notification deadline,
 * consent coverage, the open data subject requests, the last day of the
 * ids-only audit search, and the evidence bundle's outline.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * Read-only. Consent counts from 1 to 9 are shown as "fewer than 10" (the
 * console's k ≥ 10 floor, files/10 §9); the audit search shows its newest rows
 * only. No `style` attribute anywhere — the CSP has no `unsafe-inline`.
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav } from "../ops/nav";
import { Rows, ScrollTable, Tile } from "../ops/tiles";
import { RefusedPage } from "../ui/states";
import { COPY, type ComplianceCopy } from "./copy";
import type { ComplianceState } from "./load";
import type { CompliancePresentation, VendorRow } from "./module";

type C = ComplianceCopy;

/** The console's k-anonymity floor (files/06 §8, files/10 §9 "k ≥ 10"). */
export const K_FLOOR = 10;
/** The audit tile's cap: the newest rows of the last day, never the chain. */
export const AUDIT_ROWS = 100;

/** A count as the page may show it: 0, or at least the floor. */
export function floored(count: number, c: C): string {
  if (count > 0 && count < K_FLOOR) return c.belowFloor;
  return count.toLocaleString("en-GB", { useGrouping: false });
}

function cell(row: VendorRow, label: string): string {
  return row.cells.find((item) => item.label === label)?.value ?? "";
}

function Transfers({ view, c }: { view: CompliancePresentation; c: C }): ReactElement {
  return (
    <Tile id="transfers" title={c.tiles.transfers} state="ok" reason={null} c={c} wide>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.host}</th>
            <th>{c.cols.purpose}</th>
            <th>{c.cols.category}</th>
            <th>{c.cols.basis}</th>
            <th>{c.cols.retention}</th>
            <th>{c.cols.dataClass}</th>
            <th>{c.cols.transfers}</th>
            <th>{c.cols.bytes}</th>
            <th>{c.cols.notification}</th>
          </tr>
        </thead>
        <Rows rows={view.vendorRegister} columns={9} kind="transfers" empty={c.empties.transfers}>
          {(row) => (
            <tr key={row.host} data-host={row.host} data-overdue={row.notificationOverdue}>
              <td>
                <code>{row.host}</code>
              </td>
              <td>{cell(row, "purpose")}</td>
              <td>
                <code>{cell(row, "category")}</code>
              </td>
              <td>{cell(row, "basis")}</td>
              <td>{cell(row, "retention")}</td>
              <td>
                <code>{cell(row, "data class")}</code>
              </td>
              <td>{cell(row, "transfers")}</td>
              <td>{cell(row, "bytes").replace(/ bytes$/, "")}</td>
              <td>
                {row.notificationOverdue ? c.elapsed : c.dueBy} <time>{row.notificationDue}</time>
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Consents({ view, c }: { view: CompliancePresentation; c: C }): ReactElement {
  return (
    <Tile id="consents" title={c.tiles.consents} state="ok" reason={null} c={c}>
      <p className="window">{c.floorNote}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.scope}</th>
            <th>{c.cols.version}</th>
            <th>{c.cols.granted}</th>
            <th>{c.cols.withdrawn}</th>
          </tr>
        </thead>
        <Rows rows={view.consents} columns={4} kind="consents" empty={c.empties.consents}>
          {(row) => (
            <tr key={`${row.scope}@${row.version}`}>
              <td>
                <code>{row.scope}</code>
              </td>
              <td>
                <code>{row.version}</code>
              </td>
              <td>{floored(row.granted, c)}</td>
              <td>{floored(row.withdrawn, c)}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Dsar({ view, c }: { view: CompliancePresentation; c: C }): ReactElement {
  return (
    <Tile id="dsar" title={c.tiles.dsar} state="ok" reason={null} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.request}</th>
            <th>{c.cols.kind}</th>
            <th>{c.cols.status}</th>
            <th>{c.cols.dueAt}</th>
          </tr>
        </thead>
        <Rows rows={view.dsar} columns={4} kind="dsar" empty={c.empties.dsar}>
          {(row) => (
            <tr key={row.requestId} data-overdue={row.overdue}>
              <td>
                <code>{row.requestId}</code>
              </td>
              <td>
                <code>{row.kind}</code>
              </td>
              <td>
                <code>{row.status}</code>
              </td>
              <td>
                <time>{row.dueAt}</time> · {row.overdue ? c.overdue : c.onTime}
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Audit({ view, c }: { view: CompliancePresentation; c: C }): ReactElement {
  const newest = [...view.auditSearch].sort((a, b) => b.seq - a.seq).slice(0, AUDIT_ROWS);
  return (
    <Tile id="audit" title={c.tiles.audit} state="ok" reason={null} c={c} wide>
      <p className="window">{c.auditCap}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.seq}</th>
            <th>{c.cols.at}</th>
            <th>{c.cols.actor}</th>
            <th>{c.cols.action}</th>
          </tr>
        </thead>
        <Rows rows={newest} columns={4} kind="audit" empty={c.empties.audit}>
          {(row) => (
            <tr key={row.seq}>
              <td>{row.seq}</td>
              <td>
                <time>{row.occurredAt}</time>
              </td>
              <td>
                <code>{row.actor}</code>
              </td>
              <td>
                <code>{row.action}</code>
              </td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

function Evidence({ view, c }: { view: CompliancePresentation; c: C }): ReactElement {
  const bundle = view.evidence;
  return (
    <Tile id="evidence" title={c.tiles.evidence} state="ok" reason={null} c={c}>
      <dl className="facts">
        <dt>{c.generatedAt}</dt>
        <dd>
          <time>{bundle.generatedAt}</time>
        </dd>
        <dt>{c.legalRefs}</dt>
        <dd>{bundle.legalRefs.join(", ")}</dd>
        <dt>{c.digest}</dt>
        <dd>
          <code>{bundle.digest}</code>
        </dd>
        <dt>{c.sections}</dt>
        {bundle.sections.length === 0 ? (
          <dd>{c.empties.evidence.title}</dd>
        ) : (
          bundle.sections.map((section) => (
            <dd key={section.title} data-section={section.title}>
              <code>{section.title}</code> · {section.rows.length} {c.rows}
            </dd>
          ))
        )}
      </dl>
    </Tile>
  );
}

export function ComplianceConsole({
  state,
  lang,
}: {
  state: ComplianceState;
  lang: Lang;
}): ReactElement {
  const c = COPY[lang];
  if (state.kind === "not_admitted") {
    return (
      <RefusedPage page="compliance" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-refusal={state.reason}>
          {c.refusals[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <RefusedPage page="compliance" lang={lang} title={c.title} state={state}>
        <p className="refusal" data-unavailable={state.reason}>
          {c.unavailable[state.reason]}
        </p>
      </RefusedPage>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="compliance">
      <header className="page-head">
        <ConsoleNav current="compliance" lang={lang} />
        <h1>{c.title}</h1>
      </header>
      <section className="band" aria-labelledby="band-transfers">
        <h2 id="band-transfers" className="band-head">
          {c.tiles.transfers}
        </h2>
        <div className="grid">
          <Transfers view={view} c={c} />
          <Consents view={view} c={c} />
          <Dsar view={view} c={c} />
        </div>
      </section>
      <section className="band" aria-labelledby="band-evidence">
        <h2 id="band-evidence" className="band-head">
          {c.tiles.evidence}
        </h2>
        <div className="grid">
          <Evidence view={view} c={c} />
          <Audit view={view} c={c} />
        </div>
      </section>
    </main>
  );
}
