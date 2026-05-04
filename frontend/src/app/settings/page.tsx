"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, AppSettings, ModelList, EditableDraft, PatchSettingsResult } from "../../lib/api";

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

function parseUserRolesInput(raw: string): string | null {
  const entries = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  for (const entry of entries) {
    const parts = entry.split(":");
    if (parts.length !== 2) {
      return "Each role mapping must use username:role format.";
    }
    const [username, role] = parts.map((part) => part.trim());
    if (!username) {
      return "Each role mapping must include a username.";
    }
    if (role !== "analyst" && role !== "planner") {
      return "Each role must be analyst or planner.";
    }
  }

  return null;
}

function toUserRolesCsv(raw: string): string {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join(",");
}

function normalizeRoleMappings(value: string | undefined): string {
  return (value ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .join(",");
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [modelList, setModelList] = useState<ModelList | null>(null);
  const [loading, setLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<EditableDraft>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [applyLoading, setApplyLoading] = useState(false);
  const [applySuccess, setApplySuccess] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [restartRequired, setRestartRequired] = useState<string[]>([]);
  const [savedDraft, setSavedDraft] = useState<EditableDraft>({});
  const [modelVerificationRequired, setModelVerificationRequired] = useState(false);

  const isDirty = Object.keys(draft).length > 0;
  const isPlanner = settings?.current_user?.role === "planner";
  const controlsLocked = applyLoading;

  const discardEdits = () => {
    setDraft({});
    setFieldErrors({});
    setApplyError(null);
    setModelVerificationRequired(false);
    setIsEditing(false);
  };

  const confirmDiscardAndLeave = () => {
    if (!isDirty) return true;
    return window.confirm("Discard unsaved settings changes and leave this page?");
  };

  const handleDashboardClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (controlsLocked) {
      e.preventDefault();
      return;
    }
    if (!isEditing) return;

    e.preventDefault();
    if (confirmDiscardAndLeave()) {
      discardEdits();
      router.push("/");
    }
  };

  const handleLeaveEditMode = () => {
    if (controlsLocked) return;
    if (confirmDiscardAndLeave()) {
      discardEdits();
      router.push("/");
    }
  };

  const syncSettingsState = (nextSettings: AppSettings) => {
    setSettings(nextSettings);
    setSavedDraft(nextSettings.persisted_editable ?? {});
  };

  useEffect(() => {
    api.getSettings()
      .then(syncSettingsState)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

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

  const applyChanges = async () => {
    setApplyLoading(true);
    setApplySuccess(false);
    setApplyError(null);
    setFieldErrors({});
    try {
      const submittedDraft = { ...draft };
      const result: PatchSettingsResult = await api.patchSettings(draft);
      if (Object.keys(result.errors).length > 0) {
        setFieldErrors(result.errors);
        return;
      }
      setRestartRequired(result.restart_required);
      setSavedDraft((current) => {
        const next = { ...current };
        for (const key of result.applied) {
          const typedKey = key as keyof EditableDraft;
          const value = submittedDraft[typedKey];
          if (value !== undefined) {
            next[typedKey] = value;
          }
        }
        return next;
      });
      setApplySuccess(true);
      setDraft({});
      setFieldErrors({});
      setModelVerificationRequired(false);
      setIsEditing(false);
      // Refresh runtime-only fields without relying on this response to reflect persisted .env edits.
      api.getSettings().then(syncSettingsState).catch(() => {});
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to save settings.";
      if (message.includes("Planner role required")) {
        setApplyError("Planner access is required to save settings. Your session no longer has planner permissions, so edit mode has been closed.");
        setDraft({});
        setFieldErrors({});
        setIsEditing(false);
        api.getSettings().then(syncSettingsState).catch(() => {});
      } else {
        setApplyError(message);
      }
    } finally {
      setApplyLoading(false);
    }
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
  const effectiveModel = s.env_overrides.AGENT_MODEL || s.agent.model;
  const effectiveProvider = s.env_overrides.AGENT_PROVIDER || s.agent.provider;
  const editBaselineProvider = savedDraft.AGENT_PROVIDER ?? effectiveProvider;
  const editBaselineModel = savedDraft.AGENT_MODEL ?? effectiveModel;
  const editBaselineOllamaBaseUrl = savedDraft.OLLAMA_BASE_URL ?? s.agent.ollama_base_url;
  const editBaselineBackendPort = savedDraft.BACKEND_PORT ?? s.env_overrides.BACKEND_PORT;
  const editBaselineDefaultRole = savedDraft.API_USER_ROLE ?? s.default_role;
  const selectedProvider = (draft.AGENT_PROVIDER ?? editBaselineProvider).toLowerCase();
  const selectedOllamaBaseUrl = draft.OLLAMA_BASE_URL ?? editBaselineOllamaBaseUrl;
  const runtimeProviderKey = effectiveProvider.toLowerCase();
  const providerForProviderSpecificUi = isEditing ? selectedProvider : runtimeProviderKey;
  const modelDraftBaseline =
    selectedProvider === editBaselineProvider.toLowerCase() &&
    (selectedProvider !== "ollama" || selectedOllamaBaseUrl === editBaselineOllamaBaseUrl)
      ? editBaselineModel
      : "";
  const selectedModel = modelVerificationRequired && draft.AGENT_MODEL === undefined
    ? ""
    : (draft.AGENT_MODEL ?? modelDraftBaseline);
  const effectiveDefaultRole = s.default_role;
  const inferredDefaultRole = draft.API_USER_ROLE ?? editBaselineDefaultRole;
  const runtimeUserRolesCsv = Object.entries(s.user_roles).map(([user, role]) => `${user}:${role}`).join(",");
  const baselineUserRolesCsv = savedDraft.API_USER_ROLES ?? runtimeUserRolesCsv;
  const persistedUserRolesText = savedDraft.API_USER_ROLES !== undefined
    ? savedDraft.API_USER_ROLES.split(",").map((role) => role.trim()).filter(Boolean).join("\n")
    : runtimeUserRolesCsv.split(",").map((role) => role.trim()).filter(Boolean).join("\n");
  const providerPendingRestart =
    savedDraft.AGENT_PROVIDER !== undefined && savedDraft.AGENT_PROVIDER !== effectiveProvider;
  const modelPendingRestart =
    savedDraft.AGENT_MODEL !== undefined && savedDraft.AGENT_MODEL !== effectiveModel;
  const ollamaBaseUrlPendingRestart =
    savedDraft.OLLAMA_BASE_URL !== undefined && savedDraft.OLLAMA_BASE_URL !== s.agent.ollama_base_url;
  const backendPortPendingRestart =
    savedDraft.BACKEND_PORT !== undefined && savedDraft.BACKEND_PORT !== s.env_overrides.BACKEND_PORT;
  const userRolesPendingRestart =
    savedDraft.API_USER_ROLES !== undefined &&
    normalizeRoleMappings(savedDraft.API_USER_ROLES) !== normalizeRoleMappings(runtimeUserRolesCsv);
  const defaultRolePendingRestart =
    savedDraft.API_USER_ROLE !== undefined && savedDraft.API_USER_ROLE !== effectiveDefaultRole;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/60 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-100">Settings</h1>
            <p className="text-xs text-slate-500 mt-0.5">Runtime configuration — read from .env and config.yaml</p>
          </div>
          <div className="flex items-center gap-2">
            {!isEditing ? (
              <>
                <Link
                  href="/"
                  onClick={handleDashboardClick}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
                >
                  ← Dashboard
                </Link>
                <button
                  onClick={() => { setIsEditing(true); setApplySuccess(false); }}
                  disabled={!isPlanner || controlsLocked}
                  title={isPlanner ? undefined : "Planner role required"}
                  className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Edit Settings
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleLeaveEditMode}
                  disabled={controlsLocked}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Leave Without Saving
                </button>
                <button
                  onClick={discardEdits}
                  disabled={controlsLocked}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-rose-400 hover:text-rose-300"
                >
                  Discard
                </button>
                <button
                  onClick={applyChanges}
                  disabled={!isDirty || controlsLocked || Object.keys(fieldErrors).length > 0}
                  className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {applyLoading ? "Saving…" : "Apply Changes"}
                </button>
              </>
            )}
          </div>
        </div>
        {isEditing && (
          <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-2">
            <p className="text-xs text-amber-300 max-w-3xl mx-auto">
              You are editing settings — unsaved changes will be lost if you navigate away. Saved changes take effect after backend restart.
            </p>
          </div>
        )}
      </header>

      {applySuccess && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-3">
          <p className="text-xs text-amber-300 max-w-3xl mx-auto">
            Settings saved to <code className="text-amber-200">.env</code>. Restart the backend (
            <code className="text-amber-200">bash scripts/dev.sh</code>) to apply changes.
            {restartRequired.length > 0 ? ` Restart required for: ${restartRequired.join(", ")}.` : ""}
          </p>
        </div>
      )}
      {applyError && (
        <div className="bg-rose-500/10 border-b border-rose-500/20 px-6 py-3">
          <p className="text-xs text-rose-300 max-w-3xl mx-auto">{applyError}</p>
        </div>
      )}

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">

        {/* LLM Provider */}
        <Section title="AI Provider">
          {/* Provider */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Provider</p>
              <p className="text-xs text-slate-500 mt-0.5">Set AGENT_PROVIDER in .env to switch. Options: claude · openai · gemini · ollama</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <select
                    value={draft.AGENT_PROVIDER ?? editBaselineProvider}
                    onChange={(e) => {
                      const nextProvider = e.target.value;
                      const providerChanged = nextProvider !== editBaselineProvider;
                      const nextOllamaBaseUrl = draft.OLLAMA_BASE_URL ?? editBaselineOllamaBaseUrl;
                      setDraft((d) => {
                        const next = { ...d };
                        if (providerChanged) {
                          next.AGENT_PROVIDER = nextProvider;
                        } else {
                          delete next.AGENT_PROVIDER;
                        }
                        delete next.AGENT_MODEL;
                        return next;
                      });
                      setModelVerificationRequired(
                        providerChanged ||
                        (nextProvider === "ollama" && nextOllamaBaseUrl !== editBaselineOllamaBaseUrl)
                      );
                      setFieldErrors((fe) => {
                        const n = { ...fe };
                        delete n.AGENT_PROVIDER;
                        if (providerChanged || (nextProvider === "ollama" && nextOllamaBaseUrl !== editBaselineOllamaBaseUrl)) {
                          n.AGENT_MODEL = "Re-enter and verify a model for the selected provider.";
                        } else {
                          delete n.AGENT_MODEL;
                        }
                        return n;
                      });
                    }}
                    disabled={controlsLocked}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1"
                  >
                    {["claude", "openai", "gemini", "ollama"].map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.AGENT_PROVIDER && <p className="text-xs text-rose-400">{fieldErrors.AGENT_PROVIDER}</p>}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-emerald-300">{effectiveProvider}</span>
                  {s.env_overrides.AGENT_PROVIDER && <Badge text="env override" variant="warn" />}
                  {providerPendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                </div>
              )}
            </div>
          </div>

          {/* Model */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Model</p>
              <p className="text-xs text-slate-500 mt-0.5">Set AGENT_MODEL in .env. Use &apos;Verify Available Models&apos; below to find valid names.</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={selectedModel}
                      onChange={(e) => {
                        const nextModel = e.target.value;
                        setDraft((d) => {
                          const next = { ...d };
                          if (nextModel === modelDraftBaseline) {
                            delete next.AGENT_MODEL;
                          } else {
                            next.AGENT_MODEL = nextModel;
                          }
                          return next;
                        });
                        setFieldErrors((fe) => {
                          const n = { ...fe };
                          n.AGENT_MODEL = modelVerificationRequired
                            ? "Verify the model for the selected provider."
                            : "";
                          if (!n.AGENT_MODEL) {
                            delete n.AGENT_MODEL;
                          }
                          return n;
                        });
                      }}
                      disabled={controlsLocked}
                      className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56"
                    />
                    <button
                      onClick={async () => {
                        if (!selectedModel.trim()) {
                          setFieldErrors((fe) => ({ ...fe, AGENT_MODEL: "Enter a model ID to verify." }));
                          return;
                        }
                        try {
                          const result = await api.validateDraftModel({
                            provider: selectedProvider,
                            model: selectedModel,
                            ollama_base_url: selectedOllamaBaseUrl,
                          });
                          if (result.error || !result.model_available) {
                            setFieldErrors((fe) => ({
                              ...fe,
                              AGENT_MODEL: result.error ?? `Model not found for provider ${selectedProvider}`,
                            }));
                          } else {
                            setModelVerificationRequired(false);
                            setFieldErrors((fe) => { const n = { ...fe }; delete n.AGENT_MODEL; return n; });
                          }
                        } catch (e) {
                          setFieldErrors((fe) => ({
                            ...fe,
                            AGENT_MODEL: e instanceof Error ? e.message : "Unable to verify model right now.",
                          }));
                        }
                      }}
                      disabled={controlsLocked || !selectedModel.trim()}
                      className="rounded bg-slate-700 border border-slate-600 text-slate-300 text-xs px-2 py-1 hover:border-blue-400 hover:text-blue-300"
                    >
                      Verify
                    </button>
                  </div>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.AGENT_MODEL && <p className="text-xs text-rose-400">{fieldErrors.AGENT_MODEL}</p>}
                </div>
              ) : (
                <div className="flex flex-col items-end gap-1">
                  <span className="font-mono text-emerald-300">{effectiveModel}</span>
                  {s.env_overrides.AGENT_MODEL && <Badge text="env override" variant="warn" />}
                  {modelList?.current_model_available === false && <Badge text="⚠ model not found" variant="error" />}
                  {modelList?.current_model_available === true && <Badge text="✓ confirmed available" variant="ok" />}
                  {modelPendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                </div>
              )}
            </div>
          </div>

          <SettingRow
            label="API Key Env Var"
            value={<Badge text={PROVIDER_KEY_ENV[providerForProviderSpecificUi] ?? "—"} />}
            hint="Set this in your .env file. Keys are never transmitted to the UI."
          />
          {/* Ollama URL — show in read mode when provider=ollama; always show in edit mode */}
          {providerForProviderSpecificUi === "ollama" && (
            <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60 last:border-0">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-300">Ollama Base URL</p>
                <p className="text-xs text-slate-500 mt-0.5">Set OLLAMA_BASE_URL in .env to change.</p>
              </div>
              <div className="text-right">
                {isEditing ? (
                  <div className="flex flex-col items-end gap-1">
                    <input
                      type="text"
                      value={draft.OLLAMA_BASE_URL ?? editBaselineOllamaBaseUrl}
                      onChange={(e) => {
                        const nextValue = e.target.value;
                        const urlChanged = nextValue !== editBaselineOllamaBaseUrl;
                        const verificationStillRequired = urlChanged || selectedProvider !== editBaselineProvider.toLowerCase();
                        setDraft((d) => {
                          const next = { ...d };
                          if (!urlChanged) {
                            delete next.OLLAMA_BASE_URL;
                          } else {
                            next.OLLAMA_BASE_URL = nextValue;
                          }
                          return next;
                        });
                        setModelVerificationRequired(verificationStillRequired);
                        setFieldErrors((fe) => {
                          const n = { ...fe };
                          delete n.OLLAMA_BASE_URL;
                          if (verificationStillRequired) {
                            n.AGENT_MODEL = "Verify the model for the selected provider.";
                          } else {
                            delete n.AGENT_MODEL;
                          }
                          return n;
                        });
                      }}
                      disabled={controlsLocked}
                      className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56"
                    />
                    <Badge text="⚠ restart required" variant="warn" />
                    {fieldErrors.OLLAMA_BASE_URL && <p className="text-xs text-rose-400">{fieldErrors.OLLAMA_BASE_URL}</p>}
                  </div>
                ) : (
                  <div className="flex flex-col items-end gap-1">
                    <span className="font-mono text-emerald-300">{s.agent.ollama_base_url}</span>
                    {ollamaBaseUrlPendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Verify models button — read mode only */}
          {!isEditing && (
            <div className="pt-2 flex flex-wrap gap-2">
              <button
                onClick={fetchModels}
                disabled={modelsLoading}
                className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {modelsLoading ? "Loading…" : "Verify Available Models"}
              </button>
              {PROVIDER_DOCS[providerForProviderSpecificUi] && (
                <a
                  href={PROVIDER_DOCS[providerForProviderSpecificUi]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
                >
                  View Model Docs ↗
                </a>
              )}
            </div>
          )}

          {/* Model list results — read mode only */}
          {!isEditing && modelList && (
            <div className="mt-3 rounded-lg border border-slate-700/60 bg-slate-900/50 p-4 space-y-2">
              {modelList.error && <p className="text-xs text-rose-400">{modelList.error}</p>}
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
          <div className="rounded-lg border border-slate-800/60 bg-slate-900/30 px-3 py-2">
            <p className="text-xs text-slate-400">
              Read-only in the UI. Update <code className="text-emerald-400">config/config.yaml</code> and restart the backend to change pipeline behavior.
            </p>
          </div>
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
          {/* Backend Port */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Backend Port</p>
              <p className="text-xs text-slate-500 mt-0.5">Set BACKEND_PORT in .env. Requires restart.</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <input
                    type="number"
                    min={1024}
                    max={65535}
                    value={draft.BACKEND_PORT ?? editBaselineBackendPort}
                    onChange={(e) => {
                      const nextValue = e.target.value;
                      setDraft((d) => {
                        const next = { ...d };
                        if (nextValue === editBaselineBackendPort) {
                          delete next.BACKEND_PORT;
                        } else {
                          next.BACKEND_PORT = nextValue;
                        }
                        return next;
                      });
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.BACKEND_PORT; return n; });
                    }}
                    disabled={controlsLocked}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-28"
                  />
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.BACKEND_PORT && <p className="text-xs text-rose-400">{fieldErrors.BACKEND_PORT}</p>}
                </div>
              ) : (
                <div className="flex flex-col items-end gap-1">
                  <span className="font-mono text-emerald-300">{s.env_overrides.BACKEND_PORT}</span>
                  {backendPortPendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                </div>
              )}
            </div>
          </div>
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

        {/* User Roles */}
        <Section title="User Roles">
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60 last:border-0">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Role Mappings</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Comma-separated <code className="text-emerald-400">username:role</code> pairs (API_USER_ROLES). Each role must be analyst or planner.
              </p>
            </div>
            <div className="text-right min-w-[220px]">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <textarea
                    rows={3}
                    value={draft.API_USER_ROLES !== undefined
                      ? draft.API_USER_ROLES.split(",").map((r) => r.trim()).filter(Boolean).join("\n")
                      : persistedUserRolesText}
                    onChange={(e) => {
                      const csv = toUserRolesCsv(e.target.value);
                      setDraft((d) => {
                        const next = { ...d };
                        if (csv === baselineUserRolesCsv) {
                          delete next.API_USER_ROLES;
                        } else {
                          next.API_USER_ROLES = csv;
                        }
                        return next;
                      });
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.API_USER_ROLES; return n; });
                    }}
                    onBlur={(e) => {
                      const errorMessage = parseUserRolesInput(e.target.value);
                      if (errorMessage) {
                        setFieldErrors((fe) => ({ ...fe, API_USER_ROLES: errorMessage }));
                      } else {
                        setFieldErrors((fe) => {
                          const next = { ...fe };
                          delete next.API_USER_ROLES;
                          return next;
                        });
                      }
                    }}
                    disabled={controlsLocked}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56 resize-none"
                    placeholder={"alice:planner\nbob:analyst"}
                  />
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.API_USER_ROLES && <p className="text-xs text-rose-400">{fieldErrors.API_USER_ROLES}</p>}
                </div>
              ) : (
                <div className="flex flex-col items-end gap-1">
                  {Object.keys(s.user_roles).length > 0
                    ? Object.entries(s.user_roles).map(([user, role]) => {
                        return (
                        <div key={user} className="flex items-center gap-2">
                          <span className="text-xs text-slate-400 font-mono">{user}</span>
                          <Badge text={role} variant={role === "planner" ? "ok" : "default"} />
                        </div>
                      );
                    })
                    : <span className="text-xs text-slate-500">No mappings set</span>
                  }
                  {userRolesPendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                </div>
              )}
            </div>
          </div>

          {/* Default role */}
          <div className="flex items-start justify-between gap-4 py-3 last:border-0">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Default Role</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Applied to any user not listed above (<code className="text-emerald-400">API_USER_ROLE</code>).
                Saved changes take effect after restart.
              </p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <select
                    value={draft.API_USER_ROLE ?? inferredDefaultRole}
                    onChange={(e) => {
                      const nextValue = e.target.value;
                      setDraft((d) => {
                        const next = { ...d };
                        if (nextValue === editBaselineDefaultRole) {
                          delete next.API_USER_ROLE;
                        } else {
                          next.API_USER_ROLE = nextValue;
                        }
                        return next;
                      });
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.API_USER_ROLE; return n; });
                    }}
                    disabled={controlsLocked}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1"
                  >
                    <option value="" disabled>Select default role…</option>
                    <option value="analyst">analyst</option>
                    <option value="planner">planner</option>
                  </select>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.API_USER_ROLE && <p className="text-xs text-rose-400">{fieldErrors.API_USER_ROLE}</p>}
                </div>
              ) : (
                  <div className="flex flex-col items-end gap-1">
                    <Badge
                      text={effectiveDefaultRole}
                      variant={effectiveDefaultRole === "planner" ? "ok" : "default"}
                    />
                    {defaultRolePendingRestart && <Badge text="saved, restart pending" variant="ok" />}
                  </div>
              )}
            </div>
          </div>
        </Section>

        {/* Bottom hint */}
        {!isEditing && (
          <div className="rounded-lg border border-slate-800/60 bg-slate-900/30 p-4 space-y-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">How to change these settings</p>
            <p className="text-xs text-slate-400">
              Click <strong className="text-slate-300">Edit Settings</strong> above (planner role required), or edit{" "}
              <code className="text-emerald-400">.env</code> in the repo root and restart the backend with{" "}
              <code className="text-emerald-400">bash scripts/dev.sh</code>.
              Changes to <code className="text-emerald-400">config/config.yaml</code> also require a restart.
            </p>
          </div>
        )}

      </main>
    </div>
  );
}
