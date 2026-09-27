/**
 * INT-366 — the access review, rendered (files/08 §2.7, §3 Access & identity):
 * the console review's age and what it makes read-only, each section with its
 * reviewer and digest, every staff account with its roles, last login and
 * distance to the 60-day auto-disable, and the offboardings still open.
 *
 * A synchronous, presentational tree over the loader's state; the App Router
 * page renders it on the server and the e2e spec renders the very same tree.
 * Read-only: signing, countersigning and offboarding are the API's routes, each
 * behind a fresh WebAuthn assertion (docs/runbooks/access-review.md). No
 * `style` attribute anywhere — the CSP has no `unsafe-inline`.
 */
import type { ReactElement } from "react";

import { ConsoleNav } from "../ops/nav";
import { Cell, ScrollTable } from "../ops/tiles";
import { COPY, type AccessCopy, type Lang } from "./copy";
import type { AccessState } from "./load";
import type { AccessView } from "./module";

type C = AccessCopy;

function Status({ view, c }: { view: AccessView; c: C }): ReactElement {
  return (
    <section data-tile="status" className="tile tile-ok" aria-labelledby="tile-status">
      <header className="tile-head">
        <h2 id="tile-status">{c.status.title}</h2>
      </header>
      <dl className="facts">
        <dt>{c.status.age}</dt>
        <dd data-review-age={view.age ?? "never"}>
          {view.neverReviewed ? c.status.neverReviewed : <Cell value={view.age} c={c} />}
        </dd>
        <dt>{c.status.readOnly}</dt>
        <dd data-read-only={view.readOnly.join(",")}>
          {view.readOnly.length === 0
            ? c.none
            : view.readOnly.map((role) => <code key={role}>{role} </code>)}
        </dd>
      </dl>
      <p className="window">{c.status.rule}</p>
    </section>
  );
}

function Sections({ view, c }: { view: AccessView; c: C }): ReactElement {
  return (
    <section data-tile="sections" className="tile tile-ok" aria-labelledby="tile-sections">
      <header className="tile-head">
        <h2 id="tile-sections">{c.sections.title}</h2>
      </header>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.sections.section}</th>
            <th>{c.sections.signer}</th>
            <th>{c.sections.countersigner}</th>
            <th>{c.sections.holders}</th>
            <th>{c.sections.digest}</th>
            <th>{c.sections.lastSigned}</th>
            <th>{c.sections.age}</th>
            <th>{c.sections.overdue}</th>
          </tr>
        </thead>
        <tbody>
          {view.sections.map((row) => (
            <tr key={row.section} data-section={row.section} data-overdue={String(row.overdue)}>
              <td>
                <code>{row.section}</code>
              </td>
              <td>
                <code>{row.signerRole}</code>
                {row.signerTenant === null ? null : <> · {row.signerTenant}</>}
              </td>
              <td>{row.external ? c.sections.external : c.sections.secondPerson}</td>
              <td>{row.holders}</td>
              <td>
                <code>{row.digest}</code>
              </td>
              <td>{row.lastSignedAt === null ? c.never : <time>{row.lastSignedAt}</time>}</td>
              <td>
                <Cell value={row.age} c={c} />
              </td>
              <td>{row.overdue ? c.yes : c.no}</td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </section>
  );
}

function Holders({ view, c }: { view: AccessView; c: C }): ReactElement {
  const h = c.holders;
  return (
    <section data-tile="holders" className="tile tile-ok" aria-labelledby="tile-holders">
      <header className="tile-head">
        <h2 id="tile-holders">{h.title}</h2>
      </header>
      <ScrollTable>
        <thead>
          <tr>
            <th>{h.subject}</th>
            <th>{h.username}</th>
            <th>{h.enabled}</th>
            <th>{h.roles}</th>
            <th>{h.tenant}</th>
            <th>{h.lastLogin}</th>
            <th>{h.idle}</th>
            <th>{h.untilDisable}</th>
            <th>{h.lastAction}</th>
            <th>{h.lastReviewed}</th>
          </tr>
        </thead>
        <tbody>
          {view.holders.map((row) => (
            <tr key={row.subject} data-subject={row.subject} data-dormant={String(row.dormant)}>
              <td>
                <code>{row.subject}</code>
              </td>
              <td>{row.username ?? c.none}</td>
              <td>{row.enabled ? c.yes : c.no}</td>
              <td>{row.roles.join(", ")}</td>
              <td>{row.tenant ?? c.none}</td>
              <td>{row.lastLoginAt === null ? c.never : <time>{row.lastLoginAt}</time>}</td>
              <td>{row.idle}</td>
              <td>{!row.enabled ? c.none : row.dormant ? h.dormant : row.untilDisable}</td>
              <td>
                {row.lastConsoleActionAt === null ? c.none : <time>{row.lastConsoleActionAt}</time>}
              </td>
              <td>{row.lastReviewedAt === null ? c.never : <time>{row.lastReviewedAt}</time>}</td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </section>
  );
}

function Offboardings({ view, c }: { view: AccessView; c: C }): ReactElement {
  const o = c.offboardings;
  return (
    <section data-tile="offboardings" className="tile tile-ok" aria-labelledby="tile-offboardings">
      <header className="tile-head">
        <h2 id="tile-offboardings">{o.title}</h2>
      </header>
      {view.offboardings.length === 0 ? (
        <p>{o.none}</p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{o.id}</th>
              <th>{o.subject}</th>
              <th>{o.reason}</th>
              <th>{o.pending}</th>
              <th>{o.failed}</th>
            </tr>
          </thead>
          <tbody>
            {view.offboardings.map((row) => (
              <tr key={row.id} data-offboarding={row.id}>
                <td>
                  <code>{row.id}</code>
                </td>
                <td>
                  <code>{row.subject}</code>
                </td>
                <td>
                  <code>{row.reason}</code>
                </td>
                <td>{row.pending.join(", ") || c.none}</td>
                <td>{row.failed.join(", ") || c.none}</td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
    </section>
  );
}

export function AccessConsole({ state, lang }: { state: AccessState; lang: Lang }): ReactElement {
  const c = COPY[lang];
  if (state.kind !== "console") {
    const attribute =
      state.kind === "not_admitted"
        ? { "data-refusal": state.reason }
        : { "data-unavailable": state.reason };
    const text =
      state.kind === "not_admitted" ? c.refusals[state.reason] : c.unavailable[state.reason];
    return (
      <main lang={lang} className="ops" data-page="access">
        <ConsoleNav current="access" lang={lang} />
        <h1>{c.title}</h1>
        <p className="refusal" {...attribute}>
          {text}
        </p>
      </main>
    );
  }
  const view = state.view;
  return (
    <main lang={lang} className="ops" data-page="access">
      <header className="page-head">
        <ConsoleNav current="access" lang={lang} />
        <h1>{c.title}</h1>
        <p>
          {c.generatedAt}: <time>{view.generatedAt}</time>
        </p>
      </header>
      <div className="grid">
        <Status view={view} c={c} />
        <Sections view={view} c={c} />
        <Holders view={view} c={c} />
        <Offboardings view={view} c={c} />
      </div>
    </main>
  );
}
