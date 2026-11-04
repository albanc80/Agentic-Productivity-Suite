import { useCallback, useEffect, useState } from "react";
import { api, ApiError, setToken, type Overview } from "./api";
import { ErrorNote } from "./ui";
import Command from "./pages/Command";
import Playbooks from "./pages/Playbooks";
import RunForm from "./pages/RunForm";
import RunView from "./pages/RunView";
import Approvals from "./pages/Approvals";
import Library from "./pages/Library";
import Agents from "./pages/Agents";
import SettingsPage from "./pages/Settings";
import ChatPage from "./pages/Chat";

type Theme = "system" | "light" | "dark";

function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try { return (localStorage.getItem("suite.theme") as Theme) || "system"; } catch { return "system"; }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    try { localStorage.setItem("suite.theme", theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, setTheme];
}

function useHash() {
  const [hash, setHash] = useState(() => window.location.hash.slice(1) || "/");
  useEffect(() => {
    const on = () => { setHash(window.location.hash.slice(1) || "/"); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

const NAV = [
  { path: "/", label: "Command" },
  { path: "/chat", label: "Chat" },
  { path: "/playbooks", label: "Playbooks" },
  { path: "/approvals", label: "Approvals" },
  { path: "/library", label: "Library" },
  { path: "/agents", label: "Agents" },
  { path: "/settings", label: "Settings" },
];

export default function App() {
  const hash = useHash();
  const [theme, setTheme] = useTheme();
  const [ov, setOv] = useState<Overview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [needToken, setNeedToken] = useState(false);
  const [tokenDraft, setTokenDraft] = useState("");

  const refresh = useCallback(async () => {
    try {
      setOv(await api.overview());
      setError(null);
      setNeedToken(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setNeedToken(true);
      else setError(e);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const [section, arg] = (() => {
    const parts = hash.split("/").filter(Boolean);
    return [parts[0] || "", parts[1] || ""];
  })();

  let page;
  if (!ov) page = null;
  else if (section === "") page = <Command ov={ov} />;
  else if (section === "chat") page = <ChatPage ov={ov} chatId={arg} />;
  else if (section === "playbooks") page = <Playbooks ov={ov} />;
  else if (section === "start") page = <RunForm ov={ov} playbookId={arg} />;
  else if (section === "runs") page = <RunView ov={ov} runId={arg} onChange={refresh} />;
  else if (section === "approvals") page = <Approvals onChange={refresh} />;
  else if (section === "library") page = <Library ov={ov} />;
  else if (section === "agents") page = <Agents ov={ov} agentId={arg} onChange={refresh} />;
  else if (section === "settings") page = <SettingsPage ov={ov} onChange={refresh} />;
  else page = <p>Page not found.</p>;

  const active = "/" + section;
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/">
            <img className="brand-mark" src="/icon.svg" alt="" width="28" height="28" />
            <span><span className="brand-eyebrow">Agentic</span> Productivity<span className="brand-accent">Suite</span></span>
          </a>
          <nav aria-label="Main">
            {NAV.map((n) => (
              <a key={n.path} href={`#${n.path}`} className={active === n.path ? "active" : ""} aria-current={active === n.path ? "page" : undefined}>
                {n.label}
                {n.path === "/approvals" && ov && ov.pending_approvals > 0 && <span className="count">{ov.pending_approvals}</span>}
              </a>
            ))}
          </nav>
          <div className="topbar-tools">
            {ov && (
              <button className={`mode-switch ${ov.offline ? "is-offline" : ""}`} aria-pressed={ov.offline}
                title={ov.offline ? "Offline: local models and local files only. Click to go online." : "Online. Click to switch to offline mode (local models and local files only)."}
                onClick={async () => { try { await api.setOffline(!ov.offline); refresh(); } catch (e) { setError(e); } }}>
                <span className="mode-track" aria-hidden="true"><span className="mode-knob" /></span>
                {ov.offline ? "Offline" : "Online"}
              </button>
            )}
            <label className="sr-only" htmlFor="theme">Theme</label>
            <select id="theme" className="theme-select" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </div>
        </div>
      </header>
      {ov?.kill_switch && (
        <div className="banner bad">Kill switch is on. No runs can start or continue. Turn it off in <a href="#/settings">Settings</a>.</div>
      )}
      <main className="page">
        {needToken && (
          <form className="card narrow" onSubmit={(e) => { e.preventDefault(); setToken(tokenDraft); refresh(); }}>
            <h2>API token required</h2>
            <p className="muted">This server requires the token set in SUITE_API_TOKEN.</p>
            <label htmlFor="token">Token</label>
            <input id="token" type="password" value={tokenDraft} onChange={(e) => setTokenDraft(e.target.value)} autoComplete="off" />
            <button className="primary" type="submit">Connect</button>
          </form>
        )}
        <ErrorNote error={error} />
        {!ov && !needToken && !error && <p className="muted">Loading…</p>}
        {page}
      </main>
    </div>
  );
}
