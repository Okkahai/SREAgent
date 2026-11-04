#!/usr/bin/env bash
# Daily Postgres dump, keeps the last 7. Cron: 0 3 * * * cd /opt/sreagent && ./scripts/backup.sh
set -euo pipefail
dir="${BACKUP_DIR:-/var/backups/opspilot}"
mkdir -p "$dir"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U opspilot -Fc opspilot > "$dir/opspilot-$(date +%F).dump"
ls -1t "$dir"/opspilot-*.dump | tail -n +8 | xargs -r rm --
