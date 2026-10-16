/**
 * INT-490 — the wire shape the Analytics page reads: the `GET /admin/analytics`
 * document (`intake.admin.analytics.v1`, produced by
 * `intake_platform.analytics.research.payload.release_payload`). Field names
 * are the API's, snake_case, so a rename on either side is a type error here
 * rather than a silently blank cell.
 *
 * Counts, closed words, id-shaped dimension values and instants — nothing
 * else. A withheld view carries no cell at all (LD-06 `whole_views_only`).
 */

export const ANALYTICS_SCHEMA = "intake.admin.analytics.v1";

export type ViewKind =
  | "funnel"
  | "triage"
  | "locale"
  | "platform"
  | "question_outcome"
  | "question_mode"
  | "question_repeat"
  | "question_time"
  | "question_asr";

export interface CellPayload {
  value: string;
  subjects: number;
}

export interface DimensionsPayload {
  protocol: string;
  protocol_version: string;
  question?: string;
}

interface ViewBase {
  kind: ViewKind;
  partition: string;
  dimensions: DimensionsPayload;
}

export interface ShownViewPayload extends ViewBase {
  state: "shown";
  cells: CellPayload[];
}

export interface WithheldViewPayload extends ViewBase {
  state: "withheld";
  reason: "below_k" | "cross_view";
}

export type ViewPayload = ShownViewPayload | WithheldViewPayload;

export type RetentionPayload = { state: "undecided" } | { state: "set"; days: number };

export interface AnalyticsPayload {
  schema: typeof ANALYTICS_SCHEMA;
  generated_at: string;
  k: number;
  grain: "iso_week";
  period: {
    id: string;
    start: string;
    end: string;
    previous: string;
    following: string | null;
  };
  tenants: { state: "unconfigured" } | { state: "configured"; admitted: number; refused: number };
  retention: { aggregates: RetentionPayload; raw_telemetry: RetentionPayload };
  views: ViewPayload[];
  not_collected: { kind: ViewKind; reason: string }[];
}
