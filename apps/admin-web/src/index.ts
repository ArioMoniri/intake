/**
 * `@intake/admin-web` — the console's typed surface (INT-183).
 *
 * The app is assembled module by module inside the INT-180 admin shell; this
 * index is the public API of what exists today, which is the Models &
 * self-hosting registry module (files/08 §148) and the measurement discipline
 * every figure on the console must pass through (CLAUDE.md invariant 20).
 */
export {
  InconsistentReleaseState,
  renderModelsModule,
  type BenchmarkLane,
  type BlockReason,
  type Cell,
  type Finding,
  type LanePresentation,
  type ModelsPayload,
  type ModelsPresentation,
  type ModelsRow,
  type RowPresentation,
  type Severity,
} from "./models/module";
export { UnlabelledMeasurement, renderMeasurement, type Measurement } from "./models/measurement";
