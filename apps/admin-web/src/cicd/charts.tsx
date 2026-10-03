/**
 * INT-450 — the CI/CD module's charts: each workflow's recent run durations,
 * coloured by conclusion, and each ref's required-gate pass share. Drawn over
 * the strings the tables print (`../ui/figure`), inside the tile's `ok` branch
 * only (invariant 17).
 *
 * INT-459 — a legend names each conclusion's colour (after Astryx's
 * `ChartLegend`), and each workflow's durations also run as a trend line,
 * oldest first (after EvilCharts' area fade). The conclusions are GitHub's
 * codes, shown as the codes they are, like the table under them.
 */
import type { ReactElement } from "react";

import { BarList, Legend, Spark, toneOf, type LegendItem } from "../ui/charts";
import { ratioOf, sharesOf } from "../ui/figure";
import type { CicdView } from "./module";

interface ChartsCopy {
  unknown: string;
  cols: { duration: string; passing: string };
  charts: { legend: string; trend: string };
}

/** Each conclusion that appears, in first-seen order, then the trend line. */
function legendOf(view: CicdView, c: ChartsCopy): LegendItem[] {
  const codes = [
    ...new Set(view.pipelines.workflows.flatMap((w) => w.runs.map((r) => r.conclusion))),
  ];
  return [
    ...codes.map((code) => ({ label: code, tone: toneOf(code), shape: "square" as const })),
    { label: c.charts.trend, tone: "data", shape: "line" },
  ];
}

export function RunDurations({ view, c }: { view: CicdView; c: ChartsCopy }): ReactElement | null {
  const workflows = view.pipelines.workflows.filter((w) => w.runs.length > 0);
  if (workflows.length === 0) return null;
  return (
    <>
      <Legend label={c.charts.legend} items={legendOf(view, c)} />
      <div className="viz">
        {workflows.map((w) => {
          const shares = sharesOf(w.runs.map((run) => run.duration));
          return (
            <div key={w.workflow} className="chart-stack">
              <Spark
                id={`trend-${w.workflow}`}
                title={`${w.workflow} · ${c.charts.trend}`}
                points={[...w.runs].reverse().map((run) => ({
                  key: `#${run.runNumber}`,
                  text: run.duration,
                }))}
                c={c}
              />
              <BarList
                id={`runs-${w.workflow}`}
                title={`${w.workflow} · ${c.cols.duration}`}
                rows={w.runs.map((run, i) => ({
                  key: `#${run.runNumber}`,
                  text: run.duration,
                  share: shares[i] ?? null,
                  tone: toneOf(run.conclusion),
                }))}
                c={c}
              />
            </div>
          );
        })}
      </div>
    </>
  );
}

export function GatePass({ view, c }: { view: CicdView; c: ChartsCopy }): ReactElement | null {
  const refs = view.gates.refs;
  if (refs.length === 0) return null;
  return (
    <div className="viz">
      <BarList
        id="gate-pass"
        title={c.cols.passing}
        rows={refs.map((ref) => ({
          key: ref.ref,
          text: `${ref.passing}/${ref.total}`,
          share: ratioOf(ref.passing, ref.total),
          tone: ref.passing === ref.total ? "ok" : "bad",
        }))}
        c={c}
      />
    </div>
  );
}
