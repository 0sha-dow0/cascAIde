import type {
  FireIncidentResponse, ImplementationPlan, RegisterRepoResponse,
  ReviewResponse, StrategyKind, Transplant,
} from "./types";

export type DiscussKind = "issue" | "discussion";
export interface DiscussResult { kind: DiscussKind; number: number | null; url: string; }

import { API_BASE, bearerToken, clearSession, getSession, refreshSession } from "./session";

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken()}`, "Content-Type": "application/json" };
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res = await fetch(url, { ...init, headers: authHeaders() });
  if (res.status === 401 && getSession()) {
    // Access token likely expired — refresh once and retry, else drop the session.
    if (await refreshSession()) {
      res = await fetch(url, { ...init, headers: authHeaders() });
    } else {
      clearSession();
      window.location.hash = "";
    }
  }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}
async function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { detail?: { message?: string }; message?: string };
    return new ApiError(res.status, body.detail?.message ?? body.message ?? `HTTP ${res.status}`);
  } catch {
    return new ApiError(res.status, `HTTP ${res.status}`);
  }
}

export interface FileDecisionIn { path: string; kind: "accept" | "reject"; reason: string | null; }

export const api = {
  registerRepo: (url: string) => post<RegisterRepoResponse>("/repos", { url, owner: "demo" }),
  fireIncident: (repoId: string) => post<FireIncidentResponse>("/incidents", { repo_id: repoId }),
  chooseStrategy: (incidentId: string, strategy: StrategyKind) =>
    post<unknown>(`/incidents/${incidentId}/strategy`, { strategy }),
  explore: (incidentId: string, strategy: StrategyKind) =>
    post<ImplementationPlan>(`/incidents/${incidentId}/explore`, { strategy }),
  discuss: (incidentId: string, kind: DiscussKind) =>
    post<DiscussResult>(`/incidents/${incidentId}/discuss`, { kind }),
  getTransplant: (transplantId: string) => get<Transplant>(`/transplants/${transplantId}`),
  submitReview: (transplantId: string, decision: "accept_all" | "reject", perFile: FileDecisionIn[], reason: string | null) =>
    post<ReviewResponse>(`/transplants/${transplantId}/review`, { decision, per_file: perFile, reason }),
};
