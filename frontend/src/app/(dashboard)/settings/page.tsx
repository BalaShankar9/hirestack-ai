"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Settings, Users, CreditCard, Shield, Building2, Plus,
  ArrowRight, Loader2, CheckCircle, Crown, User, Lock, Eye, EyeOff,
  LogOut, Mail, Trash2,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

const SETTINGS_LINKS = [
  { href: "/settings/members", label: "Team Members", desc: "Invite and manage your team", icon: Users, color: "text-blue-500 bg-blue-500/10" },
  { href: "/settings/billing", label: "Usage", desc: "Monitor account usage", icon: CreditCard, color: "text-emerald-500 bg-emerald-500/10" },
  { href: "/settings/audit", label: "Audit Log", desc: "Activity history and compliance", icon: Shield, color: "text-violet-500 bg-violet-500/10" },
  { href: "/api-keys", label: "API Keys", desc: "Manage API access tokens", icon: Settings, color: "text-amber-500 bg-amber-500/10" },
];

const LINK_HOVER = "transition-all duration-300 hover:-translate-y-0.5 hover:shadow-soft-sm";

export default function SettingsPage() {
  const { user, session, signOut } = useAuth();
  const [orgs, setOrgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Profile editing state
  const [displayName, setDisplayName] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  // Password change state
  const [showPasswordChange, setShowPasswordChange] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  // Account deletion state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  useEffect(() => {
    if (user?.displayName || user?.full_name) {
      setDisplayName(user.displayName || user.full_name || "");
    }
  }, [user?.displayName, user?.full_name]);

  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
      api.request("/orgs").then((r: any) => setOrgs(Array.isArray(r) ? r : [])).catch(() => {
        setOrgs([]);
        toast({ title: "Failed to load organization", variant: "error" });
      }).finally(() => setLoading(false));
    }
  }, [session?.access_token]);

  const updateProfile = async () => {
    if (!displayName.trim()) return;
    setSavingProfile(true);
    try {
      const { error } = await supabase.auth.updateUser({
        data: { full_name: displayName.trim() },
      });
      if (error) throw error;
      toast({ title: "Profile updated", description: "Your display name has been saved." });
    } catch (e: any) {
      toast({ title: "Failed to update profile", description: e.message, variant: "error" });
    }
    setSavingProfile(false);
  };

  const changePassword = async () => {
    if (newPassword.length < 8) {
      toast({ title: "Password too short", description: "Password must be at least 8 characters.", variant: "error" });
      return;
    }
    if (newPassword !== confirmPassword) {
      toast({ title: "Passwords don't match", description: "Please make sure both passwords match.", variant: "error" });
      return;
    }
    setSavingPassword(true);
    try {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
      toast({ title: "Password updated", description: "Your password has been changed." });
      setNewPassword("");
      setConfirmPassword("");
      setShowPasswordChange(false);
    } catch (e: any) {
      toast({ title: "Failed to change password", description: e.message, variant: "error" });
    }
    setSavingPassword(false);
  };

  const createOrg = async () => {
    if (!newOrgName.trim()) return;
    setCreating(true);
    try {
      const slug = newOrgName.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 50);
      const org = await api.request("/orgs", { method: "POST", body: { name: newOrgName, slug } });
      if (org) {
        setOrgs((prev) => [...prev, org]);
        setNewOrgName("");
        setShowCreate(false);
        toast({ title: "Organization created!" });
      }
    } catch (e: any) {
      toast({ title: "Failed", description: e.message });
    }
    setCreating(false);
  };

  const currentOrg = orgs[0];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-500 to-zinc-600 shadow-glow-sm">
          <Settings className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Settings</h1>
          <p className="text-sm text-muted-foreground">Account, organization, and security settings</p>
        </div>
      </div>

      {/* ── Account & Profile ── */}
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
        <h2 className="font-semibold flex items-center gap-2 mb-4"><User className="h-4 w-4" /> Account</h2>
        <div className="space-y-4">
          {/* Email (read-only) */}
          <div>
            <label className="text-xs text-muted-foreground flex items-center gap-1.5"><Mail className="h-3 w-3" /> Email</label>
            <p className="text-sm font-medium mt-0.5">{user?.email || "—"}</p>
          </div>
          {/* Display Name */}
          <div>
            <label className="text-xs text-muted-foreground">Display Name</label>
            <div className="flex gap-2 mt-1">
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your name"
                className="rounded-xl max-w-sm"
              />
              <Button
                onClick={updateProfile}
                disabled={savingProfile || !displayName.trim() || displayName === (user?.displayName || user?.full_name || "")}
                className="rounded-xl gap-1.5 shrink-0"
                size="sm"
              >
                {savingProfile ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
                Save
              </Button>
            </div>
          </div>

          {/* Password Change */}
          <div className="border-t pt-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs text-muted-foreground flex items-center gap-1.5"><Lock className="h-3 w-3" /> Password</label>
                <p className="text-xs text-muted-foreground mt-0.5">Change your account password</p>
              </div>
              {!showPasswordChange && (
                <Button variant="outline" size="sm" className="rounded-xl" onClick={() => setShowPasswordChange(true)}>
                  Change Password
                </Button>
              )}
            </div>
            {showPasswordChange && (
              <div className="mt-3 space-y-2 max-w-sm">
                <div className="relative">
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="New password (min 8 characters)"
                    className="rounded-xl pr-10"
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {newPassword.length > 0 && newPassword.length < 8 && (
                  <p className="text-xs text-destructive">Password must be at least 8 characters</p>
                )}
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  className="rounded-xl"
                />
                {confirmPassword.length > 0 && newPassword !== confirmPassword && (
                  <p className="text-xs text-destructive">Passwords don&apos;t match</p>
                )}
                <div className="flex gap-2">
                  <Button onClick={changePassword} disabled={savingPassword || newPassword.length < 8 || newPassword !== confirmPassword} className="rounded-xl gap-1.5" size="sm">
                    {savingPassword ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
                    Update Password
                  </Button>
                  <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => { setShowPasswordChange(false); setNewPassword(""); setConfirmPassword(""); }}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Sign Out & Danger Zone */}
          <div className="border-t pt-4 flex items-center justify-between">
            <Button variant="outline" size="sm" className="rounded-xl gap-1.5 text-muted-foreground" onClick={() => signOut()}>
              <LogOut className="h-3.5 w-3.5" /> Sign Out
            </Button>
            <div>
              {!showDeleteConfirm ? (
                <Button variant="ghost" size="sm" className="rounded-xl gap-1.5 text-destructive/60 hover:text-destructive hover:bg-destructive/5" onClick={() => setShowDeleteConfirm(true)}>
                  <Trash2 className="h-3.5 w-3.5" /> Delete Account
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  <Input
                    value={deleteConfirmText}
                    onChange={(e) => setDeleteConfirmText(e.target.value)}
                    placeholder='Type "DELETE" to confirm'
                    className="rounded-xl w-48 text-xs"
                  />
                  <Button
                    variant="destructive"
                    size="sm"
                    className="rounded-xl"
                    disabled={deleteConfirmText !== "DELETE"}
                    onClick={() => {
                      toast({ title: "Account deletion", description: "Please contact support to complete account deletion.", variant: "error" });
                      setShowDeleteConfirm(false);
                      setDeleteConfirmText("");
                    }}
                  >
                    Confirm
                  </Button>
                  <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => { setShowDeleteConfirm(false); setDeleteConfirmText(""); }}>
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Organization Card */}
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold flex items-center gap-2"><Building2 className="h-4 w-4" /> Organization</h2>
          {currentOrg && (
            <Badge variant="outline" className={cn("text-[10px]",
              currentOrg.tier === "enterprise" ? "border-violet-500/30 text-violet-500" :
              currentOrg.tier === "pro" ? "border-emerald-500/30 text-emerald-500" :
              "border-border"
            )}>
              <Crown className="h-2.5 w-2.5 mr-1" />
              {currentOrg.tier?.charAt(0).toUpperCase() + currentOrg.tier?.slice(1) || "Free"}
            </Badge>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : currentOrg ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div><label className="text-2xs text-muted-foreground">Name</label><p className="text-sm font-medium">{currentOrg.name}</p></div>
              <div><label className="text-2xs text-muted-foreground">Slug</label><p className="text-sm font-mono">{currentOrg.slug}</p></div>
              <div><label className="text-2xs text-muted-foreground">Your Role</label><p className="text-sm capitalize">{currentOrg.member_role || "owner"}</p></div>
              <div><label className="text-2xs text-muted-foreground">Plan</label><p className="text-sm capitalize">{currentOrg.tier || "free"}</p></div>
            </div>
          </div>
        ) : (
          <div className="text-center py-6">
            <Building2 className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
            <h3 className="font-semibold text-sm">No Organization</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">Create an organization to unlock team features, billing, and API access.</p>
            {!showCreate ? (
              <Button className="mt-4 rounded-xl gap-2" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> Create Organization</Button>
            ) : (
              <div className="flex gap-2 mt-4 max-w-sm mx-auto">
                <Input placeholder="Organization name" value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} className="rounded-xl" />
                <Button onClick={createOrg} disabled={creating || !newOrgName.trim()} className="rounded-xl gap-1 shrink-0">
                  {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />} Create
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Settings Links */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {SETTINGS_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className={cn("rounded-2xl border bg-card p-4 hover:border-primary/20 group", LINK_HOVER)}>
            <div className="flex items-center gap-3">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", link.color)}>
                <link.icon className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-semibold text-sm group-hover:text-primary transition-colors">{link.label}</p>
                <p className="text-2xs text-muted-foreground">{link.desc}</p>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
          </Link>
        ))}
      </div>

      {/* All Organizations */}
      {orgs.length > 1 && (
        <div className="rounded-2xl border bg-card p-5">
          <h2 className="font-semibold text-sm mb-3">All Organizations</h2>
          <div className="space-y-2">
            {orgs.map((org) => (
              <div key={org.id} className="flex items-center justify-between rounded-xl border p-3">
                <div>
                  <p className="text-sm font-medium">{org.name}</p>
                  <p className="text-2xs text-muted-foreground capitalize">{org.member_role || "member"} · {org.tier || "free"}</p>
                </div>
                <Badge variant="outline" className="text-[10px]">{org.slug}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
