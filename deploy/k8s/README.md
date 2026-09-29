# Kubernetes deployment

Kustomize layout:

| Path | Purpose |
|------|---------|
| `base/` | OpsPilot: api (HPA, PDB), worker, beat, web, otel-collector, redis, postgres (single instance, for evaluation), migration Job, NetworkPolicies |
| `demo/` | Kustomize component: the demo shop (gateway, checkout, payments, shop-db, loadgen) |
| `overlays/kind/` | Local/CI overlay: dev Secret, 1-minute recovery window, single api replica, images tagged `ci` |
| `secret.example.yaml` | The Secret contract for real environments (create it out of band) |

Render or apply (the collector config is shared with docker compose from `deploy/otel/`, hence the load restrictor):

```bash
kubectl kustomize --load-restrictor=LoadRestrictionsNone deploy/k8s/overlays/kind | kubectl apply -f -
make kind-up kind-check kind-down   # kind cluster, deploy, failure-injection scenario, cleanup
```

Hardening applied to every workload: `restricted` Pod Security level on the namespace, non-root users, `readOnlyRootFilesystem` (except Postgres), all capabilities dropped, seccomp `RuntimeDefault`, no service account token, resource requests/limits, default-deny NetworkPolicies with explicit flows (only the worker may reach the internet, HTTPS to public addresses). Actions stay disabled (`OPSPILOT_ACTIONS_ENABLED=false`) in the ConfigMap.

For production: replace `base/postgres.yaml` with a managed database (set `DATABASE_URL` in the Secret), add an Ingress to `web` and `api` (the policies already admit the `ingress-nginx` namespace), pin image digests, and install metrics-server for the HPA.
