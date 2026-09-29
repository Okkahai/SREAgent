#!/usr/bin/env bash
# Run OpsPilot and the demo shop on a kind cluster (Phase 9). Needs docker, kind, kubectl, jq.
#   scripts/kind.sh up       create cluster, build + load images, deploy, wait
#   scripts/kind.sh deploy   (re)apply manifests and wait for rollouts
#   scripts/kind.sh check    port-forward and run the failure-injection scenario
#   scripts/kind.sh down     delete the cluster
set -euo pipefail
cd "$(dirname "$0")/.."
CLUSTER="${KIND_CLUSTER:-opspilot}"
NS=opspilot
PIDS=/tmp/opspilot-port-forwards.pids

images() {
  docker build -q -t opspilot/backend:ci backend
  docker build -q -t opspilot/web:ci web
  docker build -q -t opspilot/demo-shop:ci demo/shop
  kind load docker-image --name "$CLUSTER" opspilot/backend:ci opspilot/web:ci opspilot/demo-shop:ci
}

deploy() {
  kubectl kustomize --load-restrictor=LoadRestrictionsNone deploy/k8s/overlays/kind | kubectl apply -f -
  kubectl -n $NS wait --for=condition=complete job/migrate --timeout=300s
  kubectl -n $NS rollout status statefulset/postgres --timeout=300s
  for d in redis shop-db api worker beat web otel-collector payments checkout gateway loadgen; do
    kubectl -n $NS rollout status "deployment/$d" --timeout=300s
  done
}

forward() {
  : >"$PIDS"
  # service port-forwards die when their pod is replaced (e.g. checkout rollouts), so retry forever
  for m in api:8000:8000 web:3000:3000 gateway:8080:8000 checkout:8081:8000 payments:8082:8000; do
    IFS=: read -r svc local remote <<<"$m"
    (while true; do kubectl -n $NS port-forward "svc/$svc" "$local:$remote" >/dev/null 2>&1 || true; sleep 1; done) &
    echo $! >>"$PIDS"
  done
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null http://127.0.0.1:8000/readyz && curl -fsS -o /dev/null http://127.0.0.1:8080/healthz && return 0
    sleep 2
  done
  echo "port-forwards did not become ready" >&2; return 1
}

stop_forward() { [ -f "$PIDS" ] && xargs -r kill <"$PIDS" 2>/dev/null || true; }

case "${1:-}" in
  up)
    kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
    images; deploy ;;
  deploy) deploy ;;
  check)
    trap stop_forward EXIT
    forward
    DEPLOY_TARGET=k8s OPSPILOT_INGEST_TOKEN=dev-ingest-token ./scripts/demo_check.sh ;;
  down) kind delete cluster --name "$CLUSTER" ;;
  *) echo "usage: $0 up|deploy|check|down" >&2; exit 2 ;;
esac
