"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, AppSettings, ModelList } from "../../lib/api";

const PROVIDER_DOCS: Record<string, string> = {
  claude: "https://docs.anthropic.com/en/docs/about-claude/models",
  openai: "https://platform.openai.com/docs/models",
  gemini: "https://ai.google.dev/gemini-api/docs/models",
  ollama: "https://ollama.com/library",
};

const PROVIDER_KEY_ENV: Record<string, string> = {
  claude: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  gemini: "GEMINI_API_KEY",
  ollama: "— (no key required)",
};

function SettingRow({ label, value, mono = false, hint }: { label: string; value: React.ReactNode; mono?: boolean; hint?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-300">{label}</p>
        {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
      </div>
      <div className={`text-sm ${mono ? "font-mono text-emerald-300" : "text-slate-200"} text-right`}>
        {value}
      </div>
    </div>
  );
}

function Badge({ text, variant = "default" }: { text: string; variant?: "default" | "ok" | "warn" | "error" }) {
  const colours: Record<string, string> = {
    default: "bg-slate-700/60 text-slate-300",
    ok: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25",
    warn: "bg-amber-500/15 text-amber-300 border border-amber-500/25",
    error: "bg-rose-500/15 text-rose-300 border border-rose-500/25",
  };
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${colours[variant]}`}>
      {text}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass rounded-xl p-6 space-y-1">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">{title}</h2>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [modelList, setModelList] = useState<ModelList | null>(null);
  const [loading, setLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings()
      .then(setSettings)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, []);

  const fetchModels = () => {
    setModelsLoading(true);
    api.listModels()
      .then(setModelList)
      .catch((e: unknown) => {
        setModelList({
          provider: settings?.agent.provider ?? "",
          current_model: settings?.agent.model ?? "",
          models: [],
          current_model_available: null,
          error: e instanceof Error ? e.message : "Failed to list models",
        });
      })
      .finally(() => setModelsLoading(false));
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
        <div className="text-slate-400 animate-pulse">Loading settings…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
        <div className="glass rounded-xl p-8 max-w-md text-center space-y-3">
          <p className="text-rose-400 text-sm">{error}</p>
          <Link href="/" className="text-xs text-slate-400 hover:text-slate-200 underline">
            ← Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const s = settings!;
  const provider = s.agent.provider.toLowerCase();
  const effectiveModel = s.env_overrides.AGENT_MODEL || s.agent.model;
  const effectiveProvider = s.env_overrides.AGENT_PROVIDER || s.agent.provider;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/60 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-100">Settings</h1>
            <p className="text-xs text-slate-500 mt-0.5">Runtime configuration — read from .env and config.yaml</p>
          </div>
          <Link
            href="/"
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
          >
            ← Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">

        {/* LLM Provider */}
        <Section title="AI Provider">
          <SettingRow
            label="Provider"
            value={
              <div className="flex items-center gap-2">
                <span className="font-mono text-emerald-300">{effectiveProvider}</span>
                {s.env_overrides.AGENT_PROVIDER && (
                  <Badge text="env override" variant="warn" />
                )}
              </div>
            }
            hint="Set AGENT_PROVIDER in .env to switch. Options: claude · openai · gemini · ollama"
          />
          <SettingRow
            label="Model"
            value={
              <div className="flex flex-col items-end gap-1">
                <span className="font-mono text-emerald-300">{effectiveModel}</span>
                {s.env_overrides.AGENT_MODEL && (
                  <Badge text="env override" variant="warn" />
                )}
                {modelList && modelList.current_model_available === false && (
                  <Badge text="⚠ model not found" variant="error" />
                )}
                {modelList && modelList.current_model_available === true && (
                  <Badge text="✓ confirmed available" variant="ok" />
                )}
              </div>
            }
            hint="Set AGENT_MODEL in .env. Use 'Verify Available Models' below to find valid names."
          />
          <SettingRow
            label="API Key Env Var"
            value={<Badge text={PROVIDER_KEY_ENV[provider] ?? "—"} />}
            hint="Set this in your .env file. Keys are never transmitted to the UI."
          />
          {provider === "ollama" && (
            <SettingRow
              label="Ollama Base URL"
              value={s.agent.ollama_base_url}
              mono
              hint="Set OLLAMA_BASE_URL in .env to change."
            />
          )}
          <div className="pt-2 flex flex-wrap gap-2">
            <button
              onClick={fetchModels}
              disabled={modelsLoading}
              className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {modelsLoading ? "Loading…" : "Verify Available Models"}
            </button>
            {PROVIDER_DOCS[provider] && (
              <a
                href={PROVIDER_DOCS[provider]}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
              >
                View Model Docs ↗
              </a>
            )}
          </div>

          {/* Model list results */}
          {modelList && (
            <div className="mt-3 rounded-lg border border-slate-700/60 bg-slate-900/50 p-4 space-y-2">
              {modelList.error && (
                <p className="text-xs text-rose-400">{modelList.error}</p>
              )}
              {modelList.models.length > 0 ? (
                <>
                  <p className="text-xs text-slate-400 mb-2">
                    {modelList.models.length} models available — copy the exact ID to <code className="text-emerald-400">AGENT_MODEL</code> in your .env:
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 max-h-48 overflow-y-auto">
                    {modelList.models.map((m) => (
                      <div
                        key={m}
                        className={`flex items-center gap-2 rounded px-2 py-1 text-xs font-mono ${
                          m === effectiveModel
                            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        {m === effectiveModel && <span>✓</span>}
                        {m}
                      </div>
                    ))}
                  </div>
                </>
              ) : !modelList.error ? (
                <p className="text-xs text-slate-500">No models returned — provider may not support listing.</p>
              ) : null}
            </div>
          )}
        </Section>

        {/* Pipeline config */}
        <Section title="Pipeline Behaviour">
          <SettingRow
            label="Batch Size"
            value={String(s.agent.batch_size)}
            mono
            hint="Exceptions per LLM call. Reduce for smaller context-window models. Set in config.yaml."
          />
          <SettingRow
            label="Max Tokens (per call)"
            value={String(s.agent.max_tokens)}
            mono
            hint="Maximum output tokens for each LLM response. Set in config.yaml."
          />
          <SettingRow
            label="Retry Attempts"
            value={String(s.agent.retry_attempts)}
            mono
            hint="Number of times the agent retries a failed LLM call before giving up."
          />
        </Section>

        {/* Server */}
        <Section title="Server">
          <SettingRow
            label="Backend Port"
            value={s.env_overrides.BACKEND_PORT}
            mono
            hint="Set BACKEND_PORT in .env. Requires restart."
          />
          <SettingRow
            label="API User"
            value={s.current_user.username}
            mono
            hint="HTTP Basic Auth username (API_USERNAME in .env, default: admin)."
          />
          <SettingRow
            label="Your Role"
            value={
              <Badge
                text={s.current_user.role}
                variant={s.current_user.role === "planner" ? "ok" : "default"}
              />
            }
            hint="Set API_USER_ROLES=username:role in .env. Planners can approve overrides and use additional action types."
          />
        </Section>

        {/* Role map */}
        {Object.keys(s.user_roles).length > 0 && (
          <Section title="User Roles">
            {Object.entries(s.user_roles).map(([user, role]) => (
              <SettingRow
                key={user}
                label={user}
                value={<Badge text={role} variant={role === "planner" ? "ok" : "default"} />}
              />
            ))}
          </Section>
        )}

        {/* Env overrides hint */}
        <div className="rounded-lg border border-slate-800/60 bg-slate-900/30 p-4 space-y-1">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">How to change these settings</p>
          <p className="text-xs text-slate-400">
            Edit <code className="text-emerald-400">.env</code> in the repo root, then restart the backend with{" "}
            <code className="text-emerald-400">bash scripts/dev.sh</code>.
            Changes to <code className="text-emerald-400">config/config.yaml</code> also require a restart (hot-reload does not pick up YAML changes).
          </p>
        </div>

      </main>
    </div>
  );
}
