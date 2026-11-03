import { useEffect, useState } from "react";
import { api, type Overview } from "../api";
import { ErrorNote, Markdown } from "../ui";

type Detail = Awaited<ReturnType<typeof api.agent>>;

export default function Agents({ ov, agentId }: { ov: Overview; agentId: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState("");

  useEffect(() => {
    setDetail(null); setMode("");
    if (agentId) api.agent(agentId).then(setDetail).catch(setError);
  }, [agentId]);

  if (agentId) {
    if (error) return <ErrorNote error={error} />;
    if (!detail) return <p className="muted">Loading agent…</p>;
    const text = mode ? detail.modes_detail[mode]?.instructions : detail.instructions;
    return (
      <div className="stack-lg">
        <header className="stack-sm">
          <a href="#/agents" className="small">← Agents</a>
          <span className="code">{ov.desks.find((d) => d.id === detail.desk)?.name} · {detail.callsign}</span>
          <h1>{detail.name}</h1>
          <p className="muted measure">{detail.summary}</p>
          <div className="tags">
            <span className="tag">Default tier: {detail.default_tier}</span>
            {detail.safety_critical && <span className="tag danger">Safety-critical · advisory only</span>}
            {detail.persona && <span className="tag outline">Persona: {detail.persona}</span>}
            {detail.tools.map((t) => <span key={t} className="tag outline">Tool: {t}</span>)}
            {detail.merged_from.length > 0 && <span className="tag outline">Merged from: {detail.merged_from.join(", ")}</span>}
          </div>
        </header>
        <div className="run-grid">
          <section className="stack">
            <div className="row">
              <h2 className="grow">Instructions</h2>
              {Object.keys(detail.modes).length > 0 && (
                <>
                  <label htmlFor="mode" className="sr-only">Mode</label>
                  <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)}>
                    <option value="">Default{detail.default_mode ? ` (${detail.default_mode})` : ""}</option>
                    {Object.entries(detail.modes).map(([k, v]) => <option key={k} value={k}>{k}: {v}</option>)}
                  </select>
                </>
              )}
            </div>
            <article className="card doc"><Markdown text={text || ""} /></article>
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
            {detail.persona_text && (<><h2>Persona</h2><div className="card small muted">{detail.persona_text}</div></>)}
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
                  <span className="meta">{a.core_skills.length + a.skills.length} skills{Object.keys(a.modes).length ? ` · ${Object.keys(a.modes).length + 1} modes` : ""}{a.safety_critical ? " · safety-critical" : ""}</span>
                </a>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
