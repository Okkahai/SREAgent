.PHONY: help up down logs ps build test lint fmt web-check check-compose smoke

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
