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
 *
 * INT-459 adds a threshold mark on a bar's track (after Astryx's
 * `referenceLine`), a trend line with an area fade (after EvilCharts'
 * `GradientPattern`) and a legend (after Astryx's `ChartLegend`). Each is
 * credited where it is defined, and the notices are in THIRD_PARTY_NOTICES.
 */
import type { ReactElement } from "react";

import { figureOf } from "./figure";

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
  /** INT-459 — where a printed threshold falls on this row's track, as a
   * share (clamped to the track); `null` or absent draws no mark. */
  mark?: number | null;
  /** The threshold exactly as the page prints it, spoken with the figure. */
  markText?: string | null;
}

export interface ChartCopy {
  unknown: string;
  stale?: string;
  /** The word for a row's threshold (`eşik` / `threshold`). */
  mark?: string;
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
  const said = row.stale && c.stale ? `${row.key} ${figure} (${c.stale})` : `${row.key} ${figure}`;
  return row.markText && c.mark ? `${said} (${c.mark} ${row.markText})` : said;
}

/** A coordinate as SVG writes it: at most two decimals, no trailing zeros. */
function coord(value: number): string {
  return String(Math.round(value * 100) / 100);
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
              {/* A printed threshold, after Astryx's `referenceLine` (MIT, (c) 2026
                  Meta Platforms, Inc., c3f64eff): a 1-unit dashed rule. Its
                  SVG text badge is dropped (it sizes text at 6.5 units a
                  character, which clips Turkish); the figure is spoken in the
                  image's label and printed in the table instead. */}
              {row.mark === null || row.mark === undefined ? null : (
                <line
                  className="bar-mark"
                  x1={coord(clampShare(row.mark) * TRACK_W)}
                  x2={coord(clampShare(row.mark) * TRACK_W)}
                  y1="0"
                  y2={TRACK_H}
                  vectorEffect="non-scaling-stroke"
                  strokeDasharray="3 2"
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

function clampShare(share: number): number {
  return Math.min(1, Math.max(0, share));
}

// --- INT-459: a trend line and a legend --------------------------------------

export interface SparkPoint {
  /** The point's id-shaped label (a run number), oldest first. */
  key: string;
  /** The figure exactly as the page prints it, or `null` when unknown. */
  text: string | null;
}

const SPARK_W = 240;
const SPARK_H = 40;
/** Headroom above the largest figure, so the line's stroke is not clipped. */
const SPARK_TOP = 2;

/** One run of consecutive known points, as SVG coordinates. */
type Run = { x: number; y: number }[];

function runsOf(values: readonly (number | null)[], max: number): Run[] {
  const step = values.length > 1 ? SPARK_W / (values.length - 1) : 0;
  const runs: Run[] = [];
  let run: Run = [];
  values.forEach((value, i) => {
    if (value === null) {
      if (run.length > 0) runs.push(run);
      run = [];
      return;
    }
    run.push({ x: i * step, y: SPARK_H - (value / max) * (SPARK_H - SPARK_TOP) });
  });
  if (run.length > 0) runs.push(run);
  return runs;
}

function lineOf(run: Run): string {
  return run.map((p, i) => `${i === 0 ? "M" : "L"}${coord(p.x)} ${coord(p.y)}`).join(" ");
}

function areaOf(run: Run): string {
  const first = run[0]!;
  const last = run[run.length - 1]!;
  return `${lineOf(run)} L${coord(last.x)} ${SPARK_H} L${coord(first.x)} ${SPARK_H} Z`;
}

/**
 * A trend over a series of printed figures, oldest first: a line, and under it
 * an area that fades from the top down.
 *
 * Adapted from EvilCharts (MIT, (c) 2026 Gurbinder) — `recharts-area-chart.tsx`
 * `GradientPattern` at ecbd6a5d: a vertical `linearGradient` from 0.1 opacity
 * to none. EvilCharts masks a colour gradient through it; here one gradient
 * carries both, its stops coloured by class (`app/native-content.css`), so no
 * `style` and no presentation colour reaches the markup.
 *
 * The scale starts at zero. An unknown point breaks the line rather than being
 * drawn through (invariant 17), and a series whose units disagree, or that
 * has fewer than two known points, draws nothing at all.
 */
export function Spark({
  id,
  title,
  points,
  c,
}: {
  id: string;
  title: string;
  points: readonly SparkPoint[];
  c: ChartCopy;
}): ReactElement | null {
  const figures = points.map((p) => figureOf(p.text));
  const known = figures.filter((f): f is NonNullable<typeof f> => f !== null);
  if (known.length < 2 || new Set(known.map((f) => f.unit)).size !== 1) return null;
  const max = Math.max(...known.map((f) => f.value));
  if (!(max > 0)) return null;
  const uid = domId(id);
  const runs = runsOf(
    figures.map((f) => f?.value ?? null),
    max,
  );
  const label = `${title}: ${points.map((p) => `${p.key} ${p.text ?? c.unknown}`).join(", ")}`;
  return (
    <div className="chart spark" data-chart={id} role="img" aria-label={label}>
      <p className="chart-title">{title}</p>
      <svg
        className="spark-plot"
        viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <linearGradient id={`${uid}-fade`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" className="fade-top" />
            <stop offset="100%" className="fade-bottom" />
          </linearGradient>
        </defs>
        {runs
          .filter((run) => run.length > 1)
          .map((run) => (
            <path
              key={`a${run[0]!.x}`}
              className="spark-area"
              d={areaOf(run)}
              fill={`url(#${uid}-fade)`}
            />
          ))}
        <path
          className="spark-line"
          d={runs.map(lineOf).join(" ")}
          fill="none"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}

export interface LegendItem {
  label: string;
  tone: Tone;
  /** A bar series gets a square chip; a line gets a short stroke. */
  shape: "square" | "line";
}

/**
 * The key to a chart's colours: a list, each label beside a swatch.
 *
 * Adapted from Astryx (MIT, (c) 2026 Meta Platforms, Inc.) — `ChartLegend`
 * and `ChartSwatch` at c3f64eff: an 8 × 8 square chip for a bar series and a
 * 10 × 3 stroke for a line, the swatch hidden from assistive technology and
 * the list labelled. Its runtime colour becomes a `data-tone` class, and the
 * list sits outside the chart's image, whose own label already names every
 * figure.
 */
export function Legend({
  label,
  items,
}: {
  label: string;
  items: readonly LegendItem[];
}): ReactElement | null {
  if (items.length === 0) return null;
  return (
    <ul className="legend" aria-label={label}>
      {items.map((item) => (
        <li key={`${item.tone}:${item.label}`} data-tone={item.tone}>
          <span className={`swatch swatch-${item.shape}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
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
