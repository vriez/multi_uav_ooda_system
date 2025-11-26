"""
Baseline Reallocation Strategies for Comparison Experiments

This module implements the baseline strategies against which the OODA-based
system is compared:

1. NoAdaptation: Mission aborts on failure (0% reallocation)
2. GreedyNearest: Naive nearest-UAV assignment (ignores constraints)
3. ManualOperator: Simulated human operator (5-10 min delay + optimal)
4. OODAStrategy: The system under test (constraint-aware + fast)

Reference: TCC Chapter 5 - Baseline Comparisons
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
    MANUAL_OPERATOR = "manual_operator"
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


class ManualOperatorStrategy(BaselineStrategy):
    """
    Manual Operator Baseline

    Simulates a human operator performing reallocation:
    - Detection delay: 30-60 seconds (noticing the failure)
    - Decision delay: 5-10 minutes (analyzing and planning)
    - Execution: Optimal allocation (human makes best choice)

    Expected results:
    - Coverage: 80-95% (optimal allocation)
    - Time: 5-10 minutes
    - Safety: Safe (human respects constraints)

    This baseline shows that OODA achieves similar coverage 75-150x faster.
    """

    def __init__(
        self, detection_delay_sec: float = 45.0, decision_delay_sec: float = 420.0
    ):  # 7 minutes default
        super().__init__(StrategyType.MANUAL_OPERATOR)
        self.detection_delay = detection_delay_sec
        self.decision_delay = decision_delay_sec

    def reallocate(
        self, fleet_state, lost_tasks: List, mission_db, constraint_validator
    ) -> ReallocationResult:
        """Simulate manual operator with delay + optimal allocation"""

        # Simulate operator delay (for timing comparison)
        total_delay = self.detection_delay + self.decision_delay

        # Perform optimal allocation (respecting constraints)
        allocation: Dict[int, List[int]] = {}
        unallocated = []

        # Sort tasks by priority for optimal allocation
        tasks_with_priority = []
        for task_ref in lost_tasks:
            task = mission_db.get_task(
                task_ref.id if hasattr(task_ref, "id") else task_ref
            )
            if task:
                tasks_with_priority.append((task, task.priority))

        tasks_with_priority.sort(key=lambda x: x[1], reverse=True)

        # Track UAV loads for optimal distribution
        uav_task_counts: Dict[int, int] = {
            uav_id: len(mission_db.get_uav_tasks(uav_id))
            for uav_id in fleet_state.operational_uavs
        }

        for task, priority in tasks_with_priority:
            best_uav = None
            best_score = float("-inf")

            # Find best UAV considering constraints AND load balancing
            for uav_id in fleet_state.operational_uavs:
                # Check constraints
                if not constraint_validator.check_all_constraints(
                    uav_id, task.id, fleet_state, mission_db
                ):
                    continue

                # Score based on distance and current load (operator optimizes)
                uav_pos = fleet_state.uav_positions[uav_id]
                dist = np.linalg.norm(uav_pos[:2] - task.position[:2])

                # Prefer UAVs with fewer tasks and closer distance
                load_penalty = uav_task_counts.get(uav_id, 0) * 100
                score = -dist - load_penalty

                if score > best_score:
                    best_score = score
                    best_uav = uav_id

            if best_uav is not None:
                if best_uav not in allocation:
                    allocation[best_uav] = []
                allocation[best_uav].append(task.id)
                uav_task_counts[best_uav] = uav_task_counts.get(best_uav, 0) + 1
            else:
                unallocated.append(task.id)

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
            adaptation_time_sec=total_delay,
            safety_violations=[],
            constraint_violations=0,
            tasks_reallocated=tasks_reallocated,
            tasks_lost=len(unallocated),
            rationale=f"Manual operator: {tasks_reallocated} tasks allocated after "
            f"{total_delay:.0f}s delay ({self.decision_delay/60:.1f} min decision time)",
            metrics={
                "detection_delay_sec": self.detection_delay,
                "decision_delay_sec": self.decision_delay,
                "total_delay_sec": total_delay,
                "recovery_rate": coverage,
                "unallocated_tasks": len(unallocated),
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
    strategy_type: StrategyType, ooda_engine=None, operator_delay_sec: float = 420.0
) -> BaselineStrategy:
    """
    Factory function to create strategy instances.

    Args:
        strategy_type: Type of strategy to create
        ooda_engine: Required for OODA strategy
        operator_delay_sec: Decision delay for manual operator

    Returns:
        BaselineStrategy instance
    """
    if strategy_type == StrategyType.NO_ADAPTATION:
        return NoAdaptationStrategy()
    elif strategy_type == StrategyType.GREEDY_NEAREST:
        return GreedyNearestStrategy()
    elif strategy_type == StrategyType.MANUAL_OPERATOR:
        return ManualOperatorStrategy(decision_delay_sec=operator_delay_sec)
    elif strategy_type == StrategyType.OODA:
        if ooda_engine is None:
            raise ValueError("OODA strategy requires ooda_engine parameter")
        return OODAStrategy(ooda_engine)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
