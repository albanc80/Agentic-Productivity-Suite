import type { Desk, PlaybookCard, StepRow } from "./api";

/** The suite's real topology: the router in the middle, one node per desk, sized by agent count.
 *  Every node and line maps to something in the registry; nothing here implies live data. */
export function OrchestrationMap({ desks, playbooks, connectorsLive }: { desks: Desk[]; playbooks: number; connectorsLive: number }) {
  const W = 560, H = 440, cx = W / 2, cy = H / 2 + 6, rx = 200, ry = 150;
  const nodes = desks.map((d, i) => {
    const a = -Math.PI / 2 + (i / desks.length) * Math.PI * 2;
    const x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
    const anchor = Math.abs(x - cx) < 20 ? "middle" : x > cx ? "start" : "end";
    const dx = anchor === "start" ? 16 : anchor === "end" ? -16 : 0;
    // Top node: name and count stacked above the dot; bottom node: below it; sides: beside it.
    const dy = anchor === "middle" ? (y < cy ? -34 : 30) : 4;
    return { d, x, y, anchor, dx, dy, r: 5 + Math.min(d.members.length, 12) * 0.6 };
  });
  return (
    <figure className="orch">
      <svg viewBox={`-90 0 ${W + 180} ${H}`} role="img" aria-labelledby="orch-title orch-desc">
        <title id="orch-title">Suite topology</title>
        <desc id="orch-desc">
          The router at the centre sends each request to a playbook, which calls specialists in {desks.length} desks:{" "}
          {desks.map((d) => `${d.name} (${d.members.length} agents)`).join(", ")}.
        </desc>
        <ellipse className="orch-orbit" cx={cx} cy={cy} rx={rx} ry={ry} />
        <ellipse className="orch-orbit faint" cx={cx} cy={cy} rx={rx * 0.55} ry={ry * 0.55} />
        {nodes.map((n) => (
          <line key={`l-${n.d.id}`} className="orch-link" x1={cx} y1={cy} x2={n.x} y2={n.y} />
        ))}
        {nodes.map((n) => (
          <a key={n.d.id} href={`#/agents`} className="orch-node" aria-label={`${n.d.name}: ${n.d.members.length} agents`}>
            <circle className="orch-halo" cx={n.x} cy={n.y} r={n.r + 7} />
            <circle className="orch-dot" cx={n.x} cy={n.y} r={n.r} />
            <text x={n.x + n.dx} y={n.y + n.dy} textAnchor={n.anchor} className="orch-label">{n.d.name}</text>
            <text x={n.x + n.dx} y={n.y + n.dy + 15} textAnchor={n.anchor} className="orch-sub">{n.d.members.length} agents</text>
          </a>
        ))}
        <g className="orch-core">
          <polygon points={hexagon(cx, cy, 56)} className="orch-core-shell" />
          <polygon points={hexagon(cx, cy, 42)} className="orch-core-inner" />
          <text x={cx} y={cy - 2} textAnchor="middle" className="orch-core-label">ROUTER</text>
          <text x={cx} y={cy + 15} textAnchor="middle" className="orch-sub core-sub">{playbooks} playbooks</text>
        </g>
      </svg>
      <figcaption className="orch-legend">
        <span><i className="dot cyan" />Desk · sized by agents</span>
        <span><i className="dot violet" />Router</span>
        <span>{connectorsLive} connector{connectorsLive === 1 ? "" : "s"} live</span>
      </figcaption>
    </figure>
  );
}

function hexagon(cx: number, cy: number, r: number) {
  return Array.from({ length: 6 }, (_, i) => {
    const a = Math.PI / 6 + (i * Math.PI) / 3;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
}

const STATE_OF: Record<string, string> = {
  COMPLETE: "ok", COMPLETE_WITH_ACCEPTED_RISK: "ok", PARTIAL: "warn", NEEDS_INPUT: "warn",
  BLOCKED: "bad", REJECTED: "bad", error: "bad", running: "live", skipped: "skip",
};

const KIND_LABEL: Record<string, string> = {
  agent: "Agent", parallel: "Parallel", review: "Review", gate: "Gate", tool: "Calc", connector: "Fetch",
};

/** Run progress: one station per top-level step. Shape encodes step kind; fill and label encode state. */
export function StepRail({ playbook, steps, cursor, runStatus }: {
  playbook: PlaybookCard; steps: StepRow[]; cursor: number; runStatus: string;
}) {
  const latest = (ids: string[]) => {
    const rows = steps.filter((s) => ids.includes(s.step_id));
    if (!rows.length) return null;
    if (rows.some((r) => r.status === "running")) return "running";
    const order = ["error", "BLOCKED", "REJECTED", "NEEDS_INPUT", "PARTIAL", "COMPLETE_WITH_ACCEPTED_RISK", "COMPLETE", "skipped"];
    const finals = new Map(rows.map((r) => [r.step_id, r.status]));
    return [...finals.values()].sort((a, b) => order.indexOf(a) - order.indexOf(b))[0];
  };
  const done = playbook.steps.filter((_, i) => i < cursor).length;
  const pct = playbook.steps.length > 1 ? Math.min(done, playbook.steps.length - 1) / (playbook.steps.length - 1) : 1;
  return (
    <div className="rail-wrap">
      <ol className="rail" style={{ ["--rail-progress" as string]: `${pct * 100}%` }} aria-label="Run progress">
        {playbook.steps.map((s, i) => {
          const ids = s.children.length ? s.children.map((c) => c.id) : [s.id];
          let st = latest(ids);
          if (!st) st = i === cursor && (runStatus === "running" || runStatus === "queued") ? "running"
            : i === cursor && runStatus === "awaiting_approval" && s.kind === "gate" ? "waiting-you" : "pending";
          const tone = STATE_OF[st] || st;
          const words = st === "waiting-you" ? "Needs you" : st === "pending" ? "Pending" : st === "running" ? "Running"
            : st === "skipped" ? "Skipped" : st.replace(/_/g, " ").toLowerCase();
          return (
            <li key={s.id} className={`station k-${s.kind} s-${tone}`}>
              <span className="station-mark" aria-hidden="true" />
              <span className="station-kind">{KIND_LABEL[s.kind] || s.kind}</span>
              <span className="station-title">{s.title}</span>
              <span className="station-state">{words}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
