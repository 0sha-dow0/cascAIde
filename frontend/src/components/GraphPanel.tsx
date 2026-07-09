import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import { useTheme } from "@/components/theme-provider";
import type { GraphEdge, GraphLayout, SurgeryPlan, UnderwritingReport } from "../types";

interface GData {
  label: string;
  sub: string;
  highlighted: boolean;
  isTarget: boolean;
  isTest: boolean;
  isAliased: boolean;
  [key: string]: unknown;
}
type GNode = Node<GData>;

const NODE_H: Record<string, number> = { package: 34, file: 38, call_site: 26 };
const HANDLE = "!h-1.5 !w-1.5 !min-w-0 !border-0 !bg-border";

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function isTestFile(path: string): boolean {
  return (
    /\.(test|spec)\.[cm]?[jt]sx?$/.test(path) ||
    /(^|\/)__tests__\//.test(path) ||
    /(^|\/)tests?\//.test(path) ||
    /(^|\/)test\.[cm]?[jt]s$/.test(path)
  );
}

function nodeWidth(kind: string, label: string): number {
  const base = kind === "call_site" ? 26 : 44;
  const per = kind === "call_site" ? 6.6 : 7.2;
  const max = kind === "file" ? 240 : kind === "package" ? 190 : 160;
  return Math.min(Math.max(label.length * per + base, 84), max);
}

function importersOf(targetId: string, edges: GraphEdge[]): Set<string> {
  const reverse = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.kind !== "imports") continue;
    const existing = reverse.get(edge.dst);
    if (existing) existing.push(edge.src);
    else reverse.set(edge.dst, [edge.src]);
  }
  const found = new Set<string>([targetId]);
  const queue = [targetId];
  while (queue.length) {
    const current = queue.shift() as string;
    for (const src of reverse.get(current) ?? []) {
      if (!found.has(src)) {
        found.add(src);
        queue.push(src);
      }
    }
  }
  return found;
}

function PackageNode({ data }: NodeProps<GNode>) {
  const tone = data.isTarget
    ? "border-destructive bg-destructive/12 text-destructive font-semibold"
    : data.highlighted
      ? "border-destructive/50 bg-destructive/[0.06] text-foreground"
      : "border-border bg-card text-muted-foreground";
  return (
    <div className={`flex h-full w-full items-center gap-1.5 rounded-full border px-3 font-mono text-[12px] ${tone}`}>
      <Handle type="target" position={Position.Left} className={HANDLE} />
      {data.isTarget && <span className="text-[10px]">⚠</span>}
      <span className="truncate">{data.label}</span>
      <Handle type="source" position={Position.Right} className={HANDLE} />
    </div>
  );
}

function FileNode({ data }: NodeProps<GNode>) {
  const tone = data.highlighted
    ? "border-destructive/60 bg-destructive/[0.07] text-foreground"
    : "border-border bg-card text-muted-foreground";
  return (
    <div
      className={`flex h-full w-full items-center gap-1.5 rounded-md border px-2.5 font-mono text-[12px] ${tone}`}
      title={data.sub}
    >
      <Handle type="target" position={Position.Left} className={HANDLE} />
      {data.isTest && (
        <span className="rounded bg-warning/15 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-warning">
          test
        </span>
      )}
      <span className="truncate">{data.label}</span>
      <Handle type="source" position={Position.Right} className={HANDLE} />
    </div>
  );
}

function CallSiteNode({ data }: NodeProps<GNode>) {
  const tone = data.isAliased
    ? "border-warning/60 bg-warning/12 text-warning"
    : data.highlighted
      ? "border-destructive/40 bg-destructive/[0.05] text-foreground"
      : "border-border bg-card text-muted-foreground";
  return (
    <div className={`flex h-full w-full items-center rounded border px-2 font-mono text-[11px] ${tone}`}>
      <Handle type="target" position={Position.Left} className={HANDLE} />
      <span className="truncate">
        {data.label}
        {data.isAliased ? " ⟨alias⟩" : ""}
      </span>
    </div>
  );
}

const nodeTypes = { package: PackageNode, file: FileNode, call_site: CallSiteNode };

function buildGraph(
  layout: GraphLayout,
  target: string | undefined,
  highlighted: Set<string>,
  aliasSyms: Set<string>,
): { rfNodes: GNode[]; rfEdges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 22, ranksep: 72, marginx: 24, marginy: 24 });
  graph.setDefaultEdgeLabel(() => ({}));
  const dims = new Map<string, { w: number; h: number }>();
  for (const node of layout.nodes) {
    const shown = node.kind === "file" ? basename(node.label) : node.label;
    const w = nodeWidth(node.kind, shown);
    const h = NODE_H[node.kind] ?? 34;
    dims.set(node.id, { w, h });
    graph.setNode(node.id, { width: w, height: h });
  }
  for (const edge of layout.edges) graph.setEdge(edge.src, edge.dst);
  dagre.layout(graph);

  const rfNodes: GNode[] = layout.nodes.map((node) => {
    const point = graph.node(node.id);
    const dim = dims.get(node.id) as { w: number; h: number };
    return {
      id: node.id,
      type: node.kind,
      position: { x: point.x - dim.w / 2, y: point.y - dim.h / 2 },
      style: { width: dim.w, height: dim.h },
      data: {
        label: node.kind === "file" ? basename(node.label) : node.label,
        sub: node.label,
        highlighted: highlighted.has(node.id),
        isTarget: node.kind === "package" && node.label === target,
        isTest: node.kind === "file" && isTestFile(node.label),
        isAliased: node.kind === "call_site" && aliasSyms.has(node.label),
      },
    };
  });

  const rfEdges: Edge[] = layout.edges.map((edge) => {
    const on = highlighted.has(edge.src) && highlighted.has(edge.dst);
    const color = on ? "hsl(var(--destructive))" : "hsl(var(--border))";
    return {
      id: `${edge.src}__${edge.dst}`,
      source: edge.src,
      target: edge.dst,
      markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13, color },
      style: {
        stroke: color,
        strokeWidth: on ? 1.6 : 1,
        strokeDasharray: edge.kind === "calls" ? "3 3" : undefined,
      },
      animated: on,
    };
  });

  return { rfNodes, rfEdges };
}

export function GraphPanel({
  layout,
  plan,
  underwriting,
}: {
  layout: GraphLayout | null;
  plan: SurgeryPlan | null;
  underwriting?: UnderwritingReport | null;
}) {
  const { isDark } = useTheme();
  const [focus, setFocus] = useState<string | null>(null);

  const aliasSyms = useMemo(
    () => new Set((plan?.call_sites ?? []).filter((c) => c.is_aliased).map((c) => c.symbol)),
    [plan],
  );
  const highlighted = useMemo(() => {
    if (!layout) return new Set<string>();
    if (focus) return importersOf(focus, layout.edges);
    return new Set(layout.nodes.filter((node) => node.impacted).map((node) => node.id));
  }, [layout, focus]);

  const graph = useMemo(
    () => (layout ? buildGraph(layout, plan?.target_package, highlighted, aliasSyms) : null),
    [layout, plan, highlighted, aliasSyms],
  );

  if (!layout || layout.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-10 text-center text-sm text-muted-foreground">
        <p className="max-w-md">
          Scan a public repository to build the module graph. Edges are real{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px] text-foreground">import</code> /{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px] text-foreground">require</code>{" "}
          relationships — including the aliased ones a grep misses.
        </p>
      </div>
    );
  }

  const files = layout.nodes.filter((node) => node.kind === "file" && highlighted.has(node.id));
  const breakingTests = files.filter((node) => isTestFile(node.label)).length;
  const focusName = focus
    ? layout.nodes.find((node) => node.id === focus)?.label ?? "dependency"
    : plan?.target_package ?? "dependency";

  return (
    <div className="relative h-full">
      <div className="pointer-events-none absolute left-3 top-3 z-10 flex items-center gap-2">
        <span className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/[0.06] px-2.5 py-1 text-[11.5px] font-medium text-destructive">
          <span className="h-1.5 w-1.5 rounded-full bg-destructive" />
          {focus ? `importers of ${focusName}` : "blast radius"} · {files.length} file
          {files.length === 1 ? "" : "s"}
          {breakingTests > 0 && (
            <>
              {" "}· {breakingTests} test{breakingTests === 1 ? "" : "s"} break
            </>
          )}
        </span>
        {focus ? (
          <button
            className="pointer-events-auto rounded-full border bg-card px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent"
            onClick={() => setFocus(null)}
          >
            reset
          </button>
        ) : (
          underwriting != null &&
          underwriting.failing_tests.length > 0 && (
            <span className="pointer-events-auto rounded-full border bg-card px-2.5 py-1 text-[11px] text-muted-foreground">
              {underwriting.failing_tests.length} kill-test failure
              {underwriting.failing_tests.length === 1 ? "" : "s"}
            </span>
          )
        )}
      </div>
      <ReactFlow
        colorMode={isDark ? "dark" : "light"}
        nodes={graph?.rfNodes ?? []}
        edges={graph?.rfEdges ?? []}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.15}
        maxZoom={2.5}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_event, node) => {
          if (node.type === "package") setFocus((current) => (current === node.id ? null : node.id));
        }}
      >
        <Background gap={22} className="!bg-transparent" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      <div className="pointer-events-none absolute bottom-2.5 left-4 text-[10px] text-muted-foreground">
        scroll to zoom · drag to pan · click a package to trace its importers
      </div>
    </div>
  );
}
