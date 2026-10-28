/**
 * INT-182 — the Voice page's control half: each tenant's control, the
 * ceremonies awaiting a second key, and the four forms.
 *
 * The forms are plain HTML posting to this app's own `/voice/action` (no
 * client script — the CSP has no `unsafe-inline`); `./actions` decides what
 * may be sent and the admin API decides everything else. Tier and the roles
 * who may request and approve are read off the payload's control catalogue —
 * the server's `DangerousAction` registry — never from a list kept here.
 *
 * INT-563 (ADR-043): each pending ceremony carries an **Onayla** form that
 * starts the four-eyes step-up — a fresh password-and-passkey login at
 * Keycloak, proven to the API, spent once on that one action (files/08 §2.3).
 */
import type { ReactElement } from "react";

import { Cell, Rows, ScrollTable, Tile } from "../ops/tiles";
import { ApproveForm } from "../step-up/form";
import type { Lang, VoiceCopy } from "./copy";
import type { ControlView, VoiceView } from "./module";

type C = VoiceCopy;

function Profile({ value, c }: { value: string | null; c: C }): ReactElement {
  if (value === null) return <span className="cell-unknown">{c.none}</span>;
  return <code title={c.profiles[value] ?? value}>{value}</code>;
}

export function ControlsTile({ view, c }: { view: VoiceView; c: C }): ReactElement {
  const t = view.controls;
  return (
    <Tile id="controls" title={c.tiles.controls} state={t.state} reason={t.reason} c={c}>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.tenant}</th>
            <th>{c.cols.killSwitch}</th>
            <th>{c.cols.defaultProfile}</th>
            <th>{c.cols.effectiveProfile}</th>
            <th>{c.cols.canary}</th>
            <th>{c.cols.revision}</th>
            <th>{c.cols.changedBy}</th>
            <th>{c.cols.changedAt}</th>
            <th>{c.cols.approvedBy}</th>
          </tr>
        </thead>
        <Rows rows={t.tenants} columns={9} kind="tenants" empty={c.empties.tenants}>
          {(row) => (
            <tr
              key={row.tenantId}
              data-tenant={row.tenantId}
              data-kill-switch={row.killSwitch ? "engaged" : "off"}
            >
              <td>
                <code>{row.tenantId}</code>
              </td>
              <td>{row.killSwitch ? c.yes : c.no}</td>
              <td>
                <Profile value={row.defaultProfile} c={c} />
              </td>
              <td data-effective={row.effectiveProfile}>
                <Profile value={row.effectiveProfile} c={c} />
              </td>
              <td>{row.canary ?? c.none}</td>
              <td>{row.revision}</td>
              <td>
                <Cell value={row.changedBy} c={c} />
              </td>
              <td>
                <Cell value={row.changedAt} c={c} />
              </td>
              <td>{row.approvedBy ?? c.none}</td>
            </tr>
          )}
        </Rows>
      </ScrollTable>
    </Tile>
  );
}

export function PendingTile({
  view,
  lang,
  c,
}: {
  view: VoiceView;
  lang: Lang;
  c: C;
}): ReactElement {
  const t = view.pending;
  return (
    <Tile id="pending" title={c.tiles.pending} state={t.state} reason={t.reason} c={c}>
      <p className="window">{c.approveStepUp}</p>
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.action}</th>
            <th>{c.cols.control}</th>
            <th>{c.cols.tenant}</th>
            <th>{c.cols.change}</th>
            <th>{c.cols.requestedRole}</th>
            <th>{c.cols.expiresAt}</th>
            <th>{c.approve}</th>
          </tr>
        </thead>
        <Rows rows={t.actions} columns={7} kind="pending" empty={c.empties.pending}>
          {(row) => (
            <tr key={row.actionId} data-action={row.actionId}>
              <td>
                <code>{row.actionId}</code>
              </td>
              <td>{c.controlNames[row.control] ?? row.control}</td>
              <td>
                <code>{row.tenantId}</code>
              </td>
              <td>
                {row.profile === null ? c.none : <Profile value={row.profile} c={c} />}
                {row.weight === null ? null : <> · {row.weight}</>}
              </td>
              <td>
                <code>{row.requestedRole}</code>
              </td>
              <td>
                <time>{row.expiresAt}</time>
              </td>
              <td>
                <ApproveForm actionId={row.actionId} from="voice" lang={lang} label={c.approve} />
              </td>
            </tr>
          )}
        </Rows>
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
  view: VoiceView;
  lang: Lang;
  c: C;
}): ReactElement {
  const needsProfile = control.control === "default_profile" || control.control === "canary";
  const oneKey = control.tier === 1;
  return (
    <form
      action="/voice/action"
      method="post"
      data-control={control.control}
      data-tier={String(control.tier)}
      className="tile"
      autoComplete="off"
    >
      <header className="tile-head">
        <h2>{c.controlNames[control.control] ?? control.control}</h2>
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
        {c.forms.tenant}{" "}
        <input name="tenant" required pattern="[a-z0-9][a-z0-9_.\-]{0,63}" maxLength={64} />
      </label>
      {needsProfile ? (
        <label>
          {c.forms.profile}{" "}
          <select name="profile" required>
            {view.profiles.map((p) => (
              <option key={p} value={p}>
                {c.profiles[p] ?? p}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {control.control === "canary" ? (
        <label>
          {c.forms.weight} <input type="number" min="0" max="100" step="1" name="weight" required />
        </label>
      ) : null}
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

export function ControlForms({
  view,
  lang,
  c,
}: {
  view: VoiceView;
  lang: Lang;
  c: C;
}): ReactElement {
  return (
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
  );
}
