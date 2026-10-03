/**
 * INT-450 — the CI/CD module's charts: each workflow's recent run durations,
 * coloured by conclusion, and each ref's required-gate pass share. Drawn over
 * the strings the tables print (`../ui/figure`), inside the tile's `ok` branch
 * only (invariant 17).
 */
import type { ReactElement } from "react";

import { BarList, toneOf } from "../ui/charts";
import { ratioOf, sharesOf } from "../ui/figure";
import type { CicdView } from "./module";

interface ChartsCopy {
  unknown: string;
  cols: { duration: string; passing: string };
}

export function RunDurations({ view, c }: { view: CicdView; c: ChartsCopy }): ReactElement | null {
  const workflows = view.pipelines.workflows.filter((w) => w.runs.length > 0);
  if (workflows.length === 0) return null;
  return (
    <div className="viz">
      {workflows.map((w) => {
        const shares = sharesOf(w.runs.map((run) => run.duration));
        return (
          <BarList
            key={w.workflow}
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
        );
      })}
    </div>
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
