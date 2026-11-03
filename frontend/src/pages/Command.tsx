import { useEffect, useState } from "react";
import { api, type Overview, type RouteResult, type RunSummary } from "../api";
import { ErrorNote, Pill, fmtTime, go } from "../ui";
import { OrchestrationMap } from "../viz";
import { setPrefill } from "./RunForm";

export default function Command({ ov }: { ov: Overview }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RouteResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [recent, setRecent] = useState<RunSummary[]>([]);

  useEffect(() => { api.runs().then((r) => setRecent(r.slice(0, 6))).catch(() => {}); }, []);

  const realModels = ov.providers.filter((p) => p.available);
  const liveConnectors = ov.connectors.filter((c) => !["unconfigured", "disabled", "offline"].includes(c.status)).length;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true); setError(null);
    try {
      const r = await api.route(text);
      setResult(r);
      if (r.auto) open(r.playbook);
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  function open(pid: string) {
    const pb = ov.playbooks.find((p) => p.id === pid);
    const first = pb?.inputs.find((i) => i.required && (i.type === "text" || i.type === "longtext"));
    if (first) setPrefill(pid, { [first.id]: text });
    go(`/start/${pid}`);
  }

  const mvp = ov.playbooks.filter((p) => p.status === "mvp" && p.id !== "quick-ask");

  return (
    <div className="stack-lg">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">{ov.agents.length} agents · {ov.desks.length} desks · {mvp.length + 1} playbooks</span>
          <h1>Tell it what needs doing.</h1>
          <p className="lede">Route it to a playbook: specialists do the work, a different agent checks it, and nothing leaves until a named person approves. Or ask the Chief of Staff, who answers or brings in the right specialists.</p>
          <form className="command" onSubmit={submit}>
            <label htmlFor="cmd" className="sr-only">Request</label>
            <textarea id="cmd" rows={3} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Ops wants a CSV export added this sprint. It's about 40 hours. Should we take it?"
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e); }} />
            <div className="command-bar">
              <span className="muted small"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
              <button type="button" disabled={busy || !text.trim()} onClick={() => {
                try { sessionStorage.setItem("suite.chatDraft", text); } catch { /* storage unavailable */ }
                go("/chat");
              }}>Ask the Chief of Staff</button>
              <button className="primary cut" type="submit" disabled={busy || !text.trim()}>{busy ? "Routing…" : "Route to a playbook"}</button>
            </div>
          </form>
          <ErrorNote error={error} />
          {result && !result.auto && (
            <div className="route">
              <p><strong>Best match:</strong> {ov.playbooks.find((p) => p.id === result.playbook)?.name}
                <span className="muted small"> · {Math.round(result.confidence * 100)}% confidence · {result.method}</span></p>
              <p className="muted small">Below the auto-start threshold. Choose one:</p>
              <div className="choices">
                {result.candidates.map((c) => (
                  <button key={c.id} className="choice" onClick={() => open(c.id)}>
                    <strong>{c.name}</strong><span>{c.summary}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <OrchestrationMap desks={ov.desks} playbooks={mvp.length + 1} connectorsLive={liveConnectors} />
      </section>

      <section className="telemetry" aria-label="System status">
        <div className={`tele ${realModels.length ? "t-ok" : "t-warn"}`}>
          <span className="label">Models</span>
          <strong>{realModels.length ? realModels.map((p) => p.name).join(" · ") : "None configured"}</strong>
          {!realModels.length && <a className="small" href="#/settings">Add a model in Settings →</a>}
        </div>
        <div className="tele"><span className="label">Connectors live</span><strong className="num">{liveConnectors}<span className="muted">/{ov.connectors.length}</span></strong></div>
        <div className={`tele ${ov.pending_approvals ? "t-warn" : ""}`}>
          <span className="label">Waiting for you</span>
          <strong className="num">{ov.pending_approvals}</strong>
          {ov.pending_approvals > 0 && <a className="small" href="#/approvals">Review →</a>}
        </div>
        <div className="tele"><span className="label">Mode</span><strong>{ov.offline ? "Offline · local only" : `Online · ${ov.default_data_class}`}</strong></div>
      </section>

      <section className="stack">
        <h2 className="section-title">Playbooks</h2>
        <div className="grid cards">
            {mvp.map((p) => (
              <button key={p.id} className="card pb" onClick={() => go(`/start/${p.id}`)}>
                <span className="code">{p.code}<span className="area">{p.area}</span>{p.safety_critical && <span className="flag">Safety-critical</span>}</span>
                <strong>{p.name}</strong>
                <span className="muted">{p.summary}</span>
                <span className="meta">
                  <span>{p.steps.length} steps</span>
                  {p.steps.some((s) => s.kind === "review") && <span>Independent review</span>}
                  {p.steps.some((s) => s.kind === "gate") && <span>Human gate</span>}
                  {p.steps.some((s) => s.kind === "tool") && <span>{p.desk === "upstream" ? "Calculators" : "Evidence check"}</span>}
                </span>
              </button>
            ))}
        </div>
      </section>

      {recent.length > 0 && (
        <section className="stack">
          <h2 className="section-title">Recent runs</h2>
          <ul className="list">
            {recent.map((r) => (
              <li key={r.id}>
                <a href={`#/runs/${r.id}`}>
                  <span className="grow"><strong>{r.title}</strong><span className="muted small"> · {ov.playbooks.find((p) => p.id === r.playbook_id)?.name}</span></span>
                  <Pill value={r.status === "completed" ? r.outcome : r.status} />
                  <span className="muted small nowrap">{fmtTime(r.created_at)}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
