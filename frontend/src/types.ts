export type IncidentStatus =
  | "pending" | "running" | "awaiting_review"
  | "completed" | "rejected" | "contested" | "failed";

export type NodeKind = "package" | "file" | "call_site";

export interface CallSite {
  file_path: string;
  line: number;
  symbol: string;
  is_aliased: boolean;
  alias: string | null;
  snippet: string;
}
export interface SurgeryPlan {
  target_package: string;
  call_sites: CallSite[];
  affected_files: string[];
}
export interface GraphNode { id: string; x: number; y: number; kind: NodeKind; label: string; }
export interface GraphEdge { src: string; dst: string; kind: string; }
export interface GraphLayout { nodes: GraphNode[]; edges: GraphEdge[]; }
export interface Centrality { package: string; score: number; }
export interface Warning { shape: string; reason: string; }
export interface UnderwritingReport {
  affected_file_count: number;
  failing_tests: string[];
  centrality: Centrality[];
  warnings: Warning[];
  target_package: string;
}
export interface Repo { id: string; url: string; owner: string; registered_at: string; }
export interface RegisterRepoResponse {
  repo: Repo;
  surgery_plan: SurgeryPlan;
  graph_layout: GraphLayout;
  underwriting: UnderwritingReport;
}
export type StrategyKind = "upgrade" | "shim" | "transplant" | "accept_risk";
export interface MitigationOption {
  kind: StrategyKind; title: string; effort: string;
  blast_radius: string; residual_risk: string; executable: boolean; rationale: string;
}
export interface Incident { id: string; repo_id: string; status: IncidentStatus; chosen_strategy: StrategyKind | null; }
export interface FireIncidentResponse { incident: Incident; options: { incident_id: string; options: MitigationOption[] }; }
export interface PipelineEvent { incident_id: string; stage: string; seq: number; message: string; at: string; terminal: boolean; }
export interface FileDiff { path: string; unified_diff: string; before: string; after: string; }
export type Verdict = "approve" | "reject";
export interface JudgeVerdict { judge_name: string; verdict: Verdict; rationale: string; }
export interface ConsensusResult { approvals: number; panel_size: number; approved: boolean; contested: boolean; verdicts: JudgeVerdict[]; }
export interface Transplant { id: string; incident_id: string; diff: FileDiff[]; consensus: ConsensusResult; }
export interface PullRequestRef { number: number; url: string; }
export interface ReviewResponse { status: IncidentStatus; pull_request: PullRequestRef | null; }
