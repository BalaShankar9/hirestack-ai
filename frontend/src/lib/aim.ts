export type AIMSourceType =
  | "assignment_brief"
  | "rubric"
  | "lecture_notes"
  | "journal_article"
  | "book"
  | "book_chapter"
  | "textbook"
  | "official_statistics"
  | "standard"
  | "government_report"
  | "ngo_report"
  | "institution_report"
  | "industry_report"
  | "company_report"
  | "trade_publication"
  | "news"
  | "dataset"
  | "web_page"
  | "blog"
  | "image_figure"
  | "user_notes"
  | "other";

export type AIMReliabilityTier = "tier_1" | "tier_2" | "tier_3" | "tier_4" | "blocked";
export type AIMVerificationStatus = "needs_metadata" | "unverified" | "verified" | "blocked";

export interface AIMSource {
  id: string;
  assignment_id: string;
  user_id: string;
  source_type: AIMSourceType;
  title: string | null;
  authors: string[];
  year: number | null;
  publisher: string | null;
  journal: string | null;
  doi: string | null;
  url: string | null;
  access_date: string | null;
  reliability_tier: AIMReliabilityTier;
  verification_status: AIMVerificationStatus;
  raw_text: string | null;
  extracted_summary: string | null;
  relevant_quotes: unknown[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AIMSourceCreate {
  source_type?: AIMSourceType;
  title?: string | null;
  authors?: string[];
  year?: number | null;
  publisher?: string | null;
  journal?: string | null;
  doi?: string | null;
  url?: string | null;
  access_date?: string | null;
  reliability_tier?: AIMReliabilityTier | null;
  verification_status?: AIMVerificationStatus | null;
  raw_text?: string | null;
  extracted_summary?: string | null;
  relevant_quotes?: unknown[];
  metadata?: Record<string, unknown>;
}

export const AIM_SOURCE_TYPES: Array<{ value: AIMSourceType; label: string }> = [
  { value: "journal_article", label: "Journal article" },
  { value: "book", label: "Book" },
  { value: "book_chapter", label: "Book chapter" },
  { value: "textbook", label: "Textbook" },
  { value: "official_statistics", label: "Official statistics" },
  { value: "standard", label: "Standard" },
  { value: "government_report", label: "Government report" },
  { value: "ngo_report", label: "NGO report" },
  { value: "institution_report", label: "Institution report" },
  { value: "industry_report", label: "Industry report" },
  { value: "company_report", label: "Company report" },
  { value: "trade_publication", label: "Trade publication" },
  { value: "news", label: "News" },
  { value: "dataset", label: "Dataset" },
  { value: "web_page", label: "Web page" },
  { value: "blog", label: "Blog" },
  { value: "lecture_notes", label: "Lecture notes" },
  { value: "image_figure", label: "Image or figure" },
  { value: "user_notes", label: "User notes" },
  { value: "assignment_brief", label: "Assignment brief" },
  { value: "rubric", label: "Rubric" },
  { value: "other", label: "Other" },
];

export const AIM_RELIABILITY_LABELS: Record<AIMReliabilityTier, string> = {
  tier_1: "Tier 1",
  tier_2: "Tier 2",
  tier_3: "Tier 3",
  tier_4: "Tier 4",
  blocked: "Blocked",
};

export const AIM_VERIFICATION_LABELS: Record<AIMVerificationStatus, string> = {
  needs_metadata: "Needs metadata",
  unverified: "Unverified",
  verified: "Verified",
  blocked: "Blocked",
};

export function sourceTypeLabel(value: string | null | undefined): string {
  return AIM_SOURCE_TYPES.find((item) => item.value === value)?.label || "Other";
}

export function splitAuthors(value: string): string[] {
  const seen = new Set<string>();
  const authors: string[] = [];
  for (const item of value.split(/,|\n/g)) {
    const cleaned = item.trim();
    const key = cleaned.toLowerCase();
    if (!cleaned || seen.has(key)) continue;
    seen.add(key);
    authors.push(cleaned);
  }
  return authors;
}

export function missingSourceMetadata(source: AIMSource): string[] {
  const missing: string[] = [];
  if (!source.title) missing.push("title");
  if (!source.year) missing.push("year");
  if (!source.authors?.length) missing.push("author");
  if (!source.doi && !source.url && !source.raw_text) missing.push("DOI, URL, or text");
  return missing;
}