import { useCallback, useEffect, useState } from "react";
import { api, type Approval } from "../api";
import { Empty, ErrorNote, Pill, fmtTime } from "../ui";
import { ApprovalPanel } from "./RunView";

export default function Approvals({ onChange }: { onChange: () => void }) {
  const [pending, setPending] = useState<Approval[] | null>(null);
  const [history, setHistory] = useState<Approval[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setPending(await api.approvals("pending"));
      setHistory((await api.approvals("")).filter((a) => a.status !== "pending").slice(0, 30));
    } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Approvals</h1>
        <p className="muted measure">Runs pause here before anything would leave the suite, and when an agent needs information only you can give. Approving records your name and decision; a run that needs your input waits until you answer, choose Ignore and continue, or stop it. The suite itself never sends, publishes or writes to other systems.</p>
      </header>
      <ErrorNote error={error} />
      {pending && pending.length === 0 && <Empty title="Nothing waiting for you">Gates in Status Update, Scope-Change, Architecture Review and Investment Case land here.</Empty>}
      {pending?.map((a) => (
        <div key={a.id} className="stack-sm">
          <a href={`#/runs/${a.run_id}`} className="small">{a.run_title} →</a>
          <ApprovalPanel approval={a} onDone={() => { load(); onChange(); }} />
        </div>
      ))}
      {history.length > 0 && (
        <section className="stack">
          <h2>Decided</h2>
          <ul className="list">
            {history.map((a) => (
              <li key={a.id}><a href={`#/runs/${a.run_id}`}>
                <span className="grow"><strong>{a.title}</strong><span className="muted small"> · {a.run_title}</span></span>
                <Pill value={a.status} />
                <span className="muted small nowrap">{a.decided_by} · {fmtTime(a.decided_at)}</span>
              </a></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
