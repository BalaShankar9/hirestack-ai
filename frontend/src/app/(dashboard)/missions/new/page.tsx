"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, Sparkles } from "lucide-react";

import { useAuth } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import api from "@/lib/api";
import {
  fitFloorLabel,
  formatCompBand,
  parseMissionListInput,
  type VoicePreset,
  voicePresetLabel,
} from "@/lib/missions";

const STEPS = [
  { key: "roles", label: "Roles" },
  { key: "market", label: "Comp & locations" },
  { key: "guardrails", label: "Must-have filters" },
  { key: "voice", label: "Voice preset" },
  { key: "review", label: "Review" },
] as const;

const VOICE_OPTIONS: Array<{ value: VoicePreset; title: string; body: string }> = [
  {
    value: "confident_selective",
    title: "Confident & selective",
    body: "Use when you want crisp positioning, seniority, and high-signal restraint in the generated materials.",
  },
  {
    value: "warm_eager",
    title: "Warm & eager",
    body: "Use when momentum, enthusiasm, and obvious culture alignment should come through without sounding junior.",
  },
  {
    value: "formal_traditional",
    title: "Formal & traditional",
    body: "Use when the target roles skew conservative or heavily structured in tone.",
  },
];

function parseFieldError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err ?? "Unknown error");
  const match = raw.match(/\{[^{}]*"reason"[^{}]*\}/);
  if (match) {
    try {
      const parsed = JSON.parse(match[0]);
      if (parsed && typeof parsed.reason === "string") {
        return parsed.reason;
      }
    } catch {
      return raw;
    }
  }
  return raw;
}

export default function MissionSetupPage() {
  const router = useRouter();
  const { session } = useAuth();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [roleTitlesText, setRoleTitlesText] = useState("");
  const [locationsText, setLocationsText] = useState("");
  const [compBandMin, setCompBandMin] = useState("");
  const [compBandMax, setCompBandMax] = useState("");
  const [mustHavesText, setMustHavesText] = useState("");
  const [dealBreakersText, setDealBreakersText] = useState("");
  const [minFitScore, setMinFitScore] = useState(4.0);
  const [targetVolume, setTargetVolume] = useState(5);
  const [voicePreset, setVoicePreset] = useState<VoicePreset>("confident_selective");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const roleTitles = useMemo(() => parseMissionListInput(roleTitlesText), [roleTitlesText]);
  const locations = useMemo(() => parseMissionListInput(locationsText), [locationsText]);
  const mustHaves = useMemo(() => parseMissionListInput(mustHavesText), [mustHavesText]);
  const dealBreakers = useMemo(() => parseMissionListInput(dealBreakersText), [dealBreakersText]);

  function validateCurrentStep(): boolean {
    const trimmedName = name.trim();
    if (step === 0) {
      if (!trimmedName) {
        setError("Mission name is required.");
        return false;
      }
      if (roleTitles.length === 0) {
        setError("Add at least one target role title.");
        return false;
      }
    }
    if (step === 1) {
      const min = compBandMin ? Number(compBandMin) : null;
      const max = compBandMax ? Number(compBandMax) : null;
      if (min != null && Number.isNaN(min)) {
        setError("Comp band minimum must be a number.");
        return false;
      }
      if (max != null && Number.isNaN(max)) {
        setError("Comp band maximum must be a number.");
        return false;
      }
      if (min != null && max != null && max < min) {
        setError("Comp band maximum must be greater than or equal to the minimum.");
        return false;
      }
      if (targetVolume < 1 || targetVolume > 100) {
        setError("Target volume must stay between 1 and 100 roles per week.");
        return false;
      }
    }
    setError(null);
    return true;
  }

  function goNext() {
    if (!validateCurrentStep()) return;
    setStep((current) => Math.min(current + 1, STEPS.length - 1));
  }

  function goBack() {
    setError(null);
    setStep((current) => Math.max(current - 1, 0));
  }

  async function handleCreate() {
    if (!validateCurrentStep()) return;
    if (!session?.access_token) {
      setError("You need an active session before creating a mission.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      api.setToken(session.access_token);
      const created = (await api.missions.create({
        name: name.trim(),
        role_titles: roleTitles,
        locations,
        comp_band_min: compBandMin ? Number(compBandMin) : null,
        comp_band_max: compBandMax ? Number(compBandMax) : null,
        must_haves: mustHaves,
        deal_breakers: dealBreakers,
        min_fit_score: minFitScore,
        target_volume_per_week: targetVolume,
        voice_preset: voicePreset,
      })) as { id: string };
      router.push(`/missions/${created.id}`);
    } catch (err) {
      setError(parseFieldError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/missions" className="text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="mr-1 inline h-4 w-4" />
            Back to missions
          </Link>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">Mission setup wizard</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Five screens, one durable brief. Capture your roles, compensation band, guardrails, and tone once,
            then reuse it as the control plane for surfaced workspaces and future orchestration.
          </p>
        </div>
        <Badge variant="premium" className="gap-2 px-3 py-1 text-[11px] uppercase tracking-[0.2em]">
          <Sparkles className="h-3.5 w-3.5" />
          Step {step + 1} of {STEPS.length}
        </Badge>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_360px]">
        <Card>
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-background to-primary/5">
            <div className="flex flex-wrap gap-2">
              {STEPS.map((item, index) => (
                <Badge key={item.key} variant={index === step ? "premium" : index < step ? "success" : "outline"}>
                  {index < step ? <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> : null}
                  {item.label}
                </Badge>
              ))}
            </div>
          </CardHeader>
          <CardContent className="space-y-6 p-6">
            {step === 0 && (
              <div className="space-y-5">
                <div>
                  <label htmlFor="mission-name" className="text-sm font-medium text-foreground">Mission name</label>
                  <input
                    id="mission-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Design leadership in AI product companies"
                    className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div>
                  <label htmlFor="mission-target-roles" className="text-sm font-medium text-foreground">Target roles</label>
                  <textarea
                    id="mission-target-roles"
                    value={roleTitlesText}
                    onChange={(event) => setRoleTitlesText(event.target.value)}
                    placeholder={"Staff Product Designer\nPrincipal Product Designer\nDesign Director"}
                    rows={7}
                    className="mt-2 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                  <p className="mt-2 text-xs text-muted-foreground">One role per line or comma-separated. This is the core targeting signal for the mission.</p>
                </div>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-5">
                <div>
                  <label htmlFor="mission-locations" className="text-sm font-medium text-foreground">Locations</label>
                  <textarea
                    id="mission-locations"
                    value={locationsText}
                    onChange={(event) => setLocationsText(event.target.value)}
                    placeholder={"Remote\nNew York\nLondon"}
                    rows={4}
                    className="mt-2 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <label htmlFor="mission-comp-min" className="text-sm font-medium text-foreground">Comp min</label>
                    <input
                      id="mission-comp-min"
                      type="number"
                      inputMode="numeric"
                      value={compBandMin}
                      onChange={(event) => setCompBandMin(event.target.value)}
                      placeholder="180000"
                      className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                  <div>
                    <label htmlFor="mission-comp-max" className="text-sm font-medium text-foreground">Comp max</label>
                    <input
                      id="mission-comp-max"
                      type="number"
                      inputMode="numeric"
                      value={compBandMax}
                      onChange={(event) => setCompBandMax(event.target.value)}
                      placeholder="240000"
                      className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                  <div>
                    <label htmlFor="mission-target-volume" className="text-sm font-medium text-foreground">Roles per week</label>
                    <input
                      id="mission-target-volume"
                      type="number"
                      min={1}
                      max={100}
                      value={targetVolume}
                      onChange={(event) => setTargetVolume(Number(event.target.value || 0))}
                      className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-4 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                </div>
                <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">Minimum fit score</div>
                      <p className="text-xs text-muted-foreground">Set the floor for what gets surfaced into the mission inbox.</p>
                    </div>
                    <Badge variant="premium">{fitFloorLabel(minFitScore)}</Badge>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={5}
                    step={0.1}
                    value={minFitScore}
                    onChange={(event) => setMinFitScore(Number(event.target.value))}
                    className="mt-4 h-2 w-full accent-primary"
                  />
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-5">
                <div>
                  <label htmlFor="mission-must-haves" className="text-sm font-medium text-foreground">Must-haves</label>
                  <textarea
                    id="mission-must-haves"
                    value={mustHavesText}
                    onChange={(event) => setMustHavesText(event.target.value)}
                    placeholder={"B2B SaaS\n0-1 product work\nLeadership scope"}
                    rows={6}
                    className="mt-2 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div>
                  <label htmlFor="mission-deal-breakers" className="text-sm font-medium text-foreground">Deal-breakers</label>
                  <textarea
                    id="mission-deal-breakers"
                    value={dealBreakersText}
                    onChange={(event) => setDealBreakersText(event.target.value)}
                    placeholder={"On-site five days\nBelow staff level\nNo design systems ownership"}
                    rows={6}
                    className="mt-2 w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="grid gap-4 md:grid-cols-3">
                {VOICE_OPTIONS.map((option) => {
                  const active = option.value === voicePreset;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setVoicePreset(option.value)}
                      className={`rounded-3xl border p-5 text-left transition ${
                        active
                          ? "border-primary bg-primary/5 shadow-soft-md"
                          : "border-border bg-card hover:border-primary/40"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-base font-semibold">{option.title}</div>
                        {active ? <Badge variant="premium">Selected</Badge> : null}
                      </div>
                      <p className="mt-3 text-sm leading-6 text-muted-foreground">{option.body}</p>
                    </button>
                  );
                })}
              </div>
            )}

            {step === 4 && (
              <div className="grid gap-5 lg:grid-cols-2">
                <Card className="border-border/60 bg-muted/20 shadow-none hover:shadow-none">
                  <CardHeader>
                    <CardTitle className="text-lg">Targeting brief</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Mission name</div>
                      <div className="mt-1 font-medium">{name || "Untitled mission"}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Roles</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {roleTitles.map((role) => (
                          <Badge key={role} variant="outline">{role}</Badge>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Locations</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {locations.length > 0 ? locations.map((location) => (
                          <Badge key={location} variant="outline">{location}</Badge>
                        )) : <span className="text-muted-foreground">Open</span>}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/60 bg-muted/20 shadow-none hover:shadow-none">
                  <CardHeader>
                    <CardTitle className="text-lg">Guardrails & tone</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Comp band</div>
                        <div className="mt-1 font-medium">{formatCompBand(compBandMin ? Number(compBandMin) : null, compBandMax ? Number(compBandMax) : null)}</div>
                      </div>
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Fit floor</div>
                        <div className="mt-1 font-medium">{fitFloorLabel(minFitScore)}</div>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Voice preset</div>
                      <div className="mt-1 font-medium">{voicePresetLabel(voicePreset)}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Must-haves</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {mustHaves.length > 0 ? mustHaves.map((item) => (
                          <Badge key={item} variant="outline">{item}</Badge>
                        )) : <span className="text-muted-foreground">No hard requirements added.</span>}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Deal-breakers</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {dealBreakers.length > 0 ? dealBreakers.map((item) => (
                          <Badge key={item} variant="outline">{item}</Badge>
                        )) : <span className="text-muted-foreground">No explicit exclusions yet.</span>}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-4">
              <Button variant="outline" onClick={step === 0 ? undefined : goBack} asChild={step === 0}>
                {step === 0 ? <Link href="/missions">Cancel</Link> : <span>Back</span>}
              </Button>
              {step < STEPS.length - 1 ? (
                <Button onClick={goNext}>
                  Next
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button onClick={handleCreate} loading={saving}>
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Create mission
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="h-fit border-border/60 bg-gradient-to-br from-card to-primary/5">
          <CardHeader>
            <CardTitle className="text-xl">Live summary</CardTitle>
            <CardDescription>
              This stays visible while you move through the wizard so you can keep the mission coherent.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Mission</div>
              <div className="mt-1 font-medium">{name.trim() || "Untitled mission"}</div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Role titles</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {roleTitles.length > 0 ? roleTitles.map((role) => (
                  <Badge key={role} variant="outline">{role}</Badge>
                )) : <span className="text-muted-foreground">Not set yet.</span>}
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Locations</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {locations.length > 0 ? locations.map((location) => (
                  <Badge key={location} variant="outline">{location}</Badge>
                )) : <span className="text-muted-foreground">Open geography.</span>}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Fit floor</div>
                <div className="mt-1 font-medium">{fitFloorLabel(minFitScore)}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Weekly target</div>
                <div className="mt-1 font-medium">{targetVolume} roles</div>
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Voice preset</div>
              <div className="mt-1 font-medium">{voicePresetLabel(voicePreset)}</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}