const TONES: Record<string, string> = {
  CRITICAL: "bad", HIGH: "bad", MEDIUM: "warn", LOW: "ok",
  DETECTED: "bad", INVESTIGATING: "warn", IDENTIFIED: "warn", MITIGATING: "warn",
  MONITORING: "info", RESOLVED: "ok", CLOSED: "ok",
  OBSERVATION: "info", HYPOTHESIS: "warn", CONFIRMED_FACT: "ok",
  FAILED: "bad", COMPLETED: "ok", RUNNING: "info",
  PENDING_APPROVAL: "warn", APPROVED: "ok", SUCCEEDED: "ok", REJECTED: "bad", EXPIRED: "muted",
  DESTRUCTIVE: "bad", READ_ONLY: "muted",
};

export default function Badge({ value }: { value: string }) {
  return <span className={`badge ${TONES[value] ?? "muted"}`}>{value.replace("_", " ")}</span>;
}
