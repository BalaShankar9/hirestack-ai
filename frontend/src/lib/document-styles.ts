/**
 * Professional document CSS styles for PaperContainer preview and PDF export.
 * Each document type gets distinct typography and layout.
 */

const BASE_CSS = `
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body, html { font-family: 'Calibri', 'Segoe UI', Arial, sans-serif; color: #1a1a2e; line-height: 1.55; }
  h1 { font-size: 22pt; font-weight: 700; color: #1a1a2e; margin-bottom: 2px; letter-spacing: -0.02em; }
  h2 { font-size: 12pt; font-weight: 700; color: #4338ca; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 18px; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 2px solid #4338ca; }
  h3 { font-size: 11pt; font-weight: 600; color: #1a1a2e; margin-top: 10px; margin-bottom: 3px; }
  p { font-size: 10.5pt; margin-bottom: 6px; }
  ul { padding-left: 18px; margin-bottom: 8px; }
  li { font-size: 10.5pt; margin-bottom: 3px; }
  strong { font-weight: 600; }
  em { font-style: italic; }
  a { color: #4338ca; text-decoration: none; }
  .contact-grid { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 9.5pt; color: #555; margin-bottom: 12px; }
  .contact-grid a { color: #4338ca; }
  .skills-grid { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
  .skills-grid span { display: inline-block; background: #f0f0ff; color: #4338ca; padding: 2px 8px; border-radius: 3px; font-size: 9pt; font-weight: 500; }
`;

export const DOCUMENT_CSS: Record<string, string> = {
  resume: `
    ${BASE_CSS}
    h1 { font-size: 20pt; }
    h2 { font-size: 10.5pt; margin-top: 14px; margin-bottom: 6px; }
    p, li { font-size: 10pt; line-height: 1.45; }
    ul { padding-left: 16px; }
    li { margin-bottom: 2px; }
  `,

  cv: `
    ${BASE_CSS}
    h1 { font-size: 24pt; text-align: center; margin-bottom: 4px; }
    h2 { font-size: 13pt; color: #1e3a5f; border-bottom-color: #1e3a5f; letter-spacing: 0.1em; margin-top: 22px; }
    h3 { font-size: 11.5pt; }
    p, li { font-size: 10.5pt; line-height: 1.6; }
    .contact-grid { justify-content: center; margin-bottom: 16px; }
  `,

  personalStatement: `
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body, html { font-family: 'Georgia', 'Times New Roman', serif; color: #1a1a2e; line-height: 1.75; }
    h1 { font-family: 'Calibri', sans-serif; font-size: 18pt; font-weight: 700; color: #1a1a2e; margin-bottom: 16px; text-align: center; }
    p { font-size: 11.5pt; margin-bottom: 14px; text-align: justify; text-indent: 24px; }
    p:first-of-type { text-indent: 0; }
    p:first-of-type::first-letter { font-size: 2.5em; float: left; line-height: 0.8; margin-right: 6px; margin-top: 4px; font-weight: 700; color: #4338ca; }
    strong { font-weight: 700; }
    em { font-style: italic; }
  `,

  portfolio: `
    ${BASE_CSS}
    h1 { font-size: 20pt; color: #4338ca; }
    h2 { font-size: 14pt; color: #1a1a2e; border-bottom: none; text-transform: none; letter-spacing: normal; margin-top: 20px; }
    h3 { font-size: 11pt; color: #4338ca; margin-top: 12px; }
    .project-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .project-card h3 { margin-top: 0; }
    .tech-stack { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
    .tech-stack span { background: #f0fdf4; color: #059669; padding: 2px 8px; border-radius: 3px; font-size: 9pt; font-weight: 500; }
    ul { list-style-type: "→  "; }
    li { margin-bottom: 4px; }
  `,
};

export type DocumentType = keyof typeof DOCUMENT_CSS;

export function getDocumentCSS(type: DocumentType): string {
  return DOCUMENT_CSS[type] || DOCUMENT_CSS.resume;
}
