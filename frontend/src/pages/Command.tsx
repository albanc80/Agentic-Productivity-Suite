import { useEffect, useState } from "react";
import { api, type Overview, type RouteResult, type RunSummary } from "../api";
import { ErrorNote, Pill, fmtTime, go } from "../ui";
import { setPrefill } from "./RunForm";

export default function Command({ ov }: { ov: Overview }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RouteResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [recent, setRecent] = useState<RunSummary[]>([]);

  useEffect(() => { api.runs().then((r) => setRecent(r.slice(0, 6))).catch(() => {}); }, []);

  const realModels = ov.providers.some((p) => p.available && p.type !== "mock");
  const liveConnectors = ov.connectors.filter((c) => c.status !== "unconfigured" && c.status !== "disabled").length;

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
        <h1>What needs doing?</h1>
        <p className="muted">Describe the request. The suite picks a playbook, or you choose one below.</p>
        <form className="command" onSubmit={submit}>
          <label htmlFor="cmd" className="sr-only">Request</label>
          <textarea id="cmd" rows={3} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Ops wants a CSV export added this sprint. It's about 40 hours. Should we take it?"
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e); }} />
          <div className="row">
            <button className="primary" type="submit" disabled={busy || !text.trim()}>{busy ? "Routing…" : "Find the playbook"}</button>
            <span className="muted small">Ctrl + Enter</span>
          </div>
        </form>
        <ErrorNote error={error} />
        {result && !result.auto && (
          <div className="card route">
            <p><strong>Best match:</strong> {ov.playbooks.find((p) => p.id === result.playbook)?.name}
              <span className="muted small"> · confidence {Math.round(result.confidence * 100)}% · {result.method}</span></p>
            <p className="muted small">Confidence is below the auto-start threshold. Pick one:</p>
            <div className="choices">
              {result.candidates.map((c) => (
                <button key={c.id} className="choice" onClick={() => open(c.id)}>
                  <strong>{c.name}</strong><span>{c.summary}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="status-strip" aria-label="System status">
        <div><span className="label">Models</span>{realModels ? <Pill value="ready" /> : <span className="pill warn">Demo only</span>}</div>
        <div><span className="label">Connectors live</span><strong>{liveConnectors}</strong> of {ov.connectors.length}</div>
        <div><span className="label">Approvals waiting</span><strong>{ov.pending_approvals}</strong></div>
        <div><span className="label">Default data class</span><strong>{ov.default_data_class}</strong></div>
        {!realModels && <a className="small" href="#/settings">Configure a model →</a>}
      </section>

      <section className="stack">
        <h2>Playbooks</h2>
        <div className="grid cards">
          {mvp.map((p) => (
            <button key={p.id} className="card pb" onClick={() => go(`/start/${p.id}`)}>
              <span className="code">{p.code} · {p.area}</span>
              <strong>{p.name}</strong>
              <span className="muted">{p.summary}</span>
              <span className="meta">{p.steps.length} steps{p.steps.some((s) => s.kind === "gate") ? " · human gate" : ""}{p.steps.some((s) => s.kind === "review") ? " · independent review" : ""}</span>
            </button>
          ))}
        </div>
      </section>

      {recent.length > 0 && (
        <section className="stack">
          <h2>Recent runs</h2>
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
