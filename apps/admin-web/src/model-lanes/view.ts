/**
 * INT-428 — the tree the Model lanes page paints: what `renderModelLanes`
 * returns. Every figure is already a string a reader cannot misread
 * (invariant 22), and every unknown is `null`, painted as the word.
 */
import type { COST_STATES, Ceremony, DataClass, LaneId, ProviderId, Route } from "./payload";

export interface ModelRefView {
  source: "self_hosted" | "hosted";
  provider: string;
  modelId: string;
  version: string;
  shortVersion: string;
  wire: string;
  sha256: string | null;
  shortPin: string | null;
  component: string | null;
  key: string;
}

export interface SettingView {
  route: Route;
  model: string | null;
  fallback: ProviderId | null;
  fallbackModel: string | null;
}

export interface UsageView {
  route: "self_hosted" | "hosted";
  provider: string;
  p50: string | null;
  p95: string | null;
  calls: string | null;
  cost: { state: (typeof COST_STATES)[number]; usd: string | null };
}

export interface RoleView {
  role: string;
  lane: LaneId;
  isLane: boolean;
  inherits: boolean;
  setting: SettingView | null;
  serving: {
    available: boolean;
    reason: string;
    provider: string | null;
    route: Route | null;
    fallback: boolean;
    model: ModelRefView | null;
    qualified: boolean;
    clinicalEvidence: boolean;
  };
  selfHosted: { identity: string; expected: ModelRefView | null };
  usage: UsageView[] | null;
}

export interface SelfHostedOptionView {
  component: string;
  pinned: boolean;
  attested: boolean;
  jurisdiction: string | null;
  model: ModelRefView | null;
  identity: string;
  qualified: boolean;
  selectable: boolean;
}

export interface HostedOptionView {
  provider: ProviderId;
  model: ModelRefView;
  isDefault: boolean;
  probe: { state: string; reason: string | null };
  qualified: boolean;
}

export interface LaneOptionsView {
  lane: LaneId;
  gated: boolean;
  selfHosted: SelfHostedOptionView[];
  hosted: HostedOptionView[];
}

export interface ProviderView {
  provider: ProviderId;
  egressRow: string;
  listed: boolean;
  key: { state: string; last4: string | null; setAt: string | null };
  ready: { state: string; reason: string | null };
}

export interface PendingView {
  actionId: string;
  ceremony: Ceremony;
  tier: string;
  state: string;
  expiresAt: string;
  approverRole: string | null;
}

export type Banner = "no_hosted_lanes" | "real_phi" | "data_class_mismatch";

export interface DeploymentView {
  declared: DataClass;
  bound: DataClass | null;
  effective: DataClass;
  hostedLanes: boolean;
  mismatch: boolean;
}

export interface ControlView {
  state: "known" | "unknown";
  reason: string | null;
  revision: string | null;
  hostedDisabled: boolean | null;
  changedAt: string | null;
  changedBy: string | null;
  approvedBy: string | null;
  lastChange: string | null;
}

export interface ModelLanesView {
  generatedAt: string;
  state: "known" | "unknown";
  reason: string | null;
  deployment: DeploymentView | null;
  banners: Banner[];
  control: ControlView;
  lanes: RoleView[];
  roles: RoleView[];
  options: LaneOptionsView[];
  providers: ProviderView[];
  usage: { window: string; reason: string | null };
  pending: PendingView[];
  /** The routes a switch form may offer: hosted ones only where hosted lanes exist. */
  routes: Route[];
}
