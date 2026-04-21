// Visit public + dashboard routes at iPhone width.
// For dashboard routes, inject a mock auth state so middleware/layout doesn't redirect.
// Report any element wider than viewport (horizontal overflow culprits).
import { chromium, devices } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:3002";
const VIEWPORT = devices["iPhone 12"].viewport; // 390x844

const PUBLIC_ROUTES = ["/", "/login", "/login?mode=register", "/privacy", "/terms"];

// We can't easily auth without creds, so we'll only check public routes for real signal
// AND check dashboard routes after disabling middleware redirect via document cookies hack.
// Without auth dashboard pages will redirect to /login — accept that.

async function audit(page, route) {
  const url = `${BASE}${route}`;
  console.log(`\n=== ${route} ===`);
  await page.goto(url, { waitUntil: "networkidle", timeout: 30000 }).catch((e) => {
    console.log(`  load error: ${e.message}`);
  });
  await page.waitForTimeout(500);

  const finalUrl = page.url();
  if (finalUrl !== url && !finalUrl.startsWith(url)) {
    console.log(`  redirected -> ${finalUrl}`);
  }

  const overflow = await page.evaluate((vw) => {
    const out = [];
    const all = document.querySelectorAll("body *");
    all.forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > vw + 1 && r.right > vw + 1) {
        const s = window.getComputedStyle(el);
        if (s.position === "fixed" || s.position === "absolute") return; // ignore positioned decoratives
        if (el.tagName === "HTML" || el.tagName === "BODY") return;
        out.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className || "").toString().slice(0, 120),
          w: Math.round(r.width),
          right: Math.round(r.right),
          text: (el.textContent || "").trim().slice(0, 60),
        });
      }
    });
    return { vw, scrollW: document.documentElement.scrollWidth, items: out.slice(0, 25) };
  }, VIEWPORT.width);

  console.log(`  vw=${overflow.vw} scrollW=${overflow.scrollW}`);
  if (overflow.scrollW > overflow.vw) {
    console.log(`  ⚠ HORIZONTAL OVERFLOW (${overflow.scrollW - overflow.vw}px)`);
  }
  if (overflow.items.length === 0) {
    console.log(`  ✓ no overflow elements`);
  } else {
    overflow.items.forEach((it) => {
      console.log(`  - <${it.tag}> w=${it.w} right=${it.right} "${it.text}" :: ${it.cls}`);
    });
  }

  // Save screenshot
  const safe = route.replace(/[^a-z0-9]+/gi, "_") || "root";
  await page.screenshot({ path: `output/mobile-audit/${safe}.png`, fullPage: true });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices["iPhone 12"] });
  const page = await ctx.newPage();

  for (const r of PUBLIC_ROUTES) {
    await audit(page, r);
  }

  await browser.close();
  console.log("\nDone. Screenshots in output/mobile-audit/");
})();
