/**
 * Document Universe — the canonical registry of all application document types.
 *
 * Every document the platform can generate is registered here. Each entry
 * belongs to a tier (`benchmark` or `tailored`) and is flagged as either
 * part of the **core package** (the 7 highest-impact docs recommended for
 * every application) or the **extended catalogue** (available on demand).
 *
 * The catalog is designed to grow: the backend `document_catalog` service
 * and `DocumentPackPlanner` agent can discover new document types from JD
 * analysis and feed them back. Newly discovered types start in the extended
 * set and can be promoted to core via the `auto_evolve` source flag.
 */

/* ── Single document type definition ─────────────────────────────── */

export interface UniverseDocType {
  /** Unique key matching backend doc_type / SEED_CATALOG key */
  key: string;
  /** Human-readable label */
  label: string;
  /** Short description of what this document is for */
  description: string;
  /** Whether this is part of the core recommended package */
  core: boolean;
  /** Grouping category within the tier */
  group: "core" | "professional" | "executive" | "academic" | "compliance" | "technical" | "creative";
}

/* ── Core Package (7 docs) ───────────────────────────────────────── */

export const CORE_PACKAGE_KEYS = [
  "cv",
  "cover_letter",
  "personal_statement",
  "portfolio",
  "executive_summary",
  "elevator_pitch",
  "linkedin_summary",
] as const;

/* ── Tailored Document Universe ──────────────────────────────────── */

export const TAILORED_UNIVERSE: UniverseDocType[] = [
  // ── Core Package ──
  { key: "cv",                  label: "Tailored CV",               description: "ATS-optimised CV tailored to the role's exact requirements",                    core: true,  group: "core" },
  { key: "cover_letter",        label: "Cover Letter",              description: "Evidence-backed narrative connecting your experience to the role",              core: true,  group: "core" },
  { key: "personal_statement",  label: "Personal Statement",        description: "Compelling motivation narrative — authentic, specific, memorable",              core: true,  group: "core" },
  { key: "portfolio",           label: "Portfolio & Evidence",       description: "Curated project showcase proving real capability with outcomes",               core: true,  group: "core" },
  { key: "executive_summary",   label: "Executive Summary",         description: "One-page leadership snapshot for senior and executive roles",                  core: true,  group: "core" },
  { key: "elevator_pitch",      label: "Elevator Pitch",            description: "30-second verbal summary of your candidacy — ready to deliver",                core: true,  group: "core" },
  { key: "linkedin_summary",    label: "LinkedIn Summary",          description: "Keyword-rich LinkedIn About section aligned to target role",                   core: true,  group: "core" },
  // ── Professional ──
  { key: "references_list",     label: "References List",           description: "Formatted reference sheet with contact details and relationship context",       core: false, group: "professional" },
  { key: "follow_up_email",     label: "Follow-Up Email",           description: "Post-interview follow-up reinforcing key strengths and fit",                   core: false, group: "professional" },
  { key: "thank_you_note",      label: "Thank-You Note",            description: "Concise post-interview thank-you with personalised recall",                    core: false, group: "professional" },
  { key: "motivation_letter",   label: "Motivation Letter",         description: "Extended motivation narrative for roles requiring deeper rationale",            core: false, group: "professional" },
  { key: "recommendation_letter_template", label: "Recommendation Letter Template", description: "Pre-drafted recommendation for your referee to adapt",          core: false, group: "professional" },
  { key: "values_statement",    label: "Values Statement",          description: "Personal values alignment to company mission and culture",                     core: false, group: "professional" },
  { key: "professional_development_plan", label: "Development Plan", description: "90-day growth roadmap showing initiative and self-awareness",                 core: false, group: "professional" },
  { key: "interview_prep_guide", label: "Interview Prep Guide",     description: "Role-specific Q&A preparation with STAR examples",                             core: false, group: "professional" },
  { key: "salary_negotiation_script", label: "Salary Negotiation Script", description: "Data-backed negotiation talking points for offer stage",                 core: false, group: "professional" },
  { key: "networking_email",    label: "Networking Email",           description: "Professional outreach template for hiring managers or referrals",              core: false, group: "professional" },
  { key: "linkedin_recommendation_request", label: "LinkedIn Recommendation Request", description: "Template request to former colleagues for LinkedIn endorsement", core: false, group: "professional" },
  // ── Executive ──
  { key: "ninety_day_plan",     label: "90-Day Plan",               description: "Structured onboarding plan demonstrating strategic thinking",                  core: false, group: "executive" },
  { key: "thirty_sixty_ninety_day_plan", label: "30-60-90 Day Plan", description: "Phased integration plan for leadership and management roles",                core: false, group: "executive" },
  { key: "leadership_philosophy", label: "Leadership Philosophy",   description: "Your leadership approach, style, and team-building principles",               core: false, group: "executive" },
  { key: "consulting_deck",    label: "Consulting Deck",            description: "Slide-ready pitch deck for consulting or advisory engagements",               core: false, group: "executive" },
  { key: "board_presentation", label: "Board Presentation",         description: "Executive-level presentation for board or C-suite audiences",                 core: false, group: "executive" },
  { key: "board_bio",          label: "Board Bio",                  description: "Formal biographical summary for board nominations",                           core: false, group: "executive" },
  // ── Academic ──
  { key: "research_statement",  label: "Research Statement",        description: "Research agenda and methodology for academic positions",                       core: false, group: "academic" },
  { key: "teaching_philosophy", label: "Teaching Philosophy",       description: "Pedagogical approach and teaching experience narrative",                       core: false, group: "academic" },
  { key: "publications_list",  label: "Publications List",          description: "Formatted bibliography of your published work",                               core: false, group: "academic" },
  { key: "thesis_abstract",    label: "Thesis Abstract",            description: "Concise summary of thesis research and findings",                             core: false, group: "academic" },
  { key: "grant_proposal",     label: "Grant Proposal",             description: "Funding application narrative with objectives and methodology",               core: false, group: "academic" },
  // ── Compliance ──
  { key: "selection_criteria",  label: "Selection Criteria Response", description: "Point-by-point response to formal selection criteria",                       core: false, group: "compliance" },
  { key: "diversity_statement", label: "Diversity Statement",       description: "Commitment to diversity, equity, and inclusion",                               core: false, group: "compliance" },
  { key: "safety_statement",   label: "Safety Statement",           description: "Workplace safety awareness and commitment",                                   core: false, group: "compliance" },
  { key: "equity_statement",   label: "Equity Statement",           description: "Equity and accessibility practice statement",                                 core: false, group: "compliance" },
  { key: "conflict_of_interest_declaration", label: "COI Declaration", description: "Formal conflict of interest disclosure",                                   core: false, group: "compliance" },
  { key: "capability_statement", label: "Capability Statement",     description: "Organisational capability and capacity summary",                              core: false, group: "compliance" },
  { key: "expression_of_interest", label: "Expression of Interest", description: "Formal EOI for tenders and procurement processes",                            core: false, group: "compliance" },
  { key: "letter_of_intent",   label: "Letter of Intent",           description: "Formal declaration of intent to apply or participate",                        core: false, group: "compliance" },
  { key: "community_engagement_statement", label: "Community Engagement Statement", description: "Community service and outreach involvement",                  core: false, group: "compliance" },
  // ── Technical ──
  { key: "technical_assessment", label: "Technical Assessment",     description: "Structured technical skills demonstration",                                    core: false, group: "technical" },
  { key: "code_samples",       label: "Code Samples",               description: "Curated code examples showcasing your best work",                             core: false, group: "technical" },
  { key: "writing_sample",     label: "Writing Sample",             description: "Professional writing sample demonstrating communication ability",              core: false, group: "technical" },
  { key: "case_study",         label: "Case Study",                 description: "Problem-solution-result narrative proving impact",                             core: false, group: "technical" },
  { key: "project_proposal",   label: "Project Proposal",           description: "Proposed project plan demonstrating initiative and methodology",              core: false, group: "technical" },
  // ── Creative ──
  { key: "design_portfolio",   label: "Design Portfolio",           description: "Visual portfolio for design, UX, and creative roles",                         core: false, group: "creative" },
  { key: "clinical_portfolio", label: "Clinical Portfolio",         description: "Clinical experience portfolio for healthcare professionals",                   core: false, group: "creative" },
  { key: "speaker_bio",        label: "Speaker Bio",                description: "Speaking engagement biographical summary",                                    core: false, group: "creative" },
  { key: "media_kit",          label: "Media Kit",                  description: "Press and media package with bio, headshot brief, and achievements",          core: false, group: "creative" },
  { key: "personal_website_brief", label: "Personal Website Brief", description: "Content and structure brief for a professional website",                      core: false, group: "creative" },
  { key: "pitch_deck_bio_slide", label: "Pitch Deck Bio Slide",    description: "Single-slide biography for investor or client decks",                         core: false, group: "creative" },
  { key: "speaking_proposal",  label: "Speaking Proposal",          description: "Conference talk proposal with abstract and bio",                              core: false, group: "creative" },
];

/* ── Benchmark Document Universe ─────────────────────────────────── */

export const BENCHMARK_UNIVERSE: UniverseDocType[] = [
  { key: "cv",                    label: "Benchmark CV",                  description: "The ideal candidate's CV for this exact role",                    core: true,  group: "core" },
  { key: "cover_letter",          label: "Benchmark Cover Letter",        description: "The perfect cover letter for this opportunity",                   core: true,  group: "core" },
  { key: "personal_statement",    label: "Benchmark Personal Statement",  description: "Gold-standard personal statement for this role",                  core: true,  group: "core" },
  { key: "executive_summary",     label: "Benchmark Executive Summary",   description: "Ideal executive summary matching role requirements",              core: true,  group: "core" },
  { key: "skills_matrix",         label: "Benchmark Skills Matrix",       description: "Complete skills-to-requirements mapping matrix",                  core: true,  group: "core" },
  { key: "interview_preparation", label: "Benchmark Interview Guide",     description: "Ideal interview answers and preparation framework",               core: true,  group: "core" },
  { key: "competency_framework",  label: "Benchmark Competency Framework", description: "Role competency model with proficiency levels",                  core: true,  group: "core" },
  // Extended benchmark docs
  { key: "portfolio",             label: "Benchmark Portfolio",           description: "Gold-standard project portfolio for this role",                   core: false, group: "technical" },
  { key: "elevator_pitch",        label: "Benchmark Elevator Pitch",     description: "Perfect 30-second pitch for this opportunity",                    core: false, group: "professional" },
  { key: "selection_criteria",    label: "Benchmark Selection Criteria",  description: "Model responses to formal selection criteria",                    core: false, group: "compliance" },
  { key: "ninety_day_plan",       label: "Benchmark 90-Day Plan",        description: "Ideal onboarding plan for this role",                             core: false, group: "executive" },
  { key: "technical_assessment",  label: "Benchmark Technical Assessment", description: "Model technical demonstration for this role",                   core: false, group: "technical" },
];

/* ── Group metadata ──────────────────────────────────────────────── */

export const GROUP_META: Record<string, { label: string; order: number }> = {
  core:         { label: "Core Package",       order: 0 },
  professional: { label: "Professional",       order: 1 },
  executive:    { label: "Executive & Leadership", order: 2 },
  academic:     { label: "Academic",           order: 3 },
  compliance:   { label: "Compliance & Formal", order: 4 },
  technical:    { label: "Technical",          order: 5 },
  creative:     { label: "Creative & Media",   order: 6 },
};

/* ── Utility ─────────────────────────────────────────────────────── */

/** Look up a universe entry by key */
export function findUniverseDoc(key: string, tier: "tailored" | "benchmark" = "tailored"): UniverseDocType | undefined {
  const universe = tier === "benchmark" ? BENCHMARK_UNIVERSE : TAILORED_UNIVERSE;
  return universe.find((d) => d.key === key);
}

/** Merge universe definitions with actual generated doc data */
export function mergeWithUniverse<T extends { docType: string; status: string }>(
  universe: UniverseDocType[],
  actual: T[],
): { def: UniverseDocType; doc: T | null }[] {
  const byKey = new Map<string, T>();
  for (const d of actual) {
    // Keep the latest (first occurrence if pre-sorted newest-first)
    if (!byKey.has(d.docType)) byKey.set(d.docType, d);
  }
  return universe.map((def) => ({ def, doc: byKey.get(def.key) ?? null }));
}
