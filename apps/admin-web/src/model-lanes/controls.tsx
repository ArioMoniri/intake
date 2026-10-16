/**
 * INT-428 — the Model lanes page's control half: the ceremonies awaiting a
 * second key and the forms.
 *
 * The forms are plain HTML posting to this app's own `/model-lanes/action`
 * (no client script — the CSP has no `unsafe-inline`); `./actions` decides
 * what may be sent and the admin API decides everything else.
 *
 * - **Tier 1, always present:** "Disable hosted lanes" and "Switch to GPU /
 *   self-hosted" — the safe direction, one key.
 * - **Tier 2, requests only:** a route-and-model switch for every lane and
 *   configured role, offering only what this deployment can serve (a hosted
 *   route and hosted models only where hosted lanes exist; self-hosted models
 *   only when attested); the release of a hosted-lane kill switch, only while
 *   it is engaged; and a provider key per provider, only where hosted lanes
 *   exist. There is no `mock` option anywhere.
 * - **The key field** is `type="password"` and is never given a value: the
 *   page has nothing to put in it, and after a post it renders empty.
 *
 * There is no approve form. Approval needs a fresh single-use WebAuthn
 * assertion (files/08 §2.3), and a script-free page cannot mint one; the
 * button is present, disabled, and says why.
 */
import type { ReactElement, ReactNode } from "react";

import { ScrollTable, Tile } from "../ops/tiles";
import type { ModelLanesAction } from "./actions";
import type { Lang, ModelLanesCopy } from "./copy";
import { LANES, PROVIDERS, REASON_CLASSES } from "./payload";
import type { LaneOptionsView, ModelLanesView, ProviderView, RoleView } from "./view";

type C = ModelLanesCopy;

export function PendingTile({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  return (
    <Tile id="pending" title={c.tiles.pending} state="ok" reason={null} c={c}>
      <p className="window">{c.approveNeedsStepUp}</p>
      {view.pending.length === 0 ? (
        <p className="window">{c.none}</p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.cols.action}</th>
              <th>{c.cols.ceremony}</th>
              <th>{c.cols.tier}</th>
              <th>{c.cols.state}</th>
              <th>{c.cols.approverRole}</th>
              <th>{c.cols.expiresAt}</th>
              <th>{c.approve}</th>
            </tr>
          </thead>
          <tbody>
            {view.pending.map((row) => (
              <tr key={row.actionId} data-action={row.actionId} data-ceremony={row.ceremony}>
                <td>
                  <code>{row.actionId}</code>
                </td>
                <td>{c.ceremonies[row.ceremony] ?? row.ceremony}</td>
                <td>{row.tier}</td>
                <td data-state={row.state}>{c.pendingStates[row.state] ?? row.state}</td>
                <td>{row.approverRole === null ? c.none : <code>{row.approverRole}</code>}</td>
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
      )}
    </Tile>
  );
}

function ControlForm({
  action,
  tier,
  title,
  note,
  submit,
  target,
  lang,
  c,
  children,
}: {
  action: ModelLanesAction;
  tier: 1 | 2;
  title: string;
  note?: string;
  submit: string;
  target?: string;
  lang: Lang;
  c: C;
  children?: ReactNode;
}): ReactElement {
  return (
    <form
      action="/model-lanes/action"
      method="post"
      data-control={action}
      data-tier={String(tier)}
      data-target={target}
      className="tile"
      autoComplete="off"
    >
      <header className="tile-head">
        <h2>{title}</h2>
      </header>
      <p className="window">{tier === 1 ? c.forms.tier1 : c.forms.tier2}</p>
      {note === undefined ? null : <p className="window">{note}</p>}
      <input type="hidden" name="action" value={action} />
      <input type="hidden" name="lang" value={lang} />
      {children}
      <label>
        {c.forms.reasonClass}{" "}
        <select name="reason_class" required>
          {REASON_CLASSES.map((r) => (
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
      <button type="submit">{submit}</button>
    </form>
  );
}

function hostedKeys(o: LaneOptionsView | undefined, provider: string): string[] {
  return (o?.hosted ?? []).filter((h) => h.provider === provider).map((h) => h.model.key);
}

function SwitchForm({
  row,
  view,
  lang,
  c,
}: {
  row: RoleView;
  view: ModelLanesView;
  lang: Lang;
  c: C;
}): ReactElement {
  const options = view.options.find((o) => o.lane === row.lane);
  const selfHosted = (options?.selfHosted ?? []).flatMap((s) =>
    s.selectable && s.model !== null ? [s.model.key] : [],
  );
  const hosted = view.routes.flatMap((route) =>
    route === "self_hosted" ? [] : [{ route, keys: hostedKeys(options, route.slice(7)) }],
  );
  const offersHosted = hosted.length > 0;
  return (
    <ControlForm
      action="route_switch"
      tier={2}
      title={`${c.forms.switchTitle} · ${row.role}`}
      submit={c.forms.request}
      target={row.role}
      lang={lang}
      c={c}
    >
      <input type="hidden" name="role" value={row.role} />
      <label>
        {c.forms.route}{" "}
        <select name="route" required defaultValue={row.setting?.route ?? "self_hosted"}>
          {view.routes.map((route) => (
            <option key={route} value={route}>
              {c.routes[route] ?? route}
            </option>
          ))}
        </select>
      </label>
      <label>
        {c.forms.model}{" "}
        <select name="model" defaultValue={row.setting?.model ?? ""}>
          <option value="">{c.laneDefault}</option>
          <optgroup label={c.forms.selfHostedGroup}>
            {selfHosted.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </optgroup>
          {hosted.map((h) => (
            <optgroup
              key={h.route}
              label={`${c.forms.hostedGroup} · ${c.routes[h.route] ?? h.route}`}
            >
              {h.keys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      {offersHosted ? (
        <>
          <label>
            {c.forms.fallback}{" "}
            <select name="fallback" defaultValue={row.setting?.fallback ?? ""}>
              <option value="">{c.none}</option>
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label>
            {c.forms.fallbackModel}{" "}
            <select name="fallback_model" defaultValue={row.setting?.fallbackModel ?? ""}>
              <option value="">{c.laneDefault}</option>
              {hosted.flatMap((h) =>
                h.keys.map((key) => (
                  <option key={`${h.route}/${key}`} value={key}>
                    {key}
                  </option>
                )),
              )}
            </select>
          </label>
        </>
      ) : null}
    </ControlForm>
  );
}

function KeyForm({ p, lang, c }: { p: ProviderView; lang: Lang; c: C }): ReactElement {
  return (
    <ControlForm
      action="key_set"
      tier={2}
      title={`${c.forms.keyTitle} · ${p.provider}`}
      note={c.forms.keyNote}
      submit={c.forms.request}
      target={p.provider}
      lang={lang}
      c={c}
    >
      <input type="hidden" name="provider" value={p.provider} />
      <label>
        {c.forms.apiKey}{" "}
        <input
          type="password"
          name="api_key"
          required
          minLength={20}
          maxLength={512}
          pattern="[A-Za-z0-9_.\-]{20,}"
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="off"
        />
      </label>
    </ControlForm>
  );
}

export function ControlForms({
  view,
  lang,
  c,
}: {
  view: ModelLanesView;
  lang: Lang;
  c: C;
}): ReactElement | null {
  const d = view.deployment;
  if (d === null) return null;
  const released = view.control.hostedDisabled === true && d.hostedLanes;
  return (
    <section className="band" aria-labelledby="band-controls">
      <h2 id="band-controls" className="band-head">
        {c.forms.section}
      </h2>
      <p className="window">{c.forms.policy}</p>
      <div className="grid">
        <ControlForm
          action="hosted_disable"
          tier={1}
          title={c.forms.disable}
          submit={c.forms.disable}
          lang={lang}
          c={c}
        />
        <ControlForm
          action="self_hosted_engage"
          tier={1}
          title={c.forms.engage}
          note={c.forms.engageNote}
          submit={c.forms.engage}
          lang={lang}
          c={c}
        >
          <fieldset>
            <legend>{c.forms.lanesField}</legend>
            {LANES.map((lane) => (
              <label key={lane}>
                <input type="checkbox" name="lanes" value={lane} defaultChecked />{" "}
                {c.lanes[lane] ?? lane}
              </label>
            ))}
          </fieldset>
        </ControlForm>
        {released ? (
          <ControlForm
            action="hosted_release"
            tier={2}
            title={c.forms.release}
            submit={c.forms.request}
            lang={lang}
            c={c}
          />
        ) : null}
        {[...view.lanes, ...view.roles].map((row) => (
          <SwitchForm key={row.role} row={row} view={view} lang={lang} c={c} />
        ))}
        {d.hostedLanes
          ? view.providers.map((p) => <KeyForm key={p.provider} p={p} lang={lang} c={c} />)
          : null}
      </div>
    </section>
  );
}
