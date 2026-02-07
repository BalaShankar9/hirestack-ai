/**
 * HireStack AI - Document Export Utilities
 * Provides PDF export functionality for resumes and cover letters
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
}

const DEFAULT_OPTIONS: Required<ExportOptions> = {
  filename: "document",
  format: "pdf",
  pageSize: "letter",
  margin: 0.5,
  quality: 2,
};

/**
 * Export HTML content to PDF
 */
export async function exportToPdf(
  htmlContent: string,
  options: ExportOptions = {}
): Promise<Blob> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const html2pdf = await loadHtml2Pdf();

  // Create a container for rendering
  const container = document.createElement("div");
  container.innerHTML = htmlContent;
  container.style.cssText = `
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #333;
    max-width: 100%;
  `;

  // Add professional styling for resume/CV
  const styleSheet = document.createElement("style");
  styleSheet.textContent = `
    h1 { font-size: 18pt; margin-bottom: 8pt; color: #1a1a1a; }
    h2 { font-size: 14pt; margin-top: 12pt; margin-bottom: 6pt; color: #2a2a2a; border-bottom: 1px solid #ddd; padding-bottom: 4pt; }
    h3 { font-size: 12pt; margin-top: 8pt; margin-bottom: 4pt; color: #333; }
    p { margin: 0 0 8pt 0; }
    ul, ol { margin: 0 0 8pt 0; padding-left: 20pt; }
    li { margin-bottom: 4pt; }
    strong { color: #1a1a1a; }
    a { color: #2563eb; text-decoration: none; }
    table { width: 100%; border-collapse: collapse; margin: 8pt 0; }
    th, td { padding: 4pt 8pt; border: 1px solid #ddd; text-align: left; }
    th { background: #f5f5f5; }
  `;
  container.prepend(styleSheet);

  // Temporarily add to DOM for rendering
  container.style.position = "absolute";
  container.style.left = "-9999px";
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
      .outputPdf("blob");

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
