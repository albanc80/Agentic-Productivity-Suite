import { isLive, openConnectors, shortName } from "../connectors";
import { useEffect, useMemo, useState } from "react";
import { api, type Overview, type PlaybookInput, type RunDetail } from "../api";
import { ErrorNote, go } from "../ui";

const prefills: Record<string, Record<string, unknown>> = {};
export function setPrefill(pid: string, values: Record<string, unknown>) { prefills[pid] = values; }

const DATA_CLASS_HELP: Record<string, string> = {
  public: "Published or shareable information.",
  internal: "Normal work content.",
  confidential: "Sensitive business content. Check your organisation allows the providers listed.",
  restricted: "Highly sensitive. Sent only to local models.",
};

function initial(inp: PlaybookInput, pre: Record<string, unknown>) {
  if (pre[inp.id] !== undefined) return pre[inp.id];
  if (inp.default !== null && inp.default !== undefined) return inp.default;
  return inp.type === "multiselect" || inp.type === "documents" ? [] : "";
}

type FileRef = { id: string; name: string; chars: number };

/** Library → Edit and run as new: the start form filled in from an earlier run, with corrections. */
export function ReviseForm({ ov, runId }: { ov: Overview; runId: string }) {
  const [from, setFrom] = useState<{ run: RunDetail; files: Record<string, FileRef[]> } | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    (async () => {
      try {
        const run = await api.run(runId);
        const pb = ov.playbooks.find((p) => p.id === run.playbook_id);
        const files: Record<string, FileRef[]> = {};
        for (const inp of pb?.inputs || []) {
          if (inp.type !== "documents") continue;
          const ids = (run.inputs[inp.id] as string[] | undefined) || [];
          files[inp.id] = (await Promise.all(ids.map((id) => api.fileInfo(id).catch(() => null)))).filter((f): f is FileRef => !!f);
        }
        setFrom({ run, files });
      } catch (e) { setError(e); }
    })();
  }, [runId]);
  if (error) return <ErrorNote error={error} />;
  if (!from) return <p className="muted">Loading the earlier run…</p>;
  return <RunForm ov={ov} playbookId={from.run.playbook_id} from={from} />;
}

export default function RunForm({ ov, playbookId, from }: { ov: Overview; playbookId: string;
  from?: { run: RunDetail; files: Record<string, FileRef[]> } }) {
  const pb = ov.playbooks.find((p) => p.id === playbookId);
  const pre = from ? from.run.inputs : prefills[playbookId] || {};
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries((pb?.inputs || []).map((i) => [i.id, initial(i, pre)])));
  const [files, setFiles] = useState<Record<string, FileRef[]>>(from?.files || {});
  const [dataClass, setDataClass] = useState(from?.run.data_class || ov.default_data_class);
  const [persona, setPersona] = useState(typeof from?.run.options.persona === "boolean" ? from.run.options.persona as boolean
    : pb?.style === "chat" ? ov.persona.chat : ov.persona.exports);
  const [corrections, setCorrections] = useState("");
  const [withPrevious, setWithPrevious] = useState(!!from?.run.deliverable);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const allowed = ov.data_classes[dataClass] || [];
  const reachable = useMemo(() => ov.providers.filter((p) => p.available && allowed.includes(p.locality)), [ov, allowed]);
  const chosen = (id: string) => {  // a connector the form can leave out counts only while its option is ticked
    const w = pb?.connector_choice?.[id];
    const v = w ? values[w.input] : undefined;
    return !w || (Array.isArray(v) ? v.includes(w.contains) : v === w.contains);
  };
  const missing = (pb?.connectors || []).filter((id) => {
    const c = ov.connectors.find((x) => x.id === id);
    return chosen(id) && (!c || !isLive(c));
  });

  if (!pb) return <p>Playbook not found. <a href="#/playbooks">Back to playbooks</a></p>;

  const set = (id: string, v: unknown) => setValues((s) => ({ ...s, [id]: v }));

  async function addFiles(id: string, list: FileList | null) {
    if (!list) return;
    setError(null);
    try {
      const uploaded: { id: string; name: string; chars: number }[] = [];
      for (const f of Array.from(list)) uploaded.push(await api.upload(f));
      setFiles((s) => ({ ...s, [id]: [...(s[id] || []), ...uploaded] }));
    } catch (e) { setError(e); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    const inputs: Record<string, unknown> = { ...values };
    for (const inp of pb!.inputs) if (inp.type === "documents") inputs[inp.id] = (files[inp.id] || []).map((f) => f.id);
    try {
      const { id } = from
        ? await api.rerun(from.run.id, { inputs, data_class: dataClass, persona, corrections, include_previous: withPrevious })
        : await api.startRun(pb!.id, inputs, dataClass, { persona });
      delete prefills[pb!.id];
      go(`/runs/${id}`);
    } catch (err) { setError(err); setBusy(false); }
  }

  return (
    <form className="stack-lg form" onSubmit={submit}>
      <header className="stack-sm">
        {from ? <a href={`#/runs/${from.run.id}`} className="small">← Back to the earlier run</a> : <a href="#/playbooks" className="small">← Playbooks</a>}
        <span className="code">{pb.code} · {pb.area}</span>
        <h1>{from ? `Revise: ${from.run.title}` : pb.name}</h1>
        <p className="muted measure">{from
          ? "Filled in from the earlier run. Change any input, remove or add files, and say what to correct. It runs as a new run; the earlier one stays in the Library."
          : pb.summary}</p>
      </header>

      <div className="form-grid">
        <div className="stack">
          {pb.inputs.map((inp) => (
            <div key={inp.id} className="field">
              <label htmlFor={`f-${inp.id}`}>{inp.label}{inp.required && <span className="req" aria-label="required"> *</span>}</label>
              {inp.type === "longtext" && (
                <textarea id={`f-${inp.id}`} rows={inp.example ? 4 : inp.required ? 4 : 5} value={String(values[inp.id] ?? "")}
                  className={inp.example.trim().startsWith("{") ? "mono" : undefined} spellCheck={!inp.example}
                  placeholder={inp.example || undefined}
                  onChange={(e) => set(inp.id, e.target.value)} required={inp.required} />
              )}
              {(inp.type === "text" || inp.type === "date") && (
                <input id={`f-${inp.id}`} type="text" value={String(values[inp.id] ?? "")} onChange={(e) => set(inp.id, e.target.value)} required={inp.required} />
              )}
              {inp.type === "number" && (
                <input id={`f-${inp.id}`} type="number" min="0" step="any" value={String(values[inp.id] ?? "")} onChange={(e) => set(inp.id, e.target.value)} required={inp.required} />
              )}
              {inp.type === "select" && (
                <select id={`f-${inp.id}`} value={String(values[inp.id] ?? "")} onChange={(e) => set(inp.id, e.target.value)}>
                  {inp.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {inp.type === "multiselect" && (
                <div className="checks" id={`f-${inp.id}`} role="group">
                  {inp.options.map((o) => {
                    const cur = (values[inp.id] as string[]) || [];
                    return (
                      <label key={o} className="check">
                        <input type="checkbox" checked={cur.includes(o)}
                          onChange={(e) => set(inp.id, e.target.checked ? [...cur, o] : cur.filter((x) => x !== o))} />
                        {o}
                      </label>
                    );
                  })}
                </div>
              )}
              {inp.type === "documents" && (
                <div className="stack-sm">
                  <input id={`f-${inp.id}`} type="file" multiple accept=".txt,.md,.csv,.json,.yaml,.yml,.log,.pdf,.docx,.xlsx"
                    onChange={(e) => addFiles(inp.id, e.target.files)} />
                  {(files[inp.id] || []).map((f) => (
                    <span key={f.id} className="small muted file-row">{f.name} · {f.chars.toLocaleString()} characters{" "}
                      <button type="button" className="link-btn" aria-label={`Remove ${f.name}`}
                        onClick={() => setFiles((s) => ({ ...s, [inp.id]: (s[inp.id] || []).filter((x) => x.id !== f.id) }))}>Remove</button>
                    </span>
                  ))}
                </div>
              )}
              {inp.help && <span className="help">{inp.help}</span>}
            </div>
          ))}
          {from && (
            <div className="field card revise-box">
              <label htmlFor="f-corrections">What to correct</label>
              <textarea id="f-corrections" rows={5} value={corrections} onChange={(e) => setCorrections(e.target.value)}
                placeholder="e.g. The launch date is March, not May. Use the attached v2 budget. Shorter executive summary." />
              <label className="check">
                <input type="checkbox" checked={withPrevious} disabled={!from.run.deliverable} onChange={(e) => setWithPrevious(e.target.checked)} />
                Give the agents the earlier result to correct
              </label>
              <span className="help">{from.run.deliverable
                ? "They keep what is right and fix what your corrections and changed inputs say. Your corrections override the earlier result."
                : "The earlier run has no result to correct, so it starts from your inputs and corrections."}</span>
            </div>
          )}
        </div>

        <aside className="card stack side">
          <div className="field">
            <label htmlFor="dc">Data class</label>
            <select id="dc" value={dataClass} onChange={(e) => setDataClass(e.target.value)}>
              {Object.keys(ov.data_classes).map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <span className="help">{DATA_CLASS_HELP[dataClass]}</span>
          </div>
          <div>
            <span className="label">This run can reach</span>
            {reachable.length ? (
              <ul className="plain small">
                {reachable.map((p) => <li key={p.name}><strong>{p.name}</strong> <span className="muted">({p.locality})</span></li>)}
              </ul>
            ) : <p className="note bad small">No configured model is allowed for this data class. The run will stop at its first step.</p>}
          </div>
          {pb.safety_critical && (
            <p className="note warn small">Safety-critical. Output is planning-grade and advisory. A qualified engineer signs off before use.</p>
          )}
          {missing.length > 0 && (
            <p className="note small">Not connected: {missing.map((id) => shortName(ov, id)).join(", ")}. This playbook's steps can only use the connectors it requires, so agents will work from what you paste or upload.{" "}
              <button type="button" className="link-btn" onClick={openConnectors}>Set them up in Settings → Connectors</button></p>
          )}
          <label className="check">
            <input type="checkbox" checked={persona} onChange={(e) => setPersona(e.target.checked)} />
            Use agent personas
          </label>
          <p className="help">Nothing is sent, published or written by this run. Outbound drafts wait for approval.</p>
          <ErrorNote error={error} />
          <button className="primary block" type="submit" disabled={busy}>{busy ? "Starting…" : from ? "Run as new" : "Start run"}</button>
        </aside>
      </div>
    </form>
  );
}
