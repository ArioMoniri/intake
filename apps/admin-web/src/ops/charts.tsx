/**
 * INT-450 — the ops console's charts: GPU load, model-lane usage and the clip
 * cache, drawn over the very strings the tiles print (`../ui/figure`). Each
 * renders inside its tile's `ok` branch only, so an unknown tile still carries
 * no figure (invariant 17), and a row the view-model left unknown draws no bar.
 */
import type { ReactElement } from "react";

import { BarList, Gauge, type BarRow } from "../ui/charts";
import { percentOf, ratioOf, sharesOf } from "../ui/figure";
import type { Copy } from "./copy";
import type { OpsView } from "./module";

export function GpuCharts({ view, c }: { view: OpsView; c: Copy }): ReactElement | null {
  const gpus = view.tiles.gpu.hosts.flatMap((host) =>
    host.up ? host.gpus.map((g) => ({ key: `${host.hostId}/${g.index}`, g })) : [],
  );
  if (gpus.length === 0) return null;
  const load: BarRow[] = gpus.map(({ key, g }) => ({
    key,
    text: g.utilization,
    share: percentOf(g.utilization),
    tone: "data",
  }));
  const memory: BarRow[] = gpus.map(({ key, g }) => ({
    key,
    text:
      g.memoryUsed === null || g.memoryTotal === null ? null : `${g.memoryUsed} / ${g.memoryTotal}`,
    share: ratioOf(g.memoryUsed, g.memoryTotal),
    tone: "data",
  }));
  return (
    <div className="viz">
      <BarList id="gpu-utilisation" title={c.gpu.utilization} rows={load} c={c} />
      <BarList id="gpu-memory" title={c.gpu.memory} rows={memory} c={c} />
    </div>
  );
}

export function UsageCharts({ view, c }: { view: OpsView; c: Copy }): ReactElement | null {
  const lanes = view.tiles.modelUsage.lanes;
  if (lanes.length === 0) return null;
  const requests = sharesOf(lanes.map((l) => l.requests));
  const p95 = sharesOf(lanes.map((l) => l.p95));
  return (
    <div className="viz">
      <BarList
        id="lane-requests"
        title={c.usage.requests}
        rows={lanes.map((l, i) => ({
          key: l.lane,
          text: l.requests,
          share: requests[i] ?? null,
          tone: "data",
        }))}
        c={c}
      />
      <BarList
        id="lane-p95"
        title={c.usage.p95}
        rows={lanes.map((l, i) => ({
          key: l.lane,
          text: l.p95,
          share: p95[i] ?? null,
          tone: "data",
        }))}
        c={c}
      />
    </div>
  );
}

export function ClipCharts({ view, c }: { view: OpsView; c: Copy }): ReactElement {
  const t = view.tiles.clipCache;
  return (
    <div className="viz">
      <Gauge
        id="clip-hit-ratio"
        label={c.clips.hitRatio}
        text={t.hitRatio}
        share={percentOf(t.hitRatio)}
        tone="data"
        c={c}
      />
      <BarList
        id="clip-coverage"
        title={c.clips.coverage}
        rows={t.manifests.map((m) => ({
          key: `${m.pack} · ${m.voice}`,
          text: m.coverage,
          share: percentOf(m.coverage),
          tone: "data",
        }))}
        c={c}
      />
    </div>
  );
}
