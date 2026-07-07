import { useRef, useState, type WheelEvent, type MouseEvent } from "react";
import type { GraphLayout, SurgeryPlan } from "../types";

interface View { k: number; x: number; y: number; }

export function GraphPanel({ layout, plan }: { layout: GraphLayout | null; plan: SurgeryPlan | null }) {
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  if (!layout || !plan || layout.nodes.length === 0) {
    return (
      <div className="graph-empty">
        Enter a public repo and Scan to build the call-site graph. The graph catches aliased imports
        (<code>const http = require('axios')</code>) that grep misses.
      </div>
    );
  }

  const aliasSyms = new Set(plan.call_sites.filter((c) => c.is_aliased).map((c) => c.symbol));
  const target = plan.target_package;
  const byId = new Map(layout.nodes.map((n) => [n.id, n]));
  const xs = layout.nodes.map((n) => n.x);
  const ys = layout.nodes.map((n) => n.y);
  const pad = 60;
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const W = Math.max(Math.max(...xs) - minX, 300) + pad * 2;
  const H = Math.max(Math.max(...ys) - minY, 180) + pad * 2;
  const X = (x: number) => x - minX + pad;
  const Y = (y: number) => y - minY + pad;

  const clamp = (k: number) => Math.min(Math.max(k, 0.25), 12);

  const onWheel = (e: WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vbx = ((e.clientX - rect.left) / rect.width) * W;
    const vby = ((e.clientY - rect.top) / rect.height) * H;
    const k2 = clamp(view.k * (1 - e.deltaY * 0.0025));
    const ratio = k2 / view.k;
    setView({ k: k2, x: vbx - ratio * (vbx - view.x), y: vby - ratio * (vby - view.y) });
  };
  const onDown = (e: MouseEvent<SVGSVGElement>) => { drag.current = { x: e.clientX, y: e.clientY }; };
  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    if (!drag.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((e.clientX - drag.current.x) / rect.width) * W;
    const dy = ((e.clientY - drag.current.y) / rect.height) * H;
    drag.current = { x: e.clientX, y: e.clientY };
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const onUp = () => { drag.current = null; };
  const zoom = (f: number) => setView((v) => ({ ...v, k: clamp(v.k * f) }));
  const reset = () => setView({ k: 1, x: 0, y: 0 });

  return (
    <div className="graph-holder">
      <div className="graph-controls">
        <button onClick={() => zoom(1.4)}>＋</button>
        <button onClick={() => zoom(0.7)}>－</button>
        <button onClick={reset}>fit</button>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="graph-svg"
        onWheel={onWheel}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={onUp}
        style={{ cursor: drag.current ? "grabbing" : "grab" }}
      >
        <defs>
          <marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6" fill="#44546e" />
          </marker>
        </defs>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {layout.edges.map((e, i) => {
            const a = byId.get(e.src), b = byId.get(e.dst);
            if (!a || !b) return null;
            return (
              <line key={i} className={`edge edge-${e.kind}`} markerEnd="url(#ar)"
                x1={X(a.x)} y1={Y(a.y)} x2={X(b.x)} y2={Y(b.y)} strokeWidth={1.4} />
            );
          })}
          {layout.nodes.map((n) => {
            const cx = X(n.x), cy = Y(n.y);
            if (n.kind === "package") {
              const vuln = n.label === target;
              return (
                <g key={n.id}>
                  {vuln && <circle className="vuln-ring" cx={cx} cy={cy} />}
                  <circle cx={cx} cy={cy} r={22} fill={vuln ? "#fdeef3" : "#eef4ff"}
                    stroke={vuln ? "var(--vuln)" : "#9fbdf0"} strokeWidth={2} />
                  <text className="nlabel" x={cx} y={cy + 4} textAnchor="middle"
                    fill={vuln ? "#c5326b" : "#2f5bb0"} fontWeight={700}>{n.label}</text>
                  {vuln && <text x={cx} y={cy - 30} textAnchor="middle" fill="var(--vuln)" fontSize={10} fontWeight={700}>⚠ VULNERABLE</text>}
                </g>
              );
            }
            if (n.kind === "file") {
              const bw = Math.min(Math.max(n.label.length * 6.2, 54), 170);
              return (
                <g key={n.id}>
                  <rect x={cx - bw / 2} y={cy - 11} width={bw} height={22} rx={5} fill="#eef4ff" stroke="#9fbdf0" />
                  <text className="nlabel" x={cx} y={cy + 4} textAnchor="middle" fill="#2f5bb0">{n.label}</text>
                </g>
              );
            }
            const al = aliasSyms.has(n.label);
            return (
              <g key={n.id}>
                <circle cx={cx} cy={cy} r={8} fill={al ? "#fff3da" : "#eef2f8"} stroke={al ? "var(--warn)" : "#94a3b8"} strokeWidth={1.6} />
                <text className="nlabel" x={cx + 12} y={cy + 4} fill={al ? "#b4530a" : "#5a6b84"}>
                  {n.label}{al ? " ⟨alias⟩" : ""}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <div className="graph-hint">scroll to zoom · drag to pan</div>
    </div>
  );
}
