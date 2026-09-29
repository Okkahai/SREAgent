export type Readiness = {
  status: "ready" | "degraded";
  checks: Record<string, string>;
};

const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchReadiness(): Promise<Readiness | null> {
  try {
    const res = await fetch(`${API_URL}/readyz`, { cache: "no-store" });
    return (await res.json()) as Readiness;
  } catch {
    return null;
  }
}
