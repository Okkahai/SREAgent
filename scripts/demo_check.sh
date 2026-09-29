#!/usr/bin/env bash
# End-to-end check of the demo: healthy traffic, fault injection changes behaviour,
# telemetry (traces, metrics, logs) reaches the collector, and faults are reversible.
set -euo pipefail
gw=http://127.0.0.1:8080
code() { curl -s -o /dev/null -w '%{http_code}' -X POST "$gw/checkout" -H 'content-type: application/json' -d '{}'; }
count_errors() { local n=0; for _ in $(seq 1 20); do [ "$(code)" != 200 ] && n=$((n+1)); done; echo "$n"; }

# Burst of concurrent requests: exposes pool saturation that serial requests never reach.
count_errors_burst() {
  seq 1 60 | xargs -P 30 -I{} curl -s -o /dev/null -w '%{http_code}\n' -X POST "$gw/checkout" \
    -H 'content-type: application/json' -d '{}' | grep -vc '^200$' || true
}

echo "healthy baseline"; [ "$(count_errors)" -eq 0 ] || { echo "FAIL: baseline has errors"; exit 1; }

echo "inject payments down"; ./scripts/fault.sh payments set down >/dev/null
[ "$(count_errors)" -ge 15 ] || { echo "FAIL: dependency failure not visible"; exit 1; }
./scripts/fault.sh payments clear >/dev/null

echo "inject checkout http_500"; ./scripts/fault.sh checkout set http_500 '{"rate":1.0}' >/dev/null
[ "$(count_errors)" -ge 15 ] || { echo "FAIL: 500 spike not visible"; exit 1; }
./scripts/fault.sh checkout clear >/dev/null

echo "inject checkout db_timeout"; ./scripts/fault.sh checkout set db_timeout >/dev/null
[ "$(count_errors)" -ge 15 ] || { echo "FAIL: db timeout not visible"; exit 1; }
./scripts/fault.sh checkout clear >/dev/null

api=http://127.0.0.1:8000

# poll <description> <timeout_s> <command...>: retry the command until it succeeds or times out
poll() {
  local what="$1" timeout="$2"; shift 2
  local deadline=$((SECONDS + timeout))
  until "$@"; do
    [ "$SECONDS" -lt "$deadline" ] || { echo "FAIL: timed out waiting for $what"; return 1; }
    sleep 5
  done
}
open_incidents() { curl -fsS "$api/v1/incidents?open_only=true"; }
has_open_incident() { [ "$(open_incidents | jq length)" -gt 0 ]; }
no_open_incident() { [ "$(open_incidents | jq length)" -eq 0 ]; }
has_open_incident_for_version() {
  open_incidents | jq -e --arg v "$1" 'map(select(.deployment.version == $v)) | length > 0' >/dev/null
}
burst_and_check_version() { count_errors_burst >/dev/null; has_open_incident_for_version "$1"; }

echo "sustained fault -> incident detected (checkout http_500 60%)"
./scripts/fault.sh checkout set http_500 '{"rate":0.6}' >/dev/null
poll "incident for sustained 500s" 180 has_open_incident
short_id="$(open_incidents | jq -r '.[0].short_id')"
detail="$(curl -fsS "$api/v1/incidents/$short_id")"
echo "$short_id: $(jq -r .title <<<"$detail")"
jq -e '(.timeline | length) >= 2 and (.evidence | length) >= 1 and (.evidence | all(.level == "OBSERVATION"))' \
  <<<"$detail" >/dev/null || { echo "FAIL: incident lacks timeline/observation evidence"; exit 1; }
./scripts/fault.sh checkout clear >/dev/null

echo "recovery -> incidents resolve"
poll "incidents to resolve" 360 no_open_incident

echo "bad deployment (checkout pool size 20 -> 2) under load"
./scripts/deploy.sh bad >/dev/null 2>&1
poll "incident linked to deployment 1.1.0" 300 burst_and_check_version 1.1.0
curl -fsS "$api/v1/incidents" | jq -c 'map({short_id, rule, severity, status, version: .deployment.version})'
./scripts/deploy.sh good >/dev/null 2>&1
poll "incidents to resolve after rollback" 420 no_open_incident
curl -fsS "$api/v1/incidents" | jq -e 'map(select(.status == "RESOLVED" and .outcome.mttr_s > 0)) | length > 0' \
  >/dev/null || { echo "FAIL: no resolved incident with outcome metrics"; exit 1; }

echo "recovery"; [ "$(count_errors)" -eq 0 ] || { echo "FAIL: did not recover"; exit 1; }

echo "telemetry at collector"
sleep 6
logs="$(docker compose logs otel-collector 2>&1)"
for sig in traces metrics logs; do
  # here-string, not a pipe: grep -q exits early and would SIGPIPE echo under pipefail
  grep -qE "\"kind\": \"exporter\", \"data_type\": \"$sig\"" <<<"$logs" || { echo "FAIL: no $sig at collector"; exit 1; }
done
echo "telemetry stored in OpsPilot"
sleep 20   # let the 15s rollup task run
stats="$(curl -fsS "$api/v1/telemetry/stats")"; echo "$stats"
for t in spans log_records metric_points; do
  [ "$(jq ".$t" <<<"$stats")" -gt 0 ] || { echo "FAIL: no $t stored in OpsPilot"; exit 1; }
done
services="$(curl -fsS "$api/v1/services")"
jq -e 'map(select(.name=="checkout")) | length == 1' <<<"$services" >/dev/null || { echo "FAIL: checkout not registered"; exit 1; }
deploys="$(curl -fsS "$api/v1/deployments?service=checkout")"
jq -e 'map(.version) | (index("1.1.0") != null and index("1.0.0") != null)' <<<"$deploys" >/dev/null \
  || { echo "FAIL: bad/good deployments not recorded"; exit 1; }
echo "OK"
