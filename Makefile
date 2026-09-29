.PHONY: k8s-render kind-up kind-check kind-down demo-up demo-down demo-telemetry demo-check help up down logs ps build test lint fmt web-check check-compose smoke

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Build and start the full local stack
	docker compose up -d --build --wait

down: ## Stop the stack (keeps volumes)
	docker compose down

logs: ## Tail logs
	docker compose logs -f --tail=100

ps: ## Show service status
	docker compose ps

test: ## Backend unit tests (INTEGRATION=1 make test needs the stack up)
	cd backend && python -m pytest -q

lint: ## Ruff + mypy (backend), eslint + tsc (web)
	cd backend && ruff check . && ruff format --check . && mypy
	cd web && npm run lint && npm run typecheck

fmt: ## Auto-format backend
	cd backend && ruff check --fix . && ruff format .

check-compose: ## Validate compose file
	docker compose config -q

smoke: ## Hit health endpoints of the running stack
	curl -fsS localhost:8000/healthz && echo
	curl -fsS localhost:8000/readyz && echo
	curl -fsS -o /dev/null -w "web: %{http_code}\n" localhost:3000

demo-up: .env ## Start the stack plus the demo shop and load generator
	docker compose --profile demo up -d --build --wait

demo-down: ## Stop everything including demo services
	docker compose --profile demo down

demo-telemetry: ## Show OTLP telemetry arriving at the collector
	docker compose logs --tail=40 otel-collector

demo-check: ## Smoke test: demo traffic works and faults change behaviour
	./scripts/demo_check.sh

k8s-render: ## Render the kind overlay (Kustomize)
	kubectl kustomize --load-restrictor=LoadRestrictionsNone deploy/k8s/overlays/kind

kind-up: ## Create a kind cluster, build/load images and deploy OpsPilot + demo
	./scripts/kind.sh up

kind-check: ## Run the failure-injection scenario against the kind deployment
	./scripts/kind.sh check

kind-down: ## Delete the kind cluster
	./scripts/kind.sh down
