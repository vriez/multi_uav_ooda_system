.PHONY: help install gui dash launch gcs uav test test-unit test-integration test-regression test-verbose test-coverage experiments clean

help:
	@echo "UAV System - Quick Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install    - Install dependencies"
	@echo ""
	@echo "Run:"
	@echo "  make gui        - Launch with GUI"
	@echo "  make dash       - Dashboard only"
	@echo "  make launch     - Full system"
	@echo "  make gcs        - GCS only"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Run all tests"
	@echo "  make test-unit       - Run unit tests only"
	@echo "  make test-integration- Run integration tests only"
	@echo "  make test-regression - Run regression tests only"
	@echo "  make test-verbose    - Run tests with verbose output"
	@echo "  make test-coverage   - Run tests with coverage report"
	@echo "  make experiments     - Run experiments and generate results.md"
	@echo ""
	@echo "Development:"
	@echo "  make clean      - Clean cache files"

install:
	uv sync --group dev

gui:
	uv run launch_with_gui.py

dash:
	uv run run_dashboard.py

launch:
	uv run launch.py

gcs:
	uv run python -m gcs.main

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit/ -v

test-integration:
	uv run pytest tests/integration/ -v

test-regression:
	uv run pytest tests/regression/ -v

test-verbose:
	uv run pytest -vv

test-coverage:
	uv run pytest --cov=visualization --cov=gcs --cov=uav --cov-report=html --cov-report=term

experiments:
	uv run python -m tests.experiments.run_experiments --output results.md

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Cleaned cache files"
