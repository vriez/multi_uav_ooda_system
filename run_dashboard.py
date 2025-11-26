#!/usr/bin/env python3
"""
Realistic Mission Completion Assistance - Dashboard Launcher

Author: Vítor EULÁLIO REIS
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from visualization.web_dashboard import start_dashboard

if __name__ == "__main__":
    print("Realistic Mission Completion Assistance")
    print("Author: Vítor EULÁLIO REIS")
    print("=" * 50)
    start_dashboard(port=8085)
