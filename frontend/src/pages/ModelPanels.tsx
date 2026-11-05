import { useState } from "react";
import { api, type AgentCard, type Overview } from "../api";
import { ErrorNote } from "../ui";

const TIER_LABEL: Record<string, string> = {
  router: "Choosing the playbook", specialist: "Agent steps and chats", synthesis: "Combining results", review: "Independent reviews",
};

/** Every model of every provider that is switched on, local and cloud, with whether it is ready now. */
function modelOptions(ov: Overview) {
  return ov.providers.filter((p) => p.enabled).flatMap((p) => p.models.map((m) => ({
    ref: m.ref, local: p.locality === "local", ready: p.available,
    label: `${m.ref}${p.locality === "local" ? " · local" : ""}${p.available ? "" : " · not ready"}`,
  })));
}

/** What a model is for right now: default, fallback, used by some kind of work or agent, or not used. */
export function modelRole(ov: Overview, ref: string): { text: string; tone: string } {
  if (ov.default_model === ref) return { text: "Default", tone: "ok" };
  if (ov.fallback_model === ref) return { text: "Fallback", tone: "warn" };
  const tiers = Object.entries(ov.in_use).filter(([, r]) => r === ref).map(([t]) => t);
  const agents = Object.entries(ov.agent_in_use).filter(([, r]) => r === ref).length;
  if (tiers.length || agents) return { text: `In use${agents ? ` · ${agents} agent${agents > 1 ? "s" : ""}` : ""}`, tone: "ok" };
  return { text: "Not used", tone: "neutral" };
}

export function ModelsInUse({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const opts = modelOptions(ov);
  async function set(edit: { default_model?: string; fallback_model?: string }) {
    setBusy(true); setError(null);
    try { await api.saveGeneral(edit); onChange(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const pick = (id: string, label: string, value: string | null, other: string | null, key: "default_model" | "fallback_model", help: string) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value || ""} disabled={busy} onChange={(e) => set({ [key]: e.target.value })}>
        <option value="">None: follow the fallback order below</option>
        {opts.filter((o) => o.ref !== other).map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}
      </select>
      <span className="help">{help}</span>
    </div>
  );
  return (
    <section className="stack" aria-labelledby="inuse-h">
      <div className="stack-sm">
        <h2 id="inuse-h">Models in use</h2>
        <p className="muted small measure">Choose the model every agent uses by default and the one to try when it fails or is not ready; both can be local or cloud models from any provider that is switched on. An agent with its own model (Model per agent, below) uses that first. Restricted data only ever reaches local models.{ov.offline ? " Offline, the offline model below goes first." : ""}</p>
      </div>
      <div className="card stack">
        <div className="pair-grid">
          {pick("m-default", "Default model", ov.default_model, ov.fallback_model, "default_model", "Tried first for every kind of work.")}
          {pick("m-fallback", "Fallback model", ov.fallback_model, ov.default_model, "fallback_model", "Tried next when the default fails, is switched off or is not ready.")}
        </div>
        {opts.length === 0 && <p className="small note">No provider is switched on yet. Switch one on below and add a model.</p>}
        <div className="stack-xs">
          <strong className="small">Used right now ({ov.default_data_class} data)</strong>
          <ul className="plain in-use-list small">
            {Object.entries(ov.in_use).map(([t, ref]) => (
              <li key={t}><span className="muted">{TIER_LABEL[t] || t}</span>{ref ? <code>{ref}</code> : <span className="provider-reason">no model ready: this work stops</span>}</li>
            ))}
          </ul>
        </div>
        <ErrorNote error={error} />
      </div>
    </section>
  );
}

const HEAVY = (a: AgentCard) => a.default_tier === "synthesis" || a.default_tier === "review" || a.safety_critical;

export function AgentModels({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [heavy, setHeavy] = useState("");
  const [light, setLight] = useState("");
  const opts = modelOptions(ov);
  const desks = ov.desks.map((d) => ({ d, agents: ov.agents.filter((a) => a.desk === d.id) })).filter((x) => x.agents.length);
  async function save(map: Record<string, string | null>) {
    setBusy(true); setError(null);
    try { await api.saveGeneral({ agent_models: map }); onChange(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  function assign() {
    const map: Record<string, string | null> = {};
    for (const a of ov.agents) {
      const ref = HEAVY(a) ? heavy : light;
      if (ref) map[a.id] = ref;
    }
    save(map);
  }
  if (ov.offline) {
    return <p className="note small">Offline, every agent uses the offline model. Your choices per agent are kept for when you go online.</p>;
  }
  return (
    <section className="stack" aria-labelledby="agentm-h">
      <div className="stack-sm">
        <h2 id="agentm-h">Model per agent</h2>
        <p className="muted small measure">Give each agent a model that fits its work to save tokens and cost: a small or local model for everyday drafting and analysis, a stronger one for agents that combine results, review others' work or handle safety-critical topics. An agent without its own model uses the default above. Its choice is tried first; the default and fallback stay behind it.</p>
      </div>
      <div className="card stack">
        <strong className="small">Quick assign by workload</strong>
        <div className="pair-grid">
          <div className="field">
            <label htmlFor="am-heavy">Reasoning-heavy agents ({ov.agents.filter(HEAVY).length})</label>
            <select id="am-heavy" value={heavy} onChange={(e) => setHeavy(e.target.value)}>
              <option value="">Leave as they are</option>
              {opts.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}
            </select>
            <span className="help">Agents that combine results or review others' work, and safety-critical agents.</span>
          </div>
          <div className="field">
            <label htmlFor="am-light">Everyday agents ({ov.agents.filter((a) => !HEAVY(a)).length})</label>
            <select id="am-light" value={light} onChange={(e) => setLight(e.target.value)}>
              <option value="">Leave as they are</option>
              {opts.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}
            </select>
            <span className="help">Specialists that draft, analyse and answer most chats.</span>
          </div>
        </div>
        <div className="row-tight">
          <button className="primary" disabled={busy || (!heavy && !light)} onClick={assign}>Assign</button>
          {Object.keys(ov.agent_models).length > 0 && (
            <button className="ghost grow-left" disabled={busy}
              onClick={() => save(Object.fromEntries(Object.keys(ov.agent_models).map((k) => [k, null])))}>Clear every agent's model</button>
          )}
        </div>
      </div>
      <ErrorNote error={error} />
      {desks.map(({ d, agents }) => (
        <div key={d.id} className="card stack-sm">
          <strong>{d.name}</strong>
          <div className="agent-model-list">
            {agents.map((a) => (
              <div key={a.id} className="agent-model-row">
                <div className="stack-xs grow">
                  <span className="row-tight"><strong className="small">{a.name}</strong>
                    <span className="tag outline">{HEAVY(a) ? "reasoning-heavy" : "everyday"}</span></span>
                  <span className="small muted">{a.summary}</span>
                </div>
                <div className="field agent-model-pick">
                  <label className="sr-only" htmlFor={`am-${a.id}`}>Model for {a.name}</label>
                  <select id={`am-${a.id}`} value={ov.agent_models[a.id] || ""} disabled={busy}
                    onChange={(e) => save({ [a.id]: e.target.value || null })}>
                    <option value="">Default model</option>
                    {opts.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}
                  </select>
                  <span className="help">Uses now: {ov.agent_in_use[a.id] ? <code>{ov.agent_in_use[a.id]}</code> : "no model ready"}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
