import { useEffect, useRef, useState } from "react";
import { api, type ChatDetail, type ChatMsg, type ChatSummary, type Overview } from "../api";
import { ErrorNote, Markdown, fmtCost, fmtTime, go } from "../ui";

const COORDINATOR = "chief-of-staff";

function modelFor(ov: Overview, agentId: string): string {
  if (ov.offline) return ov.offline_default ? `${ov.offline_default} (offline default)` : "no local model available";
  const pick = ov.agent_models[agentId];
  if (pick) return pick;
  const agent = ov.agents.find((a) => a.id === agentId);
  const chain = ov.tiers[agent?.default_tier || "specialist"] || [];
  const ready = new Set(ov.providers.filter((p) => p.available).map((p) => p.name));
  return chain.find((r) => ready.has(r.split("/")[0])) || "no model available";
}

/** Talk to the Chief of Staff (who answers or asks specialists) or to any single agent. */
export default function ChatPage({ ov, chatId }: { ov: Overview; chatId: string }) {
  const [list, setList] = useState<ChatSummary[] | null>(null);
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [agentId, setAgentId] = useState(COORDINATOR);
  const [dataClass, setDataClass] = useState(ov.default_data_class);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<{ id: string; name: string }[]>([]);
  const [busy, setBusy] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const alive = useRef(true);  // false once the user has moved to another chat
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const loadList = () => api.chats().then(setList).catch(setError);
  useEffect(() => { loadList(); }, []);
  // A question typed on Command ("Ask the Chief of Staff") arrives as a draft and is sent straight away.
  const [draftSent, setDraftSent] = useState(false);
  useEffect(() => {
    if (draftSent || chatId) return;
    let draft = "";
    try { draft = sessionStorage.getItem("suite.chatDraft") || ""; sessionStorage.removeItem("suite.chatDraft"); } catch { /* storage unavailable */ }
    setDraftSent(true);
    if (draft.trim()) send(undefined, draft);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    setChat(null); setError(null); setConfirmDelete(false);
    if (chatId) api.chat(chatId).then(setChat).catch(setError);
  }, [chatId]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [chat?.messages.length, pending]);

  async function send(e?: React.FormEvent, preset?: string) {
    e?.preventDefault();
    const content = (preset ?? text).trim();
    if (!content || busy) return;
    setBusy("send"); setError(null); setPending(content); setText("");
    try {
      let target = chat;
      if (!target) target = await api.startChat(agentId, dataClass);
      await api.sendChat(target.id, content, files.map((f) => f.id));
      if (!alive.current) return;  // the user switched chats while this one was answering: leave them where they are
      setFiles([]);
      const fresh = await api.chat(target.id);
      if (!alive.current) return;
      setChat(fresh);
      if (!chat) go(`/chat/${target.id}`);
      loadList();
    } catch (err) { if (alive.current) { setError(err); setText(content); } } finally { if (alive.current) { setBusy(""); setPending(null); } }
  }
  async function attach(fl: FileList | null) {
    if (!fl) return;
    setBusy("upload"); setError(null);
    try {
      for (const f of Array.from(fl)) {
        const r = await api.upload(f);
        if (!alive.current) return;
        setFiles((x) => [...x, { id: r.id, name: r.name }]);
      }
    } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function remove() {
    if (!chat) return;
    try { await api.deleteChat(chat.id); setConfirmDelete(false); go("/chat"); loadList(); } catch (e) { setError(e); }
  }

  const activeAgent = chat?.agent_id || agentId;
  const agent = ov.agents.find((a) => a.id === activeAgent);
  const isCoordinator = activeAgent === COORDINATOR;
  const working = isCoordinator ? "The Chief of Staff is answering or asking specialists…" : `${agent?.name} is answering…`;

  return (
    <div className="chat-layout">
      <aside className="chat-side stack-sm" aria-label="Conversations">
        <button className="primary" onClick={() => { go("/chat"); setChat(null); }}>New chat</button>
        <ul className="plain chat-list">
          {(list || []).map((c) => (
            <li key={c.id}>
              <a href={`#/chat/${c.id}`} className={c.id === chatId ? "active" : ""} aria-current={c.id === chatId ? "page" : undefined}>
                <strong>{c.title}</strong>
                <span className="muted small">{ov.agents.find((a) => a.id === c.agent_id)?.name} · {fmtTime(c.updated_at)}</span>
              </a>
            </li>
          ))}
          {list && list.length === 0 && <li className="muted small">No conversations yet.</li>}
        </ul>
      </aside>

      <section className="chat-main stack" aria-label="Conversation">
        <header className="chat-head">
          {chat ? (
            <div className="grow stack-xs">
              <h1 className="chat-title">{chat.title}</h1>
              <span className="muted small">{agent?.name} · data class {chat.data_class} · model {modelFor(ov, chat.agent_id)} · {chat.tokens.toLocaleString()} tokens · {fmtCost(chat.cost_usd)}</span>
            </div>
          ) : (
            <div className="grow stack-sm">
              <h1 className="chat-title">Chat</h1>
              <p className="muted small measure">Ask anything, even if no playbook covers it. The Chief of Staff answers directly or asks up to three specialists and combines their answers. Or pick one agent to talk to.</p>
              <div className="ep-row">
                <div className="field grow">
                  <label htmlFor="chat-agent">Talk to</label>
                  <select id="chat-agent" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                    <option value={COORDINATOR}>Chief of Staff (answers or delegates)</option>
                    {ov.desks.map((d) => (
                      <optgroup key={d.id} label={d.name}>
                        {d.members.filter((m) => m !== COORDINATOR).map((m) => {
                          const a = ov.agents.find((x) => x.id === m);
                          return a ? <option key={m} value={m}>{a.name}</option> : null;
                        })}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="chat-dc">Data class</label>
                  <select id="chat-dc" value={dataClass} onChange={(e) => setDataClass(e.target.value)}>
                    {Object.keys(ov.data_classes).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              </div>
              <span className="help">Model: {modelFor(ov, agentId)}. {dataClass === "restricted" ? "Restricted: only local models see this chat." : ""}</span>
            </div>
          )}
          {chat && (confirmDelete
            ? <span className="row-tight"><button className="danger" onClick={remove}>Delete chat</button><button className="ghost" onClick={() => setConfirmDelete(false)}>Keep</button></span>
            : <button className="ghost" onClick={() => setConfirmDelete(true)}>Delete</button>)}
        </header>

        <div className="chat-thread" aria-live="polite">
          {chat?.messages.map((m, i) => <Message key={i} m={m} ov={ov} />)}
          {pending && <div className="msg user"><div className="bubble"><p>{pending}</p></div></div>}
          {busy === "send" && <div className="msg assistant"><div className="bubble thinking"><span className="pill live">Working</span> {working}</div></div>}
          {!chat && !pending && (
            <div className="chat-empty muted small">
              <p>Examples: "What should I focus on this week given these notes?" · "Compare two vendors for field data capture" · "Explain the risks of moving our historian to the cloud".</p>
            </div>
          )}
          <div ref={end} />
        </div>

        <ErrorNote error={error} />
        <form className="chat-compose" onSubmit={send}>
          <label htmlFor="chat-text" className="sr-only">Message</label>
          <textarea id="chat-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} disabled={busy === "send"}
            placeholder={isCoordinator ? "Ask the Chief of Staff…" : `Ask ${agent?.name}…`}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
          <div className="command-bar">
            <div className="row-tight">
              <label className="file-btn">
                <input type="file" multiple onChange={(e) => { attach(e.target.files); e.target.value = ""; }}
                  accept=".txt,.md,.csv,.json,.yaml,.yml,.log,.xml,.html,.tsv,.sql,.pdf,.docx,.xlsx" />
                {busy === "upload" ? "Uploading…" : "Attach files"}
              </label>
              {files.map((f) => (
                <span key={f.id} className="tag">{f.name} <button type="button" className="link-btn" aria-label={`Remove ${f.name}`}
                  onClick={() => setFiles((x) => x.filter((y) => y.id !== f.id))}>×</button></span>
              ))}
            </div>
            <span className="muted small"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
            <button className="primary cut" type="submit" disabled={!text.trim() || !!busy}>{busy === "send" ? "Sending…" : "Send"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Message({ m, ov }: { m: ChatMsg; ov: Overview }) {
  const name = (id?: string) => ov.agents.find((a) => a.id === id)?.name || id;
  if (m.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble">
          <p className="pre">{m.content}</p>
          {m.files && m.files.length > 0 && <div className="tags">{m.files.map((f) => <span key={f.id} className="tag outline">{f.name}</span>)}</div>}
        </div>
      </div>
    );
  }
  return (
    <div className="msg assistant">
      <div className="bubble">
        <div className="msg-meta small muted">{name(m.agent)} · {m.model}{m.seconds != null ? ` · ${m.seconds}s` : ""}{m.tokens ? ` · ${m.tokens.toLocaleString()} tokens` : ""}</div>
        <Markdown text={m.content} />
        {m.delegations && m.delegations.length > 0 && (
          <details className="delegations">
            <summary>Asked {m.delegations.length} specialist{m.delegations.length > 1 ? "s" : ""}: {m.delegations.map((d) => name(d.agent)).join(", ")}</summary>
            {m.delegations.map((d, i) => (
              <div key={i} className="delegation">
                <div className="small"><strong>{name(d.agent)}</strong> <span className="muted">· {d.model || "no model"}</span></div>
                <p className="small muted">Q: {d.question}</p>
                {d.error ? <p className="note bad small">{d.error}</p> : <Markdown text={d.answer} />}
              </div>
            ))}
          </details>
        )}
        {m.suggested_playbook && (
          <p className="note small">For a governed result with review and approval, run <a href={`#/start/${m.suggested_playbook.id}`}>{m.suggested_playbook.code} {m.suggested_playbook.name}</a>.</p>
        )}
        {(() => {
          const fits = (m.warnings || []).filter((w) => w.includes("context fit"));
          const other = (m.warnings || []).filter((w) => !w.includes("context fit"));
          return <>
            {other.length > 0 && <ul className="small warn-list">{other.map((w, i) => <li key={i}>{w}</li>)}</ul>}
            {fits.length > 0 && (
              <details className="small muted fit-notes">
                <summary>Prompt shortened to fit the model's context ({fits.length} note{fits.length > 1 ? "s" : ""})</summary>
                <ul>{fits.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </details>
            )}
          </>;
        })()}
      </div>
    </div>
  );
}
