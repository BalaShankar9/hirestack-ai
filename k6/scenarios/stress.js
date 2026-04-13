/**
 * HireStack AI — Stress Test
 *
 * Ramp from 0 → 100 → 200 concurrent users to find the breaking point.
 * Exercises ALL endpoint categories under growing pressure.
 *
 * Stages:
 *   0-2m   → ramp to 50 VUs (warm-up)
 *   2-5m   → ramp to 100 VUs (normal peak)
 *   5-8m   → ramp to 200 VUs (above capacity)
 *   8-10m  → hold at 200 VUs (sustained stress)
 *   10-12m → ramp down to 0
 *
 * Usage: k6 run k6/scenarios/stress.js
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
    // Read-heavy traffic (60%)
    readers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 30 },
        { duration: "3m", target: 60 },
        { duration: "3m", target: 120 },
        { duration: "2m", target: 120 },
        { duration: "2m", target: 0 },
      ],
      exec: "readerFlow",
    },
    // Write traffic (30%)
    writers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 15 },
        { duration: "3m", target: 30 },
        { duration: "3m", target: 60 },
        { duration: "2m", target: 60 },
        { duration: "2m", target: 0 },
      ],
      exec: "writerFlow",
    },
    // Mixed heavy traffic (10%)
    mixed: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 5 },
        { duration: "3m", target: 10 },
        { duration: "3m", target: 20 },
        { duration: "2m", target: 20 },
        { duration: "2m", target: 0 },
      ],
      exec: "mixedFlow",
    },
  },
  thresholds: {
    ...SLO_THRESHOLDS,
    // Relaxed thresholds for stress test
    http_req_failed: ["rate<0.05"],               // Allow 5% errors under extreme load
    http_req_duration: ["p(95)<5000", "p(99)<10000"],
    "http_req_duration{type:read}": ["p(95)<2000"],
    "http_req_duration{type:write}": ["p(95)<5000"],
  },
};

// ---------------------------------------------------------------------------
// Reader: rapid dashboard/list polling
// ---------------------------------------------------------------------------
export function readerFlow() {
  flowHealthCheck();
  flowDashboard();
  flowDocumentLibrary();
  flowGapReports();
  flowBilling();
  flowCareerAnalytics();
  sleep(Math.random() * 2 + 0.5);
}

// ---------------------------------------------------------------------------
// Writer: CRUD operations
// ---------------------------------------------------------------------------
export function writerFlow() {
  flowAuthAndProfile();
  flowJobCrud();
  flowCandidates();
  flowJobSync();
  sleep(Math.random() * 2 + 0.5);
}

// ---------------------------------------------------------------------------
// Mixed: full user journey through multiple features
// ---------------------------------------------------------------------------
export function mixedFlow() {
  flowAuthAndProfile();
  flowDashboard();
  flowJobCrud();
  flowDocumentLibrary();
  flowCareerAnalytics();
  flowLearning();
  flowSalary();
  flowInterviewSessions();
  flowAtsScans();
  flowOrgs();
  flowReviews();
  sleep(Math.random() * 3 + 1);
}
