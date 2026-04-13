"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { APIKey } from "@/types";
import { Button } from "@/components/ui/button";
import { Key, Loader2, Plus, Trash2, Copy, Check, Eye, EyeOff, BarChart3 } from "lucide-react";
import { RoleGate } from "@/components/role-gate";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export default function APIKeysPage() {
  const { user } = useAuth();
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [usage, setUsage] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeTargetId, setRevokeTargetId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [keysRes, usageRes] = await Promise.all([
        api.apiKeys.list(),
        api.apiKeys.usage(),
      ]);
      setKeys(keysRes || []);
      setUsage(usageRes);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const createKey = async () => {
    if (!keyName.trim()) return;
    setCreating(true);
    setError("");
    try {
      const result = await api.apiKeys.create({ name: keyName });
      setNewKeySecret(result.raw_key || result.key_prefix);
      setKeyName("");
      setShowCreate(false);
      loadData();
    } catch (e: any) {
      setError(e.message || "Create failed");
    } finally {
      setCreating(false);
    }
  };

  const revokeKey = async (id: string) => {
    try {
      await api.apiKeys.revoke(id);
      loadData();
    } catch (e: any) {
      setError(e.message || "Revoke failed");
    } finally {
      setRevokeTargetId(null);
    }
  };

  const copyKey = () => {
    if (newKeySecret) {
      navigator.clipboard.writeText(newKeySecret);
      setCopied(true);
      // M10-F5: Clear secret from state after copy to minimize exposure window
      setTimeout(() => {
        setCopied(false);
        setNewKeySecret(null);
      }, 3000);
    }
  };

  return (
    <RoleGate feature="api_keys" title="API Keys" features={["Create & manage API keys", "Track usage & rate limits", "Developer integrations"]}>
    <div className="space-y-8 p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Key className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">API Keys</h1>
            <p className="text-muted-foreground">Manage developer access to HireStack AI</p>
          </div>
        </div>
        <Button onClick={() => { setShowCreate(true); setNewKeySecret(null); }}>
          <Plus className="h-4 w-4 mr-2" /> Create Key
        </Button>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {/* New Key Secret Display */}
      {newKeySecret && (
        <div className="rounded-xl border-2 border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20 p-6 space-y-3">
          <div className="flex items-center gap-2">
            <Key className="h-5 w-5 text-yellow-600" />
            <h3 className="font-semibold text-yellow-700 dark:text-yellow-300">Your New API Key</h3>
          </div>
          <p className="text-xs text-yellow-600 dark:text-yellow-400">⚠️ Copy this key now — you won&apos;t be able to see it again!</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-background rounded-lg px-4 py-3 text-sm font-mono border">
              {newKeySecret}
            </code>
            <Button size="sm" variant="outline" onClick={copyKey}>
              {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="rounded-xl border p-6 space-y-4 bg-muted/30">
          <h2 className="text-lg font-semibold">Create New API Key</h2>
          <div className="space-y-2">
            <label className="text-sm font-medium">Key Name *</label>
            <input
              className="w-full rounded-lg border bg-background p-3 text-sm"
              placeholder="e.g. Production Server, CI/CD Pipeline"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
            />
          </div>
          <div className="flex gap-3">
            <Button onClick={createKey} disabled={creating || !keyName.trim()}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Key className="h-4 w-4 mr-2" />}
              Generate Key
            </Button>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Usage Stats */}
      {usage && (
        <div className="rounded-xl border p-6 space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="h-5 w-5" /> Usage Summary
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">{usage.total_requests || 0}</div>
              <div className="text-xs text-muted-foreground">Total Requests</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">{usage.requests_today || 0}</div>
              <div className="text-xs text-muted-foreground">Today</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">{usage.requests_this_month || 0}</div>
              <div className="text-xs text-muted-foreground">This Month</div>
            </div>
          </div>
        </div>
      )}

      {/* Keys List */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Your Keys ({keys.length})</h2>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : keys.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Key className="h-16 w-16 mx-auto mb-3 opacity-30" />
            <p>No API keys yet. Create one to get started.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((k) => (
              <div key={k.id} className="rounded-xl border p-4 flex items-center gap-4">
                <div className={`h-3 w-3 rounded-full ${k.is_active ? "bg-green-500" : "bg-red-500"}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{k.name}</span>
                    {!k.is_active && <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700">Revoked</span>}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
                    <code className="bg-muted px-2 py-0.5 rounded">{k.key_prefix}...</code>
                    <span>Created {new Date(k.created_at || "").toLocaleDateString()}</span>
                    {k.last_used_at && <span>Last used {new Date(k.last_used_at).toLocaleDateString()}</span>}
                  </div>
                </div>
                {k.is_active && (
                  <Button size="sm" variant="ghost" className="text-red-500 hover:text-red-700" onClick={() => setRevokeTargetId(k.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>

    <ConfirmDialog
      open={!!revokeTargetId}
      onOpenChange={(open) => { if (!open) setRevokeTargetId(null); }}
      title="Revoke API key?"
      description="This key will stop working immediately. This cannot be undone."
      confirmLabel="Revoke Key"
      variant="destructive"
      onConfirm={() => revokeKey(revokeTargetId!)}
    />
    </RoleGate>
  );
}
