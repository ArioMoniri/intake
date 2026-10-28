/**
 * INT-563 (ADR-043) — which approve route a step-up grant is presented on, and
 * which page the approver lands back on.
 *
 * The API answers a completed step-up with the pending action's
 * `DangerousAction` id. The console maps it to the action's own approve (or
 * countersign) route here — a closed table, so a grant is only ever sent to a
 * route this console already calls, built from an id-shaped action id, never
 * from a path the response supplied. An id not in the table is refused.
 */

/** The pending-action id the API's four-eyes service mints (uuid4 hex). */
export const ACTION_ID = /^[0-9a-f]{32}$/;
/** A step-up grant (`intake_platform.admin.step_up`: "sug_" + 16 random bytes). */
export const GRANT = /^sug_[0-9a-f]{32}$/;

/** The pages an approval starts from and returns to. */
export const PAGES = ["voice", "cicd", "model-lanes", "access", "step-up"] as const;
export type Page = (typeof PAGES)[number];

export function isPage(value: unknown): value is Page {
  return typeof value === "string" && (PAGES as readonly string[]).includes(value);
}

interface Approval {
  page: Page;
  path: (actionId: string) => `/admin/${string}`;
}

export const APPROVALS: Readonly<Record<string, Approval>> = {
  "admin.voice.kill_switch.release": {
    page: "voice",
    path: (id) => `/admin/voice/kill-switch/release/${id}/approve`,
  },
  "admin.voice.profile.switch": {
    page: "voice",
    path: (id) => `/admin/voice/profile/pending/${id}/approve`,
  },
  "admin.voice.canary.set": {
    page: "voice",
    path: (id) => `/admin/voice/canary/pending/${id}/approve`,
  },
  "admin.cicd.freeze.lift": {
    page: "cicd",
    path: (id) => `/admin/cicd/freeze/lift/${id}/approve`,
  },
  "admin.model_lanes.hosted.release": {
    page: "model-lanes",
    path: (id) => `/admin/model-lanes/hosted/release/${id}/approve`,
  },
  "admin.model_lanes.route.switch": {
    page: "model-lanes",
    path: (id) => `/admin/model-lanes/route/pending/${id}/approve`,
  },
  "admin.model_lanes.key.set": {
    page: "model-lanes",
    path: (id) => `/admin/model-lanes/keys/pending/${id}/approve`,
  },
  "admin.break_glass.open": {
    page: "step-up",
    path: (id) => `/admin/break-glass/${id}/approve`,
  },
  "admin.access.review.sign": {
    page: "access",
    path: (id) => `/admin/access/review/sign/${id}/countersign`,
  },
};

export function approvalFor(action: unknown): Approval | null {
  return typeof action === "string" && Object.hasOwn(APPROVALS, action) ? APPROVALS[action]! : null;
}
