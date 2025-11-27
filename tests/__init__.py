"""
UAV System Test Suite

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025

Test organization:
- tests/unit/: Unit tests for individual components
- tests/integration/: Integration tests for mission workflows
- tests/regression/: Regression tests for fixed bugs

Run tests:
    pytest                      # All tests
    pytest -m unit              # Unit tests only
    pytest -m integration       # Integration tests only
    pytest -m regression        # Regression tests only
    pytest tests/unit/          # Specific directory
    pytest -v                   # Verbose output
    pytest -k battery           # Tests matching 'battery'
"""
