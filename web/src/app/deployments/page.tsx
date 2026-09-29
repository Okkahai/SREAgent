import Badge from "@/components/Badge";
import Refresh from "@/components/Refresh";
import { api, type Deployment } from "@/lib/api";
import { fmtTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Deployments() {
  const rows = await api<Deployment[]>("/v1/deployments?limit=100");
  return (
    <main>
      <Refresh />
      <h1>Deployments</h1>
      {rows === null ? <div className="empty">API unreachable.</div> : rows.length === 0 ? (
        <div className="empty">No deployments recorded. Send one with POST /v1/deployments.</div>
      ) : (
        <table>
          <thead><tr><th>Service</th><th>Env</th><th>Version</th><th>Commit</th><th>Status</th><th>Started</th></tr></thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.service}</td><td>{d.environment}</td><td>{d.version}</td>
                <td className="mono">{d.commit_sha?.slice(0, 7) ?? "—"}</td>
                <td><Badge value={d.status ?? "SUCCEEDED"} /></td><td>{fmtTime(d.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
