"""
Experiment Fixtures - Shared test infrastructure for baseline comparison experiments

Provides:
- Mock mission database with configurable tasks
- Mock fleet state with failure injection
- Constraint validator configuration
- OODA engine setup for experiments
"""
import pytest
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from gcs.ooda_engine import OODAEngine, FleetState, OODAPhase, RecoveryStrategy
from gcs.constraint_validator import ConstraintValidator
from gcs.objective_function import MissionContext, MissionType


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

    def add_task(self, position: np.ndarray, priority: float,
                 deadline: Optional[float] = None,
                 payload_kg: Optional[float] = None,
                 zone_id: Optional[int] = None,
                 task_type: str = "patrol",
                 duration_sec: float = 60.0) -> MockTask:
        """Add a task to the database"""
        task = MockTask(
            id=self._next_task_id,
            position=position,
            priority=priority,
            deadline=deadline,
            payload_kg=payload_kg,
            zone_id=zone_id,
            task_type=task_type,
            duration_sec=duration_sec
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
        'ooda_engine': {
            'telemetry_rate_hz': 2.0,
            'timeout_threshold_sec': 1.5,
            'phase_timeouts': {
                'observe': 1.5,
                'orient': 1.5,
                'decide': 1.5,
                'act': 1.0
            }
        },
        'constraints': {
            'battery_safety_reserve_percent': 20.0,
            'anomaly_thresholds': {
                'battery_discharge_rate': 5.0,
                'position_discontinuity': 100.0,
                'altitude_deviation': 50.0
            }
        },
        'collision_avoidance': {
            'safety_buffer_meters': 15.0,
            'temporal_buffer_seconds': 10.0
        },
        'mission_context': {
            'mission_type': 'surveillance'
        }
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
        num_tasks=8,  # 8 patrol zones
        failure=FailureScenario(
            name="mid_mission_battery",
            failed_uav_id=3,
            failure_time_percent=50.0,
            failure_type="battery",
            description="UAV-3 battery anomaly at t=45min, Zone C"
        ),
        expected_results={
            'no_adaptation_coverage': 83.3,
            'greedy_coverage': 95.0,
            'manual_coverage': 95.0,
            'ooda_coverage': 91.7,
            'ooda_time_sec': 5.5
        }
    )


@pytest.fixture
def surveillance_fleet_state():
    """Fleet state for surveillance scenario before failure"""
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[1, 2, 4, 5],  # UAV-3 has failed
        failed_uavs=[3],
        uav_positions={
            1: np.array([100.0, 100.0, 50.0]),   # Zone A
            2: np.array([300.0, 100.0, 50.0]),   # Zone B
            3: np.array([500.0, 100.0, 50.0]),   # Zone C (failed)
            4: np.array([100.0, 300.0, 50.0]),   # Zone D
            5: np.array([300.0, 300.0, 50.0]),   # Zone E
        },
        uav_battery={
            1: 75.0,
            2: 45.0,  # 15% spare
            3: 8.0,   # Failed - below threshold
            4: 40.0,  # 12% spare
            5: 80.0,
        },
        uav_payloads={},  # No payload for surveillance
        lost_tasks=[5, 6]  # Zone C tasks
    )


@pytest.fixture
def surveillance_mission_db():
    """Mission database for surveillance scenario"""
    db = MockMissionDatabase()

    # 8 patrol zones arranged in 2x4 grid (200m spacing)
    zones = [
        (100, 100, 90, "Zone A - High Priority"),
        (300, 100, 90, "Zone B - High Priority"),
        (500, 100, 60, "Zone C - Medium Priority"),  # Failed UAV zone
        (700, 100, 60, "Zone D - Medium Priority"),
        (100, 300, 40, "Zone E - Standard"),
        (300, 300, 40, "Zone F - Standard"),
        (500, 300, 40, "Zone G - Standard"),
        (700, 300, 40, "Zone H - Standard"),
    ]

    for i, (x, y, priority, desc) in enumerate(zones, 1):
        task = db.add_task(
            position=np.array([x, y, 50.0]),
            priority=priority,
            zone_id=i,
            task_type="patrol"
        )

    # Assign tasks to UAVs
    db.assign_task(1, 1)  # Zone A -> UAV 1
    db.assign_task(2, 2)  # Zone B -> UAV 2
    db.assign_task(3, 3)  # Zone C -> UAV 3 (will fail)
    db.assign_task(4, 3)  # Zone C extra -> UAV 3 (will fail)
    db.assign_task(5, 4)  # Zone D -> UAV 4
    db.assign_task(6, 5)  # Zone E -> UAV 5
    db.assign_task(7, 5)  # Zone F -> UAV 5
    db.assign_task(8, 4)  # Zone G -> UAV 4

    return db


# =============================================================================
# SAR Scenario (R5)
# =============================================================================

@pytest.fixture
def sar_scenario():
    """R5: Search & Rescue baseline comparison scenario"""
    return ExperimentScenario(
        name="R5_SAR_Baseline",
        mission_type=MissionType.SEARCH_RESCUE,
        num_uavs=4,
        num_tasks=6,  # 6 search zones
        failure=FailureScenario(
            name="gps_loss",
            failed_uav_id=2,
            failure_time_percent=13.3,  # 8 min into 60 min mission
            failure_type="gps",
            description="UAV-2 GPS signal loss at t=8min"
        ),
        expected_results={
            'no_adaptation_coverage': 70.0,
            'greedy_coverage': 90.0,
            'manual_coverage': 100.0,  # But violates golden hour!
            'ooda_coverage': 100.0,    # High-priority coverage
            'ooda_time_sec': 6.0,
            'golden_hour_sec': 3600.0
        }
    )


@pytest.fixture
def sar_fleet_state():
    """Fleet state for SAR scenario after UAV-2 failure"""
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[1, 3, 4],  # UAV-2 has failed
        failed_uavs=[2],
        uav_positions={
            1: np.array([200.0, 200.0, 50.0]),   # Zone 1 - LKP
            2: np.array([600.0, 400.0, 50.0]),   # Zone 2 - Water (failed)
            3: np.array([400.0, 600.0, 50.0]),   # Zone 4 - Trails
            4: np.array([800.0, 800.0, 50.0]),   # Zone 6 - Dense forest
        },
        uav_battery={
            1: 75.0,  # 20% spare
            2: 50.0,  # Failed - GPS loss
            3: 80.0,  # 35% spare
            4: 78.0,  # 30% spare
        },
        uav_payloads={},
        lost_tasks=[3, 4]  # Water source + shelter tasks
    )


@pytest.fixture
def sar_mission_db():
    """Mission database for SAR scenario"""
    db = MockMissionDatabase()
    current_time = time.time()
    golden_hour_deadline = current_time + 3600  # 1 hour

    # Search zones with priorities
    zones = [
        (200, 200, 90, "Zone 1 - LKP radius"),
        (400, 200, 80, "Zone 2 - Water sources"),
        (600, 400, 80, "Zone 3 - Shelters"),      # Lost task
        (200, 600, 75, "Zone 3b - More shelters"), # Lost task
        (400, 600, 60, "Zone 4 - Trails"),
        (800, 800, 30, "Zone 6 - Dense forest"),
    ]

    for i, (x, y, priority, desc) in enumerate(zones, 1):
        task = db.add_task(
            position=np.array([x, y, 50.0]),
            priority=priority,
            zone_id=i,
            task_type="search",
            deadline=golden_hour_deadline,
            duration_sec=300.0  # 5 min per zone
        )

    # Assign tasks
    db.assign_task(1, 1)  # LKP -> UAV 1
    db.assign_task(2, 1)  # Water -> UAV 1
    db.assign_task(3, 2)  # Shelters -> UAV 2 (will fail)
    db.assign_task(4, 2)  # More shelters -> UAV 2 (will fail)
    db.assign_task(5, 3)  # Trails -> UAV 3
    db.assign_task(6, 4)  # Dense -> UAV 4

    return db


# =============================================================================
# Delivery Scenario (D6)
# =============================================================================

@pytest.fixture
def delivery_scenario():
    """D6: Delivery baseline comparison scenario"""
    return ExperimentScenario(
        name="D6_Delivery_Baseline",
        mission_type=MissionType.DELIVERY,
        num_uavs=3,
        num_tasks=5,  # 5 packages
        failure=FailureScenario(
            name="battery_anomaly",
            failed_uav_id=1,
            failure_time_percent=25.0,  # 15 min into 60 min mission
            failure_type="battery",
            description="UAV-1 (heavy lifter) battery anomaly at t=15min"
        ),
        expected_results={
            'no_adaptation_coverage': 60.0,  # 3/5 packages
            'greedy_coverage': 100.0,        # But UNSAFE!
            'manual_coverage': 100.0,
            'ooda_coverage': 80.0,           # 4/5, escalates for package B
            'ooda_time_sec': 5.5
        }
    )


@pytest.fixture
def delivery_fleet_state():
    """Fleet state for delivery scenario after UAV-1 partial failure"""
    return FleetState(
        timestamp=time.time(),
        operational_uavs=[2, 3],  # UAV-1 can only complete package A
        failed_uavs=[1],         # Partially failed - can finish current task
        uav_positions={
            1: np.array([600.0, 1000.0, 50.0]),  # Near Clinic 1
            2: np.array([1800.0, 1400.0, 50.0]), # En route to Clinic 3
            3: np.array([1000.0, 500.0, 50.0]),  # En route to Clinic 5
        },
        uav_battery={
            1: 40.0,  # Low - anomaly detected
            2: 70.0,
            3: 75.0,
        },
        uav_payloads={
            1: 0.5,   # Only 0.5kg spare (was carrying 4.5kg)
            2: 0.3,   # 2.2kg loaded, 0.3kg spare
            3: 0.7,   # 1.8kg loaded, 0.7kg spare
        },
        lost_tasks=[2]  # Package B (2.0kg) cannot be delivered by UAV-1
    )


@pytest.fixture
def delivery_mission_db():
    """Mission database for delivery scenario"""
    db = MockMissionDatabase()
    current_time = time.time()

    # Packages with different priorities and weights
    packages = [
        # (x, y, priority, payload_kg, deadline_min, description)
        (800, 1200, 100, 2.5, 30, "Package A - Insulin (CRITICAL)"),
        (1500, 800, 70, 2.0, 45, "Package B - Antibiotics (HIGH)"),   # Lost task
        (2200, 1500, 40, 1.2, 60, "Package C - Bandages"),
        (2800, 600, 40, 1.0, 60, "Package D - Gauze"),
        (1200, 300, 20, 1.8, 90, "Package E - Vitamins"),
    ]

    for i, (x, y, priority, payload, deadline_min, desc) in enumerate(packages, 1):
        task = db.add_task(
            position=np.array([x, y, 0.0]),  # Ground level delivery
            priority=priority,
            payload_kg=payload,
            deadline=current_time + deadline_min * 60,
            task_type="delivery",
            duration_sec=120.0  # 2 min per delivery
        )

    # Assign packages
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
    results: Dict[str, 'ReallocationResult'] = field(default_factory=dict)
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
