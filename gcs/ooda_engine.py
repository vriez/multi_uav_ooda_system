"""
OODA Loop Engine - Core decision-making system for fault-tolerant fleet control.

Author: Vítor Eulálio Reis
Copyright (c) 2025

This module implements the four-phase OODA (Observe-Orient-Decide-Act) decision
cycle for autonomous fault recovery in multi-UAV systems.

Overview:
    When a UAV failure is detected, the OODA engine executes a complete cycle:

    1. OBSERVE: Aggregate fleet telemetry and identify failed vehicles
    2. ORIENT: Analyze mission impact (coverage loss, capacity, deadlines)
    3. DECIDE: Optimize task reallocation using objective function J(A)
    4. ACT: Dispatch updated mission commands to operational UAVs

Key Classes:
    OODAEngine: Main engine orchestrating the decision cycle
    FleetState: Snapshot of fleet status at a point in time
    MissionImpact: Analysis of how failure affects mission objectives
    OODADecision: Output containing recovery strategy and reallocation plan

Recovery Strategies:
    FULL_REALLOCATION: All lost tasks can be recovered (coverage >= 75%)
    PARTIAL_REALLOCATION: Some tasks recovered (50-74% coverage)
    OPERATOR_ESCALATION: Human intervention needed (< 50% coverage)
    ABORT_MISSION: Mission cannot continue (no operational UAVs)

Performance Targets:
    - Total OODA cycle: < 2500ms
    - OBSERVE phase: < 500ms
    - ORIENT phase: < 500ms
    - DECIDE phase: < 1200ms (includes optimization)
    - ACT phase: < 300ms

Example:
    >>> from gcs.ooda_engine import OODAEngine, FleetState
    >>> engine = OODAEngine(config)
    >>> decision = engine.trigger_ooda_cycle(fleet_state, mission_db, validator)
    >>> print(f"Strategy: {decision.strategy.value}")
    >>> print(f"Tasks reallocated: {len(decision.reallocation_plan)}")

References:
    Boyd, John. "The OODA Loop." Military briefing, 1987.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np

# Import objective function module for optimized DECIDE phase
from .objective_function import (
    ObjectiveFunction,
    AllocationOptimizer,
    MissionContext,
    AllocationResult,
    create_optimizer,
)

logger = logging.getLogger(__name__)


class OODAPhase(Enum):
    """OODA loop phases"""

    IDLE = "idle"
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"


class RecoveryStrategy(Enum):
    """Recovery strategies based on mission impact"""

    FULL_REALLOCATION = "full_reallocation"
    PARTIAL_REALLOCATION = "partial_reallocation"
    OPERATOR_ESCALATION = "operator_escalation"
    ABORT_MISSION = "abort_mission"


@dataclass
class FleetState:
    """
    Complete fleet state snapshot at a specific point in time.

    This dataclass captures all relevant information about the UAV fleet
    needed for OODA decision-making, including positions, battery levels,
    payload capacities, and failure status.

    Attributes:
        timestamp: Unix timestamp when snapshot was taken
        operational_uavs: List of UAV IDs that are currently operational
        failed_uavs: List of UAV IDs that have failed
        uav_positions: Mapping of UAV ID to [x, y, z] position (meters)
        uav_battery: Mapping of UAV ID to battery state-of-charge (0-100%)
        uav_payloads: Mapping of UAV ID to available payload capacity (kg)
        lost_tasks: List of task IDs that need reallocation (from failed UAVs)
        uav_permissions: Special permissions per UAV, e.g., {'out_of_grid': True}

    Example:
        >>> state = FleetState(
        ...     timestamp=time.time(),
        ...     operational_uavs=[1, 2, 3],
        ...     failed_uavs=[4],
        ...     uav_positions={1: np.array([0, 0, 25]), ...},
        ...     uav_battery={1: 80.0, 2: 75.0, 3: 90.0},
        ...     uav_payloads={1: 5.0, 2: 5.0, 3: 5.0},
        ...     lost_tasks=[5, 6],  # Tasks from failed UAV 4
        ... )
    """

    timestamp: float
    operational_uavs: List[int]
    failed_uavs: List[int]
    uav_positions: Dict[int, np.ndarray]
    uav_battery: Dict[int, float]
    uav_payloads: Dict[int, float]
    lost_tasks: List[int]
    uav_permissions: Dict[int, Dict[str, bool]] = (
        None  # e.g., {1: {'out_of_grid': True}}
    )

    def __post_init__(self):
        if self.uav_permissions is None:
            self.uav_permissions = {}


@dataclass
class MissionImpact:
    """
    Analysis of failure impact on mission objectives.

    Computed during the ORIENT phase, this captures how a UAV failure
    affects overall mission success potential.

    Attributes:
        coverage_loss_percent: Percentage of total tasks now unassigned (0-100)
        affected_zones: List of zone IDs impacted by the failure
        fleet_capacity_battery: Total spare battery capacity across fleet (Wh)
        fleet_capacity_payload: Total spare payload capacity across fleet (kg)
        temporal_margin_sec: Time until nearest deadline (seconds)
        recoverable_tasks: Estimated number of tasks that can be reallocated
        total_lost_tasks: Total number of tasks needing reallocation
    """

    coverage_loss_percent: float
    affected_zones: List[int]
    fleet_capacity_battery: float
    fleet_capacity_payload: float
    temporal_margin_sec: float
    recoverable_tasks: int
    total_lost_tasks: int


@dataclass
class OODADecision:
    """
    Output of OODA cycle containing recovery strategy and reallocation plan.

    This is the final output of the DECIDE phase, containing all information
    needed to execute the recovery action.

    Attributes:
        strategy: Selected recovery strategy (full/partial/escalate/abort)
        reallocation_plan: Mapping of UAV ID to list of task IDs to assign
        rationale: Human-readable explanation of the decision
        metrics: Performance and quality metrics from the cycle
        execution_time_ms: Total OODA cycle execution time (milliseconds)
        phase_timings: Breakdown of time spent in each phase (ms)

    Metrics Dictionary Keys:
        - recovery_rate: Percentage of lost tasks successfully reallocated
        - coverage_loss: Original coverage loss from failure
        - tasks_recovered: Number of tasks in reallocation plan
        - tasks_lost: Number of tasks from failed UAV(s)
        - objective_score: J(A) score from optimization
        - optimization_time_ms: Time spent in optimization
        - optimality_gap_estimate: Estimated distance from optimal solution

    Example:
        >>> decision = engine.trigger_ooda_cycle(state, db, validator)
        >>> if decision.strategy == RecoveryStrategy.FULL_REALLOCATION:
        ...     for uav_id, tasks in decision.reallocation_plan.items():
        ...         dispatch_tasks(uav_id, tasks)
    """

    strategy: RecoveryStrategy
    reallocation_plan: Dict[int, List[int]]  # UAV ID -> Task IDs
    rationale: str
    metrics: Dict[str, float]
    execution_time_ms: float
    phase_timings: Dict[str, float] = field(
        default_factory=dict
    )  # Phase-specific timing breakdown


class OODAEngine:
    """
    OODA Loop Engine implementing the four-phase decision cycle for fault-tolerant
    mission control.

    The engine orchestrates the complete OODA (Observe-Orient-Decide-Act) cycle
    when triggered by a failure event. It coordinates with the FleetMonitor,
    MissionManager, ConstraintValidator, and ObjectiveFunction to produce
    optimal recovery decisions.

    Attributes:
        config: GCS configuration dictionary
        phase: Current OODA phase (IDLE when not in cycle)
        cycle_count: Number of OODA cycles executed
        mission_context: Mission-specific parameters for optimization

    Args:
        config: GCS configuration with ooda_engine and constraints sections
        dashboard_bridge: Optional bridge for real-time UI updates
        mission_context: Optional mission context (inferred if not provided)

    Example:
        >>> config = load_yaml("config/gcs_config.yaml")
        >>> engine = OODAEngine(config)
        >>> engine.set_mission_context(MissionContext.for_surveillance())
        >>>
        >>> # Trigger on failure
        >>> decision = engine.trigger_ooda_cycle(fleet_state, mission_db, validator)
        >>> print(f"Cycle #{engine.cycle_count}: {decision.strategy.value}")
    """

    def __init__(
        self,
        config: dict,
        dashboard_bridge=None,
        mission_context: Optional[MissionContext] = None,
    ):
        self.config = config
        self.phase = OODAPhase.IDLE
        self.cycle_start_time = 0
        self.phase_timeouts = config["ooda_engine"]["phase_timeouts"]
        self.dashboard_bridge = dashboard_bridge

        # Mission context for objective function optimization
        # If not provided, will be inferred from mission_db or default to surveillance
        self.mission_context = mission_context

        # Optimizer instances (lazily initialized per mission)
        self._objective_fn: Optional[ObjectiveFunction] = None
        self._optimizer: Optional[AllocationOptimizer] = None

        # Performance tracking
        self.cycle_count = 0
        self.phase_times = {phase: [] for phase in OODAPhase}

        # Aggregate metrics tracking
        self.total_tasks_recovered = 0
        self.total_tasks_lost = 0
        self.recovery_rates = []
        self.objective_scores = []

    def set_mission_context(self, context: MissionContext):
        """Update mission context (resets optimizer)"""
        self.mission_context = context
        self._objective_fn = None
        self._optimizer = None
        logger.info(f"Mission context updated: {context.mission_type.value}")

    def _get_optimizer(
        self, mission_db, constraint_validator
    ) -> Tuple[ObjectiveFunction, AllocationOptimizer]:
        """Get or create optimizer for current mission context"""
        if self._objective_fn is None or self._optimizer is None:
            # Determine mission type
            if self.mission_context:
                context = self.mission_context
            else:
                # Try to infer from mission_db or config
                mission_type = self.config.get("mission_context", {}).get(
                    "mission_type", "surveillance"
                )
                self._objective_fn, self._optimizer = create_optimizer(
                    mission_type, mission_db, constraint_validator
                )
                return self._objective_fn, self._optimizer

            self._objective_fn = ObjectiveFunction(
                context, mission_db, constraint_validator
            )
            self._optimizer = AllocationOptimizer(self._objective_fn, context)

        return self._objective_fn, self._optimizer

    def trigger_ooda_cycle(
        self, fleet_state: FleetState, mission_db, constraint_validator
    ) -> OODADecision:
        """
        Execute complete OODA cycle upon failure detection

        Args:
            fleet_state: Current state of all UAVs
            mission_db: Mission database with tasks and assignments
            constraint_validator: Constraint checking system

        Returns:
            OODADecision with recovery strategy and reallocation plan
        """
        self.cycle_start_time = time.time()
        self.cycle_count += 1

        # Track phase timings for this cycle
        phase_timings = {}

        logger.info(
            f"OODA Cycle #{self.cycle_count} triggered - "
            f"{len(fleet_state.failed_uavs)} UAV(s) failed"
        )

        try:
            # Phase 1: OBSERVE
            phase_start = time.time()
            observed_state = self._observe_phase(fleet_state, mission_db)
            phase_timings["observe_ms"] = (time.time() - phase_start) * 1000

            # Phase 2: ORIENT
            phase_start = time.time()
            impact = self._orient_phase(observed_state, mission_db)
            phase_timings["orient_ms"] = (time.time() - phase_start) * 1000

            # Phase 3: DECIDE
            phase_start = time.time()
            decision = self._decide_phase(
                impact, observed_state, mission_db, constraint_validator
            )
            phase_timings["decide_ms"] = (time.time() - phase_start) * 1000

            # Phase 4: ACT
            phase_start = time.time()
            self._act_phase(decision, mission_db)
            phase_timings["act_ms"] = (time.time() - phase_start) * 1000

            # Record execution time and phase breakdown
            decision.execution_time_ms = (time.time() - self.cycle_start_time) * 1000
            decision.phase_timings = phase_timings

            # Update aggregate statistics
            self.total_tasks_lost += len(fleet_state.lost_tasks)
            tasks_recovered = len(
                [t for ts in decision.reallocation_plan.values() for t in ts]
            )
            self.total_tasks_recovered += tasks_recovered

            recovery_rate = decision.metrics.get("recovery_rate", 0)
            self.recovery_rates.append(recovery_rate)

            if "objective_score" in decision.metrics:
                self.objective_scores.append(decision.metrics["objective_score"])

            logger.info(
                f"OODA Cycle completed: {decision.strategy.value} "
                f"in {decision.execution_time_ms:.1f}ms "
                f"(O:{phase_timings['observe_ms']:.1f} "
                f"O:{phase_timings['orient_ms']:.1f} "
                f"D:{phase_timings['decide_ms']:.1f} "
                f"A:{phase_timings['act_ms']:.1f})"
            )

            return decision

        except Exception as e:
            logger.error(f"OODA cycle failed: {e}", exc_info=True)
            return OODADecision(
                strategy=RecoveryStrategy.OPERATOR_ESCALATION,
                reallocation_plan={},
                rationale=f"OODA cycle exception: {str(e)}",
                metrics={},
                execution_time_ms=(time.time() - self.cycle_start_time) * 1000,
                phase_timings={},
            )

    def _observe_phase(self, fleet_state: FleetState, mission_db) -> FleetState:
        """
        OBSERVE: Collect fleet telemetry and identify failures
        """
        phase_start = time.time()
        self.phase = OODAPhase.OBSERVE

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Observing fleet: {len(fleet_state.operational_uavs)} operational, "
                f"{len(fleet_state.failed_uavs)} failed",
                phase="observe",
                cycle_num=self.cycle_count,
                details={
                    "operational_uavs": fleet_state.operational_uavs,
                    "failed_uavs": fleet_state.failed_uavs,
                    "lost_tasks": fleet_state.lost_tasks,
                },
            )

        # Aggregate fleet state
        # Identify failed vehicles
        # Extract lost tasks

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.OBSERVE].append(elapsed)

        if elapsed > self.phase_timeouts["observe"]:
            logger.warning(f"Observe phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Observe complete: {elapsed*1000:.1f}ms",
                phase="observe",
                cycle_num=self.cycle_count,
                duration_ms=elapsed * 1000,
            )

        return fleet_state

    def _orient_phase(self, fleet_state: FleetState, mission_db) -> MissionImpact:
        """
        ORIENT: Evaluate mission impact and fleet capacity
        """
        phase_start = time.time()
        self.phase = OODAPhase.ORIENT

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Orienting: Analyzing mission impact...",
                phase="orient",
                cycle_num=self.cycle_count,
            )

        # Calculate coverage loss
        total_tasks = len(mission_db.tasks)
        lost_tasks = len(fleet_state.lost_tasks)
        coverage_loss = (lost_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Fleet capacity analysis
        battery_spare = self._calculate_battery_spare_capacity(fleet_state, mission_db)
        payload_spare = self._calculate_payload_spare_capacity(fleet_state, mission_db)

        # Temporal margin
        temporal_margin = self._calculate_temporal_margin(mission_db)

        # Determine recoverability
        recoverable = self._estimate_recoverable_tasks(
            fleet_state, mission_db, battery_spare, payload_spare
        )

        impact = MissionImpact(
            coverage_loss_percent=coverage_loss,
            affected_zones=mission_db.get_affected_zones(fleet_state.lost_tasks),
            fleet_capacity_battery=battery_spare,
            fleet_capacity_payload=payload_spare,
            temporal_margin_sec=temporal_margin,
            recoverable_tasks=recoverable,
            total_lost_tasks=lost_tasks,
        )

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.ORIENT].append(elapsed)

        if elapsed > self.phase_timeouts["orient"]:
            logger.warning(f"Orient phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Orient complete: {coverage_loss:.1f}% coverage loss, "
                f"{recoverable}/{lost_tasks} tasks recoverable",
                phase="orient",
                cycle_num=self.cycle_count,
                duration_ms=elapsed * 1000,
                details={
                    "coverage_loss": coverage_loss,
                    "battery_spare": battery_spare,
                    "payload_spare": payload_spare,
                    "temporal_margin": temporal_margin,
                    "recoverable_tasks": recoverable,
                    "total_lost_tasks": lost_tasks,
                },
            )

        return impact

    def _decide_phase(
        self,
        impact: MissionImpact,
        fleet_state: FleetState,
        mission_db,
        constraint_validator,
    ) -> OODADecision:
        """
        DECIDE: Select recovery strategy and plan reallocation

        Uses two-stage optimization:
        1. Greedy initialization (Algorithm 2)
        2. Local search refinement (when time permits)

        The objective function J(A) guides allocation quality.
        """
        phase_start = time.time()
        self.phase = OODAPhase.DECIDE

        # Get optimizer for current mission context
        objective_fn, optimizer = self._get_optimizer(mission_db, constraint_validator)

        # Prepare lost tasks for optimization
        lost_tasks = [mission_db.get_task(tid) for tid in fleet_state.lost_tasks]
        lost_tasks = [t for t in lost_tasks if t is not None]

        # Execute two-stage optimization
        if lost_tasks and fleet_state.operational_uavs:
            opt_result: AllocationResult = optimizer.optimize(
                fleet_state, lost_tasks, constraint_validator
            )

            # Determine strategy based on coverage achieved
            coverage = opt_result.coverage_percentage

            if coverage >= 75:
                strategy = RecoveryStrategy.FULL_REALLOCATION
            elif coverage >= 50:
                strategy = RecoveryStrategy.PARTIAL_REALLOCATION
            else:
                strategy = RecoveryStrategy.OPERATOR_ESCALATION

            reallocation_plan = opt_result.allocation
            objective_score = opt_result.objective_score

            rationale = (
                f"Optimized reallocation: {len([t for ts in reallocation_plan.values() for t in ts])} tasks "
                f"across {len(reallocation_plan)} UAVs. "
                f"Coverage: {coverage:.1f}%, Objective: {objective_score:.3f}, "
                f"Optimization: {opt_result.optimization_time_ms:.1f}ms ({opt_result.iterations} iterations)"
            )

            # Extended metrics including optimization details and mission impact
            metrics = {
                # Decision Quality Metrics
                "recovery_rate": coverage,
                "coverage_loss": impact.coverage_loss_percent,
                "tasks_recovered": len(
                    [t for ts in reallocation_plan.values() for t in ts]
                ),
                "tasks_lost": len(fleet_state.lost_tasks),
                "unallocated_count": len(opt_result.unallocated_tasks),
                # Fleet Capacity Metrics
                "battery_spare": impact.fleet_capacity_battery,
                "payload_spare": impact.fleet_capacity_payload,
                "operational_uavs": len(fleet_state.operational_uavs),
                "failed_uavs": len(fleet_state.failed_uavs),
                # Temporal Metrics
                "temporal_margin": impact.temporal_margin_sec,
                "recoverable_tasks": impact.recoverable_tasks,
                # Optimization Metrics
                "objective_score": objective_score,
                "optimization_time_ms": opt_result.optimization_time_ms,
                "optimization_iterations": opt_result.iterations,
                "optimality_gap_estimate": opt_result.optimality_gap_estimate,
                # Mission Impact Metrics
                "affected_zones": len(impact.affected_zones),
            }
        else:
            # No tasks to reallocate or no operational UAVs
            strategy = RecoveryStrategy.OPERATOR_ESCALATION
            reallocation_plan = {}
            rationale = "No tasks to reallocate or no operational UAVs available."
            metrics = {
                # Decision Quality Metrics
                "recovery_rate": 0,
                "coverage_loss": impact.coverage_loss_percent,
                "tasks_recovered": 0,
                "tasks_lost": len(fleet_state.lost_tasks),
                "unallocated_count": len(fleet_state.lost_tasks),
                # Fleet Capacity Metrics
                "battery_spare": impact.fleet_capacity_battery,
                "payload_spare": impact.fleet_capacity_payload,
                "operational_uavs": len(fleet_state.operational_uavs),
                "failed_uavs": len(fleet_state.failed_uavs),
                # Temporal Metrics
                "temporal_margin": impact.temporal_margin_sec,
                "recoverable_tasks": impact.recoverable_tasks,
                # Optimization Metrics
                "objective_score": 0,
                "optimization_time_ms": 0,
                "optimization_iterations": 0,
                "optimality_gap_estimate": 0,
                # Mission Impact Metrics
                "affected_zones": len(impact.affected_zones),
            }

        decision = OODADecision(
            strategy=strategy,
            reallocation_plan=reallocation_plan,
            rationale=rationale,
            metrics=metrics,
            execution_time_ms=0,  # Will be set later
        )

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.DECIDE].append(elapsed)

        if elapsed > self.phase_timeouts["decide"]:
            logger.warning(f"Decide phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Decide complete: {strategy.value} - {rationale}",
                phase="decide",
                cycle_num=self.cycle_count,
                duration_ms=elapsed * 1000,
                details={
                    "strategy": strategy.value,
                    "recovery_rate": metrics.get("recovery_rate", 0),
                    "reallocation_count": len(reallocation_plan),
                    "objective_score": metrics.get("objective_score", 0),
                    "optimality_gap": metrics.get("optimality_gap_estimate", 0),
                },
                metrics=metrics,  # Send all enhanced metrics to dashboard
            )

        return decision

    def _act_phase(self, decision: OODADecision, mission_db):
        """
        ACT: Dispatch mission updates and refresh operator dashboard
        """
        phase_start = time.time()
        self.phase = OODAPhase.ACT

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Acting: Executing {decision.strategy.value}...",
                phase="act",
                cycle_num=self.cycle_count,
            )

        # Commit reallocation to mission database
        if decision.reallocation_plan:
            mission_db.commit_reallocation(decision.reallocation_plan)

        # Mission updates will be dispatched by fleet manager

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.ACT].append(elapsed)

        if elapsed > self.phase_timeouts["act"]:
            logger.warning(f"Act phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Act complete: Strategy executed in {elapsed*1000:.1f}ms",
                phase="act",
                cycle_num=self.cycle_count,
                duration_ms=elapsed * 1000,
            )

        self.phase = OODAPhase.IDLE

    def _calculate_battery_spare_capacity(
        self, fleet_state: FleetState, mission_db
    ) -> float:
        """Calculate total spare battery capacity across fleet"""
        safety_reserve = (
            self.config["constraints"]["battery_safety_reserve_percent"] / 100
        )
        spare_capacity = 0

        for uav_id in fleet_state.operational_uavs:
            current_battery = fleet_state.uav_battery[uav_id]
            committed_tasks = mission_db.get_uav_tasks(uav_id)

            # Estimate committed energy (simplified)
            committed_energy = len(committed_tasks) * 5  # 5% per task estimate

            spare = current_battery - committed_energy - (safety_reserve * 100)
            spare_capacity += max(0, spare)

        return spare_capacity

    def _calculate_payload_spare_capacity(
        self, fleet_state: FleetState, mission_db
    ) -> float:
        """Calculate total spare payload capacity across fleet"""
        spare_capacity = 0

        for uav_id in fleet_state.operational_uavs:
            if uav_id in fleet_state.uav_payloads:
                spare_capacity += fleet_state.uav_payloads[uav_id]

        return spare_capacity

    def _calculate_temporal_margin(self, mission_db) -> float:
        """Calculate time margin until nearest deadline"""
        current_time = time.time()
        min_margin = float("inf")

        for task in mission_db.tasks.values():
            if task.deadline:
                margin = task.deadline - current_time
                min_margin = min(min_margin, margin)

        return min_margin if min_margin != float("inf") else 0

    def _estimate_recoverable_tasks(
        self,
        fleet_state: FleetState,
        mission_db,
        battery_spare: float,
        payload_spare: float,
    ) -> int:
        """Estimate number of lost tasks that can be recovered"""
        recoverable = 0

        for task_id in fleet_state.lost_tasks:
            task = mission_db.get_task(task_id)

            # Simple heuristic: check if any UAV has spare capacity
            if battery_spare > 5 and (
                not task.payload_kg or payload_spare > task.payload_kg
            ):
                recoverable += 1
                battery_spare -= 5  # Rough estimate
                if task.payload_kg:
                    payload_spare -= task.payload_kg

        return recoverable

    def _plan_reallocation(
        self,
        fleet_state: FleetState,
        impact: MissionImpact,
        mission_db,
        constraint_validator,
    ) -> Dict[int, List[int]]:
        """
        Plan task reallocation using greedy constraint-aware assignment
        (Simplified implementation - full algorithm in reallocation_planner.py)
        """
        reallocation = {}
        lost_tasks = sorted(
            [mission_db.get_task(tid) for tid in fleet_state.lost_tasks],
            key=lambda t: t.priority,
            reverse=True,
        )

        for task in lost_tasks:
            # Find nearest operational UAV
            best_uav = None
            min_dist = float("inf")

            for uav_id in fleet_state.operational_uavs:
                uav_pos = fleet_state.uav_positions[uav_id]
                dist = np.linalg.norm(uav_pos - task.position)

                # Check constraints (simplified)
                if constraint_validator.check_all_constraints(
                    uav_id, task.id, fleet_state, mission_db
                ):
                    if dist < min_dist:
                        min_dist = dist
                        best_uav = uav_id

            if best_uav:
                if best_uav not in reallocation:
                    reallocation[best_uav] = []
                reallocation[best_uav].append(task.id)

        return reallocation

    def get_performance_stats(self) -> Dict[str, float]:  # noqa: C901
        """
        Get comprehensive OODA cycle performance statistics

        Returns:
            Dictionary containing:
            - Cycle counts and timing statistics
            - Phase-specific timing (avg, max, min, std)
            - Decision quality metrics (recovery rates, objective scores)
            - Aggregate mission impact
        """
        stats = {
            # Cycle Statistics
            "total_cycles": self.cycle_count,
            "total_tasks_lost": self.total_tasks_lost,
            "total_tasks_recovered": self.total_tasks_recovered,
        }

        # Overall recovery rate
        if self.total_tasks_lost > 0:
            stats["overall_recovery_rate"] = (
                self.total_tasks_recovered / self.total_tasks_lost
            ) * 100
        else:
            stats["overall_recovery_rate"] = 0

        # Phase timing statistics
        all_phase_times = []
        for phase, times in self.phase_times.items():
            if times and phase != OODAPhase.IDLE:
                times_ms = np.array(times) * 1000
                stats[f"avg_{phase.value}_ms"] = np.mean(times_ms)
                stats[f"max_{phase.value}_ms"] = np.max(times_ms)
                stats[f"min_{phase.value}_ms"] = np.min(times_ms)
                stats[f"std_{phase.value}_ms"] = np.std(times_ms)
                all_phase_times.extend(times)

        # Total cycle time statistics
        if all_phase_times:
            cycle_times_ms = []
            # Reconstruct total cycle times from phase times
            for i in range(len(self.phase_times[OODAPhase.OBSERVE])):
                cycle_time = 0
                for phase in [
                    OODAPhase.OBSERVE,
                    OODAPhase.ORIENT,
                    OODAPhase.DECIDE,
                    OODAPhase.ACT,
                ]:
                    if i < len(self.phase_times[phase]):
                        cycle_time += self.phase_times[phase][i]
                cycle_times_ms.append(cycle_time * 1000)

            if cycle_times_ms:
                stats["avg_cycle_time_ms"] = np.mean(cycle_times_ms)
                stats["max_cycle_time_ms"] = np.max(cycle_times_ms)
                stats["min_cycle_time_ms"] = np.min(cycle_times_ms)
                stats["std_cycle_time_ms"] = np.std(cycle_times_ms)

        # Decision quality statistics
        if self.recovery_rates:
            stats["avg_recovery_rate"] = np.mean(self.recovery_rates)
            stats["max_recovery_rate"] = np.max(self.recovery_rates)
            stats["min_recovery_rate"] = np.min(self.recovery_rates)
            stats["std_recovery_rate"] = np.std(self.recovery_rates)

        # Objective score statistics
        if self.objective_scores:
            stats["avg_objective_score"] = np.mean(self.objective_scores)
            stats["max_objective_score"] = np.max(self.objective_scores)
            stats["min_objective_score"] = np.min(self.objective_scores)
            stats["std_objective_score"] = np.std(self.objective_scores)

        return stats
