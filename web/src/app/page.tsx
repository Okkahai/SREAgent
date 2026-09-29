import Refresh from "@/components/Refresh";
import IncidentTable from "@/components/IncidentTable";
import { api, fetchReadiness, type Deployment, type IncidentSummary, type ServiceRow } from "@/lib/api";
import { fmtTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [ready, open, services, deployments, stats] = await Promise.all([
    fetchReadiness(),
    api<IncidentSummary[]>("/v1/incidents?open_only=true"),
    api<ServiceRow[]>("/v1/services"),
    api<Deployment[]>("/v1/deployments?limit=5"),
    api<Record<string, number>>("/v1/telemetry/stats"),
  ]);
  if (ready === null) {
    return <main><h1>Overview</h1><div className="empty">API unreachable.</div></main>;
  }
  return (
    <main>
      <Refresh />
      <h1>Overview</h1>
      <div className="cards">
        <div className="card"><span className="dim">Open incidents</span><b>{open?.length ?? "—"}</b></div>
        <div className="card"><span className="dim">Services</span><b>{services?.length ?? "—"}</b></div>
        <div className="card"><span className="dim">Platform</span><b>{ready.status}</b></div>
        {stats && Object.entries(stats).map(([k, v]) => (
          <div className="card" key={k}><span className="dim">{k} (10 min)</span><b>{v}</b></div>
        ))}
      </div>
      <h2>Open incidents</h2>
      {open && open.length > 0 ? <IncidentTable items={open} /> : <div className="empty">No open incidents.</div>}
      <h2>Recent deployments</h2>
      {deployments && deployments.length > 0 ? (
        <table>
          <tbody>
            {deployments.map((d) => (
              <tr key={d.id}><td>{d.service}</td><td>{d.version}</td><td className="mono">{d.commit_sha?.slice(0, 7) ?? "—"}</td><td>{fmtTime(d.started_at)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="empty">No deployments recorded.</div>
      )}
    </main>
  );
}
