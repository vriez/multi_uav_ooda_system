#!/bin/bash
# Quick launch scripts for UAV system

case "$1" in
  gui)
    uv run launch_with_gui.py
    ;;
  dash)
    uv run run_dashboard.py
    ;;
  launch)
    uv run launch.py
    ;;
  gcs)
    uv run python -m gcs.main
    ;;
  uav)
    uv run python -m uav.client "${@:2}"
    ;;
  *)
    echo "Usage: ./scripts.sh {gui|dash|launch|gcs|uav <id> <x> <y> <z>}"
    echo ""
    echo "Examples:"
    echo "  ./scripts.sh gui          # Launch with GUI"
    echo "  ./scripts.sh dash         # Dashboard only"
    echo "  ./scripts.sh gcs          # GCS only"
    echo "  ./scripts.sh uav 1 0 0 10 # UAV client"
    exit 1
    ;;
esac
