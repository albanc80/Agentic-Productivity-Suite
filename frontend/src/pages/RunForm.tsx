import { isLive, openConnectors, shortName } from "../connectors";
import { useMemo, useState } from "react";
import { api, type Overview, type PlaybookInput } from "../api";
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

export default function RunForm({ ov, playbookId }: { ov: Overview; playbookId: string }) {
  const pb = ov.playbooks.find((p) => p.id === playbookId);
  const pre = prefills[playbookId] || {};
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries((pb?.inputs || []).map((i) => [i.id, initial(i, pre)])));
  const [files, setFiles] = useState<Record<string, { id: string; name: string; chars: number }[]>>({});
  const [dataClass, setDataClass] = useState(ov.default_data_class);
  const [persona, setPersona] = useState(pb?.style === "chat" ? ov.persona.chat : ov.persona.exports);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const allowed = ov.data_classes[dataClass] || [];
  const reachable = useMemo(() => ov.providers.filter((p) => p.available && allowed.includes(p.locality)), [ov, allowed]);
  const missing = (pb?.connectors || []).filter((id) => {
    const c = ov.connectors.find((x) => x.id === id);
    return !c || !isLive(c);
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
      const { id } = await api.startRun(pb!.id, inputs, dataClass, { persona });
      delete prefills[pb!.id];
      go(`/runs/${id}`);
    } catch (err) { setError(err); setBusy(false); }
  }

  return (
    <form className="stack-lg form" onSubmit={submit}>
      <header className="stack-sm">
        <a href="#/playbooks" className="small">← Playbooks</a>
        <span className="code">{pb.code} · {pb.area}</span>
        <h1>{pb.name}</h1>
        <p className="muted measure">{pb.summary}</p>
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
                  {(files[inp.id] || []).map((f) => <span key={f.id} className="small muted">{f.name} · {f.chars.toLocaleString()} characters</span>)}
                </div>
              )}
              {inp.help && <span className="help">{inp.help}</span>}
            </div>
          ))}
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
          <button className="primary block" type="submit" disabled={busy}>{busy ? "Starting…" : "Start run"}</button>
        </aside>
      </div>
    </form>
  );
}
