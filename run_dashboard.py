#!/usr/bin/env python3
"""
Realistic Mission Completion Assistance - Dashboard Launcher

Author: Vítor Eulálio Reis <vitor.reis@proton.me>
Copyright (c) 2025
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from visualization.web_dashboard import start_dashboard  # noqa: E402

if __name__ == "__main__":
    print("Realistic Mission Completion Assistance")
    print("Author: Vítor Eulálio Reis <vitor.reis@proton.me>")
    print("=" * 50)
    start_dashboard(port=8085)
