# Deploying on one cheap server (Hetzner VPS)

One VPS runs the whole stack with `docker-compose.prod.yml`: Caddy (HTTPS), api, worker, beat, web, Postgres, Redis. Only ports 80/443 are published. Memory limits total ~1.7 GB; use a plan with **4 GB RAM** if the server also hosts another app, 2 GB is enough for OpsPilot alone. Check current prices on hetzner.com/cloud.

## 1. Server and DNS
1. Create an Ubuntu 24.04 server (Hetzner Cloud console), add your SSH key.
2. Point two DNS A records at its IP: `opspilot.example.com` (dashboard) and `api.opspilot.example.com` (ingest, webhooks, approvals).
3. Firewall (Hetzner console or `ufw`): allow 22, 80, 443 only.

## 2. Install Docker, swap, clone
```bash
ssh root@SERVER_IP
curl -fsSL https://get.docker.com | sh
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
git clone https://github.com/okkahai/sreagent /opt/sreagent && cd /opt/sreagent
```

## 3. Configure
```bash
cp .env.prod.example .env
# secrets: run `openssl rand -hex 24` once per value
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'YOUR-DASHBOARD-PASSWORD'
```
Fill in `.env`: the two domains, `POSTGRES_PASSWORD`, the three tokens, and the dashboard hash with **every `$` doubled to `$$`**. Optional: `ANTHROPIC_API_KEY` (otherwise the rule-based investigator is used), `GITHUB_*`. Leave `OPSPILOT_ACTIONS_ENABLED=false`.

## 4. Start
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl https://api.opspilot.example.com/healthz
```
Open `https://opspilot.example.com` and log in with `DASH_USER` and your password. Restarts after a reboot are automatic (`restart: unless-stopped`).

## 5. Send telemetry from your apps
Apps export OTLP/HTTP straight to the API (the dev collector is not part of this stack):
```
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.opspilot.example.com/v1/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <OPSPILOT_INGEST_TOKEN>
```
Record deployments with `POST https://api.../v1/deployments` (same token). Approvals: `POST /v1/proposals/{id}/decision` with the approver token.

## 6. Backups and updates
```bash
echo '0 3 * * * cd /opt/sreagent && ./scripts/backup.sh' | crontab -   # keeps 7 daily dumps in /var/backups/opspilot
git pull && docker compose -f docker-compose.prod.yml up -d --build      # update (migrations run on api start)
```
Copy `/var/backups/opspilot` off the server (Hetzner Storage Box, `rclone`) so a lost server does not lose the backups.
Restore: `docker compose -f docker-compose.prod.yml exec -T postgres pg_restore -U opspilot -d opspilot --clean < file.dump`.

## Not verified
The compose file passes `docker compose config`, but this stack has not been run on a real Hetzner server and the Caddyfile has not been validated by Caddy. Memory limits are estimates; watch `docker stats` the first days. The dashboard has a single shared basic-auth login, not per-user accounts.
