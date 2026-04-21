"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { Shield, ArrowLeft, Loader2, Clock, User, FileText } from "lucide-react";
import { RoleGate } from "@/components/role-gate";

const ACTION_COLORS: Record<string, string> = {
  "org.created": "text-emerald-500",
  "member.invited": "text-blue-500",
  "member.joined": "text-emerald-500",
  "member.removed": "text-rose-500",
  "member.role_changed": "text-amber-500",
  "settings.changed": "text-violet-500",
};

export default function AuditLogPage() {
  const { session } = useAuth();
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    api.request("/orgs").then(async (orgs: any[]) => {
      if (orgs?.length > 0) {
        const audit = await api.request(`/orgs/${orgs[0].id}/audit`);
        setLogs(Array.isArray(audit) ? audit : []);
      }
    }).catch(() => { setLogs([]); }).finally(() => setLoading(false));
  }, [session?.access_token]);

  return (
    <RoleGate feature="audit" title="Audit Log" features={["View organization activity", "Track member actions", "Security & compliance monitoring"]}>
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10"><Shield className="h-5 w-5 text-violet-500" /></div>
        <div>
          <h1 className="text-lg font-bold">Audit Log</h1>
          <p className="text-xs text-muted-foreground">Complete activity history for compliance</p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="h-8 w-8 animate-spin mx-auto text-muted-foreground" /></div>
      ) : logs.length === 0 ? (
        <div className="rounded-2xl border border-dashed bg-card/50 p-6 sm:p-10 text-center">
          <Shield className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
          <h3 className="font-semibold text-sm">No audit events yet</h3>
          <p className="text-xs text-muted-foreground mt-1">Actions like member invitations, role changes, and settings updates will appear here.</p>
        </div>
      ) : (
        <div className="space-y-1">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-3 rounded-xl border bg-card p-3 hover:shadow-soft-sm transition-shadow">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={cn("text-sm font-medium", ACTION_COLORS[log.action] || "text-foreground")}>
                    {log.action.replace(/\./g, " → ")}
                  </span>
                  {log.resource_type && <Badge variant="outline" className="text-[9px]">{log.resource_type}</Badge>}
                </div>
                {log.changes && Object.keys(log.changes).length > 0 && (
                  <p className="text-2xs text-muted-foreground mt-0.5 font-mono">{JSON.stringify(log.changes).slice(0, 100)}</p>
                )}
              </div>
              <span className="text-2xs text-muted-foreground shrink-0 flex items-center gap-1">
                <Clock className="h-2.5 w-2.5" />
                {new Date(log.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
    </RoleGate>
  );
}
