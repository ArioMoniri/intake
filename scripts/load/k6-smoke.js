// scripts/load/k6-smoke.js — INT-024: k6 API smoke (sec_row: resilience).
//
// Runs against a locally running services/api instance today (`make load`).
// The acceptance's "k6 API smoke in CI (staging profile)" is the CI job this
// script becomes once a staging environment exists; no staging environment
// exists yet, so the job is deferred with it and docs/evidence/INT-024.md
// records the deferral. Nothing here fakes a staging target.
//
// Environment:
//   BASE_URL                  target origin (default http://127.0.0.1:8000)
//   INTAKE_DEV_TOKEN_PATIENT  optional INT-197 dev bearer token; when set the
//                             smoke also exercises the authed /v1/visits
//                             happy path (synthetic dev accounts only — this
//                             is never a real credential)
//
// Usage: make load
//    or: k6 run -e BASE_URL=http://127.0.0.1:8000 scripts/load/k6-smoke.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const PATIENT_TOKEN = __ENV.INTAKE_DEV_TOKEN_PATIENT || "";

export const options = {
  vus: 5,
  duration: "30s",
  thresholds: {
    // the api row in observability/registry.yaml carries budget_ms: 800
    http_req_duration: ["p(95)<800"],
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const healthz = http.get(`${BASE_URL}/healthz`);
  check(healthz, {
    "healthz is 200": (r) => r.status === 200,
    "healthz reports alive": (r) => r.json("status") === "alive",
  });

  const readyz = http.get(`${BASE_URL}/readyz`);
  check(readyz, {
    // 503 means a dependency is down — the smoke reports it, never masks it
    "readyz is 200": (r) => r.status === 200,
  });

  const version = http.get(`${BASE_URL}/version`);
  check(version, {
    "version is 200": (r) => r.status === 200,
    "version carries git_sha": (r) => typeof r.json("git_sha") === "string",
  });

  const metrics = http.get(`${BASE_URL}/metrics`);
  check(metrics, {
    "metrics is 200": (r) => r.status === 200,
    "metrics serves the catalogued http families": (r) =>
      typeof r.body === "string" && r.body.includes("http_requests_total"),
  });

  if (PATIENT_TOKEN !== "") {
    const visits = http.get(`${BASE_URL}/v1/visits`, {
      headers: { Authorization: `Bearer ${PATIENT_TOKEN}` },
    });
    check(visits, {
      "authed /v1/visits is 200": (r) => r.status === 200,
      "authed tier header says dev": (r) => r.headers["X-Intake-Auth-Tier"] === "dev",
    });
  }

  sleep(1);
}
