import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const src = path.join(root, "node_modules", "pdfjs-dist", "build", "pdf.worker.mjs");
const destDir = path.join(root, "public");
const dest = path.join(destDir, "pdf.worker.mjs");
const assetsRoot = path.join(destDir, "pdfjs");

try {
  if (!fs.existsSync(src)) {
    console.error(`[copy-pdf-worker] Source not found: ${src}`);
    process.exit(1);
  }

  fs.mkdirSync(destDir, { recursive: true });

  const inStat = fs.statSync(src);
  const outStat = fs.existsSync(dest) ? fs.statSync(dest) : null;
  const workerUpToDate = outStat && outStat.size === inStat.size;
  if (!workerUpToDate) {
    fs.copyFileSync(src, dest);
    console.log(`[copy-pdf-worker] Copied to ${path.relative(root, dest)} (${inStat.size} bytes)`);
  }

  // Copy supporting assets (cmaps + standard fonts) for reliable text extraction.
  const dirsToCopy = [
    { name: "cmaps", src: path.join(root, "node_modules", "pdfjs-dist", "cmaps") },
    { name: "standard_fonts", src: path.join(root, "node_modules", "pdfjs-dist", "standard_fonts") },
  ];

  for (const d of dirsToCopy) {
    const out = path.join(assetsRoot, d.name);
    if (!fs.existsSync(d.src)) {
      console.warn(`[copy-pdf-worker] Skipping missing dir: ${d.src}`);
      continue;
    }
    if (fs.existsSync(out)) {
      continue;
    }
    fs.mkdirSync(assetsRoot, { recursive: true });
    fs.cpSync(d.src, out, { recursive: true });
    console.log(`[copy-pdf-worker] Copied ${d.name} → ${path.relative(root, out)}`);
  }
} catch (err) {
  console.error("[copy-pdf-worker] Failed:", err);
  process.exit(1);
}
