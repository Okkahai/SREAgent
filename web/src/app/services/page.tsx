import Refresh from "@/components/Refresh";
import { api, type ServiceRow } from "@/lib/api";
import { fmtPct, fmtTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Services() {
  const rows = await api<ServiceRow[]>("/v1/services");
  return (
    <main>
      <Refresh />
      <h1>Services <span className="dim">(last 5 minutes)</span></h1>
      {rows === null ? <div className="empty">API unreachable.</div> : rows.length === 0 ? (
        <div className="empty">No services yet. They appear when telemetry or a deployment arrives.</div>
      ) : (
        <table>
          <thead><tr><th>Service</th><th>Env</th><th>Req/s</th><th>Error rate</th><th>p95 ms</th><th>Version</th><th>Deployed</th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={`${s.name}/${s.environment}`}>
                <td>{s.name}</td><td>{s.environment}</td>
                <td>{s.requests_per_second.toFixed(2)}</td>
                <td className={s.error_rate !== null && s.error_rate > 0.02 ? "bad" : ""}>{fmtPct(s.error_rate)}</td>
                <td>{s.latency_p95_ms?.toFixed(0) ?? "—"}</td>
                <td>{s.latest_version ?? "—"} <span className="mono dim">{s.latest_commit?.slice(0, 7)}</span></td>
                <td>{fmtTime(s.latest_deployed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
