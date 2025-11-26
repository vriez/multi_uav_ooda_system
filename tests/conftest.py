"""
Pytest fixtures and configuration for UAV system tests

This file contains shared fixtures used across all test modules.
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from visualization.config import (
    BASE_BATTERY_DRAIN,
    BASE_CRUISE_SPEED,
    BASE_RETURN_SPEED,
    BATTERY_LOW_THRESHOLD,
    HOME_ARRIVAL_THRESHOLD,
    DELIVERY_ARRIVAL_THRESHOLD,
    SAR_VISIBILITY_RADIUS,
    SAR_DETECTION_RADIUS,
    LOOP_REAL_INTERVAL,
)


# =============================================================================
# UAV Fixtures
# =============================================================================


@pytest.fixture
def uav_default():
    """Create a default UAV with typical starting values"""
    return {
        "id": "uav_1",
        "position": np.array([0.0, 0.0, 10.0]),
        "battery": 100.0,
        "state": "idle",
        "operational": True,
        "returning": False,
        "assigned_zones": [],
        "assigned_task": None,
        "awaiting_permission": False,
        "permission_granted_for_target": None,
        "boundary_stop_position": None,
        "out_of_grid_target": None,
        "battery_warning": False,
        "packages_delivered": 0,
    }


@pytest.fixture
def uav_at_boundary():
    """Create a UAV at grid boundary awaiting permission"""
    return {
        "id": "uav_2",
        "position": np.array([60.0, 0.0, 10.0]),
        "battery": 50.0,
        "state": "awaiting_permission",
        "operational": True,
        "returning": False,
        "awaiting_permission": True,
        "boundary_stop_position": np.array([60.0, 0.0, 10.0]),
        "out_of_grid_target": np.array([80.0, 0.0, 10.0]),
    }


@pytest.fixture
def uav_returning():
    """Create a UAV returning to base with low battery"""
    return {
        "id": "uav_3",
        "position": np.array([30.0, 30.0, 10.0]),
        "battery": 14.0,
        "state": "returning",
        "operational": False,
        "returning": True,
        "assigned_zones": [],
        "battery_warning": True,
    }


@pytest.fixture
def uav_crashed():
    """Create a crashed UAV with depleted battery"""
    return {
        "id": "uav_4",
        "position": np.array([45.0, 45.0, 0.0]),
        "battery": 0.0,
        "state": "crashed",
        "operational": False,
        "returning": False,
    }


@pytest.fixture
def uav_fleet():
    """Create a fleet of 5 UAVs with different states"""
    return {
        "uav_1": {
            "id": "uav_1",
            "position": np.array([20.0, 20.0, 10.0]),
            "battery": 100.0,
            "state": "patrolling",
            "operational": True,
            "assigned_zones": [1, 2],
        },
        "uav_2": {
            "id": "uav_2",
            "position": np.array([40.0, 40.0, 10.0]),
            "battery": 75.0,
            "state": "patrolling",
            "operational": True,
            "assigned_zones": [3, 6],
        },
        "uav_3": {
            "id": "uav_3",
            "position": np.array([0.0, 0.0, 10.0]),
            "battery": 20.0,
            "state": "returning",
            "operational": False,
            "assigned_zones": [],
        },
        "uav_4": {
            "id": "uav_4",
            "position": np.array([-20.0, -20.0, 10.0]),
            "battery": 50.0,
            "state": "patrolling",
            "operational": True,
            "assigned_zones": [7, 8],
        },
        "uav_5": {
            "id": "uav_5",
            "position": np.array([10.0, -10.0, 10.0]),
            "battery": 90.0,
            "state": "patrolling",
            "operational": True,
            "assigned_zones": [9],
        },
    }


# =============================================================================
# Mission Fixtures
# =============================================================================


@pytest.fixture
def surveillance_mission():
    """Create surveillance mission configuration"""
    return {
        "type": "surveillance",
        "num_zones": 9,
        "num_uavs": 5,
        "auto_stop": False,
        "zone_assignments": {
            "uav_1": [1, 2],
            "uav_2": [3, 6],
            "uav_3": [4, 5],
            "uav_4": [7, 8],
            "uav_5": [9],
        },
    }


@pytest.fixture
def sar_mission():
    """Create SAR mission configuration"""
    return {
        "type": "search_rescue",
        "num_zones": 9,
        "num_uavs": 5,
        "num_assets": 3,
        "auto_reassignment": False,
        "zone_assignments": {
            "uav_1": [1, 2],
            "uav_2": [3, 6],
            "uav_3": [4, 5],
            "uav_4": [7, 8],
            "uav_5": [9],
        },
    }


@pytest.fixture
def delivery_mission():
    """Create delivery mission configuration"""
    return {"type": "delivery", "num_packages": 12, "num_uavs": 5, "auto_stop": True}


@pytest.fixture
def sar_asset():
    """Create a SAR asset/target"""
    return {
        "id": "asset_1",
        "position": [50.0, 50.0, 0.0],
        "last_known_position": [50.0, 50.0, 0.0],
        "status": "unidentified",
        "detecting_uavs": [],
        "guardian": None,
    }


@pytest.fixture
def delivery_package():
    """Create a delivery package/task"""
    return {
        "id": "pkg_1",
        "pickup": [30.0, 30.0, 0.0],
        "dropoff": [-30.0, -30.0, 0.0],
        "status": "pending",
        "priority": 1.0,
        "assigned_uav": None,
        "deadline": 600.0,
    }


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def home_base():
    """Home base position"""
    return np.array([0.0, 0.0, 0.0])


@pytest.fixture
def grid_boundaries():
    """Grid boundary values"""
    return {"min": -60.0, "max": 60.0}


@pytest.fixture
def simulation_params():
    """Simulation parameters"""
    return {
        "dt": LOOP_REAL_INTERVAL,
        "simulation_speed": 1.0,
        "battery_drain_rate": BASE_BATTERY_DRAIN,
        "cruise_speed": BASE_CRUISE_SPEED,
        "return_speed": BASE_RETURN_SPEED,
    }


# =============================================================================
# Position/Distance Fixtures
# =============================================================================


@pytest.fixture
def position_inside_grid():
    """Position inside grid boundaries"""
    return np.array([30.0, 30.0, 10.0])


@pytest.fixture
def position_outside_grid():
    """Position outside grid boundaries"""
    return np.array([80.0, 80.0, 10.0])


@pytest.fixture
def position_on_boundary():
    """Position exactly on grid boundary"""
    return np.array([60.0, 0.0, 10.0])


# =============================================================================
# Helper Functions
# =============================================================================


@pytest.fixture
def calculate_distance():
    """Fixture that returns a distance calculation function"""

    def _calculate(pos1, pos2):
        return np.linalg.norm(np.array(pos1[:2]) - np.array(pos2[:2]))

    return _calculate


@pytest.fixture
def is_within_threshold():
    """Fixture that returns a threshold checking function"""

    def _check(distance, threshold):
        return distance <= threshold

    return _check


# =============================================================================
# Pytest Hooks
# =============================================================================


def pytest_configure(config):
    """Configure pytest with custom settings"""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "regression: mark test as a regression test")


def pytest_collection_modifyitems(config, items):
    """Modify test items during collection"""
    for item in items:
        # Auto-mark tests based on directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "regression" in str(item.fspath):
            item.add_marker(pytest.mark.regression)
