.DEFAULT_GOAL := help

UV ?= uv
.PHONY: help setup install test lint format format-check typecheck check clean

help: ## List available targets.
	@awk 'BEGIN {FS = ":.*## "; print "Targets:"} /^[a-zA-Z-]+:.*## / {printf "  %-13s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install the project and development dependencies.
	$(UV) sync

install: setup ## Alias for setup.

test: ## Run the unit tests.
	$(UV) run --frozen pytest

lint: ## Check the Python source with Ruff.
	$(UV) run --frozen ruff check

format: ## Format the Python source with Ruff.
	$(UV) run --frozen ruff format

format-check: ## Check Python formatting without changing files.
	$(UV) run --frozen ruff format --check

typecheck: ## Type-check the Python source and tests.
	$(UV) run --frozen mypy

check: test lint format-check typecheck ## Run every local CI check.

clean: ## Remove local test, lint, type-check, and coverage artifacts.
	$(RM) -r .mypy_cache .pytest_cache .ruff_cache .coverage
