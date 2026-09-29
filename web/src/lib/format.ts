export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export function fmtPct(x: number | null | undefined): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`;
}

export function fmtDuration(s: number | undefined): string {
  if (s === undefined) return "—";
  return s < 120 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m`;
}
