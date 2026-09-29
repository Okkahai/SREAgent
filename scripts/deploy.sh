#!/usr/bin/env bash
# Simulate a real deployment of checkout: recreates the container with a new version/commit.
#   scripts/deploy.sh good   -> v1.0.0, DB_POOL_SIZE=20
#   scripts/deploy.sh bad    -> v1.1.0, DB_POOL_SIZE=2   (regression: connection pool too small)
# Also records a deployment event in OpsPilot (POST /v1/deployments).
set -euo pipefail
variant="${1:?good|bad}"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
case "$variant" in
  good) export CHECKOUT_VERSION=1.0.0 CHECKOUT_DB_POOL_SIZE=20 ;;
  bad)  export CHECKOUT_VERSION=1.1.0 CHECKOUT_DB_POOL_SIZE=2 ;;
  *) echo "usage: $0 good|bad" >&2; exit 2 ;;
esac
export CHECKOUT_COMMIT="$sha"
echo "deploying checkout $CHECKOUT_VERSION (commit $sha, pool=$CHECKOUT_DB_POOL_SIZE)"
docker compose --profile demo up -d --no-deps --force-recreate checkout

started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
payload="{\"service\":\"checkout\",\"environment\":\"demo\",\"version\":\"$CHECKOUT_VERSION\",\"status\":\"SUCCEEDED\",\"started_at\":\"$started\""
[[ "$sha" =~ ^[0-9a-f]{7,40}$ ]] && payload+=",\"commit_sha\":\"$sha\""
payload+="}"
curl -fsS -X POST "${OPSPILOT_API_URL:-http://127.0.0.1:8000}/v1/deployments" \
  -H "Authorization: Bearer ${OPSPILOT_INGEST_TOKEN:-dev-ingest-token}" \
  -H 'content-type: application/json' -d "$payload" \
  || echo "warning: could not record deployment in OpsPilot" >&2
echo
