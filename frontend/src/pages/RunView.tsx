import { useCallback, useEffect, useState } from "react";
import { api, exportRun, type Approval, type ExportResult, type Overview, type RunDetail, type StepRow } from "../api";
import { ErrorNote, ExportNote, Markdown, NoteText, Pill, fmtCost, fmtTime } from "../ui";
import { StepRail } from "../viz";

const LIVE = new Set(["queued", "running"]);

export default function RunView({ ov, runId, onChange }: { ov: Overview; runId: string; onChange: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  async function doExport(format: "md" | "html") {
    if (!run) return;
    setExporting(true); setExported(null); setExportError(null);
    try { setExported(await exportRun(run.id, format)); } catch (e) { setExportError(e); } finally { setExporting(false); }
  }

  const load = useCallback(async () => {
    try { setRun(await api.run(runId)); setError(null); } catch (e) { setError(e); }
  }, [runId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!run || !LIVE.has(run.status)) return;
    const t = setTimeout(load, 1200);
    return () => clearTimeout(t);
  }, [run, load]);

  if (error && !run) return <ErrorNote error={error} />;
  if (!run) return <p className="muted">Loading run…</p>;

  const pb = run.playbook;
  const agentName = (id: string | null) => ov.agents.find((a) => a.id === id)?.name || id || "";
  const pending = run.approvals.filter((a) => a.status === "pending");
  const byStep = new Map<string, StepRow[]>();
  for (const s of run.steps) byStep.set(s.step_id, [...(byStep.get(s.step_id) || []), s]);

  return (
    <div className="stack-lg">
      <header className="run-head">
        <div className="stack-sm grow">
          <span className="code">{pb?.code} · {pb?.name}</span>
          <h1>{run.title}</h1>
          <div className="meta-row">
            <Pill value={run.status} />
            {run.outcome && <span>Outcome <Pill value={run.outcome} /></span>}
            <span>Data class <strong>{run.data_class}</strong></span>
            <span>{run.tokens.toLocaleString()} tokens</span>
            <span>{fmtCost(run.cost_usd)}</span>
            <span className="muted">{fmtTime(run.created_at)}</span>
          </div>
        </div>
        <div className="actions">
          {LIVE.has(run.status) || run.status === "awaiting_approval" ? (
            <button onClick={async () => { await api.cancel(run.id); load(); onChange(); }}>Cancel run</button>
          ) : null}
          {(run.status === "interrupted" || run.status === "failed") && (
            <button onClick={async () => { try { await api.resume(run.id); load(); } catch (e) { setError(e); } }}>Resume</button>
          )}
          {run.deliverable && <>
            <button disabled={exporting} onClick={() => doExport("md")}>Export Markdown</button>
            <button disabled={exporting} onClick={() => doExport("html")}>Export HTML</button>
          </>}
        </div>
      </header>
      <ErrorNote error={error} />
      <ExportNote result={exported} error={exportError} />
      {run.demo && <div className="banner warn">Made by the demo provider of an earlier version: no language model produced this content. You can delete it from the Library.</div>}

      {pb && <StepRail playbook={pb} steps={run.steps} cursor={run.cursor} runStatus={run.status} />}

      {pending.map((a) => <ApprovalPanel key={a.id} approval={a} onDone={() => { load(); onChange(); }} />)}

      <div className="run-grid">
        <section className="stack" aria-label="Steps">
          <h2>Steps</h2>
          <ol className="timeline">
            {(pb?.steps || []).map((s) => {
              const rows = s.children.length ? s.children.flatMap((c) => byStep.get(c.id) || []) : byStep.get(s.id) || [];
              const state = rows.length ? rows[rows.length - 1].status : (run.cursor > (pb?.steps.indexOf(s) ?? 0) ? "skipped" : "waiting");
              return (
                <li key={s.id} className={`tl ${s.kind}`}>
                  <div className="tl-head">
                    <span className="kind">{s.kind}</span>
                    <strong>{s.title}</strong>
                    {state === "waiting" ? <span className="pill neutral">Waiting</span> : <Pill value={s.children.length ? undefined : state} />}
                  </div>
                  {s.children.length === 0 && s.agent && <div className="muted small">{agentName(s.agent)}</div>}
                  {rows.map((r) => <StepDetail key={r.id} row={r} agentName={agentName} />)}
                </li>
              );
            })}
          </ol>
          {run.notes.length > 0 && (
            <div className="card">
              <span className="label">Run notes</span>
              <ul className="plain small">{run.notes.map((n, i) => <li key={i}><NoteText text={n} /></li>)}</ul>
            </div>
          )}
        </section>

        <section className="stack" aria-label="Deliverable">
          <h2>Deliverable</h2>
          {run.deliverable ? <article className="card doc"><Markdown text={run.deliverable} /></article>
            : <p className="muted">{run.status === "awaiting_approval" ? (pending.some((a) => a.step_id.startsWith("input:")) ? "Waiting for your answers in the panel above." : "Waiting for approval. The draft is in the approval panel above.") : LIVE.has(run.status) ? "Working…" : "No deliverable."}</p>}
        </section>
      </div>
    </div>
  );
}

function StepDetail({ row, agentName }: { row: StepRow; agentName: (id: string | null) => string }) {
  const h = row.output?.handoff;
  const label = row.attempt === 99 ? "Edited at approval" : row.attempt > 1 ? `Revision ${row.attempt}` : null;
  return (
    <details className="step-detail" open={row.status === "BLOCKED" || row.status === "error"}>
      <summary>
        {row.parent && <strong>{agentName(row.agent)} </strong>}
        {label && <span className="tag">{label}</span>}
        <Pill value={row.status} />
        {h?.verdict && <Pill value={h.verdict} title="Review verdict" />}
        {row.model && <span className="muted small"> {row.model}</span>}
        {row.tokens_in + row.tokens_out > 0 && <span className="muted small"> · {(row.tokens_in + row.tokens_out).toLocaleString()} tok · {fmtCost(row.cost_usd)} · {(row.latency_ms / 1000).toFixed(1)}s</span>}
        {row.warnings.length > 0 && <span className="pill warn">{row.warnings.length} note{row.warnings.length > 1 ? "s" : ""}</span>}
      </summary>
      <div className="stack-sm">
        {row.error && <div className="note bad small">{row.error}</div>}
        {h?.summary && <p><strong>{h.summary}</strong></p>}
        {h?.findings && h.findings.length > 0 && <ul className="small">{h.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>}
        {row.tool_calls.length > 0 && (
          <div className="small"><span className="label">Tool calls</span>
            <ul className="plain">{row.tool_calls.map((t, i) => <li key={i}><code>{t.tool}</code> {t.error ? <span className="pill bad">error</span> : `${t.chars.toLocaleString()} chars`}</li>)}</ul>
          </div>
        )}
        {row.warnings.length > 0 && <ul className="small warn-list">{row.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
        {row.deliverable && <div className="step-output"><Markdown text={row.deliverable} /></div>}
      </div>
    </details>
  );
}

type InputNeed = { step: string; title: string; agent?: string; questions: string[] };

/** "Your input is needed": the questions an agent asked, a box for each answer, and a way to go on without. */
export function InputPanel({ approval, onDone }: { approval: Approval; onDone: () => void }) {
  const need: InputNeed[] = (() => { try { return JSON.parse(approval.payload || "[]"); } catch { return []; } })();
  const total = need.reduce((n, x) => n + x.questions.length, 0);
  const [answers, setAnswers] = useState<string[]>(() => Array(total).fill(""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function send(skip: boolean) {
    setBusy(true); setError(null);
    try {
      let by = "";
      try { by = localStorage.getItem("suite.approver") || ""; } catch { /* ignore */ }
      await api.answer(approval.id, { answers, skip, by });
      onDone();
    } catch (e) { setError(e); setBusy(false); }
  }
  let i = -1;
  return (
    <section className="card gate input-needed stack" aria-labelledby={`in-${approval.id}`}>
      <div className="stack-xs">
        <h2 id={`in-${approval.id}`}>Your input is needed</h2>
        <p className="small muted">{approval.instructions}</p>
      </div>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); send(false); }}>
        {need.map((n) => (
          <fieldset key={n.step} className="plain stack-sm">
            <legend className="small"><strong>{n.title}</strong></legend>
            {n.questions.map((q) => {
              i += 1;
              const k = i;
              return (
                <div key={k} className="field">
                  <label htmlFor={`${approval.id}-q${k}`}>{q}</label>
                  <textarea id={`${approval.id}-q${k}`} rows={2} value={answers[k]}
                    onChange={(e) => setAnswers((a) => a.map((x, j) => (j === k ? e.target.value : x)))} placeholder="Your answer (leave blank if you do not know)" />
                </div>
              );
            })}
          </fieldset>
        ))}
        <ErrorNote error={error} />
        <div className="row-tight">
          <button className="primary" type="submit" disabled={busy || answers.every((a) => !a.trim())}>{busy ? "Sending…" : "Send answers and continue"}</button>
          <button type="button" className="ghost" disabled={busy} onClick={() => send(true)}>Continue without answering</button>
        </div>
      </form>
    </section>
  );
}

export function ApprovalPanel({ approval, onDone }: { approval: Approval; onDone: () => void }) {
  if (approval.step_id.startsWith("input:")) return <InputPanel approval={approval} onDone={onDone} />;
  return <DecisionPanel approval={approval} onDone={onDone} />;
}

function DecisionPanel({ approval, onDone }: { approval: Approval; onDone: () => void }) {
  const [name, setName] = useState(() => { try { return localStorage.getItem("suite.approver") || ""; } catch { return ""; } });
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState(approval.payload || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function decide(decision: "approved" | "rejected") {
    setBusy(true); setError(null);
    try {
      try { localStorage.setItem("suite.approver", name); } catch { /* ignore */ }
      await api.decide(approval.id, { decision, decided_by: name, note, edited: editing && edited !== approval.payload ? edited : null });
      onDone();
    } catch (e) { setError(e); setBusy(false); }
  }

  return (
    <section className="card approval" aria-label="Approval needed">
      <div className="stack-sm">
        <span className="label">Approval needed{approval.required_role ? ` · ${approval.required_role}` : ""}</span>
        <h2>{approval.title}</h2>
        {approval.instructions && <p className="muted">{approval.instructions}</p>}
      </div>
      {approval.payload && (
        editing ? (
          <textarea className="mono" rows={16} value={edited} onChange={(e) => setEdited(e.target.value)} aria-label="Edit before approving" />
        ) : (
          <div className="approval-payload"><Markdown text={approval.payload} /></div>
        )
      )}
      <div className="approval-form">
        <div className="field">
          <label htmlFor={`ap-name-${approval.id}`}>Your name</label>
          <input id={`ap-name-${approval.id}`} value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field grow">
          <label htmlFor={`ap-note-${approval.id}`}>Note (optional)</label>
          <input id={`ap-note-${approval.id}`} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
      <ErrorNote error={error} />
      <div className="row">
        <button className="primary" disabled={busy || !name.trim()} onClick={() => decide("approved")}>{editing ? "Approve edited version" : "Approve"}</button>
        <button disabled={busy || !name.trim()} onClick={() => decide("rejected")}>Reject</button>
        {approval.payload && <button className="ghost" onClick={() => setEditing(!editing)}>{editing ? "Discard edits" : "Edit before approving"}</button>}
      </div>
    </section>
  );
}
