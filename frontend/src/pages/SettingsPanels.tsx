import { useEffect, useState } from "react";
import { api, type Budgets, type ConnectorInfo, type ConnectorVariable, type Overview, type Profile, type SignedInAccount,
  type SigninState } from "../api";
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

// A setup step: commands are set off by three spaces in the text ("run   npx … --login   and …"); addresses are links.
function StepText({ text }: { text: string }) {
  return (
    <>
      {text.split(/\s{3,}/).map((part, i) => (i % 2 === 1
        ? <code key={i}>{part}</code>
        : <span key={i}>{part.split(/(https?:\/\/[^\s)]+)/).map((bit, j) => (/^https?:\/\//.test(bit)
          ? <a key={j} href={bit.replace(/[.,;:]$/, "")} target="_blank" rel="noreferrer">{bit}</a> : bit))}</span>))}
    </>
  );
}

function SetupGuide({ c }: { c: ConnectorInfo }) {
  return (
    <div className="setup-guide stack-sm">
      {c.setup && <p className="small muted">{c.setup}</p>}
      {c.steps.length > 0 && (
        <ol className="setup-steps small">{c.steps.map((st, i) => <li key={i}><StepText text={st} /></li>)}</ol>
      )}
      {c.docs_url && <p className="small"><a href={c.docs_url} target="_blank" rel="noreferrer">Full setup guide for this server ↗</a></p>}
      {c.verify && <p className="help">Check before relying on it: {c.verify}</p>}
    </div>
  );
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
          if (c.signin && (v?.flag || c.signin.accounts_vars.includes(n))) return `a ${c.signin.provider} sign-in`;
          return v?.flag ? "the one-time sign-in confirmation"
            : /^[A-Z0-9_]+$/.test(n) ? (v?.label || varLabel(n)).toLowerCase() : n;
        }).join(", ")}. Open Edit to {c.signin ? "sign in" : "set it up"}{c.enabled || c.signin ? "" : ", then switch it on"}.</p>
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
        : <VariablesEditor key={signinKey(c)} c={c} onRefresh={onChange} onDone={() => { setEditing(false); onChange(); }} />)}
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
      <p className="small muted">{c.setup}</p>
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

function VariablesEditor({ c, onDone, onRefresh }: { c: ConnectorInfo; onDone: () => void; onRefresh: () => void }) {
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
  const label = (v: ConnectorVariable) => v.label || varLabel(v.name);
  const field = (v: ConnectorVariable) => {
          const id = `${c.id}-${v.name}`;
          if (v.source === "env") {
            return (
              <div key={v.name} className="field">
                <span className="label-like">{label(v)}</span>
                <span className="muted small">Set by the environment variable <code>{v.name}</code></span>
              </div>
            );
          }
          if (v.flag && c.signin?.confirms === v.name) return null;  // set by signing in, above
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
              <label htmlFor={id}>{label(v)}{!v.optional && v.source !== "bundled" && <span className="req" aria-label="required"> *</span>}</label>
              <input id={id} type={v.secret ? "password" : "text"} value={vals[v.name] ?? ""} autoComplete="off" spellCheck={false}
                placeholder={v.source === "bundled" ? "Built into this app" : v.secret && v.set ? "•••••••• (saved)" : v.default || ""}
                onChange={(e) => setVals((x) => ({ ...x, [v.name]: e.target.value }))} />
              {v.source === "bundled" && <span className="help ok-text">Built into this app: nothing to enter. Type a value only to use your own.</span>}
              {v.hint && <span className="help">{v.hint}</span>}
              <span className="help"><code>{v.name}</code>{v.optional ? " · optional" : ""}{v.secret ? " · never shown again once saved" : ""}</span>
              {v.secret && v.set && v.source === "app" && (
                <label className="check small"><input type="checkbox" checked={clear.includes(v.name)}
                  onChange={(e) => setClear((x) => (e.target.checked ? [...x, v.name] : x.filter((y) => y !== v.name)))} /> Remove the saved value</label>
              )}
            </div>
          );
  };
  const shared = c.variables.filter((v) => !v.part);
  return (
    <form className="provider-edit stack" onSubmit={save}>
      <SetupGuide c={c} />
      {c.signin && <SigninPanel c={c} onChange={onRefresh} />}
      <div className="ep-grid">{shared.map(field)}</div>
      {c.parts.map((p) => (
        <fieldset key={p.id} className="plain part-fields">
          <legend><strong>{p.name}</strong> <span className={`pill ${p.ready ? "ok" : "neutral"}`}>{p.ready ? "on" : "off until filled in"}</span></legend>
          {p.description && <span className="small muted">{p.description}</span>}
          <div className="ep-grid">{c.variables.filter((v) => v.part === p.id).map(field)}</div>
        </fieldset>
      ))}
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

// ------------------------------------------------------------------ sign-in from the app

/** Changes when a sign-in changes the connector's values, so the open form is rebuilt from fresh ones. */
function signinKey(c: ConnectorInfo) {
  if (!c.signin) return c.id;
  const v = (n: string | null) => c.variables.find((x) => x.name === n);
  return `${c.id}:${c.signin.accounts_vars.map((n) => v(n)?.value ?? "").join("|")}:${v(c.signin.confirms)?.set ? 1 : 0}`;
}

async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* not allowed here: try the old way */ }
  const area = document.createElement("textarea");
  area.value = text; area.setAttribute("readonly", ""); area.style.position = "fixed"; area.style.opacity = "0";
  document.body.appendChild(area); area.select();
  try { return document.execCommand("copy"); } catch { return false; } finally { area.remove(); }
}

const SIGNIN_ACTIVE = ["starting", "waiting", "finishing"];

/** Sign in with a code: the connector's server shows a code, the person enters it on the provider's page. */
function SigninPanel({ c, onChange }: { c: ConnectorInfo; onChange: () => void }) {
  const provider = c.signin!.provider;
  const byAddress = c.signin!.kind === "tool";  // Google: sign in with an address, in this computer's browser
  const [address, setAddress] = useState("");
  const [s, setS] = useState<SigninState | null>(null);
  const [accounts, setAccounts] = useState<SignedInAccount[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const [copied, setCopied] = useState(false);
  const active = !!s && SIGNIN_ACTIVE.includes(s.status);
  const confirmed = c.signin!.confirms ? !!c.variables.find((v) => v.name === c.signin!.confirms)?.set
    : c.signin!.accounts_vars.some((n) => c.variables.find((v) => v.name === n)?.set);

  async function loadAccounts() {
    try { setAccounts((await api.signedInAccounts(c.id)).accounts); } catch (e) { setAccounts([]); setError(e); }
  }
  useEffect(() => {
    api.signinState(c.id).then(setS).catch(() => setS(null));
    if (!c.offline_paused) loadAccounts();
  }, [c.id]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // follow the sign-in until it ends; the server does the work
    if (!active) return;
    const t = setInterval(async () => {
      try {
        const next = await api.signinState(c.id);
        setS(next);
        if (next.status === "done") onChange();
        else if (!SIGNIN_ACTIVE.includes(next.status)) loadAccounts();
      } catch { /* keep polling */ }
    }, 1500);
    return () => clearInterval(t);
  }, [active, c.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setBusy("start"); setError(null); setCopied(false);
    try { setS(await api.signinStart(c.id, byAddress ? address.trim() : undefined)); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function cancel() {
    setBusy("cancel");
    try { setS(await api.signinCancel(c.id)); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function signOut(a: SignedInAccount) {
    if (!window.confirm(`Sign ${a.username} out? Agents stop reading this account, and the app forgets its ${provider} sign-in on this computer.`)) return;
    setBusy(a.id); setError(null);
    try { setAccounts((await api.signOut(c.id, a.id)).accounts); setS(null); onChange(); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function useExisting() {
    if (!accounts?.length) return;
    setBusy("adopt"); setError(null);
    try { await api.useSignedIn(c.id); onChange(); } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function copyCode() {
    if (s?.code) setCopied(await copyText(s.code));
  }

  return (
    <div className="signin stack-sm" aria-live="polite">
      <strong>Sign-in</strong>
      {accounts === null && !c.offline_paused && <span className="small muted">Checking who is signed in…</span>}
      {accounts && accounts.length > 0 && (
        <ul className="plain signin-accounts">
          {accounts.map((a) => (
            <li key={a.id} className="row-tight">
              <span className="grow"><strong>{a.name || a.username}</strong> <span className="muted small">{a.username}</span></span>
              {a.selected && <span className="pill ok">default</span>}
              <button type="button" className="ghost small-btn" onClick={() => signOut(a)} disabled={!!busy}>
                {busy === a.id ? "Signing out…" : "Sign out"}</button>
            </li>
          ))}
        </ul>
      )}
      {accounts && accounts.length > 0 && !confirmed && !active && (
        <p className="small note">Found {accounts.length === 1 ? "an account" : `${accounts.length} accounts`} signed in earlier.{" "}
          <button type="button" className="ghost small-btn" onClick={useExisting} disabled={!!busy}>Use {accounts.length === 1 ? "it" : "them"}</button></p>
      )}

      {s?.status === "starting" && (
        <p className="small muted">Starting the {provider} sign-in… The first time, the app downloads the connector, which can take a minute.</p>
      )}
      {s?.status === "waiting" && byAddress && (
        <ol className="setup-steps small signin-steps">
          <li>A {provider} page should have opened in your browser. If not, <a href={s.url} target="_blank" rel="noreferrer">open the {provider} sign-in page ↗</a>.</li>
          <li>Sign in and allow read-only access. If {provider} says it has not verified the app, choose Advanced, then continue: it is this app's own client.</li>
          <li>Use the browser on the computer running the app: {provider} sends you back to it. This page updates by itself.</li>
        </ol>
      )}
      {s?.status === "waiting" && !byAddress && (
        <ol className="setup-steps small signin-steps">
          {s.code ? (
            <li>Your code: <code className="signin-code">{s.code}</code>{" "}
              <button type="button" className="small-btn" onClick={copyCode}>{copied ? "Copied" : "Copy code"}</button></li>
          ) : <li>{s.message}</li>}
          <li><a href={s.url} target="_blank" rel="noreferrer" onClick={copyCode}>Open the {provider} sign-in page ↗</a>
            {s.code ? " and paste the code." : "."}</li>
          <li>Sign in with the account agents should read and accept the permissions (read-only). This page updates by itself.</li>
        </ol>
      )}
      {s?.status === "finishing" && <p className="small muted">Signed in. Saving…</p>}
      {s?.status === "done" && (
        <p className="small note ok-note">Signed in as <strong>{s.account}</strong>. {c.enabled ? "The connector is on: press Test to see its tools." : "Switch the connector on to use it."}</p>
      )}
      {s?.status === "failed" && <p className="small note bad">Sign-in failed: {s.error}</p>}
      {s?.status === "cancelled" && <p className="small muted">Sign-in cancelled.</p>}
      <ErrorNote error={error} />

      <div className="row-tight signin-actions">
        {byAddress && !active && (
          <input type="email" aria-label={`${provider} address to sign in with`} placeholder={`you@gmail.com`} value={address}
            autoComplete="email" spellCheck={false} onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address.trim())) start(); } }} />
        )}
        {active
          ? <button type="button" className="ghost" onClick={cancel} disabled={busy === "cancel" || s?.status === "finishing"}>Cancel sign-in</button>
          : <button type="button" className={accounts?.length ? "" : "primary"} onClick={start}
              disabled={!!busy || c.offline_paused || (byAddress && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address.trim()))}
              title={c.offline_paused ? "Go online to sign in" : undefined}>
              {busy === "start" ? "Starting…" : accounts?.length ? "Add another account" : `Sign in with ${provider}`}</button>}
      </div>
    </div>
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
        <div className="pair-grid">
          <div className="field"><label htmlFor="pf-name">Name</label><input id="pf-name" value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="Optional" /></div>
          <div className="field"><label htmlFor="pf-role">Role</label><input id="pf-role" value={p.role} onChange={(e) => set("role", e.target.value)} placeholder="e.g. Drilling engineering manager" /></div>
        </div>
        <div className="field"><label htmlFor="pf-org">Organisation context</label>
          <textarea id="pf-org" rows={2} value={p.organization_context} onChange={(e) => set("organization_context", e.target.value)} placeholder="Industry, team, what your organisation does" /></div>
        <div className="pair-grid">
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

// ------------------------------------------------------------------ outputs folder

function OutputsFolder({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const o = ov.outputs;
  const [path, setPath] = useState(o.path || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(0);
  useEffect(() => { setPath(o.path || ""); }, [o.path]);
  async function save(edit: { path?: string; off?: boolean }) {
    setBusy(true); setError(null);
    try { await api.saveOutputs(edit); setSaved(Date.now()); onChange(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return (
    <section className="stack" aria-labelledby="out-h">
      <div className="stack-sm">
        <h2 id="out-h">Outputs folder</h2>
        <p className="muted small measure">Readable copies of your work are saved here: each chat as a Markdown transcript (<code>Chats</code>), every finished playbook deliverable as Markdown and HTML (<code>Runs</code>), and files you ask for or save from chat (<code>Files</code>). Chats and runs marked Restricted are not copied. Your settings, keys and history database stay in the app's own folder.</p>
      </div>
      <form className="card stack" onSubmit={(e) => { e.preventDefault(); save({ path }); }}>
        <div className="ep-row">
          <div className="field grow">
            <label htmlFor="out-path">Folder</label>
            <input id="out-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder={o.default}
              autoComplete="off" spellCheck={false} />
            <span className="help">{o.path ? (o.source === "app" ? "Chosen here." : "The default.") : "Switched off: chats and deliverables stay inside the app."} Paste a full path, for example from the File Explorer address bar; the folder is created if needed and applies at once.</span>
          </div>
        </div>
        {o.shared_with_local_files.length > 0 && (
          <p className="small note">This folder is also shared with agents through Local files ({o.shared_with_local_files.join(", ")}), so agents can read your saved chats and files. Restricted work is never copied here.</p>
        )}
        <ErrorNote error={error} />
        <div className="row-tight">
          <button className="primary" type="submit" disabled={busy || !path.trim() || path === o.path}>Save folder</button>
          {o.source === "app" && <button type="button" className="ghost" disabled={busy} onClick={() => save({})}>Use the default ({o.default})</button>}
          {o.path && <button type="button" className="ghost grow-left" disabled={busy} onClick={() => save({ off: true })}>Switch off</button>}
          <Saved at={saved} />
        </div>
      </form>
    </section>
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
          <h2 id="bud-h">Spending limits</h2>
          <p className="muted small measure">Off by default: runs and chats use what they need. Switch on to cap cost and tokens. A run that reaches its limit pauses before its next step and asks whether to continue (approve doubles the limit, reject stops the run). A chat that would go past its limit stops before the next model call; start a new chat or raise the limit. Cost uses the prices set on each model; local models count tokens but cost nothing.</p>
        </div>
        <div className="card stack">
          <div className="row-tight">
            <strong className="grow">Apply spending limits</strong>
            <Switch on={b.enabled} label="Apply spending limits" busy={busy} onToggle={() => {
              const next = { ...b, enabled: !b.enabled };
              setB(next); apply({ budgets: next }).catch(() => setB(b));
            }} />
          </div>
          <fieldset className={`plain ${b.enabled ? "" : "is-dim"}`}>
            <legend className="small muted">{b.enabled ? "Applied to every run and chat" : "Not applied while the switch is off; you can set them now"}</legend>
            <div className="ep-grid">
              <div className="field"><label htmlFor="b-cost">Max cost per run (US$)</label><input id="b-cost" type="number" min={0} step="any" value={b.max_run_cost_usd} onChange={(e) => num("max_run_cost_usd", e.target.value)} /></div>
              <div className="field"><label htmlFor="b-tok">Max tokens per run</label><input id="b-tok" type="number" min={1000} step="any" value={b.max_run_tokens} onChange={(e) => num("max_run_tokens", e.target.value)} /></div>
              <div className="field"><label htmlFor="b-ccost">Max cost per chat (US$)</label><input id="b-ccost" type="number" min={0} step="any" value={b.max_chat_cost_usd} onChange={(e) => num("max_chat_cost_usd", e.target.value)} /></div>
              <div className="field"><label htmlFor="b-ctok">Max tokens per chat</label><input id="b-ctok" type="number" min={1000} step="any" value={b.max_chat_tokens} onChange={(e) => num("max_chat_tokens", e.target.value)} /></div>
            </div>
          </fieldset>
        </div>
        <div className="stack-sm">
          <h2 id="guard-h">Guardrails</h2>
          <p className="muted small measure">Always on, whatever the switch above says. They stop runaway loops and keep every prompt inside the model's context window. A run that needs more steps than allowed is refused at the start; one that reaches the limit through revisions stops with a note.</p>
        </div>
        <div className="card stack">
          <div className="ep-grid">
            <div className="field"><label htmlFor="b-steps">Max steps per run</label><input id="b-steps" type="number" min={1} value={b.max_steps} onChange={(e) => num("max_steps", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-tools">Tool calls per step</label><input id="b-tools" type="number" min={0} value={b.max_tool_calls_per_step} onChange={(e) => num("max_tool_calls_per_step", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-chars">Max characters per tool result</label><input id="b-chars" type="number" min={1000} step="any" value={b.max_tool_result_chars} onChange={(e) => num("max_tool_result_chars", e.target.value)} /></div>
            <div className="field"><label htmlFor="b-frac">Share of the context window for the prompt</label><input id="b-frac" type="number" min={0.2} max={0.95} step="any" value={b.max_context_fraction} onChange={(e) => num("max_context_fraction", e.target.value)} /></div>
          </div>
          <div className="row-tight">
            <button className="primary" type="submit" disabled={busy}>Save limits</button>
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

      <OutputsFolder ov={ov} onChange={onChange} />
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
