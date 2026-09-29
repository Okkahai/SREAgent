#!/usr/bin/env bash
# Inject or clear a reversible fault in a running demo service.
#   scripts/fault.sh <checkout|payments|gateway> set <fault> [json-params]
#   scripts/fault.sh <checkout|payments|gateway> clear [fault]
#   scripts/fault.sh <service> list
# Faults: http_500 {"rate":0.4}, db_timeout, memory_spike {"mb":200}, down, latency {"seconds":1}
set -euo pipefail
declare -A PORTS=([gateway]=8080 [checkout]=8081 [payments]=8082)
svc="${1:?service}"; cmd="${2:?set|clear|list}"
port="${PORTS[$svc]:?unknown service $svc}"
base="http://127.0.0.1:${port}/_faults"
case "$cmd" in
  set)   curl -fsS -X PUT "$base/${3:?fault name}" -H 'content-type: application/json' -d "${4:-{\}}" ;;
  clear) curl -fsS -X DELETE "$base${3:+?name=$3}" ;;
  list)  curl -fsS "$base" ;;
  *) echo "unknown command $cmd" >&2; exit 2 ;;
esac
echo
