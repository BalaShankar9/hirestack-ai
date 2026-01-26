import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const src = path.join(root, "node_modules", "pdfjs-dist", "build", "pdf.worker.mjs");
const destDir = path.join(root, "public");
const dest = path.join(destDir, "pdf.worker.mjs");

try {
  if (!fs.existsSync(src)) {
    console.error(`[copy-pdf-worker] Source not found: ${src}`);
    process.exit(1);
  }

  fs.mkdirSync(destDir, { recursive: true });

  const inStat = fs.statSync(src);
  const outStat = fs.existsSync(dest) ? fs.statSync(dest) : null;
  if (outStat && outStat.size === inStat.size) {
    // Assume already copied.
    process.exit(0);
  }

  fs.copyFileSync(src, dest);
  console.log(`[copy-pdf-worker] Copied to ${path.relative(root, dest)} (${inStat.size} bytes)`);
} catch (err) {
  console.error("[copy-pdf-worker] Failed:", err);
  process.exit(1);
}

