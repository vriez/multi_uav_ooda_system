"""
Experiment Fixtures - Shared test infrastructure for baseline comparison experiments

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025

Provides:
- Mock mission database with configurable tasks
- Mock fleet state with failure injection
- Constraint validator configuration
- OODA engine setup for experiments
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest  # noqa: E402
import time  # noqa: E402
import numpy as np  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import Dict, List, Optional  # noqa: E402
from enum import Enum  # noqa: E402

from gcs.ooda_engine import OODAEngine, FleetState  # noqa: E402
from gcs.constraint_validator import ConstraintValidator  # noqa: E402
from gcs.objective_function import MissionType  # noqa: E402


# =============================================================================
# Task and Mission Data Structures
# =============================================================================


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MockTask:
    """Mock task for testing"""

    id: int
    position: np.ndarray
    priority: float  # 0-100
    status: TaskStatus = TaskStatus.PENDING
    assigned_uav: Optional[int] = None
    deadline: Optional[float] = None
    duration_sec: float = 60.0
    payload_kg: Optional[float] = None
    zone_id: Optional[int] = None
    task_type: str = "patrol"


class MockMissionDatabase:
    """Mock mission database for experiments"""

    def __init__(self):
        self.tasks: Dict[int, MockTask] = {}
        self.uav_assignments: Dict[int, List[int]] = {}
        self._next_task_id = 1

    def add_task(
        self,
        position: np.ndarray,
        priority: float,
        deadline: Optional[float] = None,
        payload_kg: Optional[float] = None,
        zone_id: Optional[int] = None,
        task_type: str = "patrol",
        duration_sec: float = 60.0,
    ) -> MockTask:
        """Add a task to the database"""
        task = MockTask(
            id=self._next_task_id,
            position=position,
            priority=priority,
            deadline=deadline,
            payload_kg=payload_kg,
            zone_id=zone_id,
            task_type=task_type,
            duration_sec=duration_sec,
        )
        self.tasks[task.id] = task
        self._next_task_id += 1
        return task

    def get_task(self, task_id: int) -> Optional[MockTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def get_uav_tasks(self, uav_id: int) -> List[int]:
        """Get task IDs assigned to UAV"""
        return self.uav_assignments.get(uav_id, [])

    def assign_task(self, task_id: int, uav_id: int):
        """Assign task to UAV"""
        task = self.tasks.get(task_id)
        if task:
            task.assigned_uav = uav_id
            task.status = TaskStatus.ASSIGNED
            if uav_id not in self.uav_assignments:
                self.uav_assignments[uav_id] = []
            self.uav_assignments[uav_id].append(task_id)

    def get_affected_zones(self, task_ids: List[int]) -> List[int]:
        """Get zones affected by lost tasks"""
        zones = set()
        for task_id in task_ids:
            task = self.tasks.get(task_id)
            if task and task.zone_id is not None:
                zones.add(task.zone_id)
        return list(zones)

    def commit_reallocation(self, reallocation_plan: Dict[int, List[int]]):
        """Apply reallocation plan to database"""
        for uav_id, task_ids in reallocation_plan.items():
            for task_id in task_ids:
                self.assign_task(task_id, uav_id)


# =============================================================================
# Scenario Configurations
# =============================================================================


@dataclass
class FailureScenario:
    """Configuration for a failure scenario"""

    name: str
    failed_uav_id: int
    failure_time_percent: float  # 0-100, percent of mission progress
    failure_type: str  # "battery", "communication", "gps"
    description: str


@dataclass
class ExperimentScenario:
    """Complete experiment scenario configuration"""

    name: str
    mission_type: MissionType
    num_uavs: int
    num_tasks: int
    failure: FailureScenario
    expected_results: Dict[str, float]


# =============================================================================
# Pytest Fixtures
# =============================================================================


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


# =============================================================================
# Surveillance Scenario (S5)
# =============================================================================


@pytest.fixture
def surveillance_scenario():
    """S5: Surveillance baseline comparison scenario"""
    return ExperimentScenario(
        name="S5_Surveillance_Baseline",
        mission_type=MissionType.SURVEILLANCE,
        num_uavs=5,
        num_tasks=9,  # 9 patrol zones (3x3 grid, 40m x 40m each)
        failure=FailureScenario(
            name="mid_mission_battery",
            failed_uav_id=3,
            failure_time_percent=50.0,
            failure_type="battery",
            description="UAV-3 battery anomaly at t=45min, Zone 5",
        ),
        expected_results={
            "no_adaptation_coverage": 88.9,  # 8/9 zones (1 lost)
            "greedy_coverage": 100.0,
            "ooda_coverage": 100.0,
            "ooda_time_sec": 5.5,
        },
    )


@pytest.fixture
def surveillance_fleet_state():
    """Fleet state for surveillance scenario before failure

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes:
    Zone 1: (20,100)   Zone 2: (60,100)   Zone 3: (100,100)  [top row, P=0.9]
    Zone 4: (20,60)    Zone 5: (60,60)    Zone 6: (100,60)   [middle row, P=0.6]
    Zone 7: (20,20)    Zone 8: (60,20)    Zone 9: (100,20)   [bottom row, P=0.4]
    """
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[1, 2, 4, 5],  # UAV-3 has failed
        failed_uavs=[3],
        uav_positions={
            1: np.array([20.0, 100.0, 15.0]),  # Zone 1 (top-left)
            2: np.array([60.0, 100.0, 15.0]),  # Zone 2 (top-center)
            3: np.array([60.0, 60.0, 15.0]),  # Zone 5 (center, failed)
            4: np.array([100.0, 100.0, 15.0]),  # Zone 3 (top-right)
            5: np.array([20.0, 60.0, 15.0]),  # Zone 4 (middle-left)
        },
        uav_battery={
            1: 75.0,
            2: 45.0,  # 15% spare
            3: 8.0,  # Failed - below threshold
            4: 40.0,  # 12% spare
            5: 80.0,
        },
        uav_payloads={},  # No payload for surveillance
        lost_tasks=[5],  # Zone 5 (center zone, failed UAV)
    )


@pytest.fixture
def surveillance_mission_db():
    """Mission database for surveillance scenario

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    Total operational area: 120m x 120m
    """
    db = MockMissionDatabase()

    # 9 patrol zones arranged in 3x3 grid (40m x 40m each)
    zones = [
        # Top row (P=0.9) - High Priority
        (20, 100, 90, "Zone 1 - High Priority"),
        (60, 100, 90, "Zone 2 - High Priority"),
        (100, 100, 90, "Zone 3 - High Priority"),
        # Middle row (P=0.6) - Medium Priority
        (20, 60, 60, "Zone 4 - Medium Priority"),
        (60, 60, 60, "Zone 5 - Medium Priority"),  # Failed UAV zone
        (100, 60, 60, "Zone 6 - Medium Priority"),
        # Bottom row (P=0.4) - Standard Priority
        (20, 20, 40, "Zone 7 - Standard"),
        (60, 20, 40, "Zone 8 - Standard"),
        (100, 20, 40, "Zone 9 - Standard"),
    ]

    for i, (x, y, priority, _desc) in enumerate(zones, 1):
        db.add_task(
            position=np.array([x, y, 15.0]),
            priority=priority,
            zone_id=i,
            task_type="patrol",
        )

    # Assign tasks to UAVs (5 UAVs, 9 zones)
    db.assign_task(1, 1)  # Zone 1 -> UAV 1
    db.assign_task(2, 1)  # Zone 2 -> UAV 1
    db.assign_task(3, 2)  # Zone 3 -> UAV 2
    db.assign_task(4, 2)  # Zone 4 -> UAV 2
    db.assign_task(5, 3)  # Zone 5 -> UAV 3 (will fail)
    db.assign_task(6, 4)  # Zone 6 -> UAV 4
    db.assign_task(7, 4)  # Zone 7 -> UAV 4
    db.assign_task(8, 5)  # Zone 8 -> UAV 5
    db.assign_task(9, 5)  # Zone 9 -> UAV 5

    return db


# =============================================================================
# SAR Scenario (R5)
# =============================================================================


@pytest.fixture
def sar_scenario():
    """R5: Search & Rescue baseline comparison scenario

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    UAV-2 GPS failure at t=8min loses Zones 3 and 4 (high priority).
    """
    return ExperimentScenario(
        name="R5_SAR_Baseline",
        mission_type=MissionType.SEARCH_RESCUE,
        num_uavs=4,
        num_tasks=9,  # 9 search zones (3x3 grid, 40m x 40m each)
        failure=FailureScenario(
            name="gps_loss",
            failed_uav_id=2,
            failure_time_percent=13.3,  # 8 min into 60 min mission
            failure_type="gps",
            description="UAV-2 GPS signal loss at t=8min, Zones 3-4",
        ),
        expected_results={
            "no_adaptation_coverage": 77.8,  # 7/9 zones (2 lost)
            "greedy_coverage": 100.0,
            "ooda_coverage": 100.0,  # High-priority coverage
            "ooda_time_sec": 6.0,
            "golden_hour_sec": 3600.0,
        },
    )


@pytest.fixture
def sar_fleet_state():
    """Fleet state for SAR scenario after UAV-2 failure

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes:
    Zone 1: (20,100)   Zone 2: (60,100)   Zone 3: (100,100)  [top row, P=0.9]
    Zone 4: (20,60)    Zone 5: (60,60)    Zone 6: (100,60)   [middle row, P=0.6]
    Zone 7: (20,20)    Zone 8: (60,20)    Zone 9: (100,20)   [bottom row, P=0.4]

    UAV-2 fails at Zone 3, losing Zones 3 and 4 (high priority).
    """
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[1, 3, 4],  # UAV-2 has failed
        failed_uavs=[2],
        uav_positions={
            1: np.array([20.0, 100.0, 15.0]),  # Zone 1 (top-left)
            2: np.array([100.0, 100.0, 15.0]),  # Zone 3 (top-right, GPS lost)
            3: np.array([60.0, 60.0, 15.0]),  # Zone 5 (center)
            4: np.array([100.0, 20.0, 15.0]),  # Zone 9 (bottom-right)
        },
        uav_battery={
            1: 75.0,  # 20% spare
            2: 50.0,  # Failed - GPS loss
            3: 80.0,  # 35% spare
            4: 78.0,  # 30% spare
        },
        uav_payloads={},
        lost_tasks=[3, 4],  # Zone 3 (top-right) + Zone 4 (middle-left)
    )


@pytest.fixture
def sar_mission_db():
    """Mission database for SAR scenario

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    Total operational area: 120m x 120m

    SAR Priority mapping:
    - Top row (Zones 1-3): LKP area, water sources (highest priority, P=0.9)
    - Middle row (Zones 4-6): Shelters, trails (medium priority, P=0.6)
    - Bottom row (Zones 7-9): Dense forest, steep terrain (low priority, P=0.4)
    """
    db = MockMissionDatabase()
    current_time = time.time()
    golden_hour_deadline = current_time + 3600  # 1 hour

    # 9 search zones in 3x3 grid (40m x 40m each)
    zones = [
        # Top row (P=0.9) - LKP area, water sources
        (20, 100, 90, "Zone 1 - LKP radius"),
        (60, 100, 85, "Zone 2 - Water sources"),
        (100, 100, 80, "Zone 3 - Shelters"),  # UAV-2 zone (lost)
        # Middle row (P=0.6) - More shelters, trails
        (20, 60, 75, "Zone 4 - More shelters"),  # UAV-2 zone (lost)
        (60, 60, 60, "Zone 5 - Trails"),
        (100, 60, 55, "Zone 6 - Clearings"),
        # Bottom row (P=0.4) - Dense forest, steep terrain
        (20, 20, 40, "Zone 7 - Dense forest"),
        (60, 20, 35, "Zone 8 - Steep terrain"),
        (100, 20, 30, "Zone 9 - Remote area"),
    ]

    for i, (x, y, priority, _desc) in enumerate(zones, 1):
        db.add_task(
            position=np.array([float(x), float(y), 15.0]),
            priority=priority,
            zone_id=i,
            task_type="search",
            deadline=golden_hour_deadline,
            duration_sec=300.0,  # 5 min per zone
        )

    # Assign tasks (4 UAVs, 9 zones)
    db.assign_task(1, 1)  # Zone 1 -> UAV 1
    db.assign_task(2, 1)  # Zone 2 -> UAV 1
    db.assign_task(3, 2)  # Zone 3 -> UAV 2 (will fail)
    db.assign_task(4, 2)  # Zone 4 -> UAV 2 (will fail)
    db.assign_task(5, 3)  # Zone 5 -> UAV 3
    db.assign_task(6, 3)  # Zone 6 -> UAV 3
    db.assign_task(7, 4)  # Zone 7 -> UAV 4
    db.assign_task(8, 4)  # Zone 8 -> UAV 4
    db.assign_task(9, 4)  # Zone 9 -> UAV 4

    return db


# =============================================================================
# Delivery Scenario (D6)
# =============================================================================


@pytest.fixture
def delivery_scenario():
    """D6: Delivery baseline comparison scenario

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    5 clinics distributed across grid zones:
    - Clinic 1: Zone 1 (20, 100) - Package A
    - Clinic 2: Zone 3 (100, 100) - Package B (lost)
    - Clinic 3: Zone 2 (60, 100) - Package C
    - Clinic 4: Zone 6 (100, 60) - Package D
    - Clinic 5: Zone 8 (60, 20) - Package E
    """
    return ExperimentScenario(
        name="D6_Delivery_Baseline",
        mission_type=MissionType.DELIVERY,
        num_uavs=3,
        num_tasks=5,  # 5 packages to 5 clinics within 9-zone grid
        failure=FailureScenario(
            name="battery_anomaly",
            failed_uav_id=1,
            failure_time_percent=25.0,  # 15 min into 60 min mission
            failure_type="battery",
            description="UAV-1 (heavy lifter) battery anomaly at t=15min, Package B",
        ),
        expected_results={
            "no_adaptation_coverage": 80.0,  # 4/5 packages
            "greedy_coverage": 100.0,  # But UNSAFE!
            "ooda_coverage": 80.0,  # 4/5, escalates for package B
            "ooda_time_sec": 5.5,
        },
    )


@pytest.fixture
def delivery_fleet_state():
    """Fleet state for delivery scenario after UAV-1 partial failure

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    UAV positions within 120m x 120m operational area.
    """
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[2, 3],  # UAV-1 can only complete package A
        failed_uavs=[1],  # Partially failed - can finish current task
        uav_positions={
            1: np.array([20.0, 100.0, 15.0]),  # Near Clinic 1 (Zone 1)
            2: np.array([60.0, 100.0, 15.0]),  # En route to Clinic 3 (Zone 2)
            3: np.array([60.0, 20.0, 15.0]),  # En route to Clinic 5 (Zone 8)
        },
        uav_battery={
            1: 40.0,  # Low - anomaly detected
            2: 70.0,
            3: 75.0,
        },
        uav_payloads={
            1: 0.5,  # Only 0.5kg spare (was carrying 4.5kg)
            2: 0.3,  # 2.2kg loaded, 0.3kg spare
            3: 0.7,  # 1.8kg loaded, 0.7kg spare
        },
        lost_tasks=[2],  # Package B (2.0kg) cannot be delivered by UAV-1
    )


@pytest.fixture
def delivery_mission_db():
    """Mission database for delivery scenario

    3x3 grid (40m x 40m zones), centers at [20, 60, 100] on both axes.
    Total operational area: 120m x 120m

    5 clinics distributed across grid zones:
    - Clinic 1: Zone 1 (20, 100) - Package A (insulin, critical)
    - Clinic 2: Zone 3 (100, 100) - Package B (antibiotics, high) - LOST
    - Clinic 3: Zone 2 (60, 100) - Package C (bandages)
    - Clinic 4: Zone 6 (100, 60) - Package D (gauze)
    - Clinic 5: Zone 8 (60, 20) - Package E (vitamins)
    """
    db = MockMissionDatabase()
    current_time = time.time()

    # 5 packages to 5 clinics within 9-zone grid (40m x 40m each)
    packages = [
        # (x, y, priority, payload_kg, deadline_min, description)
        (20, 100, 100, 2.5, 30, "Package A - Insulin (CRITICAL)"),  # Clinic 1, Zone 1
        (100, 100, 70, 2.0, 45, "Package B - Antibiotics (HIGH)"),  # Clinic 2, Zone 3 (lost)
        (60, 100, 40, 1.2, 60, "Package C - Bandages"),  # Clinic 3, Zone 2
        (100, 60, 40, 1.0, 60, "Package D - Gauze"),  # Clinic 4, Zone 6
        (60, 20, 20, 1.8, 90, "Package E - Vitamins"),  # Clinic 5, Zone 8
    ]

    for i, (x, y, priority, payload, deadline_min, _desc) in enumerate(packages, 1):
        db.add_task(
            position=np.array([float(x), float(y), 15.0]),  # Grid altitude
            priority=priority,
            payload_kg=payload,
            deadline=current_time + deadline_min * 60,
            task_type="delivery",
            duration_sec=120.0,  # 2 min per delivery
        )

    # Assign packages (3 UAVs, 5 packages)
    db.assign_task(1, 1)  # Package A -> UAV 1 (heavy lifter)
    db.assign_task(2, 1)  # Package B -> UAV 1 (will be lost)
    db.assign_task(3, 2)  # Package C -> UAV 2
    db.assign_task(4, 2)  # Package D -> UAV 2
    db.assign_task(5, 3)  # Package E -> UAV 3

    return db


# =============================================================================
# Experiment Results Collection
# =============================================================================


@dataclass
class ExperimentResults:
    """Collection of results from running all strategies"""

    scenario_name: str
    mission_type: MissionType
    results: Dict[str, "ReallocationResult"] = field(default_factory=dict)
    comparison_table: Optional[str] = None

    def add_result(self, strategy_name: str, result):
        """Add a strategy result"""
        self.results[strategy_name] = result

    def generate_comparison_table(self) -> str:
        """Generate markdown comparison table"""
        lines = [
            f"## {self.scenario_name} Results",
            "",
            "| Strategy | Coverage | Time | Safety | Violations |",
            "|----------|----------|------|--------|------------|",
        ]

        for name, result in self.results.items():
            safety = "Safe" if len(result.safety_violations) == 0 else "**UNSAFE**"
            lines.append(
                f"| {name} | {result.coverage_percentage:.1f}% | "
                f"{result.adaptation_time_sec:.1f}s | {safety} | "
                f"{result.constraint_violations} |"
            )

        self.comparison_table = "\n".join(lines)
        return self.comparison_table


@pytest.fixture
def experiment_results():
    """Factory fixture for creating experiment results collectors"""

    def _create(scenario_name: str, mission_type: MissionType):
        return ExperimentResults(scenario_name, mission_type)

    return _create
