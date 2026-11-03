import { useState } from "react";
import { api, type ModelEdit, type ModelEndpoint, type Overview, type ProviderInfo } from "../api";
import { ErrorNote, Pill } from "../ui";

export default function SettingsPage({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [tools, setTools] = useState<Record<string, { name: string; allowed: boolean; reason: string }[]>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");

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
        <p className="muted measure">Switch model providers on or off and edit their address, API key and models here. Changes are saved on this computer and apply immediately; <code>suite.yaml</code> only sets the starting defaults. Connectors are set up in <code>connectors.yaml</code>.</p>
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

      <section className="stack" aria-labelledby="prov-h">
        <div className="stack-sm">
          <h2 id="prov-h">Model providers</h2>
          <p className="muted small measure">Switch a provider on, then use <strong>Edit</strong> to set its address, API key and models. A local server such as LM Studio or Ollama must be running with a model loaded. A provider switched on here is also used as a fallback by every tier.</p>
        </div>
        <div className="stack-sm">
          {ov.providers.filter((p) => !p.endpoint).map((p) => <ProviderRow key={p.name} p={p} onChange={onChange} />)}
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
        {!ov.profile_configured && <p className="note small">No user profile yet. Describe yourself in <code>profile.yaml</code> (in <code>.productivity-suite</code> in your home folder for the desktop app) so agents know your role and goals.</p>}
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
      const r = await api.discover({ base_url: draft.base_url, api_key: draft.api_key || undefined });
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
                    <td><strong>{e.name}</strong><div className="muted small"><code>{e.base_url}</code>{e.has_api_key ? " · API key saved" : ""}</div></td>
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
          <div className="field">
            <label htmlFor="ep-key">API key <span className="muted">(only if the server asks for one)</span></label>
            <input id="ep-key" type="password" value={draft.api_key || ""} onChange={(e) => set("api_key", e.target.value)} autoComplete="off" />
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
              <span className="help">Ticked tiers try this endpoint first. Every other tier keeps it as a fallback, used when nothing earlier in the chain is allowed or reachable.</span>
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

/** On/off switch. A real button with role="switch" so keyboards and screen readers get its state. */
function Switch({ on, label, busy, onToggle }: { on: boolean; label: string; busy?: boolean; onToggle: () => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "is-on" : ""}`} disabled={busy} onClick={onToggle}>
      <span className="switch-track" aria-hidden="true"><span className="switch-knob" /></span>
      <span className="switch-text">{on ? "On" : "Off"}</span>
    </button>
  );
}

const KEY_SOURCE: Record<string, string> = {
  env: "from an environment variable", app: "saved in the app", config: "set in suite.yaml",
};

function ProviderRow({ p, onChange }: { p: ProviderInfo; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [test, setTest] = useState("");

  async function toggle() {
    setBusy("toggle"); setError(null); setTest("");
    try { await api.updateProvider(p.name, { enabled: !p.enabled }); onChange(); }
    catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function runTest() {
    setBusy("test"); setTest("");
    try { const r = await api.testProvider(p.name); setTest(r.ok ? `OK · ${r.model} · ${r.latency_ms} ms` : `Failed: ${r.detail}`); }
    catch (e) { setTest(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  }
  const tone = p.available ? "ok" : p.enabled ? "warn" : "neutral";
  const state = p.available ? "Ready" : p.enabled ? "Needs attention" : "Off";

  return (
    <article className={`card provider ${p.enabled ? "" : "is-off"}`}>
      <div className="provider-head">
        <Switch on={p.enabled} label={`${p.name} ${p.enabled ? "on" : "off"}`} busy={busy === "toggle"} onToggle={toggle} />
        <div className="grow stack-xs">
          <div className="row-tight">
            <strong className="provider-name">{p.name}</strong>
            <span className={`tag ${p.locality === "local" ? "" : "outline"}`}>{p.locality}</span>
            {p.edited_in_app && <span className="tag">edited</span>}
          </div>
          <span className="muted small">{p.base_url || p.type}{p.models.length ? ` · ${p.models.map((m) => m.ref.split("/").slice(1).join("/")).join(", ")}` : " · no models"}</span>
        </div>
        <span className={`pill ${tone}`} title={p.reason}>{state}</span>
        <div className="row-tight">
          {p.available && <button onClick={runTest} disabled={busy === "test"}>{busy === "test" ? "Testing…" : "Test"}</button>}
          <button className={editing ? "ghost" : ""} aria-expanded={editing} onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Edit"}</button>
        </div>
      </div>
      {!p.available && p.reason !== "switched off" && <p className="small provider-reason">{p.reason}</p>}
      {test && <p className={`small ${test.startsWith("OK") ? "ok-text" : "provider-reason"}`}>{test}</p>}
      <ErrorNote error={error} />
      {editing && <ProviderEditor p={p} onDone={() => { setEditing(false); onChange(); }} onChange={onChange} />}
    </article>
  );
}

function ProviderEditor({ p, onDone, onChange }: { p: ProviderInfo; onDone: () => void; onChange: () => void }) {
  const toEdit = (m: ProviderInfo["models"][number]): ModelEdit => ({
    model: m.ref.split("/").slice(1).join("/"), context_tokens: m.context_tokens, max_output_tokens: m.max_output_tokens, tools: m.tools,
  });
  const [baseUrl, setBaseUrl] = useState(p.base_url || "");
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [models, setModels] = useState<ModelEdit[]>(p.models.map(toEdit));
  const [found, setFound] = useState<string[] | null>(null);
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);
  const local = p.locality === "local";
  const isAnthropic = p.type === "anthropic";
  const id = `pe-${p.name}`;

  const has = (m: string) => models.some((x) => x.model === m);
  const add = (m: string) => {
    const name = m.trim();
    if (name && !has(name)) setModels((ms) => [...ms, { model: name, context_tokens: local ? 8192 : 128000, max_output_tokens: local ? 2048 : 8000, tools: false }]);
  };
  const upd = (i: number, k: keyof ModelEdit, v: unknown) => setModels((ms) => ms.map((m, j) => (j === i ? { ...m, [k]: v } : m)));

  async function find() {
    setBusy("find"); setError(null);
    try {
      const r = await api.discover({ provider: p.name, base_url: baseUrl || undefined, api_key: key || undefined });
      setFound(r.models); setBaseUrl(r.base_url);
      if (r.models.length && !models.some((m) => r.models.includes(m.model))) {
        // Replace placeholders that the server does not have with the first model it reports.
        setModels([{ model: r.models[0], context_tokens: local ? 8192 : 128000, max_output_tokens: local ? 2048 : 8000, tools: false }]);
      }
    } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy("save"); setError(null);
    try {
      await api.updateProvider(p.name, {
        base_url: !isAnthropic && baseUrl !== (p.base_url || "") ? baseUrl : undefined,
        api_key: key || undefined, clear_api_key: clearKey && !key, models,
      });
      onDone();
    } catch (err) { setError(err); } finally { setBusy(""); }
  }
  async function reset() {
    setBusy("reset"); setError(null);
    try { await api.resetProvider(p.name); onDone(); } catch (e) { setError(e); onChange(); } finally { setBusy(""); }
  }

  const keyNote = p.api_key_source
    ? `A key is ${KEY_SOURCE[p.api_key_source]}. Leave blank to keep it.`
    : local ? "Leave blank unless the server requires one (for example LM Studio with authentication switched on)." : "Required for this provider.";

  return (
    <form className="provider-edit stack" onSubmit={save}>
      <div className="ep-row">
        {!isAnthropic && (
          <div className="field grow">
            <label htmlFor={`${id}-url`}>Address</label>
            <input id={`${id}-url`} value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); setFound(null); }} inputMode="url" autoComplete="off"
              placeholder={local ? "http://localhost:1234/v1" : "https://api.example.com/v1"} />
          </div>
        )}
        <div className="field grow">
          <label htmlFor={`${id}-key`}>API key</label>
          <input id={`${id}-key`} type="password" value={key} onChange={(e) => { setKey(e.target.value); setClearKey(false); }} autoComplete="off"
            placeholder={p.api_key_source ? "•••••••• (saved)" : ""} />
        </div>
        {!isAnthropic && <button type="button" onClick={find} disabled={busy === "find"}>{busy === "find" ? "Connecting…" : "Find models"}</button>}
      </div>
      <p className="help">{keyNote}{p.api_key_env && p.api_key_source !== "env" ? ` You can also set ${p.api_key_env}.` : ""} A key entered here is saved unencrypted in the app's database on this computer and never shown again; for cloud accounts an environment variable is safer.</p>
      {p.api_key_source === "app" && (
        <label className="check small"><input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} disabled={!!key} /> Remove the saved key</label>
      )}

      <div className="stack-sm">
        <span className="label">Models</span>
        {models.length === 0 && <p className="muted small">No models. Use Find models, or type a model id below.</p>}
        {models.map((m, i) => (
          <div key={m.model} className="model-row">
            <code className="grow">{m.model}</code>
            <label className="field-inline">Context
              <input type="number" min={1024} step={1024} value={m.context_tokens} onChange={(e) => upd(i, "context_tokens", Number(e.target.value))} aria-label={`${m.model} context window in tokens`} />
            </label>
            <label className="field-inline">Max answer
              <input type="number" min={128} step={128} value={m.max_output_tokens} onChange={(e) => upd(i, "max_output_tokens", Number(e.target.value))} aria-label={`${m.model} max answer length in tokens`} />
            </label>
            <label className="check small"><input type="checkbox" checked={m.tools} onChange={(e) => upd(i, "tools", e.target.checked)} /> tools</label>
            <button type="button" className="ghost" onClick={() => setModels((ms) => ms.filter((_, j) => j !== i))} aria-label={`Remove ${m.model}`}>Remove</button>
          </div>
        ))}
        {found && found.filter((m) => !has(m)).length > 0 && (
          <div className="checks" role="group" aria-label="Models on the server">
            {found.filter((m) => !has(m)).map((m) => <button type="button" key={m} className="model-chip" onClick={() => add(m)}>+ {m}</button>)}
          </div>
        )}
        {found && found.length === 0 && <p className="note small warn">The server reports no models. Load a model on it, then Find models again.</p>}
        <div className="ep-row">
          <div className="field grow">
            <label htmlFor={`${id}-manual`}>Add a model id</label>
            <input id={`${id}-manual`} value={manual} onChange={(e) => setManual(e.target.value)} autoComplete="off"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(manual); setManual(""); } }} />
          </div>
          <button type="button" onClick={() => { add(manual); setManual(""); }} disabled={!manual.trim()}>Add</button>
        </div>
        <p className="help">Set the context window to what the server actually uses (LM Studio and Ollama often default to 4,096 or 8,192 tokens). Tick tools only if the model supports tool calling.</p>
      </div>

      <ErrorNote error={error} />
      <div className="row-tight">
        <button className="primary" type="submit" disabled={busy === "save"}>{busy === "save" ? "Saving…" : "Save"}</button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
        {p.edited_in_app && <button type="button" className="ghost grow-left" onClick={reset} disabled={busy === "reset"}>Reset to file defaults</button>}
      </div>
    </form>
  );
}
