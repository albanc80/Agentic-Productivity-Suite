import { useState } from "react";
import { api, type Overview } from "../api";
import { ErrorNote, Pill } from "../ui";

export default function SettingsPage({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [tests, setTests] = useState<Record<string, string>>({});
  const [tools, setTools] = useState<Record<string, { name: string; allowed: boolean; reason: string }[]>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");

  async function test(name: string) {
    setBusy(name);
    try {
      const r = await api.testProvider(name);
      setTests((s) => ({ ...s, [name]: r.ok ? `OK · ${r.model} · ${r.latency_ms} ms` : `Failed: ${r.detail}` }));
    } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function connect(id: string) {
    setBusy(id); setError(null);
    try { const r = await api.connect(id); setTools((s) => ({ ...s, [id]: r.tools })); onChange(); }
    catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function kill(on: boolean) {
    try { await api.killSwitch(on); onChange(); } catch (e) { setError(e); }
  }

  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Settings</h1>
        <p className="muted measure">Edit <code>config/suite.yaml</code> and <code>config/connectors.yaml</code> to change providers, model chains and connectors; credentials stay in environment variables. This page shows the live state and lets you test it.</p>
      </header>
      <ErrorNote error={error} />

      <section className="card stack kill">
        <div className="row">
          <div className="grow stack-sm">
            <h2>Kill switch</h2>
            <p className="muted small">Stops every running run immediately and blocks new runs until turned off.</p>
          </div>
          {ov.kill_switch
            ? <button className="primary" onClick={() => kill(false)}>Turn off</button>
            : <button className="danger" onClick={() => kill(true)}>Stop everything</button>}
        </div>
      </section>

      <section className="stack">
        <h2>Model providers</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Provider</th><th>Where</th><th>Status</th><th>Models</th><th></th></tr></thead>
            <tbody>
              {ov.providers.map((p) => (
                <tr key={p.name}>
                  <td><strong>{p.name}</strong><div className="muted small">{p.type}{p.base_url ? ` · ${p.base_url}` : ""}</div>{p.note && <div className="help">{p.note}</div>}</td>
                  <td><span className={`tag ${p.locality === "local" ? "" : "outline"}`}>{p.locality}</span></td>
                  <td><Pill value={p.available ? "ready" : "unconfigured"} /><div className="muted small">{p.reason}</div></td>
                  <td className="small">{p.models.map((m) => <div key={m.ref}><code>{m.ref.split("/").slice(1).join("/")}</code> <span className="muted">{(m.context_tokens / 1000).toFixed(0)}k{m.tools ? " · tools" : ""}{m.price_in_per_mtok ? ` · $${m.price_in_per_mtok}/$${m.price_out_per_mtok}` : ""}</span></div>)}</td>
                  <td className="small">
                    {p.available && <button onClick={() => test(p.name)} disabled={busy === p.name}>{busy === p.name ? "Testing…" : "Test"}</button>}
                    {tests[p.name] && <div className="muted">{tests[p.name]}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card stack-sm">
          <span className="label">Fallback chains by tier (first available model allowed for the run's data class wins)</span>
          {Object.entries(ov.tiers).map(([tier, chain]) => (
            <div key={tier} className="chain"><strong>{tier}</strong>{chain.map((c, i) => <span key={c}>{i > 0 && <span className="muted"> → </span>}<code>{c}</code></span>)}</div>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2>Data classes</h2>
        <div className="grid four">
          {Object.entries(ov.data_classes).map(([k, v]) => (
            <div key={k} className="card small"><strong>{k}</strong><div className="muted">may reach: {v.join(" + ")}</div></div>
          ))}
        </div>
        <p className="help">You are responsible for the credentials and data you use. Mark sensitive runs "restricted" to keep them on local models.</p>
      </section>

      <section className="stack">
        <h2>Connectors (MCP, read-only)</h2>
        <p className="muted small measure">The suite exposes only read-only tools to agents: allow-listed, declared read-only, or named like a query. Write tools are hidden and refused.</p>
        <div className="grid two">
          {ov.connectors.map((c) => (
            <article key={c.id} className="card stack-sm connector">
              <div className="row"><strong className="grow">{c.name}</strong><Pill value={c.status} /></div>
              <span className="muted small">{c.description}</span>
              {c.status === "unconfigured" && <span className="small">Set: {c.required_env.map((e) => <code key={e}>{e} </code>)}</span>}
              {c.status === "error" && c.error && <span className="note bad small">{c.error}</span>}
              <details className="small"><summary>Setup</summary><p>{c.setup}</p>{c.verify && <p className="muted">Verify: {c.verify}</p>}</details>
              {c.status !== "unconfigured" && c.status !== "disabled" && (
                <button onClick={() => connect(c.id)} disabled={busy === c.id}>{busy === c.id ? "Connecting…" : "Connect and list tools"}</button>
              )}
              {(tools[c.id] || c.tools).length > 0 && (
                <ul className="plain small tools">
                  {(tools[c.id] || c.tools).map((t) => (
                    <li key={t.name}><code>{t.name}</code> {t.allowed ? <span className="pill ok">allowed</span> : <span className="pill neutral" title={t.reason}>blocked</span>}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2>Budgets and voice</h2>
        <div className="grid four">
          <div className="card small"><span className="label">Max cost per run</span><strong>${ov.budgets.max_run_cost_usd}</strong></div>
          <div className="card small"><span className="label">Max tokens per run</span><strong>{ov.budgets.max_run_tokens?.toLocaleString()}</strong></div>
          <div className="card small"><span className="label">Tool calls per step</span><strong>{ov.budgets.max_tool_calls_per_step}</strong></div>
          <div className="card small"><span className="label">Personas</span><strong>chat {ov.persona.chat ? "on" : "off"} · documents {ov.persona.exports ? "on" : "off"}</strong></div>
        </div>
        {!ov.profile_configured && <p className="note small">Using the example user profile. Copy <code>config/profile.example.yaml</code> to <code>config/profile.yaml</code> to describe yourself.</p>}
        {ov.warnings.length > 0 && <ul className="small warn-list">{ov.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      </section>
    </div>
  );
}
