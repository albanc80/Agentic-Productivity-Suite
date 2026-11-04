import { useEffect, useState } from "react";
import { api, type Overview } from "../api";
import { ErrorNote, go } from "../ui";

type Detail = Awaited<ReturnType<typeof api.agent>>;

export default function Agents({ ov, agentId, onChange }: { ov: Overview; agentId: string; onChange: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    setDetail(null);
    if (agentId) api.agent(agentId).then(setDetail).catch(setError);
  }, [agentId]);

  if (agentId) {
    if (error) return <ErrorNote error={error} />;
    if (!detail) return <p className="muted">Loading agent…</p>;
    return (
      <div className="stack-lg">
        <header className="stack-sm">
          <a href="#/agents" className="small">← Agents</a>
          <span className="code">{ov.desks.find((d) => d.id === detail.desk)?.name} · {detail.callsign}</span>
          <h1>{detail.name}</h1>
          <p className="muted measure">{detail.summary}</p>
          <AgentModel ov={ov} agentId={detail.id} tier={detail.default_tier} onChange={onChange} />
          <div className="row-tight">
            <button className="primary" onClick={async () => {
              try { const c = await api.startChat(detail.id); go(`/chat/${c.id}`); } catch (e) { setError(e); }
            }}>Chat with {detail.name}</button>
          </div>
          <div className="tags">
            <span className="tag">Default tier: {detail.default_tier}</span>
            {detail.safety_critical && <span className="tag danger">Safety-critical · advisory only</span>}
            {detail.tools.map((t) => <span key={t} className="tag outline">Tool: {t}</span>)}
          </div>
        </header>
        <div className="run-grid">
          <section className="stack">
            <h2>What this agent does</h2>
            <ul className="card doc caps">
              {detail.capabilities.map((c) => <li key={c}>{c}</li>)}
            </ul>
            {Object.keys(detail.modes).length > 0 && (
              <>
                <h2>Modes</h2>
                <ul className="plain stack-sm">
                  <li className="card small"><strong>{detail.default_mode || "standard"}</strong> <span className="tag">default</span>
                    <div className="muted">{detail.summary}</div></li>
                  {Object.entries(detail.modes).map(([k, v]) => (
                    <li key={k} className="card small"><strong>{k}</strong><div className="muted">{v}</div></li>
                  ))}
                </ul>
              </>
            )}
          </section>
          <aside className="stack">
            <h2>Skills</h2>
            <ul className="plain stack-sm">
              {detail.skills_detail.map((s) => (
                <li key={s.id} className="card small">
                  <strong>{s.id}</strong>{detail.core_skills.includes(s.id) ? <span className="tag">always loaded</span> : <span className="tag outline">on demand</span>}
                  <div className="muted">{s.description}</div>
                </li>
              ))}
              {detail.skills_detail.length === 0 && <li className="muted small">No attached skills.</li>}
            </ul>
          </aside>
        </div>
      </div>
    );
  }

  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Agents</h1>
        <p className="muted measure">{ov.agents.length} specialists in {ov.desks.length} desks, compiled from your agent configurations into a platform-neutral registry. Playbooks call desks and agents by role.</p>
      </header>
      {ov.desks.map((d) => (
        <section key={d.id} className="stack">
          <div className="stack-sm">
            <h2>{d.name}</h2>
            <p className="muted small">{d.summary}</p>
          </div>
          <div className="grid cards">
            {d.members.map((id) => {
              const a = ov.agents.find((x) => x.id === id)!;
              return (
                <a key={id} className="card pb" href={`#/agents/${id}`}>
                  <span className="code">{a.callsign}{d.lead === id ? " · lead" : ""}</span>
                  <strong>{a.name}</strong>
                  <span className="muted">{a.summary}</span>
                  <span className="meta">{a.core_skills.length + a.skills.length} skills{Object.keys(a.modes).length ? ` · ${Object.keys(a.modes).length + 1} modes` : ""}{a.safety_critical ? " · safety-critical" : ""}{!ov.offline && ov.agent_models[id] ? ` · ${ov.agent_models[id]}` : ""}</span>
                </a>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Online: pick the model this agent uses first (its tier chain stays as fallback). Offline: every agent uses the offline model. */
function AgentModel({ ov, agentId, tier, onChange }: { ov: Overview; agentId: string; tier: string; onChange: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const ready = new Set(ov.providers.filter((p) => p.available || p.offline_paused).map((p) => p.name));
  const auto = (ov.tiers[tier] || []).find((r) => ov.providers.some((p) => p.available && p.name === r.split("/")[0]));
  if (ov.offline) {
    return <p className="note small">Offline: this agent uses <code>{ov.offline_default || "no local model"}</code>, like every agent. Change it in Settings → Models.{ov.agent_models[agentId] ? ` Your choice for online use (${ov.agent_models[agentId]}) is kept.` : ""}</p>;
  }
  return (
    <div className="field narrow-field">
      <label htmlFor="agent-model">Model for this agent</label>
      <select id="agent-model" value={ov.agent_models[agentId] || ""}
        onChange={async (e) => { try { await api.saveGeneral({ agent_models: { [agentId]: e.target.value || null } }); onChange(); } catch (err) { setError(err); } }}>
        <option value="">Automatic ({tier} order{auto ? `: now ${auto}` : ""})</option>
        {ov.model_refs.map((r) => <option key={r} value={r}>{r}{ready.has(r.split("/")[0]) ? "" : " (not ready)"}</option>)}
      </select>
      <span className="help">Tried first in chats and playbook steps; if it fails or the data class does not allow it, the {tier} order is used.</span>
      <ErrorNote error={error} />
    </div>
  );
}
