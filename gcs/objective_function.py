"""
Objective Function and Optimization Strategy for OODA Loop DECIDE Phase

This module implements the formal objective function J(A) that quantifies
allocation quality and the two-stage optimization strategy (greedy + local search).

Reference: TCC Section 3.5 - Objective Function and Optimization Strategy
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class MissionType(Enum):
    """Mission types with distinct optimization priorities"""

    SURVEILLANCE = "surveillance"
    SEARCH_RESCUE = "search_rescue"
    DELIVERY = "delivery"


@dataclass
class MissionContext:
    """
    Mission-specific configuration injected into the OODA loop.
    Determines objective function weights and optimization behavior.
    """

    mission_type: MissionType

    # Priority weights for Algorithm 1 (task scoring)
    w_temporal: float = 0.3
    w_criticality: float = 0.5
    w_spatial: float = 0.2

    # Objective function parameters
    lambda_unallocated: float = 0.3  # Penalty for unallocated tasks
    gamma_coverage_gap: float = 0.2  # Coverage gap weight (surveillance)
    beta_golden_hour: float = 0.5  # Golden hour bonus (SAR)

    # Mission-specific parameters
    golden_hour_sec: Optional[float] = None  # SAR golden hour deadline
    uav_max_range: float = 2000.0  # Max UAV range in meters

    # Optimization budget
    optimization_budget_ms: float = 1200.0  # Total DECIDE phase budget
    local_search_enabled: bool = True
    max_local_search_iterations: int = 50

    @classmethod
    def for_surveillance(cls) -> "MissionContext":
        """Factory for surveillance mission context"""
        return cls(
            mission_type=MissionType.SURVEILLANCE,
            w_temporal=0.3,
            w_criticality=0.5,
            w_spatial=0.2,
            lambda_unallocated=0.3,
            gamma_coverage_gap=0.2,
        )

    @classmethod
    def for_search_rescue(cls, golden_hour_sec: float = 3600.0) -> "MissionContext":
        """Factory for SAR mission context"""
        return cls(
            mission_type=MissionType.SEARCH_RESCUE,
            w_temporal=0.5,
            w_criticality=0.3,
            w_spatial=0.2,
            lambda_unallocated=0.5,
            beta_golden_hour=0.5,
            golden_hour_sec=golden_hour_sec,
        )

    @classmethod
    def for_delivery(cls) -> "MissionContext":
        """Factory for delivery mission context"""
        return cls(
            mission_type=MissionType.DELIVERY,
            w_temporal=0.2,
            w_criticality=0.6,
            w_spatial=0.2,
            lambda_unallocated=0.4,
        )


@dataclass
class AllocationResult:
    """Result of optimization containing allocation and metrics"""

    allocation: Dict[int, List[int]]  # UAV ID -> Task IDs
    objective_score: float
    coverage_percentage: float
    unallocated_tasks: List[int]
    optimization_time_ms: float
    iterations: int
    optimality_gap_estimate: float  # Estimated gap from optimal


class ObjectiveFunction:
    """
    Computes allocation quality score J(A) for the DECIDE phase.

    J(A) = Σ[ P_i · φ_m(t_i, u_j) ] - λ · |T_unalloc|

    Where:
        P_i: Priority score of task i (from Algorithm 1)
        φ_m: Mission-specific modifier function
        λ: Unallocated task penalty
    """

    def __init__(self, context: MissionContext, mission_db, constraint_validator):
        self.context = context
        self.mission_db = mission_db
        self.constraint_validator = constraint_validator

    def compute_task_priority(self, task, fleet_state) -> float:
        """
        Algorithm 1: Task Priority Calculation

        P_i = w_temporal * urgency + w_criticality * criticality - w_spatial * cost
        """
        # 1. TEMPORAL URGENCY (0-1, higher = more urgent)
        if task.deadline:
            current_time = time.time()
            t_remaining = max(0, task.deadline - current_time)
            t_total = task.duration_sec * 2  # Estimate total time window
            temporal_urgency = 1.0 - min(1.0, t_remaining / max(t_total, 1))
        else:
            temporal_urgency = 0.5  # Default mid-urgency

        # 2. MISSION CRITICALITY (from task type)
        criticality = self._get_criticality_weight(task)

        # 3. SPATIAL COST (distance to nearest UAV)
        min_distance = float("inf")
        for uav_id in fleet_state.operational_uavs:
            uav_pos = fleet_state.uav_positions[uav_id]
            dist = np.linalg.norm(uav_pos[:2] - task.position[:2])
            min_distance = min(min_distance, dist)

        spatial_cost = min(1.0, min_distance / self.context.uav_max_range)

        # 4. COMBINED SCORE
        priority = (
            self.context.w_temporal * temporal_urgency
            + self.context.w_criticality * criticality
            - self.context.w_spatial * spatial_cost
        )

        return max(0.0, min(1.0, priority))

    def _get_criticality_weight(self, task) -> float:
        """Get mission-specific criticality weight for task"""
        # Map task priority (0-100) to criticality (0-1)
        # Higher task.priority = more critical
        base_criticality = task.priority / 100.0

        # Mission-specific adjustments could be added here
        # based on task.type or other attributes

        return base_criticality

    def compute_modifier(self, task, uav_id, fleet_state) -> float:
        """
        Compute mission-specific modifier φ_m(t_i, u_j)

        Surveillance: 1 - γ · Δt_gap
        SAR: 1 + β · (t_golden - t_completion) / t_golden
        Delivery: 1.0 if on-time, 0.5 if late
        """
        if self.context.mission_type == MissionType.SURVEILLANCE:
            # Penalize coverage gaps
            # For now, assume no gap (task just became available)
            coverage_gap = 0.0
            return 1.0 - self.context.gamma_coverage_gap * coverage_gap

        elif self.context.mission_type == MissionType.SEARCH_RESCUE:
            # Bonus for completing before golden hour
            if self.context.golden_hour_sec:
                completion_time = self._estimate_completion_time(
                    task, uav_id, fleet_state
                )
                time_remaining = self.context.golden_hour_sec - completion_time
                bonus = self.context.beta_golden_hour * max(
                    0, time_remaining / self.context.golden_hour_sec
                )
                return 1.0 + bonus
            return 1.0

        elif self.context.mission_type == MissionType.DELIVERY:
            # Binary penalty for deadline violation
            if task.deadline:
                completion_time = self._estimate_completion_time(
                    task, uav_id, fleet_state
                )
                if completion_time <= task.deadline:
                    return 1.0
                else:
                    return 0.5  # Late delivery penalty
            return 1.0

        return 1.0

    def _estimate_completion_time(self, task, uav_id, fleet_state) -> float:
        """Estimate task completion time for given UAV"""
        uav_pos = fleet_state.uav_positions[uav_id]
        distance = np.linalg.norm(uav_pos[:2] - task.position[:2])

        # Assume 12 m/s average speed
        travel_time = distance / 12.0
        execution_time = task.duration_sec

        return time.time() + travel_time + execution_time

    def compute_objective(
        self, allocation: Dict[int, List[int]], fleet_state, lost_tasks: List
    ) -> float:
        """
        Compute objective function J(A)

        J(A) = Σ[ P_i · φ_m(t_i, u_j) ] - λ · |T_unalloc|
        """
        score = 0.0
        allocated_task_ids = set()

        for uav_id, task_ids in allocation.items():
            for task_id in task_ids:
                task = self.mission_db.get_task(task_id)
                if task is None:
                    continue

                allocated_task_ids.add(task_id)

                # Task priority P_i
                priority = self.compute_task_priority(task, fleet_state)

                # Mission modifier φ_m
                modifier = self.compute_modifier(task, uav_id, fleet_state)

                # Add to objective
                score += priority * modifier

        # Penalty for unallocated tasks
        all_lost_ids = {t.id if hasattr(t, "id") else t for t in lost_tasks}
        unallocated_count = len(all_lost_ids - allocated_task_ids)
        score -= self.context.lambda_unallocated * unallocated_count

        return score


class AllocationOptimizer:
    """
    Two-stage optimization for task reallocation:

    Stage 1: Greedy initialization (Algorithm 2)
    Stage 2: Local search refinement (when time permits)
    """

    def __init__(self, objective_fn: ObjectiveFunction, context: MissionContext):
        self.objective_fn = objective_fn
        self.context = context

    def optimize(
        self, fleet_state, lost_tasks: List, constraint_validator
    ) -> AllocationResult:
        """
        Execute two-stage optimization within time budget.

        Returns:
            AllocationResult with best allocation found
        """
        t_start = time.time()

        # Stage 1: Greedy initialization
        allocation = self._greedy_allocate(
            fleet_state, lost_tasks, constraint_validator
        )
        initial_score = self.objective_fn.compute_objective(
            allocation, fleet_state, lost_tasks
        )

        iterations = 1
        best_allocation = allocation
        best_score = initial_score

        # Stage 2: Local search refinement (if time permits)
        elapsed_ms = (time.time() - t_start) * 1000
        remaining_ms = (
            self.context.optimization_budget_ms - elapsed_ms - 200
        )  # Reserve 200ms

        if self.context.local_search_enabled and remaining_ms > 100:
            best_allocation, best_score, search_iters = self._local_search(
                allocation,
                fleet_state,
                lost_tasks,
                constraint_validator,
                max_time_ms=remaining_ms,
            )
            iterations += search_iters

        # Compute result metrics
        elapsed_ms = (time.time() - t_start) * 1000
        allocated_ids = {tid for tids in best_allocation.values() for tid in tids}
        all_lost_ids = {t.id if hasattr(t, "id") else t for t in lost_tasks}
        unallocated = list(all_lost_ids - allocated_ids)

        coverage = (
            (len(allocated_ids) / len(all_lost_ids) * 100) if all_lost_ids else 100.0
        )

        # Estimate optimality gap (rough heuristic)
        optimality_gap = self._estimate_optimality_gap(initial_score, best_score)

        return AllocationResult(
            allocation=best_allocation,
            objective_score=best_score,
            coverage_percentage=coverage,
            unallocated_tasks=unallocated,
            optimization_time_ms=elapsed_ms,
            iterations=iterations,
            optimality_gap_estimate=optimality_gap,
        )

    def _greedy_allocate(
        self, fleet_state, lost_tasks: List, constraint_validator
    ) -> Dict[int, List[int]]:
        """
        Stage 1: Greedy allocation (Algorithm 2)

        Assigns tasks in priority order to nearest feasible UAV.
        """
        allocation: Dict[int, List[int]] = {
            uav_id: [] for uav_id in fleet_state.operational_uavs
        }

        # Sort tasks by priority (descending)
        tasks_with_priority = []
        for task_ref in lost_tasks:
            task = self.objective_fn.mission_db.get_task(
                task_ref.id if hasattr(task_ref, "id") else task_ref
            )
            if task:
                priority = self.objective_fn.compute_task_priority(task, fleet_state)
                tasks_with_priority.append((task, priority))

        tasks_with_priority.sort(key=lambda x: x[1], reverse=True)

        # Track remaining capacity (simplified)
        uav_load: Dict[int, int] = {
            uav_id: 0 for uav_id in fleet_state.operational_uavs
        }

        for task, priority in tasks_with_priority:
            best_uav = None
            min_dist = float("inf")

            # Find nearest UAV that satisfies constraints
            for uav_id in fleet_state.operational_uavs:
                uav_pos = fleet_state.uav_positions[uav_id]
                dist = np.linalg.norm(uav_pos[:2] - task.position[:2])

                # Check constraints
                if constraint_validator.check_all_constraints(
                    uav_id, task.id, fleet_state, self.objective_fn.mission_db
                ):
                    if dist < min_dist:
                        min_dist = dist
                        best_uav = uav_id

            if best_uav is not None:
                allocation[best_uav].append(task.id)
                uav_load[best_uav] += 1

        # Remove empty entries
        return {k: v for k, v in allocation.items() if v}

    def _local_search(  # noqa: C901
        self,
        initial_allocation: Dict[int, List[int]],
        fleet_state,
        lost_tasks: List,
        constraint_validator,
        max_time_ms: float,
    ) -> Tuple[Dict[int, List[int]], float, int]:
        """
        Stage 2: Local search refinement

        Iteratively improves allocation via task swaps and reassignments.
        """
        best = {k: list(v) for k, v in initial_allocation.items()}  # Deep copy
        best_score = self.objective_fn.compute_objective(best, fleet_state, lost_tasks)

        t_start = time.time()
        iterations = 0

        while (time.time() - t_start) * 1000 < max_time_ms:
            iterations += 1
            if iterations > self.context.max_local_search_iterations:
                break

            improved = False

            # Try reassigning each task to a different UAV
            for uav_from, task_ids in list(best.items()):
                if improved:
                    break

                for task_id in task_ids:
                    if improved:
                        break

                    task = self.objective_fn.mission_db.get_task(task_id)
                    if task is None:
                        continue

                    # Try moving to each other UAV
                    for uav_to in fleet_state.operational_uavs:
                        if uav_to == uav_from:
                            continue

                        # Check if move is feasible
                        if not constraint_validator.check_all_constraints(
                            uav_to, task_id, fleet_state, self.objective_fn.mission_db
                        ):
                            continue

                        # Create candidate allocation
                        candidate = {k: list(v) for k, v in best.items()}
                        candidate[uav_from].remove(task_id)
                        if uav_to not in candidate:
                            candidate[uav_to] = []
                        candidate[uav_to].append(task_id)

                        # Remove empty entries
                        candidate = {k: v for k, v in candidate.items() if v}

                        # Evaluate
                        score = self.objective_fn.compute_objective(
                            candidate, fleet_state, lost_tasks
                        )

                        if score > best_score:
                            best = candidate
                            best_score = score
                            improved = True
                            break

            if not improved:
                # Local optimum reached
                break

        return best, best_score, iterations

    def _estimate_optimality_gap(
        self, initial_score: float, final_score: float
    ) -> float:
        """
        Estimate optimality gap as percentage.

        This is a rough heuristic - true gap requires solving exact MILP.
        """
        if initial_score <= 0:
            return 0.0

        improvement = (final_score - initial_score) / abs(initial_score) * 100

        # Heuristic: assume local search finds ~85% of remaining improvement
        # So if we improved 10%, we estimate ~12% total was possible
        estimated_remaining = improvement * 0.15 / 0.85 if improvement > 0 else 0

        return max(0, min(30, estimated_remaining))  # Cap at 30%


def create_optimizer(
    mission_type: str, mission_db, constraint_validator, **kwargs
) -> Tuple[ObjectiveFunction, AllocationOptimizer]:
    """
    Factory function to create optimizer for given mission type.

    Args:
        mission_type: One of 'surveillance', 'search_rescue', 'delivery'
        mission_db: Mission database instance
        constraint_validator: Constraint validator instance
        **kwargs: Additional mission context parameters

    Returns:
        Tuple of (ObjectiveFunction, AllocationOptimizer)
    """
    mission_type_lower = mission_type.lower()

    if mission_type_lower in ["surveillance", "patrol"]:
        context = MissionContext.for_surveillance()
    elif mission_type_lower in ["search_rescue", "sar", "search"]:
        golden_hour = kwargs.get("golden_hour_sec", 3600.0)
        context = MissionContext.for_search_rescue(golden_hour)
    elif mission_type_lower in ["delivery", "cargo"]:
        context = MissionContext.for_delivery()
    else:
        # Default to surveillance
        logger.warning(
            f"Unknown mission type '{mission_type}', defaulting to surveillance"
        )
        context = MissionContext.for_surveillance()

    # Apply any override parameters
    for key, value in kwargs.items():
        if hasattr(context, key):
            setattr(context, key, value)

    objective_fn = ObjectiveFunction(context, mission_db, constraint_validator)
    optimizer = AllocationOptimizer(objective_fn, context)

    return objective_fn, optimizer
