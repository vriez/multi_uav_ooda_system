"""
Configuration constants for Realistic Mission Completion Assistance

Author: Vítor EULÁLIO REIS

This module contains all configuration constants, magic numbers, and
scenario definitions to improve maintainability and reduce code duplication.
"""

from typing import Dict, Any, List, Optional

# =============================================================================
# SIMULATION TIMING CONSTANTS
# =============================================================================
LOOP_REAL_INTERVAL = 0.05  # Fixed real-time interval for Python loop (20 Hz)
TELEMETRY_INTERVAL = (
    1.0  # Client update rate (1 Hz) - reduced to prevent payload overflow
)
OODA_LOOP_INTERVAL = 1.0  # OODA cycle interval in seconds - increased frequency for better responsiveness

# =============================================================================
# UAV PERFORMANCE CONSTANTS
# =============================================================================
BASE_CRUISE_SPEED = 8.0  # UAV patrol speed (m/s)
BASE_RETURN_SPEED = 10.0  # UAV return speed (m/s)
BASE_BATTERY_DRAIN = 0.3  # Battery drain per simulated second (30% per minute)

# Delivery mission speeds
DELIVERY_CRUISE_SPEED = 12.0  # Higher speed for deliveries (m/s)
DELIVERY_RETURN_SPEED = 14.0  # Higher return speed for deliveries (m/s)

# =============================================================================
# THRESHOLD CONSTANTS
# =============================================================================
WAYPOINT_ARRIVAL_THRESHOLD = 2.0  # Distance to consider waypoint reached (m)
HOME_ARRIVAL_THRESHOLD = 2.0  # Distance to consider arrived at home (m)
HOME_PROXIMITY_THRESHOLD = 10.0  # Distance considered "near home" for failsafe (m)
DELIVERY_ARRIVAL_THRESHOLD = (
    2.0  # Distance to consider package pickup/delivery complete (m)
)

# Battery thresholds
BATTERY_LOW_THRESHOLD = 20.0  # Battery level to trigger return (%)
BATTERY_CRITICAL_THRESHOLD = 10.0  # Critical battery level (%)
BATTERY_FULL_LEVEL = 100.0  # Full battery level (%)
BATTERY_CHARGE_RATE = 20.0  # Battery charge rate per second (%)

# =============================================================================
# SEARCH AND RESCUE CONSTANTS
# =============================================================================
SAR_VISIBILITY_RADIUS = 25.0  # Asset initial detection radius (m)
SAR_DETECTION_RADIUS = 2.0  # Final pinpoint accuracy radius (m)
SAR_SEARCH_REDUCTION_RATE = 5.0  # Search radius reduction rate (m/s)
SAR_CONSENSUS_REQUIRED = 2  # UAVs required to confirm asset detection
SAR_IDENTIFICATION_CIRCLES = 3  # Circles needed to identify asset
SAR_GUARDIAN_MONITORING_CIRCLES = 5  # Guardian monitoring circles before release

# =============================================================================
# GRID AND ZONE CONSTANTS
# =============================================================================
GRID_SIZE = 100.0  # Grid cell size (m)
DEFAULT_NUM_ZONES = 9  # Default number of surveillance zones
ZONE_COVERAGE_THRESHOLD = 80.0  # Coverage % threshold for zone completion

# =============================================================================
# DELIVERY MISSION CONSTANTS
# =============================================================================
DEFAULT_NUM_PACKAGES = 12  # Default number of delivery packages
DELIVERY_TIME_WINDOW = 600.0  # Delivery time window in seconds
DELIVERY_PRIORITY_HIGH = 2.0  # High priority multiplier
DELIVERY_PRIORITY_NORMAL = 1.0  # Normal priority multiplier

# =============================================================================
# PATROL PATTERN CONSTANTS
# =============================================================================
PATROL_PATTERNS = [
    "perimeter",
    "lawnmower",
    "spiral",
    "creeping",
    "random",
    "figure8",
    "sector",
]

PATTERN_MODES = [
    "per_zone",  # Apply pattern to each zone independently
    "grouped",  # Apply pattern across combined area
]

DEFAULT_PATROL_PATTERN = "lawnmower"
DEFAULT_PATTERN_MODE = "per_zone"

# =============================================================================
# SCENARIO DEFINITIONS
# =============================================================================
SCENARIOS: Dict[str, Dict[str, Any]] = {
    "surveillance": {
        "uavs": 5,
        "zones": 9,
        "priority_zones": [],
        "mission_type": "coverage",
        "time_limit": None,
        "description": "5 UAVs, 9 zones - Continuous patrol",
    },
    "search_rescue": {
        "uavs": 5,
        "zones": 9,
        "priority_zones": [1, 2, 3, 4, 5, 6],  # Top and middle rows
        "mission_type": "detection",
        "time_limit": 600,  # 10 minutes
        "num_assets": 3,
        "consensus_required": SAR_CONSENSUS_REQUIRED,
        "visibility_radius": SAR_VISIBILITY_RADIUS,
        "detection_radius": SAR_DETECTION_RADIUS,
        "search_reduction_rate": SAR_SEARCH_REDUCTION_RATE,
        "identification_circles": SAR_IDENTIFICATION_CIRCLES,
        "guardian_circles": SAR_GUARDIAN_MONITORING_CIRCLES,
        "description": "5 UAVs, 9 zones - Time-critical search with asset rescue",
    },
    "delivery": {
        "uavs": 6,
        "num_packages": DEFAULT_NUM_PACKAGES,
        "mission_type": "delivery",
        "time_limit": None,
        "description": "6 UAVs, 12 deliveries - Package logistics",
    },
}

# =============================================================================
# UAV STATE DEFINITIONS
# =============================================================================
UAV_STATE_IDLE = "idle"
UAV_STATE_DEPLOYING = "deploying"
UAV_STATE_PATROLLING = "patrolling"
UAV_STATE_RETURNING = "returning"
UAV_STATE_CHARGING = "charging"
UAV_STATE_RECOVERED = "recovered"
UAV_STATE_CRASHED = "crashed"
UAV_STATE_DELIVERING = "delivering"
UAV_STATE_SEARCHING = "searching"  # SAR-specific state
UAV_STATE_AWAITING_PERMISSION = (
    "awaiting_permission"  # Delivery safety - waiting at grid boundary
)

VALID_UAV_STATES = [
    UAV_STATE_IDLE,
    UAV_STATE_DEPLOYING,
    UAV_STATE_PATROLLING,
    UAV_STATE_RETURNING,
    UAV_STATE_CHARGING,
    UAV_STATE_RECOVERED,
    UAV_STATE_CRASHED,
    UAV_STATE_DELIVERING,
    UAV_STATE_SEARCHING,
    UAV_STATE_AWAITING_PERMISSION,
]

# =============================================================================
# ASSET STATE DEFINITIONS (SAR)
# =============================================================================
ASSET_STATE_UNIDENTIFIED = "unidentified"
ASSET_STATE_IDENTIFIED = "identified"
ASSET_STATE_RESCUED = "rescued"

# =============================================================================
# FLASK/SOCKETIO CONFIGURATION
# =============================================================================
FLASK_SECRET_KEY = "uav-system-secret"
SOCKETIO_PING_TIMEOUT = 60
SOCKETIO_PING_INTERVAL = 25
SOCKETIO_CORS_ORIGINS = "*"

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# =============================================================================
# DEFAULT VALUES
# =============================================================================
DEFAULT_HOME_BASE = [0, 0, 10]  # [x, y, altitude] in meters
DEFAULT_SIMULATION_SPEED = 1.0
DEFAULT_SCENARIO = "surveillance"

# =============================================================================
# WORKLOAD BALANCER CONSTANTS
# =============================================================================
REBALANCE_INTERVAL = 30.0  # Seconds between workload rebalancing
