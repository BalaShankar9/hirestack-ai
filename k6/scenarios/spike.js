/**
 * HireStack AI — Spike Test
 *
 * Sudden burst of 500 users to test auto-scaling and rate limiter behavior.
 * Validates the system recovers gracefully after the spike.
 *
 * Stages:
 *   0-30s  → ramp to 10 VUs (baseline)
 *   30-60s → SPIKE to 500 VUs
 *   60-90s → hold at 500 VUs
 *   90-2m  → drop to 10 VUs (recovery)
 *   2-3m   → hold at 10 VUs (verify recovery)
 *   3-3.5m → ramp down to 0
 *
 * Usage: k6 run k6/scenarios/spike.js
 */

import { sleep } from "k6";
import { SLO_THRESHOLDS } from "../config.js";
import {
  flowHealthCheck,
  flowAuthAndProfile,
  flowDashboard,
  flowDocumentLibrary,
  flowBilling,
} from "../flows.js";

export const options = {
  scenarios: {
    spike: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 10 },   // Baseline
        { duration: "30s", target: 500 },  // SPIKE
        { duration: "30s", target: 500 },  // Hold spike
        { duration: "30s", target: 10 },   // Drop
        { duration: "1m", target: 10 },    // Recovery
        { duration: "30s", target: 0 },    // Ramp down
      ],
    },
  },
  thresholds: {
    // During a spike we expect some failures — focus on recovery
    http_req_failed: ["rate<0.15"],                 // Allow 15% during spike
    http_req_duration: ["p(95)<10000"],              // 10s p95 acceptable
    "http_req_duration{type:health}": ["p(95)<500"], // Health must stay fast
  },
};

export default function () {
  // Lightweight flow — we're testing concurrency, not feature depth
  flowHealthCheck();
  flowAuthAndProfile();
  flowDashboard();
  flowDocumentLibrary();
  flowBilling();
  sleep(Math.random() * 1 + 0.2);
}
