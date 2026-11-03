import { useState } from "react";
import { api, type ModelEndpoint, type Overview } from "../api";
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

      <section className="card stack" aria-labelledby="mode-h">
        <div className="row">
          <div className="grow stack-sm">
            <h2 id="mode-h">Connection mode</h2>
            <p className="muted small measure">
              {ov.offline
                ? "Offline: cloud providers and internet connectors are off. Runs use local models (this computer, or endpoints on your network such as a phone) and local files."
                : "Online: every configured provider and connector is available, subject to each run's data class."}
              {ov.offline_override === null ? " Following the config file default." : " Set here; overrides the config file."}
            </p>
          </div>
          <button className={ov.offline ? "primary" : ""} onClick={async () => { try { await api.setOffline(!ov.offline); onChange(); } catch (e) { setError(e); } }}>
            {ov.offline ? "Go online" : "Go offline"}
          </button>
          {ov.offline_override !== null && (
            <button className="ghost" onClick={async () => { try { await api.setOffline(null); onChange(); } catch (e) { setError(e); } }}>Use config default</button>
          )}
        </div>
      </section>

      <EndpointsPanel ov={ov} onChange={onChange} />

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

const TIER_HELP: Record<string, string> = {
  router: "picks the playbook",
  specialist: "most agent steps",
  synthesis: "combines results",
  review: "independent checks",
};

/** Connect to models served elsewhere: a phone, a laptop, a GPU box. The suite never loads or configures them. */
function EndpointsPanel({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const blank: ModelEndpoint = { id: "", name: "", base_url: "", model: "", context_tokens: 4096, max_output_tokens: 1024, tools: false, use_for: ["router", "specialist"] };
  const [draft, setDraft] = useState<ModelEndpoint>(blank);
  const [models, setModels] = useState<string[] | null>(null);
  const [locality, setLocality] = useState<"local" | "cloud" | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof ModelEndpoint, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));

  async function find() {
    setBusy("find"); setError(null); setModels(null);
    try {
      const r = await api.discover(draft.base_url);
      setModels(r.models); setLocality(r.locality);
      setDraft((d) => ({ ...d, base_url: r.base_url, model: r.models[0] || "" }));
    } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy("save"); setError(null);
    try {
      const id = draft.id || draft.name || draft.model;
      await api.saveEndpoint({ ...draft, id, name: draft.name || draft.model });
      setDraft(blank); setModels(null); setLocality(null); onChange();
    } catch (err) { setError(err); } finally { setBusy(""); }
  }
  async function remove(id: string) {
    try { await api.deleteEndpoint(id); onChange(); } catch (e) { setError(e); }
  }

  return (
    <section className="stack" aria-labelledby="ep-h">
      <div className="stack-sm">
        <h2 id="ep-h">Model endpoints</h2>
        <p className="muted small measure">
          Connect to a model already running somewhere you control, such as a 2B–4B model served by an app on your phone, or a
          laptop running Ollama or LM Studio. Any OpenAI-compatible server works. The suite only connects; load and configure
          the model on the device that hosts it, and make it listen on your network, not only on that device.
        </p>
      </div>

      {ov.endpoints.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Endpoint</th><th>Where</th><th>Model</th><th>Used for</th><th></th></tr></thead>
            <tbody>
              {ov.endpoints.map((e) => {
                const prov = ov.providers.find((p) => p.name === e.provider);
                return (
                  <tr key={e.id}>
                    <td><strong>{e.name}</strong><div className="muted small"><code>{e.base_url}</code></div></td>
                    <td><span className={`tag ${e.locality === "local" ? "" : "outline"}`}>{e.locality}</span>{prov && !prov.available && <div className="muted small">{prov.reason}</div>}</td>
                    <td className="small"><code>{e.model}</code><div className="muted">{(e.context_tokens / 1000).toFixed(0)}k context{e.tools ? " · tools" : ""}</div></td>
                    <td className="small">{e.use_for.join(", ")}</td>
                    <td className="row">
                      <TestButton name={e.provider || ""} />
                      <button className="ghost" onClick={() => remove(e.id)}>Remove</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <form className="card stack endpoint-form" onSubmit={save}>
        <span className="label">Add an endpoint</span>
        <div className="ep-row">
          <div className="field grow">
            <label htmlFor="ep-url">Address</label>
            <input id="ep-url" value={draft.base_url} onChange={(e) => { set("base_url", e.target.value); setModels(null); }}
              placeholder="http://192.168.1.42:8080" inputMode="url" autoComplete="off" required />
          </div>
          <button type="button" onClick={find} disabled={!draft.base_url || busy === "find"}>{busy === "find" ? "Connecting…" : "Find models"}</button>
        </div>
        {locality && (
          <p className={`note small ${locality === "cloud" ? "warn" : ""}`}>
            {locality === "local"
              ? "Local: this address is on your own network, so restricted runs may use it."
              : "Cloud: this address is not on a private network, so restricted runs will not use it."}
          </p>
        )}
        {models && (
          <>
            <div className="ep-grid">
              <div className="field">
                <label htmlFor="ep-model">Model</label>
                <select id="ep-model" value={draft.model} onChange={(e) => set("model", e.target.value)} required>
                  {models.length === 0 && <option value="">No models reported</option>}
                  {models.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ep-name">Name</label>
                <input id="ep-name" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="My phone" />
              </div>
              <div className="field">
                <label htmlFor="ep-ctx">Context window (tokens)</label>
                <input id="ep-ctx" type="number" min={1024} step={1024} value={draft.context_tokens} onChange={(e) => set("context_tokens", Number(e.target.value))} />
                <span className="help">Match what the server is set to. Small phone models often run at 4,096 or 8,192.</span>
              </div>
              <div className="field">
                <label htmlFor="ep-out">Max answer length (tokens)</label>
                <input id="ep-out" type="number" min={128} step={128} value={draft.max_output_tokens} onChange={(e) => set("max_output_tokens", Number(e.target.value))} />
              </div>
            </div>
            <div className="field">
              <span className="label">Use for</span>
              <div className="checks" role="group" aria-label="Use for">
                {Object.entries(TIER_HELP).map(([t, help]) => (
                  <label key={t} className="check">
                    <input type="checkbox" checked={draft.use_for.includes(t)}
                      onChange={(e) => set("use_for", e.target.checked ? [...draft.use_for, t] : draft.use_for.filter((x) => x !== t))} />
                    {t} <span className="muted small">· {help}</span>
                  </label>
                ))}
              </div>
              <span className="help">Ticked tiers try this endpoint first. Every other tier keeps it as a local fallback, used before the demo provider when nothing else is allowed or reachable.</span>
            </div>
            <label className="check">
              <input type="checkbox" checked={draft.tools} onChange={(e) => set("tools", e.target.checked)} />
              The model supports tool calling (lets agents use connectors and calculators directly)
            </label>
            <p className="help">Small models give shorter, less reliable answers on long playbooks. Prompts are trimmed to fit their context, and the run notes say what was cut.</p>
            <button className="primary" type="submit" disabled={!draft.model || busy === "save"}>{busy === "save" ? "Saving…" : "Add endpoint"}</button>
          </>
        )}
        <ErrorNote error={error} />
      </form>
    </section>
  );
}

function TestButton({ name }: { name: string }) {
  const [res, setRes] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <span className="stack-sm">
      <button onClick={async () => {
        setBusy(true);
        try { const r = await api.testProvider(name); setRes(r.ok ? `OK · ${r.latency_ms} ms` : `Failed: ${r.detail}`); }
        catch (e) { setRes(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
      }} disabled={busy || !name}>{busy ? "Testing…" : "Test"}</button>
      {res && <span className="muted small">{res}</span>}
    </span>
  );
}
