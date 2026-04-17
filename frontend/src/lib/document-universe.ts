/**
 * Document Universe — the single canonical registry of every document type.
 *
 * ONE master array used identically by Benchmark, Tailored, and Library.
 * Each entry is flagged as **recommended** (highest-impact documents for
 * every application) or part of the **extended catalogue** (on demand).
 *
 * The catalog is designed to grow: the backend `document_catalog` service
 * and `DocumentPackPlanner` agent can discover new document types from JD
 * analysis and feed them back. Newly discovered types start in the extended
 * set and can be promoted to recommended via the `auto_evolve` source flag.
 */

/* ── Single document type definition ─────────────────────────────── */

export interface UniverseDocType {
  /** Unique key matching backend doc_type / SEED_CATALOG key */
  key: string;
  /** Human-readable label (no Benchmark/Tailored prefix — context comes from the generated instance) */
  label: string;
  /** Short description of what this document is for */
  description: string;
  /** Whether this is part of the recommended set */
  recommended: boolean;
  /** Grouping category */
  group: "recommended" | "professional" | "executive" | "academic" | "compliance" | "technical" | "creative";
}

/* ── Recommended Set (10 highest-impact docs) ────────────────────── */

export const RECOMMENDED_KEYS = [
  "cv",
  "cover_letter",
  "personal_statement",
  "portfolio",
  "executive_summary",
  "elevator_pitch",
  "linkedin_summary",
  "skills_matrix",
  "interview_preparation",
  "competency_framework",
] as const;

/* ── Master Document Universe ────────────────────────────────────── */

export const DOCUMENT_UNIVERSE: UniverseDocType[] = [
  // ── Recommended Set (10) ──
  { key: "cv",                    label: "CV / Résumé",                  description: "ATS-optimised CV tailored to the role's exact requirements",                recommended: true,  group: "recommended" },
  { key: "cover_letter",          label: "Cover Letter",                 description: "Evidence-backed narrative connecting your experience to the role",          recommended: true,  group: "recommended" },
  { key: "personal_statement",    label: "Personal Statement",           description: "Compelling motivation narrative — authentic, specific, memorable",          recommended: true,  group: "recommended" },
  { key: "portfolio",             label: "Portfolio & Evidence",          description: "Curated project showcase proving real capability with outcomes",           recommended: true,  group: "recommended" },
  { key: "executive_summary",     label: "Executive Summary",            description: "One-page leadership snapshot for senior and executive roles",              recommended: true,  group: "recommended" },
  { key: "elevator_pitch",        label: "Elevator Pitch",               description: "30-second verbal summary of your candidacy — ready to deliver",            recommended: true,  group: "recommended" },
  { key: "linkedin_summary",      label: "LinkedIn Summary",             description: "Keyword-rich LinkedIn About section aligned to target role",               recommended: true,  group: "recommended" },
  { key: "skills_matrix",         label: "Skills Matrix",                description: "Complete skills-to-requirements mapping matrix",                           recommended: true,  group: "recommended" },
  { key: "interview_preparation", label: "Interview Preparation Guide",  description: "Ideal interview answers and preparation framework",                       recommended: true,  group: "recommended" },
  { key: "competency_framework",  label: "Competency Framework",         description: "Role competency model with proficiency levels",                            recommended: true,  group: "recommended" },
  // ── Professional ──
  { key: "references_list",     label: "References List",           description: "Formatted reference sheet with contact details and relationship context",       recommended: false, group: "professional" },
  { key: "follow_up_email",     label: "Follow-Up Email",           description: "Post-interview follow-up reinforcing key strengths and fit",                   recommended: false, group: "professional" },
  { key: "thank_you_note",      label: "Thank-You Note",            description: "Concise post-interview thank-you with personalised recall",                    recommended: false, group: "professional" },
  { key: "motivation_letter",   label: "Motivation Letter",         description: "Extended motivation narrative for roles requiring deeper rationale",            recommended: false, group: "professional" },
  { key: "recommendation_letter_template", label: "Recommendation Letter Template", description: "Pre-drafted recommendation for your referee to adapt",          recommended: false, group: "professional" },
  { key: "values_statement",    label: "Values Statement",          description: "Personal values alignment to company mission and culture",                     recommended: false, group: "professional" },
  { key: "professional_development_plan", label: "Development Plan", description: "90-day growth roadmap showing initiative and self-awareness",                 recommended: false, group: "professional" },
  { key: "interview_prep_guide", label: "Interview Prep Guide",     description: "Role-specific Q&A preparation with STAR examples",                             recommended: false, group: "professional" },
  { key: "salary_negotiation_script", label: "Salary Negotiation Script", description: "Data-backed negotiation talking points for offer stage",                 recommended: false, group: "professional" },
  { key: "networking_email",    label: "Networking Email",           description: "Professional outreach template for hiring managers or referrals",              recommended: false, group: "professional" },
  { key: "linkedin_recommendation_request", label: "LinkedIn Recommendation Request", description: "Template request to former colleagues for LinkedIn endorsement", recommended: false, group: "professional" },
  // ── Executive & Leadership ──
  { key: "ninety_day_plan",     label: "90-Day Plan",               description: "Structured onboarding plan demonstrating strategic thinking",                  recommended: false, group: "executive" },
  { key: "thirty_sixty_ninety_day_plan", label: "30-60-90 Day Plan", description: "Phased integration plan for leadership and management roles",                recommended: false, group: "executive" },
  { key: "leadership_philosophy", label: "Leadership Philosophy",   description: "Your leadership approach, style, and team-building principles",               recommended: false, group: "executive" },
  { key: "consulting_deck",    label: "Consulting Deck",            description: "Slide-ready pitch deck for consulting or advisory engagements",               recommended: false, group: "executive" },
  { key: "board_presentation", label: "Board Presentation",         description: "Executive-level presentation for board or C-suite audiences",                 recommended: false, group: "executive" },
  { key: "board_bio",          label: "Board Bio",                  description: "Formal biographical summary for board nominations",                           recommended: false, group: "executive" },
  // ── Academic ──
  { key: "research_statement",  label: "Research Statement",        description: "Research agenda and methodology for academic positions",                       recommended: false, group: "academic" },
  { key: "teaching_philosophy", label: "Teaching Philosophy",       description: "Pedagogical approach and teaching experience narrative",                       recommended: false, group: "academic" },
  { key: "publications_list",  label: "Publications List",          description: "Formatted bibliography of your published work",                               recommended: false, group: "academic" },
  { key: "thesis_abstract",    label: "Thesis Abstract",            description: "Concise summary of thesis research and findings",                             recommended: false, group: "academic" },
  { key: "grant_proposal",     label: "Grant Proposal",             description: "Funding application narrative with objectives and methodology",               recommended: false, group: "academic" },
  // ── Compliance & Formal ──
  { key: "selection_criteria",  label: "Selection Criteria Response", description: "Point-by-point response to formal selection criteria",                       recommended: false, group: "compliance" },
  { key: "diversity_statement", label: "Diversity Statement",       description: "Commitment to diversity, equity, and inclusion",                               recommended: false, group: "compliance" },
  { key: "safety_statement",   label: "Safety Statement",           description: "Workplace safety awareness and commitment",                                   recommended: false, group: "compliance" },
  { key: "equity_statement",   label: "Equity Statement",           description: "Equity and accessibility practice statement",                                 recommended: false, group: "compliance" },
  { key: "conflict_of_interest_declaration", label: "COI Declaration", description: "Formal conflict of interest disclosure",                                   recommended: false, group: "compliance" },
  { key: "capability_statement", label: "Capability Statement",     description: "Organisational capability and capacity summary",                              recommended: false, group: "compliance" },
  { key: "expression_of_interest", label: "Expression of Interest", description: "Formal EOI for tenders and procurement processes",                            recommended: false, group: "compliance" },
  { key: "letter_of_intent",   label: "Letter of Intent",           description: "Formal declaration of intent to apply or participate",                        recommended: false, group: "compliance" },
  { key: "community_engagement_statement", label: "Community Engagement Statement", description: "Community service and outreach involvement",                  recommended: false, group: "compliance" },
  // ── Technical ──
  { key: "technical_assessment", label: "Technical Assessment",     description: "Structured technical skills demonstration",                                    recommended: false, group: "technical" },
  { key: "code_samples",       label: "Code Samples",               description: "Curated code examples showcasing your best work",                             recommended: false, group: "technical" },
  { key: "writing_sample",     label: "Writing Sample",             description: "Professional writing sample demonstrating communication ability",              recommended: false, group: "technical" },
  { key: "case_study",         label: "Case Study",                 description: "Problem-solution-result narrative proving impact",                             recommended: false, group: "technical" },
  { key: "project_proposal",   label: "Project Proposal",           description: "Proposed project plan demonstrating initiative and methodology",              recommended: false, group: "technical" },
  // ── Creative & Media ──
  { key: "design_portfolio",   label: "Design Portfolio",           description: "Visual portfolio for design, UX, and creative roles",                         recommended: false, group: "creative" },
  { key: "clinical_portfolio", label: "Clinical Portfolio",         description: "Clinical experience portfolio for healthcare professionals",                   recommended: false, group: "creative" },
  { key: "speaker_bio",        label: "Speaker Bio",                description: "Speaking engagement biographical summary",                                    recommended: false, group: "creative" },
  { key: "media_kit",          label: "Media Kit",                  description: "Press and media package with bio, headshot brief, and achievements",          recommended: false, group: "creative" },
  { key: "personal_website_brief", label: "Personal Website Brief", description: "Content and structure brief for a professional website",                      recommended: false, group: "creative" },
  { key: "pitch_deck_bio_slide", label: "Pitch Deck Bio Slide",    description: "Single-slide biography for investor or client decks",                         recommended: false, group: "creative" },
  { key: "speaking_proposal",  label: "Speaking Proposal",          description: "Conference talk proposal with abstract and bio",                              recommended: false, group: "creative" },
];

/** @deprecated Use DOCUMENT_UNIVERSE — unified single registry */
export const TAILORED_UNIVERSE = DOCUMENT_UNIVERSE;
/** @deprecated Use DOCUMENT_UNIVERSE — unified single registry */
export const BENCHMARK_UNIVERSE = DOCUMENT_UNIVERSE;

/* ── Group metadata ──────────────────────────────────────────────── */

export const GROUP_META: Record<string, { label: string; order: number }> = {
  recommended:  { label: "Recommended",            order: 0 },
  professional: { label: "Professional",           order: 1 },
  executive:    { label: "Executive & Leadership", order: 2 },
  academic:     { label: "Academic",               order: 3 },
  compliance:   { label: "Compliance & Formal",    order: 4 },
  technical:    { label: "Technical",              order: 5 },
  creative:     { label: "Creative & Media",       order: 6 },
};

/* ── Utility ─────────────────────────────────────────────────────── */

/** Look up a universe entry by key */
export function findUniverseDoc(key: string, _tier?: "tailored" | "benchmark"): UniverseDocType | undefined {
  return DOCUMENT_UNIVERSE.find((d) => d.key === key);
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
