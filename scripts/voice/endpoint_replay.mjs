// INT-497 — replay level traces through the device's own end-of-turn detector.
//
// `scripts/voice/voice_experience.py traces` renders synthetic level traces
// (50 ms meter readings of cast-voice clips over a quiet and a noisy room,
// with the true end of speech recorded). This feeds each one, sample by
// sample, to apps/mobile/src/lib/dialogue/endpointer.ts — the module the app
// runs, imported as-is (Node strips its types) — and reports:
//
//   delay    the endpointer's decision minus the true end of speech, ms
//   cut-off  it decided BEFORE the true end (inside a hesitation)
//   missed   it never decided (the patient would have to tap)
//
// Levels only, never samples: nothing here touches audio (invariant 3). The
// figures are this clip set through this detector on this day (invariant 20).
//
// Usage: node scripts/voice/endpoint_replay.mjs <traces.json>

import { readFileSync } from "node:fs";

import {
  createEndpointer,
  createHangoverPolicy,
} from "../../apps/mobile/src/lib/dialogue/endpointer.ts";

function percentile(values, p) {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil((p / 100) * sorted.length));
  return sorted[Math.min(rank, sorted.length) - 1];
}

const path = process.argv[2];
if (path === undefined) {
  process.stderr.write("usage: node scripts/voice/endpoint_replay.mjs <traces.json>\n");
  process.exit(2);
}
const { traces } = JSON.parse(readFileSync(path, "utf8"));
const groups = new Map();
for (const trace of traces) {
  // A fresh policy per trace: each is a first turn, before any cut-off has
  // widened the session's wait — the strictest case for the detector.
  const endpointer = createEndpointer(createHangoverPolicy(), { shape: trace.shape });
  trace.levels.forEach((level, i) => endpointer.sample(level, i * trace.step_ms));
  const key = `${trace.room}/${trace.kind}`;
  const group = groups.get(key) ?? { delays: [], cutOffs: 0, missed: 0, n: 0 };
  group.n += 1;
  if (endpointer.endedAt === null) {
    group.missed += 1;
  } else if (endpointer.endedAt < trace.speech_end_ms) {
    group.cutOffs += 1;
  } else {
    group.delays.push(endpointer.endedAt - trace.speech_end_ms);
  }
  groups.set(key, group);
}
const report = {};
for (const [key, group] of [...groups].sort(([a], [b]) => a.localeCompare(b))) {
  report[key] = {
    n: group.n,
    delay_p50_ms: percentile(group.delays, 50),
    delay_p95_ms: percentile(group.delays, 95),
    cut_offs: group.cutOffs,
    missed: group.missed,
  };
}
const all = [...groups.values()];
report.all = {
  n: all.reduce((s, g) => s + g.n, 0),
  delay_p50_ms: percentile(
    all.flatMap((g) => g.delays),
    50,
  ),
  delay_p95_ms: percentile(
    all.flatMap((g) => g.delays),
    95,
  ),
  cut_offs: all.reduce((s, g) => s + g.cutOffs, 0),
  missed: all.reduce((s, g) => s + g.missed, 0),
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
