import { isLive, openConnectors, shortName } from "../connectors";
import { useEffect, useRef, useState } from "react";
import { api, downloadAnswer, exportAnswer, type ChatDetail, type ExportResult, type ChatMsg, type ChatSummary, type Overview } from "../api";
import { EnterHint, ErrorNote, ExportNote, Markdown, NoteText, enterSends, fmtTime, go } from "../ui";

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
/** "3 lookups in Google Workspace, GitHub": how many connector calls an answer made, and in which connectors. */
function lookups(ov: Overview, calls: { connector?: string }[]): string {
  const used = [...new Set(calls.map((c) => c.connector).filter(Boolean) as string[])].map((id) => shortName(ov, id));
  return `${calls.length} lookup${calls.length > 1 ? "s" : ""}${used.length ? ` in ${used.join(", ")}` : ""}`;
}

export default function ChatPage({ ov, chatId }: { ov: Overview; chatId: string }) {
  const [list, setList] = useState<ChatSummary[] | null>(null);
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [agentId, setAgentId] = useState(COORDINATOR);
  const [dataClass, setDataClass] = useState(ov.default_data_class);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<{ id: string; name: string }[]>([]);
  const [busy, setBusy] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [offDraft, setOffDraft] = useState<string[]>([]);  // connectors switched off before the chat exists
  const end = useRef<HTMLDivElement>(null);
  const current = useRef(chatId);  // the chat on screen; replies for another chat are not shown here
  useEffect(() => { current.current = chatId; }, [chatId]);

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
    if (chatId) api.chat(chatId).then((c) => { if (current.current === chatId) setChat(c); }).catch(setError);
  }, [chatId]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [chat?.messages.length, chat?.messages.at(-1)?.status]);

  // While a message waits for or gets its answer, refresh the chat (and the list) until the answer is in.
  const working = !!chat?.messages.some((m) => m.status);
  useEffect(() => {
    if (!chat || !working) return;
    const id = chat.id;
    const t = setInterval(async () => {
      try {
        const fresh = await api.chat(id);
        if (current.current !== id) return;
        setChat(fresh);
        if (!fresh.messages.some((m) => m.status)) loadList();
      } catch { /* the next tick tries again */ }
    }, 1200);
    return () => clearInterval(t);
  }, [chat?.id, working]);

  /** New chat makes the chat at once (reusing one still unused) so it has its own place in the list. */
  async function newChat() {
    setError(null);
    const unused = (list || []).find((c) => c.messages === 0);
    if (unused) { go(`/chat/${unused.id}`); return; }
    setBusy("new");
    try {
      const c = await api.startChat(agentId, dataClass);
      await loadList();
      go(`/chat/${c.id}`);
    } catch (e) { setError(e); } finally { setBusy(""); }
  }

  async function send(e?: React.FormEvent, preset?: string) {
    e?.preventDefault();
    const content = (preset ?? text).trim();
    if (!content || busy === "send" || busy === "upload") return;
    setBusy("send"); setError(null); setText("");
    const sentFiles = files;
    try {
      let target = chat;
      if (!target) {
        target = await api.startChat(agentId, dataClass);
        if (offDraft.length) target = await api.updateChat(target.id, { connectors_off: offDraft });
      }
      const fresh = await api.sendChat(target.id, content, sentFiles.map((f) => f.id));
      setFiles([]);
      if (!chat) go(`/chat/${target.id}`);
      if (current.current === target.id || !chat) setChat(fresh);
      loadList();
    } catch (err) { setError(err); setText(content); } finally { setBusy(""); }
  }
  async function resend(index: number, content: string) {
    if (!chat) return;
    setError(null);
    try { setChat(await api.editChatMessage(chat.id, index, content)); loadList(); } catch (e) { setError(e); throw e; }
  }
  async function attach(fl: FileList | null) {
    if (!fl) return;
    setBusy("upload"); setError(null);
    try {
      for (const f of Array.from(fl)) {
        const r = await api.upload(f);
        setFiles((x) => [...x, { id: r.id, name: r.name }]);
      }
    } catch (e) { setError(e); } finally { setBusy(""); }
  }
  async function remove() {
    if (!chat) return;
    try { await api.deleteChat(chat.id); setConfirmDelete(false); go("/chat"); loadList(); } catch (e) { setError(e); }
  }
  /** Switch a connector off or on for this chat only; Settings stay as they are. The next answer uses it. */
  async function toggleConnector(id: string) {
    const off = chat ? chat.connectors_off || [] : offDraft;
    const next = off.includes(id) ? off.filter((x) => x !== id) : [...off, id];
    if (!chat) { setOffDraft(next); return; }
    try { setChat(await api.updateChat(chat.id, { connectors_off: next })); } catch (e) { setError(e); }
  }
  async function choose(body: { agent_id?: string; data_class?: string }) {
    if (body.agent_id) setAgentId(body.agent_id);
    if (body.data_class) setDataClass(body.data_class);
    if (!chat) return;
    try { setChat(await api.updateChat(chat.id, body)); loadList(); } catch (e) { setError(e); }
  }

  const activeAgent = chat?.agent_id || agentId;
  const activeClass = chat?.data_class || dataClass;
  const agent = ov.agents.find((a) => a.id === activeAgent);
  const live = ov.connectors.filter(isLive);
  const isCoordinator = activeAgent === COORDINATOR;
  const fresh = !chat || chat.messages.length === 0;  // who it talks to can still change
  const workingText = isCoordinator ? "The Chief of Staff is answering or asking specialists…" : `${agent?.name} is answering…`;

  return (
    <div className="chat-layout">
      <aside className="chat-side stack-sm" aria-label="Conversations">
        <button className="primary" onClick={newChat} disabled={busy === "new"}>{busy === "new" ? "Starting…" : "New chat"}</button>
        <ul className="plain chat-list">
          {(list || []).map((c) => (
            <li key={c.id}>
              <a href={`#/chat/${c.id}`} className={c.id === chatId ? "active" : ""} aria-current={c.id === chatId ? "page" : undefined}>
                <strong>{c.title}</strong>
                <span className="muted small">{ov.agents.find((a) => a.id === c.agent_id)?.name} · {c.busy ? <span className="ok-text">answering…</span> : fmtTime(c.updated_at)}</span>
              </a>
            </li>
          ))}
          {list && list.length === 0 && <li className="muted small">No conversations yet.</li>}
        </ul>
      </aside>

      <section className="chat-main stack" aria-label="Conversation">
        <header className="chat-head">
          {!fresh && chat ? (
            <div className="grow stack-xs">
              <h1 className="chat-title">{chat.title}</h1>
              <span className="muted small">{agent?.name} · data class {chat.data_class} · model {modelFor(ov, chat.agent_id)} · {chat.tokens.toLocaleString()} tokens{ov.budgets.enabled ? ` · limit ${ov.budgets.max_chat_tokens.toLocaleString()} tokens` : ""}</span>
            </div>
          ) : (
            <div className="grow stack-sm">
              <h1 className="chat-title">{chat ? "New chat" : "Chat"}</h1>
              <p className="muted small measure">Ask anything, even if no playbook covers it. The Chief of Staff answers directly or asks up to three specialists and combines their answers. Or pick one agent to talk to.</p>
              <div className="ep-row">
                <div className="field grow">
                  <label htmlFor="chat-agent">Talk to</label>
                  <select id="chat-agent" value={activeAgent} onChange={(e) => choose({ agent_id: e.target.value })}>
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
                  <select id="chat-dc" value={activeClass} onChange={(e) => choose({ data_class: e.target.value })}>
                    {Object.keys(ov.data_classes).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              </div>
              <span className="help">Model: {modelFor(ov, activeAgent)}. {activeClass === "restricted" ? "Restricted: only local models see this chat." : ""}</span>
            </div>
          )}
          {chat && (confirmDelete
            ? <span className="row-tight"><button className="danger" onClick={remove}>Delete chat</button><button className="ghost" onClick={() => setConfirmDelete(false)}>Keep</button></span>
            : <button className="ghost" onClick={() => setConfirmDelete(true)}>Delete</button>)}
        </header>

        <div className="chat-thread" aria-live="polite">
          {chat?.messages.map((m, i) => (
            <div key={m.id || i} className="stack-sm">
              {m.role === "user"
                ? <UserMessage m={m} index={i} canEdit={!working} onResend={resend} queuedBehind={m.status === "queued" && chat.messages.some((x) => x.status === "working")} />
                : <Message m={m} ov={ov} chatId={chat.id} index={i} restricted={chat.data_class === "restricted"} />}
              {m.status === "working" && <div className="msg assistant"><div className="bubble thinking"><span className="pill live">Working</span> {workingText}</div></div>}
            </div>
          ))}
          {fresh && (
            <div className="chat-empty muted small">
              <p>Examples: "What should I focus on this week given these notes?" · "Compare two vendors for field data capture" · "Explain the risks of moving our historian to the cloud".</p>
            </div>
          )}
          <div ref={end} />
        </div>

        <ErrorNote error={error} />
        <div className="small muted chat-connectors">
          {live.length ? <>
            <span>Agents in this chat can read:</span>{" "}
            {live.map((c) => {
              const off = (chat ? chat.connectors_off || [] : offDraft).includes(c.id);
              const label = c.name.replace(/\s*\(.*\)\s*$/, "");
              return (
                <button key={c.id} type="button" className={`chip-toggle ${off ? "off" : "on"}`} aria-pressed={!off}
                  onClick={() => toggleConnector(c.id)} title={off ? `Switched off for this chat. Click to use ${label} again.` : `Click to switch ${label} off for this chat only`}>
                  <span className="chip-dot" aria-hidden="true" />{label}
                </button>
              );
            })}
            <span> Read-only. Click one to switch it off or on for this chat only.</span>{" "}
          </> : <>No connectors are on, so agents can only use what you type or attach.{" "}</>}
          <button type="button" className="link-btn" onClick={openConnectors}>{live.length ? "Manage connectors" : "Switch on connectors"}</button>
        </div>
        <form className="chat-compose" onSubmit={send}>
          <label htmlFor="chat-text" className="sr-only">Message</label>
          <textarea id="chat-text" rows={3} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={working ? "Add a follow-up or more instructions; it is answered after the current one…" : isCoordinator ? "Ask the Chief of Staff…" : `Ask ${agent?.name}…`}
            onKeyDown={(e) => enterSends(e, () => { void send(); })} />
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
            <EnterHint />
            <button className="primary cut" type="submit" disabled={!text.trim() || busy === "send" || busy === "upload"}>{busy === "send" ? "Sending…" : "Send"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

/** One of the person's messages: queued, failed, or answered. Edit sends it again and replaces what followed. */
function UserMessage({ m, index, canEdit, onResend, queuedBehind }: { m: ChatMsg; index: number; canEdit: boolean;
  onResend: (index: number, content: string) => Promise<void>; queuedBehind: boolean }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.content);
  const [saving, setSaving] = useState(false);
  async function save(e?: React.FormEvent) {
    e?.preventDefault();
    if (!draft.trim()) return;
    setSaving(true);
    try { await onResend(index, draft.trim()); setEditing(false); } catch { /* the page shows the error */ } finally { setSaving(false); }
  }
  if (editing) {
    return (
      <form className="msg user" onSubmit={save}>
        <div className="bubble stack-sm edit-bubble">
          <label htmlFor={`edit-${index}`} className="sr-only">Edit your message</label>
          <textarea id={`edit-${index}`} rows={Math.min(10, Math.max(3, draft.split("\n").length))} value={draft}
            onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => enterSends(e, () => { void save(); })} autoFocus />
          <span className="help">Sending again replaces the answers after this message.</span>
          <div className="row-tight">
            <button className="primary" type="submit" disabled={saving || !draft.trim()}>{saving ? "Sending…" : "Save and send"}</button>
            <button type="button" className="ghost" onClick={() => { setEditing(false); setDraft(m.content); }}>Cancel</button>
          </div>
        </div>
      </form>
    );
  }
  return (
    <div className="msg user">
      <div className="bubble">
        <p className="pre">{m.content}</p>
        {m.files && m.files.length > 0 && <div className="tags">{m.files.map((f) => <span key={f.id} className="tag outline">{f.name}</span>)}</div>}
        {m.status === "queued" && <p className="small muted user-status">{queuedBehind ? "Queued: answered after the message before it." : "Queued…"}</p>}
        {m.error && <p className="note bad small user-status">{m.error}</p>}
        {!m.status && (
          <div className="user-actions">
            <button type="button" className="ghost small-btn" onClick={() => { setDraft(m.content); setEditing(true); }} disabled={!canEdit}
              title={canEdit ? "Edit this message and send it again" : "Wait for the answer in progress to finish"}>Edit</button>
          </div>
        )}
      </div>
    </div>
  );
}

/** Copy plain text, with a fallback for browsers or app windows without the async clipboard API. */
async function copyText(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return; }
  } catch { /* fall back below */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("Copy is not available here; select the text and copy it instead.");
}

function AnswerActions({ m, chatId, index, body, canSave }: { m: ChatMsg; chatId: string; index: number;
  body: React.RefObject<HTMLDivElement>; canSave: boolean }) {
  const [copied, setCopied] = useState(false);
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [exportError, setExportError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  async function copy() {
    setError(null);
    // The rendered answer as plain text: what a person sees, without Markdown symbols.
    // Styling such as upper-case table headers must not change the copied words.
    body.current?.classList.add("copying");
    const text = (body.current?.innerText || m.content).trim();
    body.current?.classList.remove("copying");
    try { await copyText(text); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch (e) { setError(e); }
  }
  const get = (f: "md" | "html") => downloadAnswer(chatId, index, f).catch(setError);
  // .md / .html: saved into the outputs folder with a notice saying where (downloaded when that is not possible).
  async function exportAs(f: "md" | "html") {
    setExported(null); setExportError(null);
    if (!canSave) { try { setExported({ saved: false, name: await downloadAnswer(chatId, index, f), why: "" }); } catch (e) { setExportError(e); } return; }
    try { setExported(await exportAnswer(chatId, index, f)); } catch (e) { setExportError(e); }
  }
  return (
    <>
      {m.file && (
        <div className="answer-file">
          <span className="answer-file-name">{m.file.name}</span>
          <span className="muted small">
            {m.file.format === "html" ? "HTML page" : "Markdown file"} built from {m.file.source != null ? "an earlier answer" : "this answer"}
            {m.file.saved_to ? <> · saved to <code className="outputs-path">{m.file.saved_to}</code></> : " · not saved to the outputs folder"}
          </span>
          <button className="primary" onClick={() => get(m.file!.format)}>Download</button>
        </div>
      )}
      <div className="answer-actions">
        <button className="icon-btn" onClick={copy} aria-label="Copy answer as text" title="Copy answer as text">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
        <button className="ghost small-btn" onClick={() => exportAs("md")} title={canSave ? "Export this answer as a Markdown file into your outputs folder" : "Download this answer as a Markdown file"}>.md</button>
        <button className="ghost small-btn" onClick={() => exportAs("html")} title={canSave ? "Export this answer as an HTML page into your outputs folder" : "Download this answer as an HTML page"}>.html</button>
        <span className="sr-only" aria-live="polite">{copied ? "Answer copied" : ""}</span>
      </div>
      <ExportNote result={exported} error={exportError} />
      <ErrorNote error={error} />
    </>
  );
}

function Message({ m, ov, chatId, index, restricted }: { m: ChatMsg; ov: Overview; chatId: string; index: number; restricted: boolean }) {
  const name = (id?: string) => ov.agents.find((a) => a.id === id)?.name || id;
  const body = useRef<HTMLDivElement>(null);
  if (m.role === "user") {
    return null;  // the person's messages are drawn by UserMessage
  }
  return (
    <div className="msg assistant">
      <div className="bubble">
        <div className="msg-meta small muted">{name(m.agent)}{m.model ? ` · ${m.model}` : ""}{m.tool_calls?.length ? ` · ${lookups(ov, m.tool_calls)}` : ""}{m.seconds != null ? ` · ${m.seconds}s` : ""}{m.tokens ? ` · ${m.tokens.toLocaleString()} tokens` : ""}{m.cached_tokens ? ` (${m.cached_tokens.toLocaleString()} from cache)` : ""}</div>
        <div ref={body}><Markdown text={m.content} /></div>
        <AnswerActions m={m} chatId={chatId} index={index} body={body} canSave={!!ov.outputs_dir && !restricted} />
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
            {other.length > 0 && <ul className="small warn-list">{other.map((w, i) => <li key={i}><NoteText text={w} /></li>)}</ul>}
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
