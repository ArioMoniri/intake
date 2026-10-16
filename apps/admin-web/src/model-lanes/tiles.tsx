/**
 * INT-428 — the Model lanes page's read-only tiles: the deployment's data
 * class and the control record, each lane and configured role with what it
 * is configured to and what serves it now, latency and cost per route and
 * provider, each lane's model options, and the hosted providers.
 *
 * Built from the ops console's primitives (`../ops/tiles`), so every tile
 * carries `data-tile` / `data-tile-state` and an unknown tile shows the word,
 * its reason and no figure (invariant 17). A cost nobody priced reads "price
 * not configured" and a self-hosted call reads "not metered" — words, never a
 * zero. No `style` attribute anywhere.
 */
import type { ReactElement } from "react";

import { Cell, ScrollTable, Tile } from "../ops/tiles";
import type { ModelLanesCopy } from "./copy";
import type {
  ModelLanesView,
  ModelRefView,
  ProviderView,
  RoleView,
  SettingView,
  UsageView,
} from "./view";

type C = ModelLanesCopy;

function word(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}

function YesNo({ value, c }: { value: boolean; c: C }): ReactElement {
  return <span data-state={value ? "ok" : "attention"}>{value ? c.yes : c.no}</span>;
}

export function Model({ m, c }: { m: ModelRefView | null; c: C }): ReactElement {
  if (m === null) return <span className="cell-unknown">{c.none}</span>;
  return (
    <span data-model={m.key}>
      <code title={m.wire}>{m.modelId}</code> ·{" "}
      <code title={m.version} data-version={m.version}>
        {m.shortVersion}
      </code>
      {m.shortPin === null ? null : (
        <>
          {" "}
          ·{" "}
          <code className="sub" title={m.sha256 ?? ""}>
            {m.shortPin}
          </code>
        </>
      )}
    </span>
  );
}

function Configured({ s, c }: { s: SettingView | null; c: C }): ReactElement {
  if (s === null) return <span className="cell-unknown">{c.unknown}</span>;
  return (
    <span data-route={s.route}>
      {word(c.routes, s.route)} · {s.model === null ? c.laneDefault : <code>{s.model}</code>}
      {s.fallback === null ? null : (
        <span className="sub">
          {" "}
          · {c.cols.fallback}: {s.fallback}
          {s.fallbackModel === null ? null : <> · {s.fallbackModel}</>}
        </span>
      )}
    </span>
  );
}

export function DeploymentTile({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  const d = view.deployment;
  const ctl = view.control;
  return (
    <Tile
      id="deployment"
      title={c.tiles.deployment}
      state={d === null ? "unknown" : "ok"}
      reason={d === null ? view.reason : null}
      c={c}
    >
      {d === null ? null : (
        <dl className="facts" data-effective={d.effective}>
          <dt>{c.cols.declared}</dt>
          <dd data-declared={d.declared}>{word(c.dataClasses, d.declared)}</dd>
          <dt>{c.cols.bound}</dt>
          <dd>{d.bound === null ? c.none : word(c.dataClasses, d.bound)}</dd>
          <dt>{c.cols.effective}</dt>
          <dd data-state={d.effective === "real_phi" ? "attention" : "ok"}>
            {word(c.dataClasses, d.effective)}
          </dd>
          <dt>{c.cols.hostedLanes}</dt>
          <dd data-hosted-lanes={String(d.hostedLanes)}>{d.hostedLanes ? c.yes : c.no}</dd>
          <dt>{c.cols.revision}</dt>
          <dd data-control-state={ctl.state}>
            {ctl.state === "unknown" ? (
              <span className="cell-unknown">
                {c.unknown} · {word(c.reasons, ctl.reason ?? "")} <code>{ctl.reason}</code>
              </span>
            ) : (
              ctl.revision
            )}
          </dd>
          <dt>{c.cols.hostedDisabled}</dt>
          <dd data-hosted-disabled={String(ctl.hostedDisabled)}>
            {ctl.hostedDisabled === null ? (
              <span className="cell-unknown">{c.unknown}</span>
            ) : ctl.hostedDisabled ? (
              c.yes
            ) : (
              c.no
            )}
          </dd>
          <dt>{c.cols.lastChange}</dt>
          <dd>{ctl.lastChange === null ? c.none : word(c.changes, ctl.lastChange)}</dd>
          <dt>{c.cols.changedBy}</dt>
          <dd>{ctl.changedBy === null ? c.none : <code>{ctl.changedBy}</code>}</dd>
          <dt>{c.cols.changedAt}</dt>
          <dd>{ctl.changedAt === null ? c.none : <time>{ctl.changedAt}</time>}</dd>
          <dt>{c.cols.approvedBy}</dt>
          <dd>{ctl.approvedBy === null ? c.none : <code>{ctl.approvedBy}</code>}</dd>
        </dl>
      )}
    </Tile>
  );
}

function RoleRow({ row, c }: { row: RoleView; c: C }): ReactElement {
  const s = row.serving;
  return (
    <tr
      data-role={row.role}
      data-available={String(s.available)}
      data-reason={s.reason}
      data-identity={row.selfHosted.identity}
    >
      <td>
        <code>{row.role}</code>
        {row.isLane ? null : <span className="sub"> {word(c.lanes, row.lane)}</span>}
      </td>
      <td>
        <Configured s={row.setting} c={c} />
      </td>
      <td data-serving-route={s.route ?? "none"}>
        {s.route === null ? (
          <span className="cell-unknown">{c.none}</span>
        ) : (
          <>
            {word(c.routes, s.route)} · <Model m={s.model} c={c} />
          </>
        )}
      </td>
      <td data-state={s.available ? "ok" : "blocked"}>
        {word(c.reasons, s.reason)} <code>{s.reason}</code>
      </td>
      <td>
        <YesNo value={s.qualified} c={c} />
      </td>
      <td data-clinical-evidence={String(s.clinicalEvidence)}>
        {s.clinicalEvidence ? c.yes : c.no}
      </td>
      <td data-state={row.selfHosted.identity}>
        {word(c.identity, row.selfHosted.identity)}
        {row.selfHosted.expected === null ? null : (
          <>
            {" "}
            · <Model m={row.selfHosted.expected} c={c} />
          </>
        )}
      </td>
    </tr>
  );
}

export function LanesTile({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  const known = view.deployment !== null;
  return (
    <Tile
      id="lanes"
      title={c.tiles.lanes}
      state={known ? "ok" : "unknown"}
      reason={known ? null : view.reason}
      c={c}
    >
      <ScrollTable>
        <thead>
          <tr>
            <th>{c.cols.role}</th>
            <th>{c.cols.configured}</th>
            <th>{c.cols.serving}</th>
            <th>{c.cols.reason}</th>
            <th>{c.cols.qualified}</th>
            <th>{c.cols.clinicalEvidence}</th>
            <th>{c.cols.identity}</th>
          </tr>
        </thead>
        <tbody>
          {[...view.lanes, ...view.roles].map((row) => (
            <RoleRow key={row.role} row={row} c={c} />
          ))}
        </tbody>
      </ScrollTable>
    </Tile>
  );
}

function Cost({ u, c }: { u: UsageView; c: C }): ReactElement {
  if (u.cost.state === "known") return <span data-cost-state="known">{u.cost.usd}</span>;
  return (
    <span className="cell-unknown" data-cost-state={u.cost.state}>
      {word(c.cost, u.cost.state)}
    </span>
  );
}

export function UsageTile({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  const reason = view.deployment === null ? view.reason : view.usage.reason;
  const rows = view.lanes.flatMap((lane) => (lane.usage ?? []).map((u) => ({ lane, u })));
  return (
    <Tile
      id="usage"
      title={c.tiles.usage}
      state={reason === null ? "ok" : "unknown"}
      reason={reason}
      c={c}
      meta={
        <p className="window">
          {c.window}: {view.usage.window}
        </p>
      }
    >
      {rows.length === 0 ? (
        <p className="window">{c.none}</p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.cols.role}</th>
              <th>{c.cols.route}</th>
              <th>{c.cols.provider}</th>
              <th>{c.cols.p50}</th>
              <th>{c.cols.p95}</th>
              <th>
                {c.cols.calls} ({view.usage.window})
              </th>
              <th>
                {c.cols.cost} ({view.usage.window})
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ lane, u }) => (
              <tr
                key={`${lane.lane}/${u.route}/${u.provider}`}
                data-usage={`${lane.lane}/${u.route}`}
              >
                <td>
                  <code>{lane.lane}</code>
                </td>
                <td>{u.route}</td>
                <td>{u.provider}</td>
                <td>
                  <Cell value={u.p50} c={c} />
                </td>
                <td>
                  <Cell value={u.p95} c={c} />
                </td>
                <td>
                  <Cell value={u.calls} c={c} />
                </td>
                <td>
                  <Cost u={u} c={c} />
                </td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
    </Tile>
  );
}

export function OptionsTiles({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  return (
    <>
      {view.options.map((o) => (
        <Tile
          key={o.lane}
          id={`options_${o.lane}`}
          title={`${c.tiles.options} — ${word(c.lanes, o.lane)}`}
          state="ok"
          reason={null}
          c={c}
          meta={
            <p className="window" data-gated={String(o.gated)}>
              {c.cols.gated}: {o.gated ? c.yes : c.no}
            </p>
          }
        >
          <ScrollTable>
            <thead>
              <tr>
                <th>{c.cols.component}</th>
                <th>{c.cols.model}</th>
                <th>{c.cols.attested}</th>
                <th>{c.cols.identity}</th>
                <th>{c.cols.qualified}</th>
              </tr>
            </thead>
            <tbody>
              {o.selfHosted.map((s) => (
                <tr
                  key={s.component}
                  data-option={s.component}
                  data-selectable={String(s.selectable)}
                >
                  <td>
                    <code>{s.component}</code>
                    {s.jurisdiction === null ? null : (
                      <span className="sub"> {s.jurisdiction}</span>
                    )}
                  </td>
                  <td>
                    <Model m={s.model} c={c} />
                  </td>
                  <td>
                    <YesNo value={s.attested} c={c} />
                  </td>
                  <td data-state={s.identity}>{word(c.identity, s.identity)}</td>
                  <td>
                    <YesNo value={s.qualified} c={c} />
                  </td>
                </tr>
              ))}
              {o.hosted.map((h) => (
                <tr key={`${h.provider}/${h.model.key}`} data-option={h.model.key}>
                  <td>
                    {h.provider}
                    {h.isDefault ? <span className="sub"> {c.cols.isDefault}</span> : null}
                  </td>
                  <td>
                    <Model m={h.model} c={c} />
                  </td>
                  <td data-probe={h.probe.state}>
                    {c.cols.probe}: {word(c.probe, h.probe.state)}
                    {h.probe.reason === null ? null : <code> {h.probe.reason}</code>}
                  </td>
                  <td>{c.none}</td>
                  <td>
                    <YesNo value={h.qualified} c={c} />
                  </td>
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </Tile>
      ))}
    </>
  );
}

function KeyState({ p, c }: { p: ProviderView; c: C }): ReactElement {
  const k = p.key;
  if (k.state === "set" && k.last4 !== null) {
    return (
      <span data-key-state="set">
        {c.keyStates.set} · …<code>{k.last4}</code>
      </span>
    );
  }
  return (
    <span className="cell-unknown" data-key-state={k.state}>
      {word(c.keyStates, k.state)}
    </span>
  );
}

export function ProvidersTile({ view, c }: { view: ModelLanesView; c: C }): ReactElement {
  return (
    <Tile id="providers" title={c.tiles.providers} state="ok" reason={null} c={c}>
      {view.providers.length === 0 ? (
        <p className="window">{c.none}</p>
      ) : (
        <ScrollTable>
          <thead>
            <tr>
              <th>{c.cols.provider}</th>
              <th>{c.cols.egressRow}</th>
              <th>{c.cols.key}</th>
              <th>{c.cols.setAt}</th>
              <th>{c.cols.ready}</th>
            </tr>
          </thead>
          <tbody>
            {view.providers.map((p) => (
              <tr key={p.provider} data-provider={p.provider}>
                <td>{p.provider}</td>
                <td>
                  <code>{p.egressRow}</code> · {c.cols.listed}: {p.listed ? c.yes : c.no}
                </td>
                <td>
                  <KeyState p={p} c={c} />
                </td>
                <td>{p.key.setAt === null ? c.none : <time>{p.key.setAt}</time>}</td>
                <td data-state={p.ready.state} data-ready-reason={p.ready.reason ?? ""}>
                  {word(c.ready, p.ready.state)}
                  {p.ready.reason === null ? null : (
                    <>
                      {" "}
                      · {word(c.reasons, p.ready.reason)} <code>{p.ready.reason}</code>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      )}
    </Tile>
  );
}
