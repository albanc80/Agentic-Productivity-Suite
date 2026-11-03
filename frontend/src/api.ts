// Typed client for the suite API. The optional API token lives in sessionStorage only.

export type Status = "COMPLETE" | "COMPLETE_WITH_ACCEPTED_RISK" | "PARTIAL" | "BLOCKED" | "REJECTED" | "NEEDS_INPUT";

export interface PlaybookInput {
  id: string; label: string; type: "text" | "longtext" | "number" | "select" | "multiselect" | "documents" | "date";
  required: boolean; options: string[]; default: unknown; help: string; example: string;
}
export interface PlaybookCard {
  id: string; code: string; name: string; area: string; desk: string; summary: string; status: string;
  style: string; patterns: string[]; safety_critical: boolean; inputs: PlaybookInput[];
  steps: { id: string; kind: string; title: string; agent: string | null; children: { id: string; agent: string; title: string }[] }[];
  connectors: string[];
}
export interface AgentCard {
  id: string; name: string; callsign: string; desk: string; summary: string; default_tier: string; safety_critical: boolean;
  persona: string | null; core_skills: string[]; skills: string[]; tools: string[]; modes: Record<string, string>; default_mode: string | null;
  merged_from: string[]; instruction_chars: number;
}
export interface ModelEndpoint {
  id: string; name: string; base_url: string; model: string; context_tokens: number; max_output_tokens: number;
  tools: boolean; use_for: string[]; provider?: string; ref?: string; locality?: "local" | "cloud";
}
export interface Desk { id: string; name: string; lead: string; summary: string; members: string[] }
export interface ProviderInfo {
  name: string; type: string; locality: "local" | "cloud"; base_url: string | null; available: boolean; reason: string;
  api_key_env: string | null; note: string; models: { ref: string; context_tokens: number; tools: boolean; price_in_per_mtok: number; price_out_per_mtok: number; note: string }[];
}
export interface ConnectorInfo {
  id: string; name: string; description: string; transport: string; status: string; error: string; setup: string;
  verify: string; required_env: string[]; tools: { name: string; allowed: boolean; reason: string }[];
}
export interface Overview {
  desks: Desk[]; agents: AgentCard[]; playbooks: PlaybookCard[]; providers: ProviderInfo[]; tiers: Record<string, string[]>;
  connectors: ConnectorInfo[]; data_classes: Record<string, string[]>; default_data_class: string; kill_switch: boolean; offline: boolean;
  offline_override: boolean | null; endpoints: ModelEndpoint[];
  budgets: Record<string, number>; persona: { chat: boolean; exports: boolean }; profile_configured: boolean;
  warnings: string[]; pending_approvals: number;
}
export interface Claim { text: string; label: string; trace: string | null }
export interface Handoff {
  status: Status; summary: string; claims: Claim[]; risks: { risk: string; severity: string; mitigation: string }[];
  open_questions: string[]; next_action: { action: string; owner: string; gate: string }; skills_invoked: string[];
  evidence: string; verdict: string | null; findings: string[];
}
export interface StepRow {
  id: string; step_id: string; parent: string | null; kind: string; agent: string | null; title: string; status: string;
  provider: string | null; model: string | null; attempt: number; tokens_in: number; tokens_out: number; cost_usd: number;
  latency_ms: number; prompt_chars: number; output: { handoff?: Handoff; data?: string } | null; deliverable: string | null;
  warnings: string[]; tool_calls: { tool: string; arguments: unknown; error: boolean; chars: number }[]; error: string | null;
  started_at: string; ended_at: string | null;
}
export interface Approval {
  id: string; run_id: string; step_id: string; title: string; instructions: string; required_role: string | null;
  payload: string; status: string; decided_by: string | null; note: string | null; created_at: string; decided_at: string | null;
  run_title?: string; playbook_id?: string;
}
export interface RunSummary {
  id: string; playbook_id: string; title: string; status: string; outcome: Status | null; data_class: string;
  tokens: number; cost_usd: number; demo: boolean; created_at: string; updated_at: string;
}
export interface RunDetail extends RunSummary {
  inputs: Record<string, unknown>; options: Record<string, unknown>; cursor: number; notes: string[];
  deliverable: string | null; steps: StepRow[]; approvals: Approval[]; playbook: PlaybookCard | null;
}
export interface RouteResult {
  playbook: string; confidence: number; method: string; reason: string; auto: boolean;
  candidates: { id: string; name: string; summary: string }[];
}

const TOKEN_KEY = "suite.token";
export function getToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}
export function setToken(t: string) {
  try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<{ status: string; auth_required: boolean; kill_switch: boolean; version: string }>("/api/health"),
  overview: () => call<Overview>("/api/overview"),
  agent: (id: string) => call<AgentCard & { instructions: string; modes_detail: Record<string, { summary: string; instructions: string }>; persona_text: string | null; skills_detail: { id: string; description: string; chars: number }[] }>(`/api/agents/${id}`),
  route: (text: string, data_class?: string) => call<RouteResult>("/api/route", { method: "POST", body: JSON.stringify({ text, data_class }) }),
  upload: (file: File) => { const fd = new FormData(); fd.append("file", file); return call<{ id: string; name: string; chars: number }>("/api/files", { method: "POST", body: fd }); },
  startRun: (playbook_id: string, inputs: Record<string, unknown>, data_class: string, options: Record<string, unknown>) =>
    call<{ id: string }>("/api/runs", { method: "POST", body: JSON.stringify({ playbook_id, inputs, data_class, options }) }),
  runs: () => call<RunSummary[]>("/api/runs"),
  run: (id: string) => call<RunDetail>(`/api/runs/${id}`),
  cancel: (id: string) => call<RunDetail>(`/api/runs/${id}/cancel`, { method: "POST" }),
  resume: (id: string) => call<{ id: string }>(`/api/runs/${id}/resume`, { method: "POST" }),
  approvals: (status = "pending") => call<Approval[]>(`/api/approvals?status=${status}`),
  decide: (id: string, body: { decision: "approved" | "rejected"; decided_by: string; note: string; edited?: string | null }) =>
    call<Approval>(`/api/approvals/${id}`, { method: "POST", body: JSON.stringify(body) }),
  testProvider: (name: string) => call<{ ok: boolean; detail?: string; model?: string; latency_ms?: number; reply?: string }>(`/api/providers/${name}/test`, { method: "POST" }),
  connect: (id: string) => call<{ id: string; tools: { name: string; allowed: boolean; reason: string; description: string }[] }>(`/api/connectors/${id}/connect`, { method: "POST" }),
  setOffline: (on: boolean | null) => call<{ on: boolean; override: boolean | null; default: boolean }>("/api/admin/offline", { method: "POST", body: JSON.stringify({ on, by: "ui" }) }),
  discover: (base_url: string) => call<{ base_url: string; locality: "local" | "cloud"; models: string[] }>("/api/endpoints/discover", { method: "POST", body: JSON.stringify({ base_url }) }),
  saveEndpoint: (ep: ModelEndpoint) => call<ModelEndpoint>("/api/endpoints", { method: "POST", body: JSON.stringify(ep) }),
  deleteEndpoint: (id: string) => call<{ deleted: string }>(`/api/endpoints/${encodeURIComponent(id)}`, { method: "DELETE" }),
  killSwitch: (on: boolean) => call<{ on: boolean }>("/api/admin/kill-switch", { method: "POST", body: JSON.stringify({ on, by: "ui" }) }),
  exportUrl: (id: string, format: "md" | "html") => `/api/runs/${id}/export?format=${format}`,
};

export async function download(id: string, format: "md" | "html") {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(api.exportUrl(id, format), { headers });
  if (!res.ok) throw new ApiError(res.status, "export failed");
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1] || `deliverable.${format}`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
