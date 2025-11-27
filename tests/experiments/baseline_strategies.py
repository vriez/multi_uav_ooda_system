"""
Baseline Reallocation Strategies for Comparison Experiments

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025

This module implements the baseline strategies against which the OODA-based
system is compared:

1. NoAdaptation: Mission aborts on failure (0% reallocation)
2. GreedyNearest: Naive nearest-UAV assignment (ignores constraints)
3. OODAStrategy: The system under test (constraint-aware + fast)

Reference: TCC Chapter 6 - Experimental Results and Validation
"""

import time
import logging
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Reallocation strategy types"""

    NO_ADAPTATION = "no_adaptation"
    GREEDY_NEAREST = "greedy_nearest"
    OODA = "ooda"


@dataclass
class ReallocationResult:
    """Result of a reallocation strategy execution"""

    strategy: StrategyType
    allocation: Dict[int, List[int]]  # UAV ID -> Task IDs
    coverage_percentage: float
    adaptation_time_sec: float
    safety_violations: List[str]
    constraint_violations: int
    tasks_reallocated: int
    tasks_lost: int
    rationale: str
    metrics: Dict[str, float] = field(default_factory=dict)


class BaselineStrategy(ABC):
    """Abstract base class for reallocation strategies"""

    def __init__(self, strategy_type: StrategyType):
        self.strategy_type = strategy_type

    @abstractmethod
    def reallocate(
        self, fleet_state, lost_tasks: List, mission_db, constraint_validator
    ) -> ReallocationResult:
        """Execute the reallocation strategy"""
        pass


class NoAdaptationStrategy(BaselineStrategy):
    """
    No Adaptation Baseline

    Simply aborts the failed UAV's tasks - no reallocation attempted.
    This represents the worst-case scenario and establishes the lower bound.

    Expected results:
    - Coverage: Loss equal to failed UAV's task share
    - Time: N/A (instant, but no recovery)
    - Safety: Always safe (no actions taken)
    """

    def __init__(self):
        super().__init__(StrategyType.NO_ADAPTATION)

    def reallocate(
        self, fleet_state, lost_tasks: List, mission_db, constraint_validator
    ) -> ReallocationResult:
        """No reallocation - all lost tasks remain unallocated"""

        total_tasks = len(mission_db.tasks) if hasattr(mission_db, "tasks") else 1
        tasks_lost = len(lost_tasks)

        # Coverage is what remains after losing the tasks
        coverage = (
            ((total_tasks - tasks_lost) / total_tasks * 100) if total_tasks > 0 else 0
        )

        return ReallocationResult(
            strategy=self.strategy_type,
            allocation={},
            coverage_percentage=coverage,
            adaptation_time_sec=0.0,
            safety_violations=[],
            constraint_violations=0,
            tasks_reallocated=0,
            tasks_lost=tasks_lost,
            rationale="No adaptation: All lost tasks abandoned",
            metrics={"coverage_loss": 100 - coverage, "recovery_rate": 0.0},
        )


class GreedyNearestStrategy(BaselineStrategy):
    """
    Greedy Nearest-Neighbor Baseline

    Assigns each lost task to the nearest UAV WITHOUT checking constraints.
    This represents naive automation that ignores real-world limits.

    Expected results:
    - Coverage: ~95-100% (optimistic)
    - Time: <1 second
    - Safety: UNSAFE - may violate battery/payload constraints

    This baseline demonstrates why constraint-awareness matters.
    """

    def __init__(self):
        super().__init__(StrategyType.GREEDY_NEAREST)

    def reallocate(  # noqa: C901
        self, fleet_state, lost_tasks: List, mission_db, constraint_validator
    ) -> ReallocationResult:
        """Assign to nearest UAV ignoring constraints"""

        start_time = time.time()
        allocation: Dict[int, List[int]] = {}
        safety_violations = []
        constraint_violations = 0

        for task_ref in lost_tasks:
            task = mission_db.get_task(
                task_ref.id if hasattr(task_ref, "id") else task_ref
            )
            if task is None:
                continue

            # Find nearest UAV (ignoring constraints!)
            best_uav = None
            min_dist = float("inf")

            for uav_id in fleet_state.operational_uavs:
                uav_pos = fleet_state.uav_positions[uav_id]
                dist = np.linalg.norm(uav_pos[:2] - task.position[:2])
                if dist < min_dist:
                    min_dist = dist
                    best_uav = uav_id

            if best_uav is not None:
                if best_uav not in allocation:
                    allocation[best_uav] = []
                allocation[best_uav].append(task.id)

                # Check if this WOULD violate constraints (for reporting)
                if not constraint_validator.check_all_constraints(
                    best_uav, task.id, fleet_state, mission_db
                ):
                    constraint_violations += 1

                    # Identify specific violation
                    if not constraint_validator.check_grid_boundary_constraint(
                        best_uav, task.id, fleet_state, mission_db
                    ):
                        safety_violations.append(
                            f"UAV {best_uav}: Out-of-grid destination for task {task.id}"
                        )
                    if not constraint_validator.check_battery_constraint(
                        best_uav, task.id, fleet_state, mission_db
                    ):
                        safety_violations.append(
                            f"UAV {best_uav}: Battery constraint violated for task {task.id}"
                        )
                    if hasattr(task, "payload_kg") and task.payload_kg:
                        if not constraint_validator.check_payload_constraint(
                            best_uav, task.id, fleet_state, mission_db
                        ):
                            safety_violations.append(
                                f"UAV {best_uav}: Payload overload for task {task.id}"
                            )

        elapsed = time.time() - start_time

        tasks_reallocated = sum(len(tasks) for tasks in allocation.values())
        tasks_lost_count = len(lost_tasks)
        coverage = (
            (tasks_reallocated / tasks_lost_count * 100)
            if tasks_lost_count > 0
            else 100
        )

        return ReallocationResult(
            strategy=self.strategy_type,
            allocation=allocation,
            coverage_percentage=coverage,
            adaptation_time_sec=elapsed,
            safety_violations=safety_violations,
            constraint_violations=constraint_violations,
            tasks_reallocated=tasks_reallocated,
            tasks_lost=tasks_lost_count - tasks_reallocated,
            rationale=f"Greedy nearest: {tasks_reallocated} tasks assigned, "
            f"{constraint_violations} constraint violations",
            metrics={
                "constraint_violations": constraint_violations,
                "recovery_rate": coverage,
                "is_safe": len(safety_violations) == 0,
            },
        )


class OODAStrategy(BaselineStrategy):
    """
    OODA-Based Strategy (System Under Test)

    Wraps the actual OODA engine for comparison experiments.
    This is the system being validated.

    Expected results:
    - Coverage: 65-95% (constraint-aware)
    - Time: 4-6 seconds
    - Safety: Always safe (constraints enforced)
    """

    def __init__(self, ooda_engine):
        super().__init__(StrategyType.OODA)
        self.ooda_engine = ooda_engine

    def reallocate(
        self, fleet_state, lost_tasks: List, mission_db, constraint_validator
    ) -> ReallocationResult:
        """Execute OODA cycle for reallocation"""

        start_time = time.time()

        # Trigger OODA cycle
        decision = self.ooda_engine.trigger_ooda_cycle(
            fleet_state, mission_db, constraint_validator
        )

        elapsed = time.time() - start_time

        # Extract results
        tasks_reallocated = sum(
            len(tasks) for tasks in decision.reallocation_plan.values()
        )
        tasks_lost_count = len(lost_tasks)
        coverage = (
            (tasks_reallocated / tasks_lost_count * 100)
            if tasks_lost_count > 0
            else 100
        )

        return ReallocationResult(
            strategy=self.strategy_type,
            allocation=decision.reallocation_plan,
            coverage_percentage=coverage,
            adaptation_time_sec=elapsed,
            safety_violations=[],
            constraint_violations=0,
            tasks_reallocated=tasks_reallocated,
            tasks_lost=tasks_lost_count - tasks_reallocated,
            rationale=decision.rationale,
            metrics={
                "ooda_strategy": decision.strategy.value,
                "recovery_rate": decision.metrics.get("recovery_rate", coverage),
                "objective_score": decision.metrics.get("objective_score", 0),
                "optimization_iterations": decision.metrics.get(
                    "optimization_iterations", 0
                ),
                "optimality_gap": decision.metrics.get("optimality_gap_estimate", 0),
            },
        )


def create_strategy(
    strategy_type: StrategyType, ooda_engine=None
) -> BaselineStrategy:
    """
    Factory function to create strategy instances.

    Args:
        strategy_type: Type of strategy to create
        ooda_engine: Required for OODA strategy

    Returns:
        BaselineStrategy instance
    """
    if strategy_type == StrategyType.NO_ADAPTATION:
        return NoAdaptationStrategy()
    elif strategy_type == StrategyType.GREEDY_NEAREST:
        return GreedyNearestStrategy()
    elif strategy_type == StrategyType.OODA:
        if ooda_engine is None:
            raise ValueError("OODA strategy requires ooda_engine parameter")
        return OODAStrategy(ooda_engine)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
