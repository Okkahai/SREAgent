import { expect, test } from "@playwright/test";

const API = process.env.API_URL ?? "http://localhost:8000";
const TOKEN = process.env.OPSPILOT_INGEST_TOKEN ?? "dev-ingest-token";

test("every page renders live data or an honest empty state", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Open incidents").first()).toBeVisible();

  // A real deployment event written through the real API shows up in the UI.
  const version = `e2e-${Date.now()}`;
  const res = await request.post(`${API}/v1/deployments`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: {
      service: "e2e-svc",
      environment: "e2e",
      version,
      commit_sha: "abcdef1",
      started_at: new Date().toISOString(),
    },
  });
  expect(res.ok()).toBeTruthy();

  await page.goto("/deployments");
  await expect(page.getByText(version)).toBeVisible();
  await page.goto("/services");
  await expect(page.getByRole("cell", { name: "e2e-svc" })).toBeVisible();

  await page.goto("/incidents");
  await expect(page.getByRole("heading", { name: "Incidents" })).toBeVisible();

  await page.goto("/incidents/INC-9999");
  await expect(page.getByText("Incident not found")).toBeVisible();
});
