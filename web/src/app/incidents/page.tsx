import IncidentTable from "@/components/IncidentTable";
import Refresh from "@/components/Refresh";
import { api, type IncidentSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Incidents() {
  const items = await api<IncidentSummary[]>("/v1/incidents?limit=100");
  return (
    <main>
      <Refresh />
      <h1>Incidents</h1>
      {items === null ? <div className="empty">API unreachable.</div> : <IncidentTable items={items} />}
    </main>
  );
}
