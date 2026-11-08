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
  connector_choice?: Record<string, { input: string; contains: string }>;
}
export interface AgentCard {
  id: string; name: string; desk: string; summary: string; capabilities: string[]; default_tier: string;
  safety_critical: boolean; core_skills: string[]; skills: string[]; tools: string[]; modes: Record<string, string>; default_mode: string | null;
}
export interface ModelEndpoint {
  id: string; name: string; base_url: string; model: string; context_tokens: number; max_output_tokens: number;
  tools: boolean; use_for: string[]; provider?: string; ref?: string; locality?: "local" | "cloud";
  api_key?: string; has_api_key?: boolean;
}
export interface ModelEdit {
  model: string; context_tokens: number; max_output_tokens: number; tools: boolean;
  price_in_per_mtok?: number | null; price_out_per_mtok?: number | null;
}
export interface ProviderEdit {
  enabled?: boolean; base_url?: string; api_key?: string; clear_api_key?: boolean; models?: ModelEdit[];
}
export interface Desk { id: string; name: string; lead: string; summary: string; members: string[] }
export interface ProviderInfo {
  name: string; type: string; locality: "local" | "cloud"; base_url: string | null; available: boolean; reason: string;
  enabled: boolean; offline_paused: boolean; api_key_env: string | null; api_key_source: "env" | "app" | "config" | null; edited_in_app: boolean;
  endpoint: boolean; note: string;
  models: { ref: string; context_tokens: number; max_output_tokens: number; tools: boolean; price_in_per_mtok: number; price_out_per_mtok: number; note: string }[];
}
export interface ConnectorVariable {
  name: string; secret: boolean; flag: boolean; optional: boolean; default: string; set: boolean;
  source: "env" | "app" | "bundled" | null; value: string | null;  // bundled: an OAuth client built into the app
  label: string; hint: string; part: string | null;  // label and help from the connector; part of a grouped connector
}
export interface ConnectorInfo {
  id: string; name: string; description: string; transport: string; status: string; error: string; setup: string;
  verify: string; required_env: string[]; tools: { name: string; allowed: boolean; reason: string }[];
  enabled: boolean; network: boolean; offline_paused: boolean; builtin: boolean; folders: string[]; variables: ConnectorVariable[];
  missing: string[];  // what is still needed before it can be switched on
  steps: string[]; docs_url: string;  // numbered setup steps and the server's own documentation
  parts: { id: string; name: string; description: string; ready: boolean }[];  // grouped connector (Databricks)
  // Sign-in from the app (Microsoft 365): the flag a sign-in confirms and the accounts list it fills in.
  // kind "tool" (Google) asks for the address to sign in with; "command" (Microsoft) shows a code.
  signin: { provider: string; kind: "command" | "tool"; confirms: string | null; accounts_vars: string[] } | null;
  // An OAuth client file (Google): uploaded in Settings, built into the app, or neither.
  client_file: { name: string; source: "uploaded" | "built-in" | null } | null;
  unsigned_accounts?: string[];  // listed but not signed in: agents skip them
}
export interface SigninState {
  connector: string; status: "none" | "starting" | "waiting" | "finishing" | "done" | "failed" | "cancelled";
  provider?: string; url?: string; code?: string; message?: string; account?: string; error?: string;
}
export interface SignedInAccount { id: string; username: string; name: string; selected: boolean }
export interface Profile {
  name: string; role: string; organization_context: string; goals: string[]; working_preferences: string[]; domain_notes: string;
}
export interface Budgets {
  enabled: boolean; max_run_cost_usd: number; max_run_tokens: number; max_chat_cost_usd: number; max_chat_tokens: number;
  max_steps: number; max_tool_calls_per_step: number;
  max_tool_result_chars: number; max_context_fraction: number;
}
export interface GeneralEdit {
  budgets?: Budgets; persona_chat?: boolean; persona_exports?: boolean; store_prompts?: boolean;
  default_data_class?: string; cloud_allowed?: Record<string, boolean>; tiers?: Record<string, string[]>;
  agent_models?: Record<string, string | null>; offline_model?: string; default_model?: string; fallback_model?: string;
}
export interface ChatDelegation { agent: string; question: string; answer: string; model: string | null; error?: string | null }
export interface ChatMsg {
  role: "user" | "assistant"; content: string; at: string; agent?: string; model?: string;
  files?: { id: string; name: string }[]; delegations?: ChatDelegation[]; warnings?: string[];
  suggested_playbook?: { id: string; code: string; name: string } | null; tokens?: number; cost_usd?: number; seconds?: number;
  // set when the person asked for the answer as a file; saved_to is where the app wrote it (null: not saved)
  file?: { format: "md" | "html"; name: string; saved_to?: string | null; source?: number };
  tool_calls?: { connector?: string; tool: string; arguments: Record<string, unknown>; error: boolean }[];
}
export interface ChatSummary {
  id: string; agent_id: string; data_class: string; title: string; tokens: number; cost_usd: number;
  created_at: string; updated_at: string; messages: number;
}
export interface ChatDetail extends Omit<ChatSummary, "messages"> { messages: ChatMsg[] }
export interface AgentPack {
  installed: boolean; folder: string | null; agents_total: number; agents_with_instructions: number;
  built_in: number; imported: number;  // agents whose instructions come from the pack built into the app / one imported here
}
export interface Overview {
  version: string; agent_pack: AgentPack;
  desks: Desk[]; agents: AgentCard[]; playbooks: PlaybookCard[]; providers: ProviderInfo[]; tiers: Record<string, string[]>;
  connectors: ConnectorInfo[]; data_classes: Record<string, string[]>; default_data_class: string; kill_switch: boolean; offline: boolean;
  offline_override: boolean | null; endpoints: ModelEndpoint[];
  budgets: Budgets; persona: { chat: boolean; exports: boolean }; profile_configured: boolean;
  profile: Profile; profile_saved_in_app: boolean; store_prompts: boolean; model_refs: string[]; general_edited: string[];
  outputs_dir: string | null;
  outputs: { path: string | null; source: "app" | "file" | "default"; default: string; shared_with_local_files: string[] };  // readable copies of chats and deliverables; null when switched off
  agent_models: Record<string, string>; offline_model: string | null; offline_default: string | null;
  default_model: string | null; fallback_model: string | null;
  in_use: Record<string, string | null>; agent_in_use: Record<string, string | null>;  // used right now (default data class)
  agent_overrides: Record<string, string[]>;
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
  agent: (id: string) => call<AgentCard & { skills_detail: { id: string; description: string }[] }>(`/api/agents/${id}`),
  route: (text: string, data_class?: string) => call<RouteResult>("/api/route", { method: "POST", body: JSON.stringify({ text, data_class }) }),
  upload: (file: File) => { const fd = new FormData(); fd.append("file", file); return call<{ id: string; name: string; chars: number }>("/api/files", { method: "POST", body: fd }); },
  startRun: (playbook_id: string, inputs: Record<string, unknown>, data_class: string, options: Record<string, unknown>) =>
    call<{ id: string }>("/api/runs", { method: "POST", body: JSON.stringify({ playbook_id, inputs, data_class, options }) }),
  runs: () => call<RunSummary[]>("/api/runs"),
  run: (id: string) => call<RunDetail>(`/api/runs/${id}`),
  cancel: (id: string) => call<RunDetail>(`/api/runs/${id}/cancel`, { method: "POST" }),
  resume: (id: string) => call<{ id: string }>(`/api/runs/${id}/resume`, { method: "POST" }),
  approvals: (status = "pending") => call<Approval[]>(`/api/approvals?status=${status}`),
  answer: (id: string, body: { answers: string[]; skip: boolean; by: string }) =>
    call<Approval>(`/api/approvals/${id}/answer`, { method: "POST", body: JSON.stringify(body) }),
  decide: (id: string, body: { decision: "approved" | "rejected"; decided_by: string; note: string; edited?: string | null }) =>
    call<Approval>(`/api/approvals/${id}`, { method: "POST", body: JSON.stringify(body) }),
  testProvider: (name: string) => call<{ ok: boolean; detail?: string; model?: string; latency_ms?: number; reply?: string }>(`/api/providers/${name}/test`, { method: "POST" }),
  connect: (id: string) => call<{ id: string; tools: { name: string; allowed: boolean; reason: string; description: string }[] }>(`/api/connectors/${id}/connect`, { method: "POST" }),
  setOffline: (on: boolean | null) => call<{ on: boolean; override: boolean | null; default: boolean }>("/api/admin/offline", { method: "POST", body: JSON.stringify({ on, by: "ui" }) }),
  discover: (q: { base_url?: string; provider?: string; api_key?: string }) =>
    call<{ base_url: string; locality: "local" | "cloud"; models: string[] }>("/api/endpoints/discover", { method: "POST", body: JSON.stringify(q) }),
  updateProvider: (name: string, edit: ProviderEdit) =>
    call<ProviderInfo>(`/api/providers/${encodeURIComponent(name)}`, { method: "PUT", body: JSON.stringify(edit) }),
  resetProvider: (name: string) => call<ProviderInfo>(`/api/providers/${encodeURIComponent(name)}/override`, { method: "DELETE" }),
  deleteRun: (id: string) => call<{ deleted: number }>(`/api/runs/${id}`, { method: "DELETE" }),
  deleteDemoRuns: () => call<{ deleted: number }>("/api/runs?demo=true", { method: "DELETE" }),
  saveEndpoint: (ep: ModelEndpoint) => call<ModelEndpoint>("/api/endpoints", { method: "POST", body: JSON.stringify(ep) }),
  deleteEndpoint: (id: string) => call<{ deleted: string }>(`/api/endpoints/${encodeURIComponent(id)}`, { method: "DELETE" }),
  updateConnector: (id: string, edit: { enabled?: boolean; values?: Record<string, string>; clear?: string[]; folders?: string[] }) =>
    call<ConnectorInfo>(`/api/connectors/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(edit) }),
  resetConnector: (id: string) => call<ConnectorInfo>(`/api/connectors/${encodeURIComponent(id)}/settings`, { method: "DELETE" }),
  signinState: (id: string) => call<SigninState>(`/api/connectors/${encodeURIComponent(id)}/signin`),
  signinStart: (id: string, account?: string) =>
    call<SigninState>(`/api/connectors/${encodeURIComponent(id)}/signin`, { method: "POST", body: JSON.stringify({ account: account || null }) }),
  uploadClientFile: (id: string, file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return call<ConnectorInfo>(`/api/connectors/${encodeURIComponent(id)}/client-file`, { method: "POST", body: fd });
  },
  importAgentPack: (files: File[]) => {
    const fd = new FormData(); files.forEach((f) => fd.append("files", f));
    return call<AgentPack & { imported_files: string[]; skipped: string[] }>("/api/agent-pack", { method: "POST", body: fd });
  },
  removeClientFile: (id: string) => call<ConnectorInfo>(`/api/connectors/${encodeURIComponent(id)}/client-file`, { method: "DELETE" }),
  useSignedIn: (id: string) => call<{ accounts: SignedInAccount[] }>(`/api/connectors/${encodeURIComponent(id)}/accounts/use`, { method: "POST" }),
  signinCancel: (id: string) => call<SigninState>(`/api/connectors/${encodeURIComponent(id)}/signin`, { method: "DELETE" }),
  signedInAccounts: (id: string) => call<{ accounts: SignedInAccount[] }>(`/api/connectors/${encodeURIComponent(id)}/accounts`),
  signOut: (id: string, accountId: string) =>
    call<{ accounts: SignedInAccount[] }>(`/api/connectors/${encodeURIComponent(id)}/accounts/${encodeURIComponent(accountId)}`, { method: "DELETE" }),
  saveGeneral: (edit: GeneralEdit) => call<Overview>("/api/settings/general", { method: "PUT", body: JSON.stringify(edit) }),
  saveAnswer: (chatId: string, index: number, format: "md" | "html") =>
    call<{ name: string; path: string }>(`/api/chats/${chatId}/messages/${index}/save?format=${format}`, { method: "POST" }),
  saveOutputs: (edit: { path?: string; off?: boolean }) =>
    call<Overview>("/api/settings/outputs", { method: "PUT", body: JSON.stringify(edit) }),
  resetGeneral: (part: "tiers" | "budgets" | "all") => call<Overview>(`/api/settings/general/${part}`, { method: "DELETE" }),
  saveProfile: (p: Profile) => call<Profile>("/api/settings/profile", { method: "PUT", body: JSON.stringify(p) }),
  resetProfile: () => call<Profile>("/api/settings/profile", { method: "DELETE" }),
  chats: () => call<ChatSummary[]>("/api/chats"),
  chat: (id: string) => call<ChatDetail>(`/api/chats/${id}`),
  startChat: (agent_id: string, data_class?: string) => call<ChatDetail>("/api/chats", { method: "POST", body: JSON.stringify({ agent_id, data_class }) }),
  sendChat: (id: string, content: string, files: string[] = []) =>
    call<ChatMsg>(`/api/chats/${id}/messages`, { method: "POST", body: JSON.stringify({ content, files }) }),
  deleteChat: (id: string) => call<{ deleted: number }>(`/api/chats/${id}`, { method: "DELETE" }),
  killSwitch: (on: boolean) => call<{ on: boolean }>("/api/admin/kill-switch", { method: "POST", body: JSON.stringify({ on, by: "ui" }) }),
  exportUrl: (id: string, format: "md" | "html") => `/api/runs/${id}/export?format=${format}`,
};

export type ExportResult = { saved: true; name: string; path: string } | { saved: false; name: string; why: string };

/** Export into the outputs folder and say where; when that is not possible (folder off, Restricted), download instead. */
async function exportOr(save: () => Promise<{ name: string; path: string }>, fallback: () => Promise<string>): Promise<ExportResult> {
  try {
    const r = await save();
    return { saved: true, name: r.name, path: r.path };
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 409) throw e;
    return { saved: false, name: await fallback(), why: e.message };
  }
}

export function exportRun(id: string, format: "md" | "html") {
  return exportOr(() => call<{ name: string; path: string }>(`/api/runs/${id}/export/save?format=${format}`, { method: "POST" }),
    () => download(id, format));
}

export function exportAnswer(chatId: string, index: number, format: "md" | "html") {
  return exportOr(() => api.saveAnswer(chatId, index, format), () => downloadAnswer(chatId, index, format));
}

export async function download(id: string, format: "md" | "html") {
  return downloadFrom(api.exportUrl(id, format), format);
}

/** One chat answer as a Markdown or HTML file. */
export async function downloadAnswer(chatId: string, index: number, format: "md" | "html") {
  return downloadFrom(`/api/chats/${chatId}/messages/${index}/export?format=${format}`, format);
}

async function downloadFrom(url: string, format: "md" | "html"): Promise<string> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { headers });
  if (!res.ok) throw new ApiError(res.status, "export failed");
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1] || `deliverable.${format}`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  return name;
}
