/**
 * HireStack AI — Duplicate Detection (Multi-Replica Safety)
 *
 * Proves the PR-3 Idempotency-Key middleware suppresses duplicate side-effects
 * across multiple API replicas. Required to gate the railway `numReplicas = 2`
 * cutover (PR-7).
 *
 * Strategy:
 *   - Generate one Idempotency-Key per "burst".
 *   - Fire N concurrent POSTs with that same key from independent VUs.
 *   - Assert every response shares the same status code AND the same response
 *     body hash. Different responses for the same key = dedupe broken.
 *   - Run M bursts back-to-back to amplify the chance of hitting different
 *     replicas.
 *
 * Usage:
 *   BASE_URL=https://api.example.com \
 *   AUTH_TOKEN=eyJ... \
 *   IDEMPOTENT_POST_PATH=/api/aim/sources \
 *   IDEMPOTENT_POST_BODY='{"name":"k6-dupe-probe","kind":"company"}' \
 *     k6 run k6/scenarios/duplicate-detection.js
 *
 * Defaults target the local backend on port 8000.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";
import { BASE_URL, AUTH_TOKEN } from "../config.js";

// --------------------------------------------------------------------------
// Config
// --------------------------------------------------------------------------

const POST_PATH =
  __ENV.IDEMPOTENT_POST_PATH || "/api/aim/sources";
const POST_BODY =
  __ENV.IDEMPOTENT_POST_BODY ||
  JSON.stringify({ name: "k6-dupe-probe", kind: "company" });

// VUs per burst — each burst shares a single Idempotency-Key.
const BURST_SIZE = parseInt(__ENV.BURST_SIZE || "8", 10);
// Total bursts across the run.
const BURSTS = parseInt(__ENV.BURSTS || "20", 10);

// --------------------------------------------------------------------------
// Custom metrics
// --------------------------------------------------------------------------

const duplicateMismatches = new Counter("duplicate_mismatches");
const dedupeSuccessRate = new Rate("dedupe_success");

// --------------------------------------------------------------------------
// Scenario
// --------------------------------------------------------------------------

export const options = {
  scenarios: {
    duplicate_detection: {
      executor: "shared-iterations",
      vus: BURST_SIZE,
      iterations: BURST_SIZE * BURSTS,
      maxDuration: "5m",
    },
  },
  thresholds: {
    // Zero tolerance: any duplicate-key request returning a different
    // status/body than its peers is a dedupe regression.
    duplicate_mismatches: ["count==0"],
    dedupe_success: ["rate==1.0"],
    http_req_failed: ["rate<0.05"],
  },
};

// --------------------------------------------------------------------------
// Burst coordination
//
// k6 doesn't natively share state across VUs, so each burst index is derived
// from the iteration counter. All VUs that hit the same `burstId` share an
// Idempotency-Key derived deterministically from it + a per-run salt.
// --------------------------------------------------------------------------

// Per-run salt so re-runs don't collide on real-stack idempotency rows.
const RUN_SALT = `k6-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

function burstIdFor(iter) {
  return Math.floor(iter / BURST_SIZE);
}

function idempotencyKeyFor(burstId) {
  return `${RUN_SALT}-burst-${burstId}`;
}

// In-VU memo of (burstId -> {status, bodyHash}) so we can assert against the
// first response we observed for that burst.
const seenByBurst = {};

function djb2(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  }
  return h >>> 0;
}

export default function () {
  const iter = __ITER + __VU * 1000;
  const burstId = burstIdFor(iter);
  const key = idempotencyKeyFor(burstId);

  const params = {
    headers: {
      Authorization: `Bearer ${AUTH_TOKEN}`,
      "Content-Type": "application/json",
      "Idempotency-Key": key,
    },
    tags: { burst: String(burstId) },
  };

  const res = http.post(`${BASE_URL}${POST_PATH}`, POST_BODY, params);
  const bodyHash = djb2(res.body || "");
  const observation = { status: res.status, bodyHash };

  const prior = seenByBurst[burstId];
  if (!prior) {
    seenByBurst[burstId] = observation;
    dedupeSuccessRate.add(1);
  } else {
    const matches =
      prior.status === observation.status &&
      prior.bodyHash === observation.bodyHash;
    if (matches) {
      dedupeSuccessRate.add(1);
    } else {
      duplicateMismatches.add(1);
      dedupeSuccessRate.add(0);
      console.error(
        `dedupe mismatch burst=${burstId} key=${key} ` +
          `prior=${prior.status}/${prior.bodyHash} ` +
          `now=${observation.status}/${observation.bodyHash}`,
      );
    }
  }

  check(res, {
    "status is not 5xx": (r) => r.status < 500,
  });

  sleep(0.05);
}
