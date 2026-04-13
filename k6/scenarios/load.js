/**
 * HireStack AI — Standard Load Test
 *
 * 50 concurrent users sustained for 5 minutes.
 * Simulates normal peak traffic with realistic user flows.
 *
 * Stages:
 *   0-1m  → ramp up to 50 VUs
 *   1-6m  → hold at 50 VUs
 *   6-7m  → ramp down to 0
 *
 * Usage: k6 run k6/scenarios/load.js
 */

import { sleep } from "k6";
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
  flowSalary,
  flowBilling,
  flowJobSync,
  flowGapReports,
  flowInterviewSessions,
  flowAtsScans,
  flowOrgs,
  flowReviews,
} from "../flows.js";

export const options = {
  scenarios: {
    // 70% of users are "browsers" — read-heavy dashboard/list flows
    browsers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 35 },
        { duration: "5m", target: 35 },
        { duration: "1m", target: 0 },
      ],
      exec: "browserFlow",
    },
    // 20% are "workers" — CRUD operations, job management
    workers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 10 },
        { duration: "5m", target: 10 },
        { duration: "1m", target: 0 },
      ],
      exec: "workerFlow",
    },
    // 10% are "explorers" — less common pages (career, salary, learning)
    explorers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: 5 },
        { duration: "5m", target: 5 },
        { duration: "1m", target: 0 },
      ],
      exec: "explorerFlow",
    },
  },
  thresholds: SLO_THRESHOLDS,
};

// ---------------------------------------------------------------------------
// Browser flow: dashboard + profile reads (most common)
// ---------------------------------------------------------------------------
export function browserFlow() {
  flowHealthCheck();
  flowAuthAndProfile();
  flowDashboard();
  flowDocumentLibrary();
  flowGapReports();
  flowBilling();
  sleep(Math.random() * 3 + 1); // 1-4s think time
}

// ---------------------------------------------------------------------------
// Worker flow: CRUD operations
// ---------------------------------------------------------------------------
export function workerFlow() {
  flowAuthAndProfile();
  flowJobCrud();
  flowCandidates();
  flowJobSync();
  flowAtsScans();
  sleep(Math.random() * 2 + 1); // 1-3s think time
}

// ---------------------------------------------------------------------------
// Explorer flow: deeper features
// ---------------------------------------------------------------------------
export function explorerFlow() {
  flowAuthAndProfile();
  flowCareerAnalytics();
  flowLearning();
  flowSalary();
  flowInterviewSessions();
  flowOrgs();
  flowReviews();
  sleep(Math.random() * 3 + 2); // 2-5s think time
}
