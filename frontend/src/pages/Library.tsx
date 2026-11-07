import { useEffect, useMemo, useState } from "react";
import { api, type Overview, type RunSummary } from "../api";
import { Empty, ErrorNote, Pill, fmtTime } from "../ui";

export default function Library({ ov }: { ov: Overview }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState("");
  const [pb, setPb] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);  // run id, or "demo" for the bulk delete
  const [busy, setBusy] = useState(false);

  const load = () => api.runs().then(setRuns).catch(setError);
  useEffect(() => { load(); }, []);
  const demoCount = (runs || []).filter((r) => r.demo).length;
  const active = (r: RunSummary) => r.status === "running" || r.status === "queued";

  async function remove(id: string) {
    setBusy(true); setError(null);
    try { id === "demo" ? await api.deleteDemoRuns() : await api.deleteRun(id); setConfirm(null); await load(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  const shown = useMemo(() => (runs || []).filter((r) =>
    (!pb || r.playbook_id === pb) && (!filter || r.title.toLowerCase().includes(filter.toLowerCase()))), [runs, filter, pb]);

  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Library</h1>
        <p className="muted">Every run with its deliverable, approvals and audit trail. Deleting a run removes it and its steps; the audit log keeps a record.</p>
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
      {demoCount > 0 && (
        <div className="banner warn row">
          <span className="grow">{demoCount} run{demoCount === 1 ? " was" : "s were"} made by the demo provider of an earlier version. No model produced {demoCount === 1 ? "it" : "them"}.</span>
          {confirm === "demo"
            ? <><button className="danger" onClick={() => remove("demo")} disabled={busy}>Delete {demoCount}</button><button className="ghost" onClick={() => setConfirm(null)}>Keep</button></>
            : <button onClick={() => setConfirm("demo")}>Delete demo runs ({demoCount})</button>}
        </div>
      )}
      <ErrorNote error={error} />
      {runs && shown.length === 0 && <Empty title="No runs yet">Start one from Command or Playbooks.</Empty>}
      {shown.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Playbook</th><th>Status</th><th>Data</th><th className="num">Tokens</th><th>Started</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td><a href={`#/runs/${r.id}`}>{r.title}</a>{r.demo && <span className="tag">old demo</span>}</td>
                  <td>{ov.playbooks.find((p) => p.id === r.playbook_id)?.code}</td>
                  <td><Pill value={r.status === "completed" ? r.outcome : r.status} /></td>
                  <td>{r.data_class}</td>
                  <td className="num">{r.tokens.toLocaleString()}</td>
                  <td className="nowrap">{fmtTime(r.created_at)}</td>
                  <td className="nowrap">
                    {confirm === r.id
                      ? <span className="row-tight"><button className="danger" onClick={() => remove(r.id)} disabled={busy}>Delete</button><button className="ghost" onClick={() => setConfirm(null)}>Keep</button></span>
                      : <button className="ghost" onClick={() => setConfirm(r.id)} disabled={active(r)} title={active(r) ? "Stop the run before deleting it" : undefined}
                          aria-label={`Delete run ${r.title}`}>Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
