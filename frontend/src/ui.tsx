import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { KeyboardEvent, ReactNode } from "react";

// A link in an answer opens in the browser, never inside the app window (which has no Back button).
function AnswerLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (!href || href.startsWith("#")) return <a href={href}>{children}</a>;
  return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
}

// Model output is rendered as Markdown without raw HTML (react-markdown ignores HTML by default).
export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: AnswerLink }}>{text}</ReactMarkdown>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  COMPLETE: "ok", COMPLETE_WITH_ACCEPTED_RISK: "ok", completed: "ok", approved: "ok", ready: "ok", PASS: "ok",
  PARTIAL: "warn", NEEDS_INPUT: "warn", awaiting_approval: "warn", pending: "warn", PASS_WITH_CHANGES: "warn", interrupted: "warn", idle: "neutral",
  BLOCKED: "bad", REJECTED: "bad", failed: "bad", error: "bad", rejected: "bad", FAIL: "bad",
  running: "live", queued: "live", connecting: "live",
  skipped: "neutral", cancelled: "neutral", unconfigured: "neutral", disabled: "neutral",
};

const LABELS: Record<string, string> = {
  COMPLETE_WITH_ACCEPTED_RISK: "Complete, accepted risk", NEEDS_INPUT: "Needs input", awaiting_approval: "Waiting for you",
  PASS_WITH_CHANGES: "Pass with changes",
};

export function Pill({ value, title }: { value: string | null | undefined; title?: string }) {
  if (!value) return null;
  const tone = STATUS_TONE[value] || "neutral";
  const label = LABELS[value] || value.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  return <span className={`pill ${tone}`} title={title}>{label}</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <div>{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="note bad" role="alert">{msg}</div>;
}

/** The outcome of an export: where the file was saved, that it was downloaded instead (and why), or that it failed. */
export function ExportNote({ result, error }: { result: import("./api").ExportResult | null; error: unknown }) {
  if (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return <div className="note bad" role="alert">Export failed: {msg}</div>;
  }
  if (!result) return null;
  return result.saved
    ? <div className="note ok" role="status">Exported <strong>{result.name}</strong> to <code className="outputs-path">{result.path}</code></div>
    : <div className="note" role="status">Downloaded <strong>{result.name}</strong> to your Downloads folder. {result.why}</div>;
}

export function fmtCost(v: number) {
  return v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
}

export function fmtTime(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function go(path: string) {
  window.location.hash = path;
}

/** Enter sends; Shift+Enter starts a new line. Ctrl/Cmd+Enter still sends. Ignored while an input method is
 * composing (Japanese, Chinese, accents), so confirming a character never sends half a message. */
export function enterSends(e: KeyboardEvent<HTMLTextAreaElement>, send: () => void) {
  if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  send();
}

export function EnterHint() {
  return <span className="muted small"><kbd>Enter</kbd> to send · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span>;
}

// Only links the app writes itself (Google Cloud steps) become clickable; other text in a warning can come from a
// connector and stays plain.
const SAFE_LINK = /(https:\/\/console\.cloud\.google\.com\/[\w./?=&%-]+)/;

export function NoteText({ text }: { text: string }) {
  const parts = text.split(SAFE_LINK);
  return <>{parts.map((p, i) => (i % 2
    ? <a key={i} href={p} target="_blank" rel="noreferrer">{p.replace(/^https:\/\//, "")} ↗</a>
    : <span key={i}>{p}</span>))}</>;
}
