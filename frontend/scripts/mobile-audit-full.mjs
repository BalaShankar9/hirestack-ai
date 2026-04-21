// Visit ALL dashboard routes at iPhone width using dev mock auth bypass.
// Detect horizontal overflow + capture screenshots.
import { chromium, devices } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:3002";
const VW = devices["iPhone 12"].viewport.width; // 390
const QS = "audit_mock_auth=1";

const ROUTES = [
  "/",
  "/login",
  "/dashboard",
  "/new",
  "/evidence",
  "/nexus",
  "/settings",
  "/settings/audit",
  "/settings/billing",
  "/settings/members",
  "/candidates",
  "/api-keys",
  "/ats-scanner",
  "/interview",
  "/salary",
  "/career",
  "/career-analytics",
  "/job-board",
  "/learning",
  "/gaps",
  "/skills",
  "/knowledge",
  "/ab-lab",
];

async function audit(page, route) {
  const sep = route.includes("?") ? "&" : "?";
  const url = `${BASE}${route}${route === "/" || route === "/login" ? "" : sep + QS}`;
  console.log(`\n=== ${route} ===`);
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 25000 });
  } catch (e) {
    console.log(`  load error: ${e.message}`);
    return;
  }
  await page.waitForTimeout(2500);

  const final = page.url();
  if (!final.startsWith(url.split("?")[0])) {
    console.log(`  redirected -> ${final}`);
  }

  const overflow = await page.evaluate((vw) => {
    const out = [];
    document.querySelectorAll("body *").forEach((el) => {
      const r = el.getBoundingClientRect();
      const s = window.getComputedStyle(el);
      if (s.position === "fixed" || s.position === "absolute") return;
      if (el.tagName === "HTML" || el.tagName === "BODY") return;
      if (r.width > vw + 1 && r.right > vw + 1) {
        out.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className || "").toString().slice(0, 100),
          w: Math.round(r.width),
          right: Math.round(r.right),
          text: (el.textContent || "").trim().slice(0, 50),
        });
      }
    });
    return { scrollW: document.documentElement.scrollWidth, items: out.slice(0, 12) };
  }, VW);

  const overflowed = overflow.scrollW > VW;
  if (overflowed) console.log(`  ⚠ HORIZONTAL OVERFLOW: scrollW=${overflow.scrollW} (vw=${VW}, +${overflow.scrollW - VW}px)`);
  else console.log(`  ✓ no horizontal overflow`);

  if (overflow.items.length === 0 && !overflowed) {
    // skip detail
  } else {
    overflow.items.forEach((it) => {
      console.log(`    <${it.tag}> w=${it.w} right=${it.right} :: ${it.cls.slice(0, 80)} :: "${it.text.slice(0, 40)}"`);
    });
  }

  const safe = (route.replace(/[^a-z0-9]+/gi, "_") || "root");
  await page.screenshot({ path: `output/mobile-audit/${safe}.png`, fullPage: true });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices["iPhone 12"] });
  const page = await ctx.newPage();

  for (const r of ROUTES) await audit(page, r);

  await browser.close();
  console.log("\n✓ Done. Screenshots in output/mobile-audit/");
})();
