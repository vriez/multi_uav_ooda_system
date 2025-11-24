.PHONY: help install gui dash launch gcs uav test clean

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
	@echo "Development:"
	@echo "  make test       - Run tests"
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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Cleaned cache files"
