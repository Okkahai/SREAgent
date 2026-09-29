import Link from "next/link";
import type { IncidentSummary } from "@/lib/api";
import { fmtDuration, fmtTime } from "@/lib/format";
import Badge from "./Badge";

export default function IncidentTable({ items }: { items: IncidentSummary[] }) {
  if (items.length === 0) return <div className="empty">No incidents.</div>;
  return (
    <table>
      <thead>
        <tr><th>Incident</th><th>Status</th><th>Severity</th><th>Service</th><th>Detected</th><th>MTTR</th></tr>
      </thead>
      <tbody>
        {items.map((i) => (
          <tr key={i.id}>
            <td><Link href={`/incidents/${i.short_id}`}>{i.short_id}</Link> <span className="dim">{i.title}</span></td>
            <td><Badge value={i.status} /></td>
            <td><Badge value={i.severity} /></td>
            <td>{i.service}</td>
            <td>{fmtTime(i.detected_at)}</td>
            <td>{fmtDuration(i.outcome?.mttr_s)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
