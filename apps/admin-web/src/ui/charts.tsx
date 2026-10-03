/**
 * INT-450 — the console's charts: server-rendered SVG, animated by the bundled
 * stylesheet alone.
 *
 * Adapted from EvilCharts (MIT, (c) 2026 Gurbinder,
 * https://github.com/legions-developer/evilcharts — `recharts-bar-chart.tsx`'s
 * colour gradient, hatched pattern and grow-in, and the radial budget block
 * `b-budget-echarts-radial-chart.tsx`). The notice is reproduced in
 * `apps/admin-web/THIRD_PARTY_NOTICES`. What changed in the port, and why:
 * - no Recharts and no client JavaScript: Recharts paints `style` attributes,
 *   which this console's CSP (no `unsafe-inline`) refuses. Geometry is SVG
 *   attributes, colour and motion are classes in `app/refresh.css`;
 * - the grow-in is a CSS keyframe with only a `from` frame, so it ends on the
 *   attribute's own value, and `prefers-reduced-motion` removes it;
 * - every mark comes from a string the page already prints (`./figure`), so a
 *   bar can never disagree with the figure beside it, and a value the view-model
 *   left unknown draws no mark at all (invariant 17).
 *
 * Each chart is one `role="img"` with an accessible name that reads the same
 * figures as the table under it; its parts are decorative.
 */
import type { ReactElement } from "react";

/** Semantic tones map to the console's state colours; `data` is a plain quantity. */
export type Tone = "data" | "ok" | "warn" | "bad" | "unknown";

export interface BarRow {
  /** The row's id-shaped label (a lane, a component, a run number). */
  key: string;
  /** The figure exactly as the page prints it, or `null` when unknown. */
  text: string | null;
  /** Bar length as a share in [0, 1]; `null` draws no bar. */
  share: number | null;
  tone: Tone;
  /** A stale reading is drawn hatched and named as stale. */
  stale?: boolean;
}

export interface ChartCopy {
  unknown: string;
  stale?: string;
}

const TRACK_W = 240;
const TRACK_H = 8;
/** A non-zero figure always shows at least this much bar. */
const MIN_BAR = 2;

function domId(id: string): string {
  return `chart-${id.toLowerCase().replace(/[^a-z0-9-]+/g, "-")}`;
}

function spoken(row: BarRow, c: ChartCopy): string {
  const figure = row.text ?? c.unknown;
  return row.stale && c.stale ? `${row.key} ${figure} (${c.stale})` : `${row.key} ${figure}`;
}

function barWidth(share: number): number {
  const width = share * TRACK_W;
  return share > 0 ? Math.max(MIN_BAR, width) : 0;
}

function Defs({ uid, rows }: { uid: string; rows: readonly BarRow[] }): ReactElement {
  const tones = [...new Set(rows.filter((r) => !r.stale).map((r) => r.tone))];
  const hatched = rows.some((r) => r.stale);
  return (
    <svg className="chart-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        {tones.map((tone) => (
          <linearGradient
            key={tone}
            id={`${uid}-${tone}`}
            className={`grad grad-${tone}`}
            x1="0"
            y1="0"
            x2="1"
            y2="0"
          >
            <stop offset="0%" className="stop-from" />
            <stop offset="100%" className="stop-to" />
          </linearGradient>
        ))}
        {hatched ? (
          <pattern
            id={`${uid}-hatch`}
            className="hatch"
            x="0"
            y="0"
            width="5"
            height="5"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(-45)"
          >
            <rect className="hatch-bg" width="5" height="5" />
            <rect className="hatch-line" width="1.5" height="5" />
          </pattern>
        ) : null}
      </defs>
    </svg>
  );
}

/** A horizontal bar list: one labelled row per item, its figure at the end. */
export function BarList({
  id,
  title,
  rows,
  c,
}: {
  id: string;
  title: string;
  rows: readonly BarRow[];
  c: ChartCopy;
}): ReactElement | null {
  if (rows.length === 0) return null;
  const uid = domId(id);
  const label = `${title}: ${rows.map((r) => spoken(r, c)).join(", ")}`;
  return (
    <div className="chart" data-chart={id} role="img" aria-label={label}>
      <p className="chart-title">{title}</p>
      <Defs uid={uid} rows={rows} />
      <ul className="bars">
        {rows.map((row, i) => (
          <li
            key={`${row.key}#${i}`}
            className="bar-row"
            data-tone={row.tone}
            data-stale={row.stale ? "true" : "false"}
          >
            <code className="bar-key">{row.key}</code>
            <svg
              className="bar-track"
              viewBox={`0 0 ${TRACK_W} ${TRACK_H}`}
              preserveAspectRatio="none"
              aria-hidden="true"
              focusable="false"
            >
              {row.share === null || row.share === 0 ? null : (
                <rect
                  className="bar"
                  x="0"
                  y="0"
                  width={barWidth(row.share)}
                  height={TRACK_H}
                  fill={row.stale ? `url(#${uid}-hatch)` : `url(#${uid}-${row.tone})`}
                />
              )}
            </svg>
            <span className={row.text === null ? "bar-value cell-unknown" : "bar-value"}>
              {row.text ?? c.unknown}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const RING_R = 20;
const RING_C = 24;

/** A radial gauge for one share, its printed figure and label beside the ring. */
export function Gauge({
  id,
  label,
  text,
  share,
  tone,
  c,
}: {
  id: string;
  label: string;
  text: string | null;
  share: number | null;
  tone: Tone;
  c: ChartCopy;
}): ReactElement {
  const pct = share === null ? 0 : Math.round(share * 1000) / 10;
  return (
    <div
      className="gauge"
      data-chart={id}
      data-tone={share === null ? "unknown" : tone}
      role="img"
      aria-label={`${label}: ${text ?? c.unknown}`}
    >
      <svg
        className="gauge-ring"
        viewBox={`0 0 ${RING_C * 2} ${RING_C * 2}`}
        width="56"
        height="56"
        aria-hidden="true"
        focusable="false"
      >
        <circle className="gauge-track" cx={RING_C} cy={RING_C} r={RING_R} pathLength={100} />
        {pct > 0 ? (
          <circle
            className="gauge-arc"
            cx={RING_C}
            cy={RING_C}
            r={RING_R}
            pathLength={100}
            strokeDasharray="100 100"
            strokeDashoffset={100 - pct}
            transform={`rotate(-90 ${RING_C} ${RING_C})`}
          />
        ) : null}
      </svg>
      <span className="gauge-text">
        <span className={text === null ? "gauge-value cell-unknown" : "gauge-value"}>
          {text ?? c.unknown}
        </span>
        <span className="gauge-label">{label}</span>
      </span>
    </div>
  );
}

/** The state vocabulary of the console pages, folded onto chart tones. */
export function toneOf(state: string | null): Tone {
  switch (state) {
    case "healthy":
    case "success":
    case "ok":
    case "up":
      return "ok";
    case "unhealthy":
    case "failure":
    case "timed_out":
    case "startup_failure":
    case "down":
      return "bad";
    case "degraded":
    case "cancelled":
    case "skipped":
    case "pending":
      return "warn";
    default:
      return "unknown";
  }
}
