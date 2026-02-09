/**
 * HireStack AI - Professional Document Export Engine
 * Elite-quality PDF export with branded templates + ZIP bundle
 */

// Dynamic import to avoid SSR issues
const loadHtml2Pdf = async () => {
  if (typeof window === "undefined") {
    throw new Error("PDF export is only available in the browser");
  }
  const html2pdf = (await import("html2pdf.js")).default;
  return html2pdf;
};

export interface ExportOptions {
  filename?: string;
  format?: "pdf" | "html" | "docx";
  pageSize?: "letter" | "a4";
  margin?: number;
  quality?: number;
  documentType?: "cv" | "coverLetter" | "personalStatement" | "portfolio" | "learningPlan" | "benchmark" | "gapAnalysis";
}

const DEFAULT_OPTIONS: Required<ExportOptions> = {
  filename: "document",
  format: "pdf",
  pageSize: "letter",
  margin: 0.5,
  quality: 2,
  documentType: "cv",
};

/** Professional branded CSS for different document types */
const PROFESSIONAL_STYLES: Record<string, string> = {
  cv: `
    @page { margin: 0.5in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Calibri', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      color: #2d2d2d;
    }
    h1 { font-size: 22pt; margin: 0 0 4pt 0; color: #1a1a2e; font-weight: 700; letter-spacing: -0.3pt; }
    h2 { font-size: 12pt; margin: 14pt 0 6pt 0; color: #1a1a2e; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2pt; border-bottom: 2pt solid #4338ca; padding-bottom: 3pt; }
    h3 { font-size: 11pt; margin: 8pt 0 2pt 0; color: #1a1a2e; font-weight: 600; }
    p { margin: 0 0 6pt 0; }
    ul, ol { margin: 2pt 0 6pt 0; padding-left: 16pt; }
    li { margin-bottom: 3pt; }
    li::marker { color: #4338ca; }
    strong { color: #1a1a2e; font-weight: 600; }
    em { color: #6b7280; }
    a { color: #4338ca; text-decoration: none; }
  `,
  coverLetter: `
    @page { margin: 0.75in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Georgia', 'Cambria', 'Times New Roman', serif;
      font-size: 11.5pt;
      line-height: 1.7;
      color: #2d2d2d;
    }
    p { margin: 0 0 12pt 0; text-align: justify; }
    p:first-child { margin-top: 0; }
    strong { color: #1a1a2e; }
    em { font-style: italic; }
  `,
  personalStatement: `
    @page { margin: 0.75in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Georgia', 'Cambria', 'Times New Roman', serif;
      font-size: 11.5pt;
      line-height: 1.75;
      color: #2d2d2d;
    }
    p { margin: 0 0 14pt 0; text-align: justify; text-indent: 0; }
    p:first-child { text-indent: 0; }
    strong { color: #1a1a2e; }
    em { font-style: italic; }
  `,
  portfolio: `
    @page { margin: 0.6in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Calibri', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      color: #2d2d2d;
    }
    h2 { font-size: 16pt; margin: 0 0 10pt 0; color: #1a1a2e; font-weight: 700; border-bottom: 2pt solid #4338ca; padding-bottom: 4pt; }
    h3 { font-size: 12pt; margin: 12pt 0 4pt 0; color: #4338ca; font-weight: 700; }
    .project-card { margin-bottom: 16pt; padding: 10pt 0; border-bottom: 0.5pt solid #e5e7eb; }
    .project-card:last-child { border-bottom: none; }
    p { margin: 0 0 6pt 0; }
    ul { margin: 2pt 0 6pt 0; padding-left: 16pt; }
    li { margin-bottom: 3pt; }
    li::marker { color: #4338ca; }
    strong { color: #1a1a2e; }
    em { color: #6b7280; }
  `,
  learningPlan: `
    @page { margin: 0.5in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Calibri', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      color: #2d2d2d;
    }
    h2 { font-size: 14pt; margin: 14pt 0 8pt 0; color: #1a1a2e; font-weight: 700; border-bottom: 2pt solid #4338ca; padding-bottom: 3pt; }
    h3 { font-size: 11pt; margin: 10pt 0 4pt 0; color: #4338ca; font-weight: 600; }
    p { margin: 0 0 6pt 0; }
    ul, ol { margin: 2pt 0 6pt 0; padding-left: 16pt; }
    li { margin-bottom: 3pt; }
    strong { color: #1a1a2e; }
  `,
  benchmark: `
    @page { margin: 0.5in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Calibri', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      color: #2d2d2d;
    }
    h2 { font-size: 14pt; color: #1a1a2e; border-bottom: 2pt solid #4338ca; padding-bottom: 3pt; }
    h3 { font-size: 11pt; color: #4338ca; }
    p { margin: 0 0 6pt 0; }
    ul { margin: 2pt 0 6pt 0; padding-left: 16pt; }
    li { margin-bottom: 3pt; }
    strong { color: #1a1a2e; }
  `,
  gapAnalysis: `
    @page { margin: 0.5in; }
    * { box-sizing: border-box; }
    body, .pdf-container {
      font-family: 'Calibri', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.55;
      color: #2d2d2d;
    }
    h2 { font-size: 14pt; color: #1a1a2e; border-bottom: 2pt solid #4338ca; padding-bottom: 3pt; }
    h3 { font-size: 11pt; color: #4338ca; }
    p { margin: 0 0 6pt 0; }
    ul { margin: 2pt 0 6pt 0; padding-left: 16pt; }
    li { margin-bottom: 3pt; }
    .severity-high { color: #dc2626; }
    .severity-medium { color: #d97706; }
    .severity-low { color: #16a34a; }
    strong { color: #1a1a2e; }
  `,
};

/**
 * Export HTML content to PDF with professional styling
 */
export async function exportToPdf(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<Blob> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const html2pdf = await loadHtml2Pdf();

  // Create a container for rendering
  const container = document.createElement("div");
  container.className = "pdf-container";
  container.innerHTML = htmlContent;

  // Add professional branded styling based on document type
  const styleSheet = document.createElement("style");
  const docStyles = PROFESSIONAL_STYLES[opts.documentType ?? "cv"] || PROFESSIONAL_STYLES.cv;
  styleSheet.textContent = docStyles;
  container.prepend(styleSheet);

  // Temporarily add to DOM for rendering
  container.style.position = "absolute";
  container.style.left = "-9999px";
  container.style.width = opts.pageSize === "a4" ? "210mm" : "8.5in";
  document.body.appendChild(container);

  try {
    const pdfOptions = {
      margin: opts.margin,
      filename: `${opts.filename}.pdf`,
      image: { type: "jpeg" as const, quality: 0.98 },
      html2canvas: { 
        scale: opts.quality,
        useCORS: true,
        letterRendering: true,
      },
      jsPDF: { 
        unit: "in" as const, 
        format: opts.pageSize, 
        orientation: "portrait" as const,
      },
      pagebreak: { mode: ["avoid-all", "css", "legacy"] },
    };

    const pdfBlob = await html2pdf()
      .set(pdfOptions)
      .from(container)
      .output("blob");

    return pdfBlob as Blob;
  } finally {
    document.body.removeChild(container);
  }
}

/**
 * Export HTML content to downloadable PDF file
 */
export async function downloadPdf(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const blob = await exportToPdf(htmlContent, opts);
  
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${opts.filename}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Export HTML content as HTML file
 */
export function downloadHtml(
  htmlContent: string,
  options: ExportOptions = {}
): void {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  
  const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${opts.filename}</title>
  <style>
    body {
      font-family: 'Georgia', 'Times New Roman', serif;
      font-size: 11pt;
      line-height: 1.6;
      color: #333;
      max-width: 800px;
      margin: 0 auto;
      padding: 40px 20px;
    }
    h1 { font-size: 24pt; margin-bottom: 16px; color: #1a1a1a; }
    h2 { font-size: 16pt; margin-top: 24px; margin-bottom: 12px; color: #2a2a2a; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }
    h3 { font-size: 13pt; margin-top: 16px; margin-bottom: 8px; color: #333; }
    p { margin: 0 0 12px 0; }
    ul, ol { margin: 0 0 12px 0; padding-left: 24px; }
    li { margin-bottom: 6px; }
    strong { color: #1a1a1a; }
    a { color: #2563eb; }
    @media print {
      body { margin: 0; padding: 20px; }
    }
  </style>
</head>
<body>
${htmlContent}
</body>
</html>`;

  const blob = new Blob([fullHtml], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${opts.filename}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Export document based on format
 */
export async function exportDocument(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  
  switch (opts.format) {
    case "pdf":
      await downloadPdf(htmlContent, opts);
      break;
    case "html":
      downloadHtml(htmlContent, opts);
      break;
    case "docx":
      // DOCX export would require additional library like docx
      // For now, fall back to HTML which can be opened in Word
      console.warn("DOCX export not yet implemented, falling back to HTML");
      downloadHtml(htmlContent, { ...opts, filename: `${opts.filename}` });
      break;
    default:
      throw new Error(`Unsupported format: ${opts.format}`);
  }
}

/**
 * Generate a professional resume PDF from structured data
 */
export async function generateResumePdf(
  name: string,
  email: string,
  phone: string | undefined,
  location: string | undefined,
  summary: string | undefined,
  experience: Array<{
    title: string;
    company: string;
    dates: string;
    highlights: string[];
  }>,
  education: Array<{
    degree: string;
    institution: string;
    year: string;
  }>,
  skills: string[],
  options: ExportOptions = {}
): Promise<void> {
  const html = `
    <h1 style="text-align: center; margin-bottom: 4px;">${name}</h1>
    <p style="text-align: center; font-size: 10pt; color: #666; margin-bottom: 20px;">
      ${[email, phone, location].filter(Boolean).join(" • ")}
    </p>
    
    ${summary ? `
    <h2>Professional Summary</h2>
    <p>${summary}</p>
    ` : ""}
    
    ${experience.length > 0 ? `
    <h2>Experience</h2>
    ${experience.map(exp => `
      <h3 style="margin-bottom: 2px;">${exp.title}</h3>
      <p style="color: #666; font-size: 10pt; margin-bottom: 8px;">${exp.company} • ${exp.dates}</p>
      <ul>
        ${exp.highlights.map(h => `<li>${h}</li>`).join("")}
      </ul>
    `).join("")}
    ` : ""}
    
    ${education.length > 0 ? `
    <h2>Education</h2>
    ${education.map(edu => `
      <p><strong>${edu.degree}</strong><br/>
      ${edu.institution}, ${edu.year}</p>
    `).join("")}
    ` : ""}
    
    ${skills.length > 0 ? `
    <h2>Skills</h2>
    <p>${skills.join(" • ")}</p>
    ` : ""}
  `;

  await downloadPdf(html, {
    filename: `${name.replace(/\s+/g, "_")}_Resume`,
    ...options,
  });
}

/* ================================================================== */
/*  ZIP BUNDLE — Download all documents as a single ZIP                */
/* ================================================================== */

export interface DocumentBundle {
  jobTitle: string;
  company: string;
  cvHtml?: string;
  coverLetterHtml?: string;
  personalStatementHtml?: string;
  portfolioHtml?: string;
  learningPlanHtml?: string;
  benchmarkHtml?: string;
  gapAnalysisHtml?: string;
}

/**
 * Download all documents as a branded ZIP bundle with PDFs
 */
export async function downloadAllAsZip(
  bundle: DocumentBundle,
  options: ExportOptions = {}
): Promise<void> {
  const JSZip = (await import("jszip")).default;
  const zip = new JSZip();

  const prefix = `${bundle.company || "Application"}_${bundle.jobTitle || "Role"}`
    .replace(/[^a-zA-Z0-9_\-\s]/g, "")
    .replace(/\s+/g, "_");

  const folder = zip.folder(`HireStack_${prefix}`)!;

  // Generate PDFs for each available document
  const pdfTasks: Array<{ name: string; html: string; type: ExportOptions["documentType"] }> = [];

  if (bundle.cvHtml) {
    pdfTasks.push({ name: "01_Tailored_CV", html: bundle.cvHtml, type: "cv" });
  }
  if (bundle.coverLetterHtml) {
    pdfTasks.push({ name: "02_Cover_Letter", html: bundle.coverLetterHtml, type: "coverLetter" });
  }
  if (bundle.personalStatementHtml) {
    pdfTasks.push({ name: "03_Personal_Statement", html: bundle.personalStatementHtml, type: "personalStatement" });
  }
  if (bundle.portfolioHtml) {
    pdfTasks.push({ name: "04_Portfolio_Evidence", html: bundle.portfolioHtml, type: "portfolio" });
  }
  if (bundle.learningPlanHtml) {
    pdfTasks.push({ name: "05_Learning_Plan", html: bundle.learningPlanHtml, type: "learningPlan" });
  }
  if (bundle.benchmarkHtml) {
    pdfTasks.push({ name: "06_Benchmark_Analysis", html: bundle.benchmarkHtml, type: "benchmark" });
  }
  if (bundle.gapAnalysisHtml) {
    pdfTasks.push({ name: "07_Gap_Analysis", html: bundle.gapAnalysisHtml, type: "gapAnalysis" });
  }

  // Generate all PDFs in sequence (html2pdf can't run in parallel)
  for (const task of pdfTasks) {
    try {
      const pdfBlob = await exportToPdf(task.html, {
        ...options,
        filename: task.name,
        documentType: task.type,
      });
      folder.file(`${task.name}.pdf`, pdfBlob);
    } catch (err) {
      console.warn(`Failed to generate PDF for ${task.name}:`, err);
      // Fall back to HTML if PDF fails
      folder.file(`${task.name}.html`, task.html);
    }
  }

  // Generate and download ZIP
  const zipBlob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(zipBlob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `HireStack_${prefix}_Application_Pack.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Generate HTML for structured data documents (benchmark, gaps, learning plan)
 */
export function buildBenchmarkHtml(benchmark: any, jobTitle: string): string {
  if (!benchmark) return "";
  const skills = (benchmark.idealSkills ?? [])
    .map((s: any) => `<li><strong>${s?.name || "Skill"}</strong> — ${s?.level || "required"} (${s?.importance || "important"})</li>`)
    .join("");
  const rubric = (benchmark.rubric ?? [])
    .map((r: any) => `<li>${typeof r === "string" ? r : r?.dimension || JSON.stringify(r)}</li>`)
    .join("");
  const keywords = (benchmark.keywords ?? []).join(", ");

  return `
    <h2>Benchmark — Ideal Candidate Profile</h2>
    <p><em>Target role: ${jobTitle}</em></p>
    <p>${benchmark.summary || ""}</p>
    <h3>Key Skills Required</h3>
    <ul>${skills}</ul>
    <h3>Scoring Rubric</h3>
    <ul>${rubric}</ul>
    <h3>Target Keywords</h3>
    <p>${keywords}</p>
  `;
}

export function buildGapAnalysisHtml(gaps: any): string {
  if (!gaps) return "";
  const missing = (gaps.missingKeywords ?? []).map((k: any) =>
    `<li>${typeof k === "string" ? k : k?.dimension || JSON.stringify(k)}</li>`
  ).join("");
  const strengths = (gaps.strengths ?? []).map((s: any) =>
    `<li>${typeof s === "string" ? s : s?.area || JSON.stringify(s)}</li>`
  ).join("");
  const recs = (gaps.recommendations ?? []).map((r: any) =>
    `<li>${typeof r === "string" ? r : r?.title || JSON.stringify(r)}</li>`
  ).join("");

  return `
    <h2>Gap Analysis</h2>
    ${gaps.compatibility != null ? `<p><strong>Compatibility Score: ${gaps.compatibility}%</strong></p>` : ""}
    ${gaps.summary ? `<p>${gaps.summary}</p>` : ""}
    <h3>Missing Keywords</h3>
    <ul>${missing}</ul>
    <h3>Strengths</h3>
    <ul>${strengths}</ul>
    <h3>Recommendations</h3>
    <ul>${recs}</ul>
  `;
}

export function buildLearningPlanHtml(plan: any): string {
  if (!plan) return "";
  const focus = (plan.focus ?? []).join(", ");
  const weeks = (plan.plan ?? []).map((w: any) => {
    const outcomes = (w.outcomes ?? w.goals ?? []).map((o: any) => `<li>${typeof o === "string" ? o : JSON.stringify(o)}</li>`).join("");
    const tasks = (w.tasks ?? []).map((t: any) => `<li>${typeof t === "string" ? t : JSON.stringify(t)}</li>`).join("");
    return `
      <h3>Week ${w.week}: ${w.theme || ""}</h3>
      <p><strong>Outcomes:</strong></p><ul>${outcomes}</ul>
      <p><strong>Tasks:</strong></p><ul>${tasks}</ul>
    `;
  }).join("");
  const resources = (plan.resources ?? []).map((r: any) =>
    `<li><strong>${r.title || ""}</strong> — ${r.provider || "Resource"} (${r.timebox || "Self-paced"})</li>`
  ).join("");

  return `
    <h2>Learning Plan</h2>
    <p><strong>Focus Areas:</strong> ${focus}</p>
    ${weeks}
    <h3>Recommended Resources</h3>
    <ul>${resources}</ul>
  `;
}
