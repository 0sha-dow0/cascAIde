import type {
  FireIncidentResponse, RegisterRepoResponse, ReviewResponse, StrategyKind, Transplant,
} from "./types";

const TOKEN = "demo-token";
const headers = { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" };

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}
async function toError(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: { message?: string }; message?: string };
    return new Error(body.detail?.message ?? body.message ?? `HTTP ${res.status}`);
  } catch {
    return new Error(`HTTP ${res.status}`);
  }
}

export interface FileDecisionIn { path: string; kind: "accept" | "reject"; reason: string | null; }

export const api = {
  registerRepo: (url: string) => post<RegisterRepoResponse>("/repos", { url, owner: "demo" }),
  fireIncident: (repoId: string) => post<FireIncidentResponse>("/incidents", { repo_id: repoId }),
  chooseStrategy: (incidentId: string, strategy: StrategyKind) =>
    post<unknown>(`/incidents/${incidentId}/strategy`, { strategy }),
  getTransplant: (transplantId: string) => get<Transplant>(`/transplants/${transplantId}`),
  submitReview: (transplantId: string, decision: "accept_all" | "reject", perFile: FileDecisionIn[], reason: string | null) =>
    post<ReviewResponse>(`/transplants/${transplantId}/review`, { decision, per_file: perFile, reason }),
};
