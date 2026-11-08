import { useRef, useState } from "react";
import { api, type AgentPack, type Overview } from "../api";
import { ErrorNote } from "../ui";

const REPO = "https://github.com/albanc80/Agentic-Productivity-Suite";

/** Settings → System → About: the installed version, what the app does and what it can do. */
export function AboutCard({ ov }: { ov: Overview }) {
  const on = ov.connectors.filter((c) => c.enabled && !c.offline_paused).length;
  return (
    <section className="card stack" aria-labelledby="about-h">
      <div className="row">
        <div className="grow stack-sm">
          <h2 id="about-h">About</h2>
          <p className="small"><strong>Agentic Productivity Suite</strong> <span className="tag" data-testid="app-version">version {ov.version}</span></p>
        </div>
        <a className="small" href={`${REPO}/releases`} target="_blank" rel="noopener noreferrer">Release notes ↗</a>
      </div>
      <p className="small measure">
        A desktop and browser app that turns a team of specialist AI agents into governed, repeatable work: daily planning,
        decisions, management, product development, engineering and investment cases. You chat with an agent, or hand a
        request to a playbook in which specialists work step by step, a different agent reviews the result, and anything
        that would leave the app waits for you.
      </p>
      <ul className="small about-list">
        <li><strong>Chat</strong> with the Chief of Staff, who answers or brings in up to three specialists, or with any one agent.</li>
        <li><strong>{ov.playbooks.length} playbooks</strong> run by <strong>{ov.agents.length} agents</strong> in {ov.desks.length} desks, with independent review and approvals.</li>
        <li><strong>Any model:</strong> local (Ollama, LM Studio, vLLM, a model on your network) or cloud (OpenAI, DeepSeek, OpenRouter, Anthropic), mixed in one run, with a fallback order.</li>
        <li><strong>Read-only connectors</strong> to your files, Microsoft 365, Google Workspace, GitHub, Jira/Confluence, Azure DevOps and Databricks; {on} switched on now.</li>
        <li><strong>Safety controls:</strong> data classes keep restricted work on local models, offline mode, spending limits, a kill switch and a full audit log.</li>
        <li><strong>Your work stays yours:</strong> settings and history live on this computer; readable copies of chats and deliverables go to your outputs folder.</li>
      </ul>
      <p className="help">New here? Open the <strong>User guide</strong> tab above.</p>
    </section>
  );
}

function packDetail(p: AgentPack): string {
  if (!p.installed) {
    return "This copy of the app has no agent instructions built in. If the app's owner gave you an agent pack (a .zip, or the agents' .yaml files), "
      + "import it: it is checked, saved on this computer readable only by you, and used at once.";
  }
  const parts: string[] = [];
  if (p.built_in) parts.push(`${p.built_in} built into the app`);
  if (p.imported) parts.push(`${p.imported} from a pack imported here${p.built_in ? ", used instead of the built-in ones" : ""}`);
  return `${p.agents_with_instructions} of ${p.agents_total} agents use their full instructions: ${parts.join("; ")}.`;
}

/** Settings → System → Agent instructions: built into the app encrypted (ADR 0007), or imported here (ADR 0005). */
export function AgentPackCard({ ov, onChange }: { ov: Overview; onChange: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState("");
  const p = ov.agent_pack;
  const full = p.installed && p.agents_with_instructions >= p.agents_total;

  async function upload(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (input.current) input.current.value = "";
    if (!files.length) return;
    setBusy(true); setError(null); setDone("");
    try {
      const r = await api.importAgentPack(files);
      setDone(`Installed ${r.imported_files.length} agent file${r.imported_files.length === 1 ? "" : "s"}; ${r.agents_with_instructions} of ${r.agents_total} agents now use their full instructions.`
        + (r.skipped.length ? ` Skipped ${r.skipped.length} file${r.skipped.length === 1 ? "" : "s"} that name no agent in this app.` : ""));
      onChange();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <section className="card stack" aria-labelledby="pack-h">
      <div className="row">
        <div className="grow stack-sm">
          <h2 id="pack-h">Agent instructions</h2>
          <p className="muted small measure">
            Each agent's full instructions and persona make its answers specific. They are built into this app encrypted, used only
            by the agents, and never shown on screen. Without them every agent still works, from its short public description,
            but answers are more generic.
          </p>
        </div>
        <span className={`pill ${full ? "ok" : p.agents_with_instructions ? "warn" : "neutral"}`} data-testid="pack-state">
          {!p.installed ? "Not installed" : full ? (p.imported ? "Installed" : "Built in") : `${p.agents_with_instructions} of ${p.agents_total} agents`}
        </span>
      </div>
      <p className="small" data-testid="pack-detail">{packDetail(p)}</p>
      <div className="row-tight">
        <input ref={input} type="file" accept=".zip,.yaml,.yml,application/zip" multiple hidden aria-hidden="true"
          data-testid="pack-input" onChange={(e) => upload(e.target.files)} />
        <button type="button" className={p.installed ? "ghost" : "primary"} onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Installing…" : p.imported ? "Update imported pack" : p.built_in ? "Import my own version" : "Import agent pack"}
        </button>
      </div>
      {done && <p className="small ok-text" role="status">{done}</p>}
      <ErrorNote error={error} />
      {p.folder && (p.imported > 0 || !p.built_in) && <p className="help">Imported packs are saved in <code>{p.folder}</code>. Importing again replaces files with the same name and keeps the rest.</p>}
    </section>
  );
}

const STEPS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Choose a model",
    body: <>Open <strong>Settings → Models</strong>. Switch on a provider, press <strong>Edit</strong>, paste its API key (cloud) or press
      <strong> Find models</strong> (LM Studio, Ollama), then <strong>Test</strong>. Pick a default and a fallback under
      <strong> Models in use</strong>. Until a model is on, agent steps stop with "No model configured".</>,
  },
  {
    title: "Connect your information (optional)",
    body: <>In <strong>Settings → Connectors</strong>, every connector starts off. <strong>Local files</strong>: choose folders.
      <strong> Microsoft 365</strong> and <strong>Google Workspace</strong>: press <strong>Sign in</strong>. Others: press
      <strong> Edit</strong>, fill in the values, switch on. Connectors only read; they never send, change or delete anything.
      <strong> Test</strong> checks that the connector starts; it does not prove a sign-in.</>,
  },
  {
    title: "Tell the agents about you",
    body: <>Fill in <strong>Settings → Profile</strong>: your role, goals and how you like to work. Every agent reads it, so answers fit you.</>,
  },
  {
    title: "Ask in Chat",
    body: <>Open <a href="#/chat">Chat</a>. Keep the <strong>Chief of Staff</strong>, who brings in specialists when needed, or pick one agent.
      <strong> Enter</strong> sends, <strong>Shift+Enter</strong> starts a new line. Attach a file, copy or download an answer, or ask
      "as an HTML file" to get a saved file.</>,
  },
  {
    title: "Run a playbook for bigger work",
    body: <>On <a href="#/">Command</a>, describe what needs doing and the app suggests a playbook, or choose one in{" "}
      <a href="#/playbooks">Playbooks</a>. Fill in the form, pick a <strong>data class</strong> and start. Specialists work in order,
      another agent reviews, and the run page shows each step.</>,
  },
  {
    title: "Answer and approve",
    body: <>When a run needs your input or your OK, <a href="#/approvals">Approvals</a> shows a count in the top bar. Answer the
      questions or approve; nothing leaves the app without a named person.</>,
  },
  {
    title: "Find your work",
    body: <><a href="#/library">Library</a> keeps every run with its deliverable and audit trail. Readable copies go to{" "}
      <code>Documents/Agentic-Suite-Outputs</code> (<code>Chats</code>, <code>Runs</code>, <code>Files</code>); change the folder in
      <strong> Settings → Policies &amp; budgets</strong>.</>,
  },
];

/** Settings → User guide: the first-time path, short. */
export function UserGuide({ ov, goTo }: { ov: Overview; goTo: (tab: "models" | "connectors" | "profile" | "policies" | "system") => void }) {
  const modelOn = ov.providers.some((p) => p.available);
  const connectorOn = ov.connectors.some((c) => c.enabled && !c.offline_paused);
  const status: Record<number, boolean> = { 0: modelOn, 1: connectorOn, 2: ov.profile_configured };
  return (
    <div className="stack-lg">
      <section className="card stack" aria-labelledby="guide-h">
        <div className="stack-sm">
          <h2 id="guide-h">Getting started</h2>
          <p className="muted small measure">Seven steps from a fresh install to finished work. The first three are set up once; ticks show what is already done on this computer.</p>
        </div>
        <ol className="guide">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <div className="row-tight">
                <strong>{s.title}</strong>
                {i in status && <span className={`pill ${status[i] ? "ok" : "neutral"}`}>{status[i] ? "Done" : "Not yet"}</span>}
              </div>
              <p className="small">{s.body}</p>
            </li>
          ))}
        </ol>
        <div className="row-tight">
          <button type="button" onClick={() => goTo("models")}>Go to Models</button>
          <button type="button" onClick={() => goTo("connectors")}>Go to Connectors</button>
          <button type="button" onClick={() => goTo("profile")}>Go to Profile</button>
        </div>
      </section>

      <section className="card stack" aria-labelledby="safe-h">
        <h2 id="safe-h">Stay in control</h2>
        <ul className="small about-list">
          <li><strong>Data classes</strong> (public, internal, confidential, restricted) decide which models a run may use; <strong>restricted</strong> work only reaches local models. Set them in Policies &amp; budgets.</li>
          <li><strong>Offline</strong>: the switch in the top bar pauses every cloud model and internet connector in one step.</li>
          <li><strong>Spending limits</strong> are off until you switch them on in Policies &amp; budgets; loop guardrails are always on.</li>
          <li><strong>Kill switch</strong> in System stops every run and chat at once.</li>
        </ul>
      </section>

      <section className="card stack" aria-labelledby="help-h">
        <h2 id="help-h">When something goes wrong</h2>
        <ul className="small about-list">
          <li>The screen says what failed and why. <strong>System → Configuration notices</strong> lists setup problems.</li>
          <li>Full details are in the log: <code>~/.productivity-suite/suite.log</code> (<code>%USERPROFILE%\.productivity-suite\suite.log</code> on Windows).</li>
          <li>Agents answering generically? Check <strong>System → Agent instructions</strong>.</li>
        </ul>
        <div className="row-tight"><button type="button" onClick={() => goTo("system")}>Go to System</button></div>
      </section>
    </div>
  );
}
