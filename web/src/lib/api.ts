export type Readiness = { status: "ready" | "degraded"; checks: Record<string, string> };

export type Deployment = {
  id?: string;
  version: string;
  commit_sha: string | null;
  started_at: string;
  service?: string;
  environment?: string;
  status?: string;
  ci_run_url?: string | null;
};

export type IncidentSummary = {
  id: string;
  short_id: string;
  title: string;
  status: string;
  severity: string;
  service: string;
  environment: string;
  rule: string;
  started_at: string;
  detected_at: string;
  resolved_at: string | null;
  confidence: string | null;
  outcome: { mttd_s?: number; mttr_s?: number; result?: string } | null;
  deployment: Deployment | null;
};

export type TimelineEvent = {
  occurred_at: string;
  kind: string;
  source: string;
  level: string;
  summary: string;
};

export type Evidence = {
  id: string;
  level: string;
  type: string;
  summary: string;
  ref: Record<string, unknown>;
  captured_query: string | null;
  created_by: string;
  created_at: string;
};

export type Investigation = {
  id: string;
  status: string;
  model: string | null;
  error: string | null;
  result: { summary?: string; unknowns?: string[]; rejected?: string[] } | null;
  started_at: string;
  finished_at: string | null;
};

export type Proposal = {
  id: string;
  type: string;
  title: string;
  risk: string;
  status: string;
  payload_hash: string;
  expires_at: string;
};

export type Commit = {
  repo: string;
  sha: string;
  message: string;
  author: string | null;
  url: string | null;
  owners: string[];
  files: { path: string; status: string; additions: number; deletions: number }[];
};

export type IncidentDetail = IncidentSummary & {
  timeline: TimelineEvent[];
  evidence: Evidence[];
  investigations: Investigation[];
  proposals: Proposal[];
  commit: Commit | null;
  ci_runs: { name: string; status: string; conclusion: string | null; html_url: string | null }[];
};

export type ServiceRow = {
  name: string;
  environment: string;
  request_count: number;
  error_count: number;
  error_rate: number | null;
  requests_per_second: number;
  latency_p95_ms: number | null;
  latest_version: string | null;
  latest_commit: string | null;
  latest_deployed_at: string | null;
};

const API_URL =
  process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Server-side GET. Returns null when the API is unreachable or answers an error. */
export async function api<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export const fetchReadiness = () => api<Readiness>("/readyz");
