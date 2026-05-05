/**
 * HireStack AI \u2014 AIM Section Generation SSE Load Scenario
 *
 * Hits POST /api/aim/sections/{id}/generate-stream and counts SSE events.
 * Requires:
 *   K6_AIM_TOKEN  \u2014 Supabase user JWT
 *   K6_AIM_SECTION_IDS \u2014 comma-separated UUIDs of pre-seeded aim_sections rows
 *   K6_BASE_URL   \u2014 e.g. http://localhost:8000
 *
 * Usage: k6 run k6/scenarios/aim-section-load.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.K6_BASE_URL || "http://localhost:8000";
const TOKEN = __ENV.K6_AIM_TOKEN || "";
const SECTION_IDS = (__ENV.K6_AIM_SECTION_IDS || "").split(",").filter(Boolean);

const eventsCounter = new Counter("aim_sse_events_total");
const passedGate = new Counter("aim_passed_gate_total");
const sectionDuration = new Trend("aim_section_duration_ms", true);

export const options = {
  scenarios: {
    aim_load: {
      executor: "constant-vus",
      vus: 3,
      duration: "5m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    aim_section_duration_ms: ["p(95)<60000"],
  },
};

export default function () {
  if (!TOKEN || SECTION_IDS.length === 0) {
    console.warn("Skip: missing K6_AIM_TOKEN or K6_AIM_SECTION_IDS");
    sleep(5);
    return;
  }
  const sectionId = SECTION_IDS[Math.floor(Math.random() * SECTION_IDS.length)];
  const url = `${BASE}/api/aim/sections/${sectionId}/generate-stream`;
  const start = Date.now();
  const res = http.post(url, null, {
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      Accept: "text/event-stream",
    },
    timeout: "120s",
  });
  sectionDuration.add(Date.now() - start);

  check(res, {
    "status is 200": (r) => r.status === 200,
    "body has events": (r) => (r.body || "").includes("event: "),
  });

  const body = res.body || "";
  const events = (body.match(/^event: /gm) || []).length;
  eventsCounter.add(events);
  if (body.includes('"passed_gate":true') || body.includes('"passed_gate": true')) {
    passedGate.add(1);
  }
  sleep(2);
}
