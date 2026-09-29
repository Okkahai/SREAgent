import Badge from "@/components/Badge";
import Refresh from "@/components/Refresh";
import { api, type IncidentDetail } from "@/lib/api";
import { fmtDuration, fmtTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const inc = await api<IncidentDetail>(`/v1/incidents/${encodeURIComponent(id)}`);
  if (inc === null) {
    return <main><h1>Incident {id}</h1><div className="empty">Incident not found, or the API is unreachable.</div></main>;
  }
  const hypotheses = inc.evidence.filter((e) => e.level === "HYPOTHESIS");
  const observations = inc.evidence.filter((e) => e.level !== "HYPOTHESIS");
  return (
    <main>
      <Refresh />
      <h1>
        {inc.short_id} <span className="dim">{inc.title}</span>
      </h1>
      <p>
        <Badge value={inc.status} /> <Badge value={inc.severity} /> {inc.service} ({inc.environment}) · rule {inc.rule} ·
        onset {fmtTime(inc.started_at)} · detected {fmtTime(inc.detected_at)}
        {inc.resolved_at && <> · resolved {fmtTime(inc.resolved_at)} (MTTD {fmtDuration(inc.outcome?.mttd_s)}, MTTR {fmtDuration(inc.outcome?.mttr_s)})</>}
        {inc.confidence !== null && <> · confidence {inc.confidence}</>}
      </p>
      {inc.deployment && (
        <p className="dim">
          Correlated deployment (a link, not proof): {inc.deployment.version}{" "}
          <span className="mono">{inc.deployment.commit_sha?.slice(0, 7)}</span> at {fmtTime(inc.deployment.started_at)}
        </p>
      )}

      <h2>Investigation</h2>
      {inc.investigations.length === 0 ? <div className="empty">Not investigated yet.</div> : inc.investigations.map((v) => (
        <div className="card" key={v.id}>
          <Badge value={v.status} /> <span className="dim">{v.model ?? "no model"} · {fmtTime(v.started_at)}</span>
          {v.error && <p className="bad">{v.error}</p>}
          {v.result?.summary && <p>{v.result.summary}</p>}
          {v.result?.unknowns && v.result.unknowns.length > 0 && (
            <p className="dim">Unknowns: {v.result.unknowns.join("; ")}</p>
          )}
        </div>
      ))}
      {hypotheses.map((h) => {
        const cited = (h.ref.evidence_ids as string[] | undefined) ?? [];
        return (
          <div className="hyp" key={h.id}>
            <Badge value="HYPOTHESIS" /> <b>{h.summary}</b>
            <div className="dim">
              {String(h.ref.category)} · confidence {String(h.ref.confidence)} · evidence:{" "}
              {cited.map((c) => <a key={c} href={`#ev-${c}`}>{c.slice(0, 8)} </a>)}
            </div>
            {typeof h.ref.reasoning === "string" && h.ref.reasoning && <div>{h.ref.reasoning}</div>}
          </div>
        );
      })}

      {inc.commit && (
        <>
          <h2>Suspect commit</h2>
          <div className="card">
            <a href={inc.commit.url ?? "#"}><span className="mono">{inc.commit.sha.slice(0, 7)}</span></a> {inc.commit.message.split("\n")[0]}
            <div className="dim">{inc.commit.author} · owners: {inc.commit.owners.join(", ") || "none"}</div>
            <ul>{inc.commit.files.map((f) => <li key={f.path} className="mono">{f.path} (+{f.additions}/-{f.deletions})</li>)}</ul>
          </div>
        </>
      )}
      {inc.ci_runs.length > 0 && (
        <>
          <h2>CI runs for the commit</h2>
          <ul>{inc.ci_runs.map((r, i) => <li key={i}>{r.name}: {r.conclusion ?? r.status}</li>)}</ul>
        </>
      )}

      <h2>Proposed actions</h2>
      {inc.proposals.length === 0 ? <div className="empty">No proposals.</div> : (
        <table>
          <thead><tr><th>Action</th><th>Risk (by policy)</th><th>Status</th><th>Expires</th></tr></thead>
          <tbody>
            {inc.proposals.map((p) => (
              <tr key={p.id}><td>{p.type}: {p.title}</td><td><Badge value={p.risk} /></td><td><Badge value={p.status} /></td><td>{fmtTime(p.expires_at)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="dim">Approvals go through the API with the approver token; this dashboard is read-only.</p>

      <h2>Timeline</h2>
      <table>
        <tbody>
          {inc.timeline.map((t, i) => (
            <tr key={i}>
              <td className="mono">{fmtTime(t.occurred_at)}</td><td>{t.kind}</td><td><Badge value={t.level} /></td><td>{t.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Evidence</h2>
      {observations.length === 0 ? <div className="empty">No evidence captured.</div> : observations.map((e) => (
        <div className="card" id={`ev-${e.id}`} key={e.id} style={{ marginBottom: ".5rem" }}>
          <Badge value={e.level} /> <span className="dim">{e.type} · by {e.created_by} · {e.id.slice(0, 8)}</span>
          <div>{e.summary}</div>
          <details>
            <summary>data and query</summary>
            {e.captured_query && <pre>{e.captured_query}</pre>}
            <pre>{JSON.stringify(e.ref, null, 2)}</pre>
          </details>
        </div>
      ))}
    </main>
  );
}
