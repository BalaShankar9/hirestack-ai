/**
 * HireStack AI - Professional Document Export Engine
 * Elite-quality PDF, Word (DOCX), and Image export with branded templates + ZIP bundle
 */

// Dynamic imports to avoid SSR issues
const loadHtml2Pdf = async () => {
  if (typeof window === "undefined") {
    throw new Error("PDF export is only available in the browser");
  }
  const mod = await import("html2pdf.js");
  return mod.default;
};

const loadHtml2Canvas = async () => {
  if (typeof window === "undefined") {
    throw new Error("Image export is only available in the browser");
  }
  const mod = await import("html2canvas");
  return mod.default;
};

export interface ExportOptions {
  filename?: string;
  format?: "pdf" | "html" | "docx" | "jpg" | "png";
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

  if (!htmlContent || htmlContent.trim().length === 0) {
    throw new Error("Cannot export empty content to PDF");
  }

  // Create a container for rendering
  const container = document.createElement("div");
  container.className = "pdf-container";
  container.textContent = "";  // Clear safely
  // Parse HTML through DOMParser for safe insertion (no script execution)
  const parser = new DOMParser();
  const parsed = parser.parseFromString(htmlContent, "text/html");
  // Remove any script tags from parsed content
  parsed.querySelectorAll("script").forEach(el => el.remove());
  while (parsed.body.firstChild) {
    container.appendChild(parsed.body.firstChild);
  }

  // Add professional branded styling based on document type
  const styleSheet = document.createElement("style");
  const docStyles = PROFESSIONAL_STYLES[opts.documentType ?? "cv"] || PROFESSIONAL_STYLES.cv;
  styleSheet.textContent = docStyles;
  container.prepend(styleSheet);

  // Add to DOM for rendering — must be visible for html2canvas to capture
  // Using fixed positioning with opacity 0 (invisible but renderable)
  container.style.position = "fixed";
  container.style.top = "0";
  container.style.left = "0";
  container.style.width = opts.pageSize === "a4" ? "210mm" : "8.5in";
  container.style.background = "#ffffff";
  container.style.zIndex = "-9999";
  container.style.opacity = "0.01"; // Near-invisible but still rendered by html2canvas
  document.body.appendChild(container);

  try {
    // Wait a tick for the browser to layout the container
    await new Promise((r) => setTimeout(r, 100));

    const pdfOptions = {
      margin: opts.margin,
      filename: `${opts.filename}.pdf`,
      image: { type: "jpeg" as const, quality: 0.98 },
      html2canvas: {
        scale: opts.quality,
        useCORS: true,
        letterRendering: true,
        logging: false,
        backgroundColor: "#ffffff",
        windowWidth: opts.pageSize === "a4" ? 794 : 816, // px equivalent
      },
      jsPDF: {
        unit: "in" as const,
        format: opts.pageSize,
        orientation: "portrait" as const,
      },
      pagebreak: { mode: ["avoid-all", "css", "legacy"] },
    };

    // Use the explicit pipeline: from → toCanvas → toPdf → output
    const pdfBlob: Blob = await html2pdf()
      .set(pdfOptions)
      .from(container)
      .toPdf()
      .output("blob");

    if (!pdfBlob || pdfBlob.size < 100) {
      throw new Error("PDF generation produced empty output");
    }

    return pdfBlob;
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
      await downloadDocx(htmlContent, opts);
      break;
    case "jpg":
    case "png":
      await downloadImage(htmlContent, opts);
      break;
    default:
      throw new Error(`Unsupported format: ${opts.format}`);
  }
}

/**
 * Export HTML content to Word (.docx) file
 * Uses the HTML-to-MHTML technique — Word can natively open styled HTML as .docx
 */
export async function downloadDocx(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  if (!htmlContent || htmlContent.trim().length === 0) {
    throw new Error("Cannot export empty content to DOCX");
  }

  const docStyles = PROFESSIONAL_STYLES[opts.documentType ?? "cv"] || PROFESSIONAL_STYLES.cv;

  // Build a complete HTML document that Word can open natively
  const fullHtml = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
  <meta charset="utf-8">
  <meta name="ProgId" content="Word.Document">
  <meta name="Generator" content="HireStack AI">
  <!--[if gte mso 9]>
  <xml>
    <w:WordDocument>
      <w:View>Print</w:View>
      <w:Zoom>100</w:Zoom>
      <w:DoNotOptimizeForBrowser/>
    </w:WordDocument>
  </xml>
  <![endif]-->
  <style>
    ${docStyles}
    @page {
      size: ${opts.pageSize === "a4" ? "A4" : "letter"};
      margin: ${opts.margin}in;
    }
    body { font-family: Calibri, Arial, sans-serif; }
  </style>
</head>
<body>
${htmlContent}
</body>
</html>`;

  const blob = new Blob([fullHtml], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${opts.filename}.docx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Export HTML content to Image (JPG/PNG) file
 */
export async function downloadImage(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<void> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const html2canvas = await loadHtml2Canvas();

  if (!htmlContent || htmlContent.trim().length === 0) {
    throw new Error("Cannot export empty content to image");
  }

  // Create a container for rendering
  const container = document.createElement("div");
  container.className = "pdf-container";
  container.textContent = "";  // Clear safely
  // Parse HTML through DOMParser for safe insertion (no script execution)
  const imgParser = new DOMParser();
  const imgParsed = imgParser.parseFromString(htmlContent, "text/html");
  imgParsed.querySelectorAll("script").forEach(el => el.remove());
  while (imgParsed.body.firstChild) {
    container.appendChild(imgParsed.body.firstChild);
  }

  const styleSheet = document.createElement("style");
  const docStyles = PROFESSIONAL_STYLES[opts.documentType ?? "cv"] || PROFESSIONAL_STYLES.cv;
  styleSheet.textContent = docStyles;
  container.prepend(styleSheet);

  container.style.position = "fixed";
  container.style.top = "0";
  container.style.left = "0";
  container.style.width = "8.5in";
  container.style.padding = "0.5in";
  container.style.background = "#ffffff";
  container.style.zIndex = "-9999";
  container.style.opacity = "0.01";
  document.body.appendChild(container);

  try {
    await new Promise((r) => setTimeout(r, 100));

    const canvas = await html2canvas(container, {
      scale: 2,
      useCORS: true,
      backgroundColor: "#ffffff",
      logging: false,
    });

    const isJpg = opts.format === "jpg";
    const mimeType = isJpg ? "image/jpeg" : "image/png";
    const ext = isJpg ? "jpg" : "png";

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${opts.filename}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      },
      mimeType,
      isJpg ? 0.95 : undefined
    );
  } finally {
    document.body.removeChild(container);
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
  /** Additional documents (benchmark docs, generated docs, library items) */
  extraDocuments?: Array<{ name: string; html: string; type?: string; category?: string }>;
}

/**
 * Download all documents as a branded ZIP bundle with PDFs and DOCX
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
  const pdfFolder = folder.folder("PDF")!;
  const docxFolder = folder.folder("Word")!;

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

  // Extra documents (benchmark docs, generated docs, library items)
  if (bundle.extraDocuments) {
    let idx = pdfTasks.length + 1;
    for (const extra of bundle.extraDocuments) {
      if (!extra.html) continue;
      const num = String(idx).padStart(2, "0");
      const safeName = extra.name.replace(/[^a-zA-Z0-9_\-\s]/g, "").replace(/\s+/g, "_");
      pdfTasks.push({ name: `${num}_${safeName}`, html: extra.html, type: (extra.type as ExportOptions["documentType"]) || "cv" });
      idx++;
    }
  }

  if (pdfTasks.length === 0) {
    throw new Error("No documents available to export yet. Generate modules first, then export.");
  }

  // Load html-to-docx for DOCX generation (browser-compatible)
  const generateDocxBlob = (html: string, type: string): Blob => {
    const docStyles = PROFESSIONAL_STYLES[type ?? "cv"] || PROFESSIONAL_STYLES.cv;
    const fullHtml = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><style>${docStyles}</style></head>
<body>${html}</body></html>`;
    return new Blob([fullHtml], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
  };

  // Generate all PDFs and DOCX in sequence
  for (const task of pdfTasks) {
    // PDF
    try {
      const pdfBlob = await exportToPdf(task.html, {
        ...options,
        filename: task.name,
        documentType: task.type,
      });
      pdfFolder.file(`${task.name}.pdf`, pdfBlob);
    } catch (err) {
      console.warn(`Failed to generate PDF for ${task.name}:`, err);
      pdfFolder.file(`${task.name}.html`, task.html);
    }

    // DOCX
    try {
      const docxBlob = generateDocxBlob(task.html, task.type ?? "cv");
      docxFolder.file(`${task.name}.docx`, docxBlob);
    } catch (err) {
      console.warn(`Failed to generate DOCX for ${task.name}:`, err);
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
