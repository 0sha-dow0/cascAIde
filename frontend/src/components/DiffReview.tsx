import { useMemo, useState } from "react";
import { api } from "../api";
import type { Transplant } from "../types";

function DiffLine({ line }: { line: string }) {
  const cls = line.startsWith("+") && !line.startsWith("+++") ? "add"
    : line.startsWith("-") && !line.startsWith("---") ? "del"
    : line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++") ? "hd" : "";
  return <span className={cls}>{line}{"\n"}</span>;
}

export function DiffReview({ transplant }: { transplant: Transplant }) {
  const c = transplant.consensus;
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [pr, setPr] = useState<string>("");
  const anyReject = rejected.size > 0;

  const toggle = (path: string, isReject: boolean) =>
    setRejected((prev) => {
      const next = new Set(prev);
      if (isReject) next.add(path); else next.delete(path);
      return next;
    });

  const accept = async () => {
    try {
      const perFile = transplant.diff.map((f) => ({ path: f.path, kind: "accept" as const, reason: null }));
      const r = await api.submitReview(transplant.id, "accept_all", perFile, null);
      setPr(r.pull_request ? `PR opened → #${r.pull_request.number} · ${r.status}` : `status ${r.status}`);
    } catch (e) { setPr(String((e as Error).message)); }
  };
  const reject = async () => {
    try {
      const perFile = transplant.diff.map((f) => ({
        path: f.path,
        kind: rejected.has(f.path) ? ("reject" as const) : ("accept" as const),
        reason: rejected.has(f.path) ? "needs manual review" : null,
      }));
      const r = await api.submitReview(transplant.id, "reject", perFile, "rejected on review");
      setPr(`status ${r.status} — PR blocked (no half-transplant ships)`);
    } catch (e) { setPr(String((e as Error).message)); }
  };

  const lines = useMemo(
    () => transplant.diff.map((f) => f.unified_diff.split("\n")),
    [transplant],
  );

  return (
    <div>
      <div className={`consensus ${c.approved ? "ok" : "no"}`}>
        {c.approved ? "✓ CONSENSUS APPROVED" : "⚠ CONTESTED"} · {c.approvals}/{c.panel_size} judges approve — human review required
      </div>
      <div className="sub">Judges</div>
      {c.verdicts.map((v) => (
        <div key={v.judge_name} className={`verdict ${v.verdict}`}>
          <b>{v.judge_name}</b> <span className={`badge ${v.verdict}`}>{v.verdict.toUpperCase()}</span>
          <div className="muted small">{v.rationale}</div>
        </div>
      ))}
      <div className="sub">Per-file diff — how it changes <span className="muted">(axios → fetch wrapper)</span></div>
      {transplant.diff.map((f, i) => (
        <div key={f.path} className="filediff">
          <div className="fh">
            <b>{f.path}</b>
            <span>
              <label className="rw"><input type="radio" name={`rw${i}`} defaultChecked onChange={() => toggle(f.path, false)} /> accept</label>
              <label className="rw"><input type="radio" name={`rw${i}`} onChange={() => toggle(f.path, true)} /> reject</label>
            </span>
          </div>
          <pre className="diff">{lines[i].map((l, j) => <DiffLine key={j} line={l} />)}</pre>
        </div>
      ))}
      <div className="actions">
        <button className="primary" disabled={anyReject} onClick={accept}>
          {anyReject ? "Some files rejected — PR blocked" : "Accept all → open PR"}
        </button>
        <button onClick={reject}>Reject transplant</button>
        <span className="muted">{pr}</span>
      </div>
    </div>
  );
}
