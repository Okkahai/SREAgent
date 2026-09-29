import { fetchReadiness } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const readiness = await fetchReadiness();
  return (
    <main style={{ maxWidth: 720, margin: "4rem auto", padding: "0 1rem" }}>
      <h1>OpsPilot</h1>
      <p>Phase 1 skeleton. The SRE dashboard arrives in Phase 8; nothing below is mocked.</p>
      <h2>Platform status</h2>
      {readiness === null ? (
        <p>API unreachable.</p>
      ) : (
        <ul>
          <li>API: {readiness.status}</li>
          {Object.entries(readiness.checks).map(([name, state]) => (
            <li key={name}>
              {name}: {state}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
