# AIM Academic Production Workspace Plan

Date: 2026-05-07
Scope: Assignment Intelligence Module only

## Executive Verdict

AIM is currently a real academic assignment module with a strong backend and agent pipeline, but it is not yet the full academic production workspace users around the world will need. The existing system is good at brief parsing, assignment planning, section generation, review loops, grade prediction, deadline planning, and diagnostic fixes. It does not yet cover the wider universe of academic deliverables: reliable source libraries, citation verification, research attachments, data tables, charts, Excel workbooks, figures, diagrams, posters, presentations, appendices, and reusable academic evidence for the Career Knowledge layer.

The product direction should be: AIM becomes a separate academic workspace inside HireStack that can produce and manage every artifact needed for coursework, dissertations, research reports, and academic/professional submissions. It should feed selected outcomes into Career Knowledge as verified academic evidence, but it should not be framed as a job-application feature.

## Current State Confirmed

Audited areas:

- Backend AIM routes and services: assignment CRUD, documents, analysis, sections, streaming generation, grade prediction, deadline planning, quota.
- AIM agents: Parser, Recon, Writer, Reviewer, Grade Predictor, Fix agent.
- Database schema: AIM has separate `aim_*` tables with RLS and section event persistence.
- Frontend: assignment list, assignment workbench, section workbench, deadline mode.
- Tests: focused AIM backend suite passed with 74 tests; frontend AIM stream resume test passed with 2 tests.

Current strengths:

- Real section-level academic pipeline.
- Strict reviewer and quality gate: score >= 85 and all key dimensions >= 85 before surfacing as passed.
- Deterministic quality filters for filler, repetition, and lack of critique.
- Persistent section outputs with current-version selection.
- Streaming events with replay support.
- Deadline Mode exists.
- Document upload supports PDF, DOCX, and TXT through the shared file parser.

Current gaps:

- No source library or citation verification inside AIM.
- No source reliability scoring.
- No DOI, URL, bibliography, or citation ledger tables.
- No chart/data/spreadsheet workflow.
- No poster/design workflow.
- No dissertation-scale chapter memory or coherence layer.
- No whole-document export package for assignment submissions.
- No AIM-to-Career-Knowledge bridge.
- UI is functional but not polished enough for a premium academic product.

## Reusable Platform Capabilities Found

The repo already has building blocks that should be reused after hardening:

| Need | Existing Capability | Status |
| --- | --- | --- |
| PDF/DOCX/TXT input parsing | `AIMDocumentParser` uses shared `FileParser` | Usable |
| PDF/DOCX/Markdown export | `ExportService` | Usable, but generic |
| Client-side PDF/image export | `frontend/src/lib/export.ts` | Usable for UI snapshots/posters |
| PPTX generation | `PPTOrchestrator` and `/api/ppt/generate` | Usable as foundation |
| Stock image lookup | `ImageFetcher` with Unsplash/Pexels | Usable if API keys and licensing metadata are handled |
| AI image generation | `AIImageGenerator` with OpenAI/Stability providers | Needs hardening before AIM reuse |
| Chart rendering | `ChartRenderer` and `NativeChartRenderer` | Strong reusable foundation |
| Evidence/citation concepts | Existing application evidence and citation tests/contracts | Conceptually reusable, not wired to AIM |

Important hardening note: the PPT AI image generator fallback path should be fixed before AIM depends on it. It currently stores `result.bytes` in one branch, but `GenerationResult` exposes `image_bytes`. That path should be covered by tests before reuse.

## Target Product Shape

AIM should become an academic production studio with these layers:

1. Assignment Workspace
   - Brief, rubric, notes, reference attachments.
   - Parsed directive, rubric criteria, expected deliverables, marking scheme.
   - Sections, chapters, tasks, deadlines, feedback cycles.

2. Research and Source Library
   - Attach PDFs, DOCX files, URLs, DOI links, web pages, book references, notes, datasets.
   - Extract source metadata: title, authors, publication year, publisher/journal, DOI/URL, source type.
   - Score reliability: peer reviewed, textbook, official source, government report, company source, news/media, blog, unknown.
   - Track source use: which paragraph/claim/section uses each source.
   - Generate bibliography in Harvard, APA, MLA, Chicago, IEEE, and custom styles.

3. Academic Artifact Layer
   - Essay/report/dissertation chapters.
   - Literature review matrix.
   - Methodology plan.
   - Data analysis tables.
   - Charts and figures.
   - Excel/CSV workbooks.
   - Appendices.
   - Presentation slides.
   - Academic posters.
   - Reflection logs.
   - Viva/interview preparation notes.

4. Quality and Integrity Layer
   - Reviewer gate per section.
   - Source coverage gate: every material claim has either a linked source or is marked as original analysis.
   - Citation format gate.
   - No fabricated citation gate.
   - Repetition and filler gate.
   - Cross-section coherence gate.
   - Rubric coverage gate.
   - Export readiness gate.

5. Career Knowledge Bridge
   - On user approval, finished assignments become academic evidence.
   - Extract skills, topics, tools, methods, research domains, deliverables, grade band, and proof snippets.
   - Feed into Career Knowledge, evidence portfolio, interview stories, and application tailoring.
   - Keep academic work separate from job applications unless the user opts in.

## Global Deliverable Coverage

Students and professionals need more than essays. AIM should recognize deliverable type from the brief and activate the right artifact tools.

| Deliverable | Required AIM Capabilities |
| --- | --- |
| Standard essay | Brief parser, section plan, writer/reviewer loop, bibliography, final DOCX/PDF export |
| Research report | Source library, method section, data tables, charts, appendices |
| Dissertation/thesis | Chapter planner, source library, literature matrix, methodology, findings, discussion, whole-document coherence |
| Case study | Company/source pack, SWOT/PESTLE/Porter charts, evidence-backed recommendations |
| Lab report | Method/procedure, results tables, charts, figure captions, limitations |
| Data analysis assignment | CSV/XLSX upload, data cleaning notes, charts, statistical explanation, workbook export |
| Business plan | Financial tables, market charts, visuals, PPT/poster/export pack |
| Poster | Layout designer, image finder/generator, chart/figure placement, print-size export |
| Presentation | PPT generator, speaker notes, source slide, chart builder |
| Reflection/logbook | Timeline, learning outcomes, evidence attachment, structured reflection prompts |
| Portfolio submission | Artifact bundle, project narrative, skills extracted into Career Knowledge |

## Reliable Sources and Attachments

AIM needs a first-class source system, not just a document upload box.

Source types:

- Assignment brief.
- Rubric/marking scheme.
- Lecture notes.
- Journal article.
- Book/book chapter.
- Official report.
- Government/NGO/statistical source.
- Company report.
- Dataset.
- Web page.
- Image/figure source.
- User notes.

Source metadata should include:

- Title.
- Authors.
- Year.
- Publisher or journal.
- DOI.
- URL.
- Access date.
- Source type.
- Reliability tier.
- User-provided or system-found.
- Extracted summary.
- Relevant quotes.
- Sections where used.

Reliability tiers:

- Tier 1: peer-reviewed article, textbook, official standards, official statistics.
- Tier 2: government/NGO/institution report, reputable industry report.
- Tier 3: company report, trade publication, reputable news outlet.
- Tier 4: web page, blog, unsourced article, unclear origin.
- Blocked: source with missing metadata, broken URL, suspicious content, or unverifiable citation.

Quality rule: AIM should not invent citations. If a source is not attached or verified, the writer must say it needs a source rather than fabricate one.

## Images, Figures, and Diagrams

Image support should be split into three paths:

1. User-attached images
   - Diagrams, screenshots, photos, scanned figures.
   - Require alt text, caption, source attribution, and permission/license field.

2. Found images
   - Use stock/image search providers only when configured.
   - Store provider, source URL, license/attribution notes, alt text, and usage rights.
   - Never drop an uncredited image into a final academic artifact.

3. Generated images
   - Use only where academically appropriate: conceptual illustration, poster background, visual metaphor, diagram draft.
   - Must be labelled as AI-generated when required by institution policy.
   - Should not generate fake data visualizations or fake evidence.

Diagrams needed:

- Concept maps.
- Framework diagrams.
- Process flows.
- Architecture diagrams.
- Research methodology flow.
- Timeline diagrams.
- Poster visual hierarchy.

## Charts, Tables, and Excel Workbooks

Current chart rendering can be reused, but AIM needs an explicit data layer.

Required capabilities:

- Upload CSV/XLSX.
- Create editable data tables.
- Generate summary statistics where appropriate.
- Recommend the right chart type for the data and assignment question.
- Render charts as PNG for DOCX/PDF/poster and native charts for PPTX.
- Export cleaned datasets and analysis workbooks.
- Maintain a chart ledger: data source, transform steps, chart type, caption, section usage.

Recommended backend additions:

- Add `openpyxl` or equivalent XLSX writer.
- Add optional `pandas` only if data analysis depth justifies the dependency.
- Add `aim_data_tables`, `aim_charts`, and `aim_artifact_exports` tables.

Minimum chart types:

- Bar/column.
- Line/area.
- Pie/donut where appropriate.
- Scatter/bubble.
- Histogram.
- Box plot.
- Heatmap.
- Waterfall.
- Radar.
- Funnel.

## Posters and Designed Outputs

Poster support should not be a generic PPT deck. It needs a separate designer workflow.

Poster modes:

- Academic research poster.
- Business/marketing poster.
- Conference poster.
- Infographic.
- One-page visual summary.

Poster builder requirements:

- Size presets: A0, A1, A2, A3, US poster, presentation slide, social preview.
- Grid layout with title, authors, abstract, methods, findings, charts, images, references.
- Export to PDF and PNG.
- Accessibility checks: contrast, readable font sizes, alt text/captions.
- Source/citation block.

The existing PPT and image/chart utilities can support this, but the UI should be purpose-built.

## Dissertation Mode

Dissertation mode must be a separate AIM mode, not just a larger word count.

Required entities:

- Dissertation project.
- Chapters.
- Research questions.
- Literature matrix.
- Methodology design.
- Data collection plan.
- Findings/results.
- Discussion and limitations.
- Supervisor notes.
- Revision history.
- Final submission pack.

Required agents:

- Research Question Agent.
- Literature Matrix Agent.
- Source Librarian Agent.
- Citation Verifier Agent.
- Methodology Agent.
- Data Analyst Agent.
- Chapter Writer Agent.
- Cross-Chapter Coherence Reviewer.
- Dissertation Examiner.
- Export Packager.

Dissertation readiness rules:

- No chapter can pass if its source coverage is weak.
- Whole-document review must check argument continuity across chapters.
- Literature review must show coverage, debate, gap, and positioning.
- Methodology must link to research questions.
- Findings must not overclaim beyond available data.
- Discussion must answer the original research questions.

## Proposed Database Additions

New tables should be additive and separate from existing AIM tables:

- `aim_sources`
  - Source metadata, reliability tier, raw text, extracted summary, DOI/URL, attachment reference.
- `aim_source_claims`
  - Claim text, source links, section/output link, verification status.
- `aim_citations`
  - Formatted citation strings by style, bibliography entries, validation status.
- `aim_assets`
  - Images, generated visuals, diagrams, figures, source/license metadata.
- `aim_data_tables`
  - Uploaded or generated tables, schema, provenance, transforms.
- `aim_charts`
  - Chart specs, rendered asset link, source data link, caption.
- `aim_artifacts`
  - Final deliverables: essay, chapter, poster, PPT, workbook, appendix, bibliography.
- `aim_knowledge_exports`
  - User-approved exports from AIM into Career Knowledge.

## Proposed Agent Additions

1. Source Librarian
   - Parses uploaded PDFs/URLs/notes into source cards.
   - Extracts metadata and reliability tier.

2. Citation Verifier
   - Checks that citations map to attached or verified sources.
   - Flags fabricated or incomplete references.

3. Evidence Binder
   - Links claims to sources, figures, datasets, or user notes.

4. Data Analyst
   - Reads tables, recommends analysis, produces chart specs.

5. Chart Builder
   - Turns data specs into charts with captions and source notes.

6. Visual Asset Agent
   - Finds or generates appropriate images only when useful and allowed.

7. Poster Designer
   - Creates academic poster layouts and export-ready poster specs.

8. Artifact Packager
   - Builds final ZIP/DOCX/PDF/PPTX/XLSX packs.

9. Academic Knowledge Extractor
   - Converts completed work into career evidence after explicit user approval.

## UI/UX Requirements

AIM needs a premium workspace layout:

- Left rail: assignment, sources, sections, artifacts, deadline, exports.
- Main pane: current work area.
- Right inspector: rubric coverage, quality score, source coverage, issues, tasks.
- Source drawer: attach, search, verify, cite, quote bank.
- Artifact studio: essay, chapter, chart, poster, PPT, spreadsheet.
- Submission checklist: rubric, citations, formatting, word count, source coverage, export status.

The current pages are too raw for this. They should be rebuilt using shared design-system components, typed API contracts, polished loading/empty/error states, and clear save/export flows.

## Honest Product Promise

AIM should not promise guaranteed marks. The correct promise is:

"AIM helps you understand the brief, build a source-backed plan, create the right academic artifacts, review quality against the rubric, and prepare submission-ready work with transparent quality gates."

Avoid:

- "100% pass mark guaranteed."
- "Undetectable AI writing."
- "We will write your dissertation for you."
- "Citations included automatically" unless verified by the source system.

Use:

- "Distinction-targeted support."
- "Source-backed academic workflow."
- "Rubric-aligned quality review."
- "Submission readiness checks."
- "Career evidence extraction from completed academic work."

## Implementation Waves

### Wave 1: AIM Workspace Polish and Typed Contracts

- Add typed AIM frontend models.
- Replace `any` in AIM pages and API methods.
- Polish assignment list, detail, section, and deadline pages.
- Add clear empty states, skeletons, toasts, dialogs, and export entry points.
- Expose manual draft application in the section UI.
- Improve stream replay to apply persisted attempt events, not only completion/error.

### Wave 2: Source Library and Citation Ledger

- Add `aim_sources`, `aim_source_claims`, and `aim_citations`.
- Add source upload and URL source cards.
- Add metadata extraction and reliability tiering.
- Add source coverage checks to reviewer/gate output.
- Add bibliography generation by citation style.

### Wave 3: Artifact Layer

- Add `aim_artifacts` with artifact type/status/version.
- Add final assignment export to DOCX/PDF/Markdown.
- Add appendix and bibliography exports.
- Add ZIP bundle export.

### Wave 4: Data, Charts, and Excel

- Add CSV/XLSX upload and table preview.
- Add chart specs and chart asset generation.
- Add workbook export.
- Add data-to-chart recommendation agent.

### Wave 5: Visuals, Image Search, and Image Generation

- Harden existing image generator and image fetcher.
- Add asset metadata, licensing, attribution, alt text, and AI-generated disclosure.
- Add image/figure insertion into artifacts.

### Wave 6: Poster and Presentation Studio

- Add academic poster artifact type.
- Build poster layout templates.
- Reuse chart/image/PPT rendering where appropriate.
- Export poster to PDF/PNG and presentation to PPTX.

### Wave 7: Dissertation Mode

- Add dissertation project type.
- Add chapters, research questions, literature matrix, supervisor notes, and whole-document review.
- Add cross-chapter coherence reviewer.
- Add dissertation export pack.

### Wave 8: Career Knowledge Bridge

- Add user-approved academic evidence export.
- Extract skills, methods, tools, topics, deliverables, outcomes, and proof snippets.
- Feed selected outputs into Career Knowledge and evidence portfolio.
- Keep AIM data separate unless explicitly exported.

## First Build Recommendation

Start with Wave 1 and Wave 2. Without a polished AIM workspace and source/citation ledger, adding posters or spreadsheets will make the module bigger but not trustworthy. Once sources are reliable and the UI feels serious, charts, Excel, images, posters, and dissertation mode can land cleanly as artifact extensions.

## Implementation Progress

- 2026-05-07: Hardened the reusable PPT AI image generator Stability fallback so successful generated images cache `image_bytes` correctly.
- 2026-05-07: Added AIM source-library foundation: `aim_sources`, `aim_source_claims`, and `aim_citations` migrations; backend source service; AIM source routes; and focused service/route tests.
- 2026-05-07: Wired the AIM source library into the frontend with typed source models, API helpers, an assignment source-library page, assignment-workspace navigation, and focused frontend API tests.
