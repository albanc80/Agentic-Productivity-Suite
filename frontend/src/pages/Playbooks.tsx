import { isLive, shortName } from "../connectors";
import type { Overview, PlaybookCard, StepWhen } from "../api";
import { go } from "../ui";

const PATTERNS: Record<string, string> = {
  P1: "Router", P2: "Pipeline", P3: "Fan-out", P4: "Maker-checker", P5: "Human gate", P6: "Deterministic tool",
};

/** When a step runs, in the person's words: "optional view" for a ticked choice, otherwise the condition. */
function condition(p: PlaybookCard, w: StepWhen | null): { tag: string; title: string } | null {
  if (!w) return null;
  const inp = p.inputs.find((i) => i.id === w.input);
  const label = inp?.label || w.input;
  if (w.contains !== undefined) return { tag: "optional", title: `Runs when "${String(w.contains)}" is ticked under ${label} on the start form` };
  if (w.equals !== undefined) return { tag: "conditional", title: `Runs only when ${label} is "${String(w.equals)}"` };
  return { tag: "conditional", title: `Runs unless ${label} is "${String(w.not_equals)}"` };
}

export default function Playbooks({ ov }: { ov: Overview }) {
  const areas = Array.from(new Set(ov.playbooks.map((p) => p.area)));
  const agentName = (id: string | null) => ov.agents.find((a) => a.id === id)?.name || id || "";
  return (
    <div className="stack-lg">
      <header className="stack-sm">
        <h1>Playbooks</h1>
        <p className="muted measure">Each playbook is a fixed sequence of steps. Specialists run in order or in parallel, a different agent reviews the work, and anything that leaves the app waits for a named person. Each card lists what the playbook needs from you; steps marked <em>optional</em> are views you choose on the start form. If an agent needs something you did not give, the run waits for you to answer, ignore and continue, or stop it.</p>
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
                    {p.connectors.map((id) => {
                      const c = ov.connectors.find((x) => x.id === id);
                      const on = !!c && isLive(c);
                      return <span key={id} className={`tag ${on ? "ok-tag" : "outline"}`}
                        title={on ? "On: the steps of this playbook can use it" : "Off or not set up: agents work from what you paste or upload"}>
                        {shortName(ov, id)} {on ? "· on" : "· off"}</span>;
                    })}
                  </div>
                </div>
                <button className="primary" onClick={() => go(`/start/${p.id}`)}>Start</button>
              </div>
              <dl className="pb-inputs small">
                <dt>Needs</dt>
                <dd>{p.inputs.filter((i) => i.required).map((i) => i.label).join(" · ") || "Nothing required"}</dd>
                {p.inputs.some((i) => !i.required) && <>
                  <dt>Optional</dt>
                  <dd className="muted">{p.inputs.filter((i) => !i.required).map((i) => i.label).join(" · ")}</dd>
                </>}
              </dl>
              <ol className="steps">
                {p.steps.map((s) => {
                  const own = condition(p, s.when);
                  return (
                    <li key={s.id} className={`step-${s.kind}`}>
                      <span className="kind">{s.kind}</span>
                      <span>
                        <strong>{s.title}</strong>
                        {s.agent && <span className="muted"> · {agentName(s.agent)}</span>}
                        {own && <span className="tag outline step-cond" title={own.title}>{own.tag}</span>}
                        {s.children.length > 0 && <span className="muted"> · {s.children.map((c, n) => {
                          const cond = condition(p, c.when);
                          return <span key={c.id}>{n > 0 && " ∥ "}{agentName(c.agent)}{cond && <span className="tag outline step-cond" title={cond.title}>{cond.tag}</span>}</span>;
                        })}</span>}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}
