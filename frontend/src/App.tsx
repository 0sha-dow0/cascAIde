import { useEffect, useState } from "react";
import { api } from "./api";
import { DiffReview } from "./components/DiffReview";
import { GraphPanel } from "./components/GraphPanel";
import { usePipelineStream } from "./usePipelineStream";
import type {
  MitigationOption, RegisterRepoResponse, StrategyKind, Transplant, UnderwritingReport,
} from "./types";

const STAGES = ["recall", "rewrite", "validate", "verify_build", "verify_test", "verify_behavioral", "judge"];

export default function App() {
  const [url, setUrl] = useState("https://github.com/depcover/victim-axios");
  const [status, setStatus] = useState("");
  const [scan, setScan] = useState<RegisterRepoResponse | null>(null);
  const [repoId, setRepoId] = useState<string | null>(null);
  const [options, setOptions] = useState<MitigationOption[] | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [transplant, setTransplant] = useState<Transplant | null>(null);
  const { events, terminalStage } = usePipelineStream(incidentId);

  useEffect(() => {
    if (!terminalStage || !incidentId) return;
    setStatus(`pipeline ${terminalStage}`);
    api.getTransplant(`transplant-${incidentId}`).then(setTransplant).catch(() => setTransplant(null));
  }, [terminalStage, incidentId]);

  const doScan = async () => {
    setStatus("cloning + scanning (public repos are git-cloned live)…");
    setScan(null); setOptions(null); setTransplant(null); setIncidentId(null);
    try {
      const d = await api.registerRepo(url.trim());
      setScan(d); setRepoId(d.repo.id); setStatus("scanned ✓ · graph built in Neo4j");
    } catch (e) { setStatus(`scan failed: ${(e as Error).message}`); }
  };
  const doFire = async () => {
    if (!repoId) return;
    setStatus("firing CVE…");
    try {
      const d = await api.fireIncident(repoId);
      setIncidentId(d.incident.id); setOptions(d.options.options); setStatus("incident open — choose a strategy");
    } catch (e) { setStatus(`incident failed: ${(e as Error).message}`); }
  };
  const runTransplant = async (kind: StrategyKind) => {
    if (!incidentId) return;
    setTransplant(null);
    setStatus("pipeline running (real Daytona sandbox + 4 live judges)…");
    try { await api.chooseStrategy(incidentId, kind); } catch (e) { setStatus(`pipeline failed: ${(e as Error).message}`); }
  };
  const fixIt = async () => {
    if (!repoId) return;
    setTransplant(null); setOptions(null);
    setStatus("firing incident + running transplant…");
    try {
      const d = await api.fireIncident(repoId);
      setIncidentId(d.incident.id);
      setOptions(d.options.options);
      await api.chooseStrategy(d.incident.id, "transplant");
      setStatus("pipeline running (real Daytona sandbox + 4 live judges)…");
    } catch (e) { setStatus(`fix failed: ${(e as Error).message}`); }
  };

  const stageState = (s: string): string => {
    const e = events.find((ev) => ev.stage === s);
    if (!e) return "";
    return e.terminal ? `term term-${s}` : "done";
  };

  return (
    <div>
      <header>
        <h1>▚ DepCover</h1>
        <span className="tag">impact analysis + autonomous transplant · axios → fetch · behavioral proof · 4-judge consensus</span>
      </header>
      <div className="repobar">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Public GitHub repo URL" />
        <button className="primary" onClick={doScan}>Scan repo</button>
        <button disabled={!repoId} onClick={doFire}>Fire CVE incident</button>
        <span className="muted">{status}</span>
      </div>

      <div className="wrap">
        <div className="panel">
          <h2>Dependency &amp; call-site graph
            <span className="legend">
              <span><b style={{ background: "var(--vuln)" }} />vulnerable dep</span>
              <span><b style={{ background: "#5f8fd6" }} />file</span>
              <span><b style={{ background: "var(--warn)" }} />aliased call site</span>
              <span><b style={{ background: "#7d8aa0" }} />call site</span>
            </span>
          </h2>
          <div className="graphwrap">
            <GraphPanel layout={scan?.graph_layout ?? null} plan={scan?.surgery_plan ?? null} />
          </div>
        </div>

        <div className="cols">
          <div className="stack">
            <Panel title="What's vulnerable · how it changes">
              {scan ? <VulnBody scan={scan} onFix={fixIt} /> : <span className="muted">—</span>}
            </Panel>
            <Panel title="Underwriting · kill-test blast radius">
              {scan ? <UnderBody u={scan.underwriting} aliased={scan.surgery_plan.call_sites.filter((c) => c.is_aliased).length} /> : <span className="muted">—</span>}
            </Panel>
            <Panel title="Mitigation strategies">
              {options ? <Mitigation options={options} onRun={runTransplant} /> : <span className="muted">—</span>}
            </Panel>
            <Panel title="Live pipeline">
              {incidentId ? (
                <div className="steps">
                  {STAGES.map((s) => {
                    const e = events.find((ev) => ev.stage === s);
                    return (
                      <div key={s} className={`step ${stageState(s)}`}>
                        <span className="dot" />{s}{e ? ` — ${e.message}` : ""}
                      </div>
                    );
                  })}
                  {terminalStage && !STAGES.includes(terminalStage) && (
                    <div className={`step term term-${terminalStage}`}><span className="dot" />{terminalStage}</div>
                  )}
                </div>
              ) : <span className="muted">—</span>}
            </Panel>
          </div>

          <Panel title="Diff review · judge verdicts">
            {transplant ? <DiffReview transplant={transplant} /> : <span className="muted">Runs after you choose the transplant strategy.</span>}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="panel"><h2>{title}</h2><div className="body">{children}</div></div>;
}

function VulnBody({ scan, onFix }: { scan: RegisterRepoResponse; onFix: () => void }) {
  const p = scan.surgery_plan;
  return (
    <div>
      <div><span className="pill vuln">{p.target_package}</span> is the flagged dependency — {p.affected_files.length} file(s), {p.call_sites.length} call site(s).</div>
      <div className="muted spaced">Why it's risky: outdated/compromised HTTP client (SSRF/CVE surface), and axios <b>throws on non-2xx</b> — a contract fetch does not share.</div>
      <div><b>How it changes:</b> each call site is rewritten to a native <code>fetch</code> wrapper that throws on non-2xx and parses JSON, so behavior is preserved. Proven by the behavioral diff, gated by 4 judges + you.</div>
      <button className="primary fixbtn" onClick={onFix}>⚡ Fix it → run transplant (axios → fetch)</button>
      <div className="sub">Call sites (surgery plan)</div>
      {p.call_sites.map((c, i) => (
        <div key={i} className={`cs ${c.is_aliased ? "alias" : ""}`}>
          <b>{c.file_path}</b>:{c.line} · <code>{c.symbol}</code>{" "}
          {c.is_aliased && <span className="pill alias">aliased → {c.alias} (grep misses this)</span>}
        </div>
      ))}
    </div>
  );
}

function UnderBody({ u, aliased }: { u: UnderwritingReport; aliased: number }) {
  return (
    <div>
      <div>Affected files: <b>{u.affected_file_count}</b> · Failing tests: <b>{u.failing_tests.length}</b> · axios centrality: <b>{(u.centrality[0]?.score ?? 0).toFixed(2)}</b></div>
      {u.failing_tests.length > 0
        ? <ul>{u.failing_tests.map((t) => <li key={t} className="err">{t}</li>)}</ul>
        : <div className="muted spaced">Graph proves {u.affected_file_count} files touch the target{aliased ? ` including ${aliased} aliased site(s) grep would miss` : ""}.</div>}
      {u.warnings.length > 0 && <div className="muted spaced">warnings: {u.warnings.map((w) => w.shape).join(", ")}</div>}
    </div>
  );
}

function Mitigation({ options, onRun }: { options: MitigationOption[]; onRun: (k: StrategyKind) => void }) {
  return (
    <div className="cards">
      {options.map((o) => (
        <div key={o.kind} className={`card ${o.executable ? "exec" : ""}`}>
          <h3>{o.title} <span className="pill">{o.executable ? "executed end-to-end" : "roadmap"}</span></h3>
          <div className="meta">effort {o.effort} · blast {o.blast_radius} · residual {o.residual_risk}</div>
          <div>{o.rationale}</div>
          {o.executable && <button className="primary small" onClick={() => onRun(o.kind)}>Run transplant ▶</button>}
        </div>
      ))}
    </div>
  );
}
