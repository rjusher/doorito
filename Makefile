.DEFAULT_GOAL := help

# Django command prefix (django-configurations requires these env vars)
MANAGE = DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py

# Docker Compose with dev override
COMPOSE_DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml

# PEP directory lookup (used by claude-pep-* targets that take PEP=NNNN)
PEP_DIR = $(shell ls -d PEPs/PEP_$(PEP)_* 2>/dev/null | head -1)

# Prompt variant (default: "default", override with PROMPT=variant)
PROMPT ?= default

.PHONY: help install migrate makemigrations run server shell test lint format check superuser clean tailwind-install css css-watch docker-up docker-down docker-logs docker-shell pep-new pep-complete pep-archive claude-pep-draft claude-pep-research claude-pep-plan claude-pep-discuss claude-pep-todo claude-pep-preflight claude-pep-implement claude-pep-review claude-pep-finalize

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install dev dependencies with uv
	uv pip install -r requirements-dev.txt

migrate: ## Run database migrations
	$(MANAGE) migrate

makemigrations: ## Create new migration files
	$(MANAGE) makemigrations

run: ## Start all dev services (web + celery worker)
	honcho start -f Procfile.dev

server: ## Start only the Django dev server
	$(MANAGE) runserver

shell: ## Open Django shell
	$(MANAGE) shell

test: ## Run tests with pytest
	$(MANAGE) test

lint: ## Run ruff linter
	ruff check .

format: ## Run ruff formatter
	ruff format .

check: ## Run Django system checks
	$(MANAGE) check

superuser: ## Create a superuser account
	$(MANAGE) createsuperuser

clean: ## Remove Python cache files
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '.pytest_cache' -exec rm -rf {} +

tailwind-install: ## Download Tailwind CSS standalone CLI
	curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
	chmod +x tailwindcss-linux-x64
	mv tailwindcss-linux-x64 tailwindcss

css: ## Compile Tailwind CSS (minified)
	./tailwindcss -i static/css/input.css -o static/css/main.css --minify

css-watch: ## Watch and recompile Tailwind CSS on changes
	./tailwindcss -i static/css/input.css -o static/css/main.css --watch

docker-up: ## Start dev stack in Docker (web, db)
	$(COMPOSE_DEV) up --build

docker-down: ## Stop and remove Docker dev stack
	$(COMPOSE_DEV) down

docker-logs: ## Tail Docker dev stack logs
	$(COMPOSE_DEV) logs -f

docker-shell: ## Open bash shell in the web container
	$(COMPOSE_DEV) exec web bash

pep-new: ## Create a new PEP (usage: make pep-new TITLE=my_feature)
	@scripts/pep-new.sh $(TITLE)

pep-complete: ## Validate PEP completion (usage: make pep-complete PEP=0022)
	@scripts/pep-complete.sh $(PEP)

pep-archive: ## Archive old IMPLEMENTED/LATEST.md entries (>10) to PAST file
	@scripts/pep-archive.sh

claude-pep-draft: ## Draft a new PEP with Claude (usage: make claude-pep-draft DESC="description")
	@test -n "$(DESC)" || (echo "Usage: make claude-pep-draft DESC=\"description\"" && exit 1)
	@test -f "scripts/prompts/pep-draft/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-draft/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_DESC__|$(DESC)|g' scripts/prompts/pep-draft/$(PROMPT).md)"

claude-pep-research: ## Research codebase for a PEP (usage: make claude-pep-research PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-research PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-research/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-research/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-research/$(PROMPT).md)"

claude-pep-plan: ## Refine PEP plan with deep codebase analysis (usage: make claude-pep-plan PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-plan PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-plan/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-plan/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-plan/$(PROMPT).md)"

claude-pep-discuss: ## Resolve open questions for a PEP (usage: make claude-pep-discuss PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-discuss PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-discuss/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-discuss/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-discuss/$(PROMPT).md)"

claude-pep-review: ## Review and resolve inline notes in a PEP (usage: make claude-pep-review PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-review PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-review/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-review/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-review/$(PROMPT).md)"

claude-pep-todo: ## Add detailed todo checklist to PEP plan (usage: make claude-pep-todo PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-todo PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-todo/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-todo/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-todo/$(PROMPT).md)"

claude-pep-preflight: ## Preflight check PEP plan against codebase (usage: make claude-pep-preflight PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-preflight PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-preflight/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-preflight/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-preflight/$(PROMPT).md)"

claude-pep-implement: ## Implement a PEP with Claude (usage: make claude-pep-implement PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-implement PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-implement/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-implement/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-implement/$(PROMPT).md)"

claude-pep-finalize: ## Finalize a PEP with Claude (usage: make claude-pep-finalize PEP=NNNN)
	@test -n "$(PEP)" || (echo "Usage: make claude-pep-finalize PEP=NNNN [PROMPT=variant]" && exit 1)
	@test -d "$(PEP_DIR)" || (echo "PEP directory not found for PEP $(PEP)" && exit 1)
	@test -f "scripts/prompts/pep-finalize/$(PROMPT).md" || (echo "Prompt variant not found: scripts/prompts/pep-finalize/$(PROMPT).md" && exit 1)
	@claude --permission-mode acceptEdits "$$(sed 's|__PEP_NUM__|$(PEP)|g; s|__PEP_DIR__|$(PEP_DIR)|g' scripts/prompts/pep-finalize/$(PROMPT).md)"
