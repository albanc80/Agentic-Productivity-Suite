import { useEffect, useState } from "react";
import { api, type Budgets, type ConnectorInfo, type Overview, type Profile } from "../api";
import { ErrorNote } from "../ui";

/** On/off switch: a real button with role="switch". `paused` shows it locked off by offline mode. */
export function Switch({ on, label, busy, paused, locked, onToggle }: { on: boolean; label: string; busy?: boolean; paused?: boolean;
  locked?: string; onToggle: () => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "is-on" : ""} ${paused ? "is-paused" : ""}`}
      disabled={busy || paused || !!locked} onClick={onToggle} title={paused ? "Paused while offline" : locked}>
      <span className="switch-track" aria-hidden="true"><span className="switch-knob" /></span>
      <span className="switch-text">{paused ? "Paused" : on ? "On" : "Off"}</span>
    </button>
  );
}

function Saved({ at }: { at: number }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!at) return;
    setShow(true);
    const t = setTimeout(() => setShow(false), 2500);
    return () => clearTimeout(t);
  }, [at]);
  return show ? <span className="ok-text small" role="status">Saved</span> : null;
}

// ------------------------------------------------------------------ fallback chains

const TIER_TEXT: Record<string, string> = {
  router: "Picks the playbook", specialist: "Most agent steps and chats", synthesis: "Combines results", review: "Independent checks",
};

export function ChainsEditor({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [edit, setEdit] = useState<Record<string, string[]> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const ready = new Set(ov.providers.filter((p) => p.available).map((p) => p.name));
  const tiers = edit || ov.tiers;

  const move = (t: string, i: number, d: number) => setEdit((e) => {
    const cur = [...(e || ov.tiers)[t]];
    const j = i + d;
    if (j < 0 || j >= cur.length) return e;
    [cur[i], cur[j]] = [cur[j], cur[i]];
    return { ...(e || ov.tiers), [t]: cur };
  });
  const drop = (t: string, i: number) => setEdit((e) => ({ ...(e || ov.tiers), [t]: (e || ov.tiers)[t].filter((_, k) => k !== i) }));
  const add = (t: string, ref: string) => ref && setEdit((e) => ({ ...(e || ov.tiers), [t]: [...(e || ov.tiers)[t], ref] }));

  async function save() {
    if (!edit) return;
    setBusy(true); setError(null);
    try { await api.saveGeneral({ tiers: edit }); setEdit(null); onChange(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true); setError(null);
    try { await api.resetGeneral("tiers"); setEdit(null); onChange(); } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <section className="stack" aria-labelledby="chains-h">
      <div className="stack-sm">
        <h2 id="chains-h">Fallback order</h2>
        <p className="muted small measure">For each kind of work, models are tried in this order. The first one that is ready and allowed for the data class is used; if it fails, the next is tried. {ov.offline && ov.offline_default ? `Offline, ${ov.offline_default} goes first everywhere.` : ""}</p>
      </div>
      <div className="grid two">
        {Object.entries(tiers).map(([t, chain]) => (
          <div key={t} className="card stack-sm">
            <div className="row-tight"><strong className="grow">{t}</strong><span className="muted small">{TIER_TEXT[t]}</span></div>
            <ol className="chain-list">
              {chain.map((ref, i) => (
                <li key={ref} className={ready.has(ref.split("/")[0]) ? "" : "is-off"}>
                  <code className="grow">{ref}</code>
                  {!ready.has(ref.split("/")[0]) && <span className="muted small">not ready</span>}
                  <button type="button" className="ghost icon-btn" onClick={() => move(t, i, -1)} disabled={i === 0} aria-label={`Move ${ref} up in ${t}`}>↑</button>
                  <button type="button" className="ghost icon-btn" onClick={() => move(t, i, 1)} disabled={i === chain.length - 1} aria-label={`Move ${ref} down in ${t}`}>↓</button>
                  <button type="button" className="ghost icon-btn" onClick={() => drop(t, i)} aria-label={`Remove ${ref} from ${t}`}>×</button>
                </li>
              ))}
              {chain.length === 0 && <li className="muted small">Empty: runs of this kind will stop.</li>}
            </ol>
            <label className="sr-only" htmlFor={`add-${t}`}>Add a model to {t}</label>
            <select id={`add-${t}`} value="" onChange={(e) => add(t, e.target.value)}>
              <option value="">Add a model…</option>
              {ov.model_refs.filter((r) => !chain.includes(r)).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        ))}
      </div>
      <ErrorNote error={error} />
      <div className="row-tight">
        <button className="primary" onClick={save} disabled={!edit || busy}>Save order</button>
        {edit && <button className="ghost" onClick={() => setEdit(null)}>Cancel</button>}
        {ov.general_edited.includes("tiers") && <button className="ghost grow-left" onClick={reset} disabled={busy}>Reset to file defaults</button>}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ connectors

function varLabel(n: string) {
  return n.toLowerCase().split("_").map((w, i) => (i === 0 ? w[0].toUpperCase() + w.slice(1) : w)).join(" ")
    .replace(/\bid\b/g, "ID").replace(/\burl\b/g, "URL").replace(/\bapi\b/g, "API").replace(/\bmcp\b/gi, "MCP")
    .replace(/\buc\b/g, "UC").replace(/\bvs\b/g, "vector search").replace(/\bms365\b/gi, "Microsoft 365")
    .replace(/\bgoogle\b/gi, "Google").replace(/\boauth\b/gi, "OAuth").replace(/^User Google email$/, "Google email (default account)");
}

const STATUS_TEXT: Record<string, string> = {
  idle: "Ready", ready: "Connected", connecting: "Connecting", error: "Error", unconfigured: "Needs setup",
  disabled: "Off", offline: "Paused offline",
};

export function ConnectorsPanel({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  return (
    <section className="stack" aria-labelledby="conn-h">
      <div className="stack-sm">
        <h2 id="conn-h">Connectors (read-only)</h2>
        <p className="muted small measure">Connectors let agents read your systems and files. Agents only ever get read-only tools: write tools are hidden and refused, whatever the connector offers. Every connector starts switched off: use <strong>Edit</strong> to enter what it needs, then switch it on. Values you type are saved on this computer; an environment variable with the same name takes precedence.</p>
      </div>
      <div className="stack-sm">
        {[...ov.connectors].sort((a, b) => Number(b.builtin) - Number(a.builtin)).map((c) => <ConnectorRow key={c.id} c={c} onChange={onChange} />)}
      </div>
    </section>
  );
}

function ConnectorRow({ c, onChange }: { c: ConnectorInfo; onChange: () => void }) {
  const [editing, setEditing] = useState(c.builtin && c.status === "unconfigured");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [tools, setTools] = useState<{ name: string; allowed: boolean; reason: string }[] | null>(null);

  async function toggle() {
    setBusy("toggle"); setError(null);
    try { await api.updateConnector(c.id, { enabled: !c.enabled }); onChange(); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function connect() {
    setBusy("connect"); setError(null);
    try { const r = await api.connect(c.id); setTools(r.tools); onChange(); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  const ready = ["idle", "ready"].includes(c.status);
  const tone = c.status === "ready" || c.status === "idle" ? "ok" : c.status === "error" ? "bad" : c.status === "unconfigured" ? "warn" : "neutral";
  const shown = tools || c.tools;

  return (
    <article className={`card provider ${c.enabled && !c.offline_paused ? "" : "is-off"}`}>
      <div className="provider-head">
        <Switch on={c.enabled && !c.offline_paused} paused={c.offline_paused} label={`${c.name} ${c.offline_paused ? "paused while offline" : c.enabled ? "on" : "off"}`}
          busy={busy === "toggle"} onToggle={toggle}
          locked={!c.enabled && c.missing.length > 0 ? "Set it up first: open Edit and fill in what it needs" : undefined} />
        <div className="grow stack-xs">
          <div className="row-tight">
            <strong className="provider-name">{c.name}</strong>
            <span className={`tag ${c.network ? "outline" : ""}`}>{c.network ? "internet" : "this computer"}</span>
          </div>
          <span className="muted small">{c.builtin ? (c.folders.length ? c.folders.join(" · ") : "No folder chosen") : c.description}</span>
        </div>
        <span className={`pill ${tone}`} title={c.error}>{c.status === "disabled" && c.missing.length ? "Off · needs setup" : STATUS_TEXT[c.status] || c.status}</span>
        <div className="row-tight">
          {ready && c.enabled && <button onClick={connect} disabled={busy === "connect"}>{busy === "connect" ? "Connecting…" : "Test"}</button>}
          <button className={editing ? "ghost" : ""} aria-expanded={editing} onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Edit"}</button>
        </div>
      </div>
      {c.missing.length > 0 && !c.offline_paused && (
        <p className="small provider-reason">Needs: {c.missing.map((n) => {
          const v = c.variables.find((x) => x.name === n);
          return v?.flag ? "the one-time sign-in confirmation" : /^[A-Z0-9_]+$/.test(n) ? varLabel(n).toLowerCase() : n;
        }).join(", ")}. Open Edit to set it up{c.enabled ? "" : ", then switch it on"}.</p>
      )}
      {c.status === "error" && <p className="small note bad">{c.error}</p>}
      {c.offline_paused && <p className="small muted">Paused while offline: it needs the internet. {c.enabled ? "It comes back when you go online." : ""}</p>}
      <ErrorNote error={error} />
      {shown.length > 0 && (
        <details className="small">
          <summary>{shown.filter((t) => t.allowed).length} read-only tools available, {shown.filter((t) => !t.allowed).length} blocked</summary>
          <ul className="plain small tools">
            {shown.map((t) => <li key={t.name}><code>{t.name}</code> {t.allowed ? <span className="pill ok">allowed</span> : <span className="pill neutral" title={t.reason}>blocked</span>}</li>)}
          </ul>
        </details>
      )}
      {editing && (c.builtin
        ? <FoldersEditor c={c} onDone={() => { setEditing(false); onChange(); }} />
        : <VariablesEditor c={c} onDone={() => { setEditing(false); onChange(); }} />)}
    </article>
  );
}

function FoldersEditor({ c, onDone }: { c: ConnectorInfo; onDone: () => void }) {
  const [folders, setFolders] = useState<string[]>(c.folders.length ? c.folders : [""]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.updateConnector(c.id, { folders: folders.filter((f) => f.trim()), enabled: true }); onDone(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true);
    try { await api.resetConnector(c.id); onDone(); } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return (
    <form className="provider-edit stack" onSubmit={save}>
      <p className="small muted measure">{c.setup}</p>
      {folders.map((f, i) => (
        <div key={i} className="ep-row">
          <div className="field grow">
            <label htmlFor={`${c.id}-folder-${i}`}>Folder {folders.length > 1 ? i + 1 : ""}</label>
            <input id={`${c.id}-folder-${i}`} value={f} onChange={(e) => setFolders((x) => x.map((y, j) => (j === i ? e.target.value : y)))}
              placeholder="C:\Users\you\Documents\Reports  or  /home/you/reports" autoComplete="off" spellCheck={false} />
          </div>
          {folders.length > 1 && <button type="button" className="ghost" onClick={() => setFolders((x) => x.filter((_, j) => j !== i))}>Remove</button>}
        </div>
      ))}
      <div className="row-tight">
        <button type="button" className="ghost" onClick={() => setFolders((x) => [...x, ""])}>Add another folder</button>
      </div>
      <p className="help">Paste the full path, for example from the address bar in File Explorer. Subfolders are included. Agents can list, search and read files (text, CSV, JSON, PDF, Word, Excel); they cannot change or delete anything.</p>
      <ErrorNote error={error} />
      <div className="row-tight">
        <button className="primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Save"}</button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
        {c.folders.length > 0 && <button type="button" className="ghost grow-left" onClick={reset} disabled={busy}>Remove all folders</button>}
      </div>
    </form>
  );
}

function VariablesEditor({ c, onDone }: { c: ConnectorInfo; onDone: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>(() => Object.fromEntries(c.variables.map((v) =>
    [v.name, v.flag ? (v.set ? "1" : "") : v.secret ? "" : v.value || ""])));
  const [clear, setClear] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const editable = c.variables.filter((v) => v.source !== "env");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const values = Object.fromEntries(editable.map((v) => [v.name, vals[v.name] ?? ""]));
      await api.updateConnector(c.id, { values, clear });
      onDone();
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true);
    try { await api.resetConnector(c.id); onDone(); } catch (err) { setError(err); } finally { setBusy(false); }
  }
  const label = varLabel;
  return (
    <form className="provider-edit stack" onSubmit={save}>
      <p className="small muted measure">{c.setup}</p>
      {c.verify && <p className="help">Check before relying on it: {c.verify}</p>}
      <div className="ep-grid">
        {c.variables.map((v) => {
          const id = `${c.id}-${v.name}`;
          if (v.source === "env") {
            return (
              <div key={v.name} className="field">
                <span className="label-like">{label(v.name)}</span>
                <span className="muted small">Set by the environment variable <code>{v.name}</code></span>
              </div>
            );
          }
          if (v.flag) {
            return (
              <label key={v.name} className="check small field">
                <input type="checkbox" checked={vals[v.name] === "1"}
                  onChange={(e) => {
                    const on = e.target.checked;
                    setVals((x) => ({ ...x, [v.name]: on ? "1" : "" }));
                    setClear((x) => (on ? x.filter((y) => y !== v.name) : [...x, v.name]));
                  }} />
                I have completed the one-time sign-in described above
              </label>
            );
          }
          return (
            <div key={v.name} className="field">
              <label htmlFor={id}>{label(v.name)}{!v.optional && <span className="req" aria-label="required"> *</span>}</label>
              <input id={id} type={v.secret ? "password" : "text"} value={vals[v.name] ?? ""} autoComplete="off" spellCheck={false}
                placeholder={v.secret && v.set ? "•••••••• (saved)" : v.default || ""}
                onChange={(e) => setVals((x) => ({ ...x, [v.name]: e.target.value }))} />
              <span className="help"><code>{v.name}</code>{v.optional ? " · optional" : ""}{v.secret ? " · never shown again once saved" : ""}</span>
              {v.secret && v.set && v.source === "app" && (
                <label className="check small"><input type="checkbox" checked={clear.includes(v.name)}
                  onChange={(e) => setClear((x) => (e.target.checked ? [...x, v.name] : x.filter((y) => y !== v.name)))} /> Remove the saved value</label>
              )}
            </div>
          );
        })}
      </div>
      <p className="help">Values are saved unencrypted in the app's database on this computer and shared by connectors that use the same name (for example the Databricks host and token). They are passed only to this connector.</p>
      <ErrorNote error={error} />
      <div className="row-tight">
        <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
        <button type="button" className="ghost grow-left" onClick={reset} disabled={busy}>Reset to file defaults</button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ profile

export function ProfilePanel({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [p, setP] = useState<Profile>(ov.profile);
  const [goals, setGoals] = useState(ov.profile.goals.join("\n"));
  const [prefs, setPrefs] = useState(ov.profile.working_preferences.join("\n"));
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Profile, v: string) => setP((x) => ({ ...x, [k]: v }));
  const lines = (t: string) => t.split("\n").map((x) => x.trim()).filter(Boolean);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.saveProfile({ ...p, goals: lines(goals), working_preferences: lines(prefs) }); setSaved(Date.now()); onChange(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true);
    try { const r = await api.resetProfile(); setP(r); setGoals(r.goals.join("\n")); setPrefs(r.working_preferences.join("\n")); onChange(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  return (
    <form className="stack" onSubmit={save} aria-labelledby="prof-h">
      <div className="stack-sm">
        <h2 id="prof-h">Your profile</h2>
        <p className="muted small measure">Sent with every model call so agents know who they work for. Keep it short; empty fields are left out. Do not put secrets here.</p>
      </div>
      <div className="card stack">
        <div className="ep-grid">
          <div className="field"><label htmlFor="pf-name">Name</label><input id="pf-name" value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="Optional" /></div>
          <div className="field"><label htmlFor="pf-role">Role</label><input id="pf-role" value={p.role} onChange={(e) => set("role", e.target.value)} placeholder="e.g. Drilling engineering manager" /></div>
        </div>
        <div className="field"><label htmlFor="pf-org">Organisation context</label>
          <textarea id="pf-org" rows={2} value={p.organization_context} onChange={(e) => set("organization_context", e.target.value)} placeholder="Industry, team, what your organisation does" /></div>
        <div className="ep-grid">
          <div className="field"><label htmlFor="pf-goals">Goals (one per line)</label>
            <textarea id="pf-goals" rows={4} value={goals} onChange={(e) => setGoals(e.target.value)} /></div>
          <div className="field"><label htmlFor="pf-prefs">How you like answers (one per line)</label>
            <textarea id="pf-prefs" rows={4} value={prefs} onChange={(e) => setPrefs(e.target.value)} placeholder="Lead with the answer, then the reasoning" /></div>
        </div>
        <div className="field"><label htmlFor="pf-dom">Domain notes</label>
          <textarea id="pf-dom" rows={3} value={p.domain_notes} onChange={(e) => set("domain_notes", e.target.value)} placeholder="Standards, systems or vocabulary agents should know" /></div>
        <ErrorNote error={error} />
        <div className="row-tight">
          <button className="primary" type="submit" disabled={busy}>Save profile</button>
          <Saved at={saved} />
          {ov.profile_saved_in_app && <button type="button" className="ghost grow-left" onClick={reset} disabled={busy}>Reset to file defaults</button>}
        </div>
      </div>
    </form>
  );
}

/** Checkbox that shows the new state at once and saves in the background; it follows the server value afterwards. */
function SavedCheck({ checked, disabled, onSave, children }: { checked: boolean; disabled?: boolean; onSave: (v: boolean) => Promise<void>; children: React.ReactNode }) {
  const [v, setV] = useState(checked);
  useEffect(() => { setV(checked); }, [checked]);
  return (
    <label className="check">
      <input type="checkbox" checked={v} disabled={disabled} onChange={async (e) => {
        const next = e.target.checked;
        setV(next);
        try { await onSave(next); } catch { setV(!next); }
      }} />
      {children}
    </label>
  );
}

// ------------------------------------------------------------------ policies and budgets

const DC_HELP: Record<string, string> = {
  public: "Published or shareable material.", internal: "Normal work content.",
  confidential: "Sensitive business content.", restricted: "Never leaves your network: local models only. Fixed.",
};

export function PoliciesPanel({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const [b, setB] = useState<Budgets>(ov.budgets);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setB(ov.budgets); }, [ov.budgets]);

  async function apply(edit: Parameters<typeof api.saveGeneral>[0]) {
    setBusy(true); setError(null);
    try { await api.saveGeneral(edit); setSaved(Date.now()); onChange(); }
    catch (e) { setError(e); throw e; } finally { setBusy(false); }
  }
  const num = (k: keyof Budgets, v: string) => setB((x) => ({ ...x, [k]: Number(v) }));

  return (
    <div className="stack-lg">
      <section className="stack" aria-labelledby="dc-h">
        <div className="stack-sm">
          <h2 id="dc-h">Data classes</h2>
          <p className="muted small measure">Each run and chat is tagged with a data class. Choose which classes may reach cloud models. You are responsible for the credentials and data you use.</p>
        </div>
        <div className="grid four">
          {Object.entries(ov.data_classes).map(([k, v]) => {
            const cloud = v.includes("cloud");
            const fixed = k === "restricted";
            return (
              <div key={k} className="card small stack-sm">
                <div className="row-tight"><strong className="grow">{k}</strong>{ov.default_data_class === k && <span className="tag">default</span>}</div>
                <span className="muted">{DC_HELP[k]}</span>
                <SavedCheck checked={cloud} disabled={fixed} onSave={(v) => apply({ cloud_allowed: { [k]: v } })}>Cloud models allowed</SavedCheck>
              </div>
            );
          })}
        </div>
        <div className="field narrow-field">
          <label htmlFor="dc-default">Default data class for new runs and chats</label>
          <select id="dc-default" value={ov.default_data_class} onChange={(e) => { apply({ default_data_class: e.target.value }).catch(() => {}); }}>
            {Object.keys(ov.data_classes).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
      </section>

      <form className="stack" aria-labelledby="bud-h" onSubmit={(e) => { e.preventDefault(); apply({ budgets: b }).catch(() => {}); }}>
        <div className="stack-sm">
          <h2 id="bud-h">Budgets per run</h2>
          <p className="muted small measure">A run that reaches the cost or token limit pauses and asks whether to continue. Cost uses the prices set on each model.</p>
        </div>
        <div className="card stack">
          <div className="ep-grid">
            <div className="field"><label htmlFor="b-cost">Max cost (US$)</label><input id="b-cost" type="number" min={0} step="any" value={b.max_run_cost_usd} onChange={(e) => num("max_run_cost_usd", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-tok">Max tokens</label><input id="b-tok" type="number" min={1000} step="any" value={b.max_run_tokens} onChange={(e) => num("max_run_tokens", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-steps">Max steps</label><input id="b-steps" type="number" min={1} value={b.max_steps} onChange={(e) => num("max_steps", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-tools">Tool calls per step</label><input id="b-tools" type="number" min={0} value={b.max_tool_calls_per_step} onChange={(e) => num("max_tool_calls_per_step", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-chars">Max characters per tool result</label><input id="b-chars" type="number" min={1000} step="any" value={b.max_tool_result_chars} onChange={(e) => num("max_tool_result_chars", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-frac">Share of the context window for the prompt</label><input id="b-frac" type="number" min={0.2} max={0.95} step="any" value={b.max_context_fraction} onChange={(e) => num("max_context_fraction", e.target.value)} /></div>
          </div>
          <div className="row-tight">
            <button className="primary" type="submit" disabled={busy}>Save budgets</button>
            {ov.general_edited.includes("budgets") && <button type="button" className="ghost grow-left" disabled={busy}
              onClick={async () => { try { await api.resetGeneral("budgets"); onChange(); } catch (e) { setError(e); } }}>Reset to file defaults</button>}
          </div>
        </div>
      </form>

      <section className="stack" aria-labelledby="voice-h">
        <h2 id="voice-h">Voice and records</h2>
        <div className="card stack-sm">
          <SavedCheck checked={ov.persona.chat} onSave={(v) => apply({ persona_chat: v })}>Agents with a persona use it in chats and chat-style playbooks</SavedCheck>
          <SavedCheck checked={ov.persona.exports} onSave={(v) => apply({ persona_exports: v })}>Use personas in documents (off keeps documents plain)</SavedCheck>
          <SavedCheck checked={ov.store_prompts} onSave={(v) => apply({ store_prompts: v })}>Keep full prompts in the run record (contains your data; off keeps only a fingerprint)</SavedCheck>
        </div>
      </section>

      <section className="stack" aria-labelledby="out-h">
        <h2 id="out-h">Outputs folder</h2>
        <div className="card stack-sm">
          {ov.outputs_dir ? (
            <>
              <code className="outputs-path">{ov.outputs_dir}</code>
              <p className="small muted measure">Readable copies of your work are saved here: each chat as a Markdown transcript (<code>Chats</code>), every finished playbook deliverable as Markdown and HTML (<code>Runs</code>), and files you ask for in chat (<code>Files</code>). Chats and runs marked Restricted are not copied. Deleting a chat in the app deletes its copy. Your settings, keys and history database stay in the app's own folder.</p>
            </>
          ) : <p className="small muted">Switched off. Chats and deliverables stay inside the app.</p>}
          <p className="small muted">To move or switch it off, set <code>outputs_dir</code> in <code>suite.yaml</code> (or <code>off</code>), or the <code>SUITE_OUTPUTS_DIR</code> environment variable, and restart.</p>
        </div>
      </section>
      <ErrorNote error={error} />
      <Saved at={saved} />
      {ov.general_edited.length > 0 && (
        <button className="ghost" onClick={async () => { try { await api.resetGeneral("all"); onChange(); } catch (e) { setError(e); } }}>
          Reset all policies, budgets and fallback order to file defaults
        </button>
      )}
      <p className="help">Fixed in the app: restricted data stays local, connectors stay read-only, and nothing is sent or changed without a named approval.</p>
    </div>
  );
}
