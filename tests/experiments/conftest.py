"""
Pytest fixtures for experiment tests

Imports all fixtures from experiment_fixtures.py and makes them available
to all tests in the experiments directory.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from gcs.constraint_validator import ConstraintValidator
from gcs.ooda_engine import OODAEngine


@pytest.fixture
def gcs_config():
    """Standard GCS configuration for experiments"""
    return {
        "ooda_engine": {
            "telemetry_rate_hz": 2.0,
            "timeout_threshold_sec": 1.5,
            "phase_timeouts": {
                "observe": 1.5,
                "orient": 1.5,
                "decide": 1.5,
                "act": 1.0,
            },
        },
        "constraints": {
            "battery_safety_reserve_percent": 20.0,
            "anomaly_thresholds": {
                "battery_discharge_rate": 5.0,
                "position_discontinuity": 100.0,
                "altitude_deviation": 50.0,
            },
        },
        "collision_avoidance": {
            "safety_buffer_meters": 15.0,
            "temporal_buffer_seconds": 10.0,
        },
        "mission_context": {"mission_type": "surveillance"},
    }


@pytest.fixture
def constraint_validator(gcs_config):
    """Create constraint validator for experiments"""
    return ConstraintValidator(gcs_config)


@pytest.fixture
def ooda_engine(gcs_config):
    """Create OODA engine for experiments"""
    return OODAEngine(gcs_config)


# Register custom markers
def pytest_configure(config):
    """Configure pytest with custom markers for experiments"""
    config.addinivalue_line(
        "markers", "experiment: mark test as an experiment validation test"
    )
    config.addinivalue_line(
        "markers",
        "statistical: mark test as requiring multiple runs for statistical validation",
    )
