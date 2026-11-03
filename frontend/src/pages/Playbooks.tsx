import type { Overview } from "../api";
import { go } from "../ui";

const PATTERNS: Record<string, string> = {
  P1: "Router", P2: "Pipeline", P3: "Fan-out", P4: "Maker-checker", P5: "Human gate", P6: "Deterministic tool",
};

export default function Playbooks({ ov }: { ov: Overview }) {
  const areas = Array.from(new Set(ov.playbooks.map((p) => p.area)));
  const agentName = (id: string | null) => ov.agents.find((a) => a.id === id)?.name || id || "";
  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Playbooks</h1>
        <p className="muted measure">Each playbook is a fixed sequence of steps. Specialists run in order or in parallel, a different agent reviews the work, and anything that leaves the app waits for a named person.</p>
      </header>
      {areas.map((area) => (
        <section key={area} className="stack">
          <h2>{area}</h2>
          {ov.playbooks.filter((p) => p.area === area).map((p) => (
            <article key={p.id} className="card playbook">
              <div className="playbook-head">
                <div className="stack-sm">
                  <span className="code">{p.code}</span>
                  <h3>{p.name}</h3>
                  <p className="muted">{p.summary}</p>
                  <div className="tags">
                    {p.patterns.map((x) => <span key={x} className="tag">{PATTERNS[x] || x}</span>)}
                    {p.connectors.length > 0 && <span className="tag outline">Uses: {p.connectors.join(", ")}</span>}
                  </div>
                </div>
                <button className="primary" onClick={() => go(`/start/${p.id}`)}>Start</button>
              </div>
              <ol className="steps">
                {p.steps.map((s) => (
                  <li key={s.id} className={`step-${s.kind}`}>
                    <span className="kind">{s.kind}</span>
                    <span>
                      <strong>{s.title}</strong>
                      {s.agent && <span className="muted"> · {agentName(s.agent)}</span>}
                      {s.children.length > 0 && <span className="muted"> · {s.children.map((c) => agentName(c.agent)).join(" ∥ ")}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}
