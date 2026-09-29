#!/usr/bin/env bash
# End-to-end check of the demo: healthy traffic, fault injection changes behaviour,
# telemetry (traces, metrics, logs) reaches the collector, and faults are reversible.
set -euo pipefail
gw=http://127.0.0.1:8080
code() { curl -s -o /dev/null -w '%{http_code}' -X POST "$gw/checkout" -H 'content-type: application/json' -d '{}'; }
count_errors() { local n=0; for _ in $(seq 1 20); do [ "$(code)" != 200 ] && n=$((n+1)); done; echo "$n"; }

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

echo "bad deployment (checkout pool size 20 -> 2) under load"
./scripts/deploy.sh bad >/dev/null 2>&1
sleep 20
[ "$(count_errors)" -ge 1 ] || { echo "FAIL: bad deployment did not degrade checkout"; exit 1; }
./scripts/deploy.sh good >/dev/null 2>&1
sleep 20

echo "recovery"; sleep 1; [ "$(count_errors)" -eq 0 ] || { echo "FAIL: did not recover"; exit 1; }

echo "telemetry at collector"
sleep 6
logs="$(docker compose logs otel-collector 2>&1)"
for sig in traces metrics logs; do
  echo "$logs" | grep -qE "(otelcol.signal|data_type)\": \"$sig\"" || { echo "FAIL: no $sig at collector"; exit 1; }
done
echo "OK"
