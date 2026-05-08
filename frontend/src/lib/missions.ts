export type MissionStatus = "active" | "paused" | "archived";
export type VoicePreset = "confident_selective" | "warm_eager" | "formal_traditional";
export type MissionDraftStatus =
  | "surfaced"
  | "prepared"
  | "ready_for_user"
  | "sent"
  | "skipped"
  | "expired";

export interface Mission {
  id: string;
  user_id: string;
  name: string;
  status: MissionStatus;
  role_titles: string[];
  locations: string[];
  comp_band_min: number | null;
  comp_band_max: number | null;
  must_haves: string[];
  deal_breakers: string[];
  min_fit_score: number;
  target_volume_per_week: number;
  voice_preset: VoicePreset;
  created_at: string;
  paused_at: string | null;
}

export interface MissionDraft {
  id: string;
  mission_id: string;
  application_id: string | null;
  surfaced_at: string;
  prepared_at: string | null;
  sent_at: string | null;
  status: MissionDraftStatus;
  fit_score: number | null;
  application?: MissionDraftApplicationSnapshot | null;
}

export interface MissionDraftApplicationSnapshot {
  id: string;
  title: string;
  role_title: string;
  company_name: string;
  status: string;
  updated_at: string | null;
  fit_score: number | null;
  source: string | null;
  canonical_url: string | null;
  company_slug: string | null;
  ready_to_apply: boolean;
  generated_document_count: number;
}

export interface MissionSyncSummary {
  status: "ok";
  mission_id: string;
  scanned_applications: number;
  matched_applications: number;
  created: number;
  updated: number;
  count: number;
}

export type MissionBadgeVariant =
  | "default"
  | "secondary"
  | "outline"
  | "success"
  | "warning"
  | "premium";

export type MissionDraftColumn = "surfaced" | "review" | "in_flight" | "closed";

export function parseMissionListInput(value: string): string[] {
  const seen = new Set<string>();
  const parts = value
    .split(/\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
  const normalized: string[] = [];
  for (const item of parts) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(item);
  }
  return normalized;
}

export function missionStatusVariant(status: MissionStatus): MissionBadgeVariant {
  if (status === "active") return "premium";
  if (status === "paused") return "warning";
  return "secondary";
}

export function missionDraftStatusVariant(status: MissionDraftStatus): MissionBadgeVariant {
  if (status === "ready_for_user") return "premium";
  if (status === "prepared") return "success";
  if (status === "sent") return "secondary";
  if (status === "skipped" || status === "expired") return "outline";
  return "warning";
}

export function voicePresetLabel(value: VoicePreset): string {
  if (value === "warm_eager") return "Warm & eager";
  if (value === "formal_traditional") return "Formal & traditional";
  return "Confident & selective";
}

export function formatCompBand(min: number | null, max: number | null): string {
  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
  if (min != null && max != null) {
    return `${formatter.format(min)} - ${formatter.format(max)}`;
  }
  if (min != null) {
    return `${formatter.format(min)}+`;
  }
  if (max != null) {
    return `Up to ${formatter.format(max)}`;
  }
  return "Open band";
}

export function fitFloorLabel(score: number): string {
  return `${score.toFixed(1)}/5 fit floor`;
}

export function missionDraftColumn(status: MissionDraftStatus): MissionDraftColumn {
  if (status === "surfaced") return "surfaced";
  if (status === "prepared" || status === "ready_for_user") return "review";
  if (status === "sent") return "in_flight";
  return "closed";
}

export function missionDraftStatusLabel(status: MissionDraftStatus): string {
  return status.replace(/_/g, " ");
}

export function formatRelativeDate(value: string | null): string {
  if (!value) return "Not yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}