import { useEffect, useMemo, useState } from "react";
import { api, type Overview, type RunSummary } from "../api";
import { Empty, ErrorNote, Pill, fmtCost, fmtTime } from "../ui";

export default function Library({ ov }: { ov: Overview }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState("");
  const [pb, setPb] = useState("");

  useEffect(() => { api.runs().then(setRuns).catch(setError); }, []);
  const shown = useMemo(() => (runs || []).filter((r) =>
    (!pb || r.playbook_id === pb) && (!filter || r.title.toLowerCase().includes(filter.toLowerCase()))), [runs, filter, pb]);

  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Library</h1>
        <p className="muted">Every run with its deliverable, approvals and audit trail.</p>
      </header>
      <div className="row filters">
        <label className="sr-only" htmlFor="lib-q">Search titles</label>
        <input id="lib-q" placeholder="Search titles" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <label className="sr-only" htmlFor="lib-pb">Playbook</label>
        <select id="lib-pb" value={pb} onChange={(e) => setPb(e.target.value)}>
          <option value="">All playbooks</option>
          {ov.playbooks.map((p) => <option key={p.id} value={p.id}>{p.code} {p.name}</option>)}
        </select>
      </div>
      <ErrorNote error={error} />
      {runs && shown.length === 0 && <Empty title="No runs yet">Start one from Command or Playbooks.</Empty>}
      {shown.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Playbook</th><th>Status</th><th>Data</th><th className="num">Tokens</th><th className="num">Cost</th><th>Started</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td><a href={`#/runs/${r.id}`}>{r.title}</a>{r.demo && <span className="tag">demo</span>}</td>
                  <td>{ov.playbooks.find((p) => p.id === r.playbook_id)?.code}</td>
                  <td><Pill value={r.status === "completed" ? r.outcome : r.status} /></td>
                  <td>{r.data_class}</td>
                  <td className="num">{r.tokens.toLocaleString()}</td>
                  <td className="num">{fmtCost(r.cost_usd)}</td>
                  <td className="nowrap">{fmtTime(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
