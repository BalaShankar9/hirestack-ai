.PHONY: help setup dev dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend format build docker-up docker-down docker-logs

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────
setup: ## First-time project setup
	@echo "Installing backend dependencies…"
	python -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	@echo "Installing frontend dependencies…"
	cd frontend && npm ci
	@echo ""
	@echo "Done. Copy env files:"
	@echo "  cp backend/.env.example backend/.env"
	@echo "  cp frontend/.env.example frontend/.env.local"

# ── Development ──────────────────────────────────────────
dev-backend: ## Start backend (hot-reload)
	cd backend && python -m uvicorn main:app --reload --port 8000

dev-frontend: ## Start frontend (hot-reload)
	cd frontend && npm run dev

# ── Testing ──────────────────────────────────────────────
test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	cd backend && python -m pytest tests/ -v --tb=short

test-frontend: ## Run frontend unit tests
	cd frontend && npm test

test-e2e: ## Run Playwright E2E tests
	cd frontend && npx playwright test

# ── Linting ──────────────────────────────────────────────
lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint Python code
	ruff check backend/ ai_engine/

lint-frontend: ## Lint and type-check frontend
	cd frontend && npx next lint && npx tsc --noEmit

format: ## Auto-format all code
	ruff format backend/ ai_engine/
	cd frontend && npx prettier --write .

# ── Docker ───────────────────────────────────────────────
docker-up: ## Start all services via Docker Compose
	docker compose -f infra/docker-compose.yml up --build -d

docker-down: ## Stop Docker services
	docker compose -f infra/docker-compose.yml down

docker-logs: ## Tail Docker logs
	docker compose -f infra/docker-compose.yml logs -f

# ── Database ─────────────────────────────────────────────
db-migrate: ## Run pending Supabase migrations
	python scripts/run_migrations.py
