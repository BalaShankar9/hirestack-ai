/**
 * HireStack AI — Soak Test
 *
 * 50 users sustained for 30 minutes to detect memory leaks,
 * connection pool exhaustion, and gradual performance degradation.
 *
 * Stages:
 *   0-2m   → ramp to 50 VUs
 *   2-32m  → hold at 50 VUs (30 min soak)
 *   32-34m → ramp down to 0
 *
 * Usage: k6 run k6/scenarios/soak.js
 */

import { sleep } from "k6";
import { Trend } from "k6/metrics";
import { SLO_THRESHOLDS } from "../config.js";
import {
  flowHealthCheck,
  flowAuthAndProfile,
  flowDashboard,
  flowJobCrud,
  flowDocumentLibrary,
  flowCareerAnalytics,
  flowLearning,
  flowCandidates,
  flowBilling,
  flowGapReports,
  flowJobSync,
  flowSalary,
} from "../flows.js";

// Custom trends to track degradation over time
const dashboardLatency = new Trend("dashboard_latency");
const crudLatency = new Trend("crud_latency");

export const options = {
  scenarios: {
    soak_browsers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 30 },
        { duration: "30m", target: 30 },
        { duration: "2m", target: 0 },
      ],
      exec: "browserSoak",
    },
    soak_workers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 15 },
        { duration: "30m", target: 15 },
        { duration: "2m", target: 0 },
      ],
      exec: "workerSoak",
    },
    soak_explorers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 5 },
        { duration: "30m", target: 5 },
        { duration: "2m", target: 0 },
      ],
      exec: "explorerSoak",
    },
  },
  thresholds: {
    ...SLO_THRESHOLDS,
    // Soak-specific: latency must NOT degrade over time
    dashboard_latency: ["p(95)<500", "p(99)<1500"],
    crud_latency: ["p(95)<1500", "p(99)<3000"],
  },
};

// ---------------------------------------------------------------------------
// Browser soak: repeated dashboard loads
// ---------------------------------------------------------------------------
export function browserSoak() {
  const start = Date.now();
  flowHealthCheck();
  flowAuthAndProfile();
  flowDashboard();
  dashboardLatency.add(Date.now() - start);

  flowDocumentLibrary();
  flowGapReports();
  flowBilling();
  sleep(Math.random() * 5 + 2); // 2-7s think time (slower for soak)
}

// ---------------------------------------------------------------------------
// Worker soak: CRUD cycles
// ---------------------------------------------------------------------------
export function workerSoak() {
  const start = Date.now();
  flowAuthAndProfile();
  flowJobCrud();
  crudLatency.add(Date.now() - start);

  flowCandidates();
  flowJobSync();
  sleep(Math.random() * 4 + 2);
}

// ---------------------------------------------------------------------------
// Explorer soak: varied feature access
// ---------------------------------------------------------------------------
export function explorerSoak() {
  flowAuthAndProfile();
  flowCareerAnalytics();
  flowLearning();
  flowSalary();
  sleep(Math.random() * 5 + 3);
}
