"""
OODA Loop Engine - Core decision-making system for fault-tolerant fleet control
"""
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np

# Import objective function module for optimized DECIDE phase
from .objective_function import (
    ObjectiveFunction, AllocationOptimizer, MissionContext,
    MissionType, AllocationResult, create_optimizer
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
    """Complete fleet state snapshot"""
    timestamp: float
    operational_uavs: List[int]
    failed_uavs: List[int]
    uav_positions: Dict[int, np.ndarray]
    uav_battery: Dict[int, float]
    uav_payloads: Dict[int, float]
    lost_tasks: List[int]
    

@dataclass
class MissionImpact:
    """Analysis of failure impact on mission"""
    coverage_loss_percent: float
    affected_zones: List[int]
    fleet_capacity_battery: float
    fleet_capacity_payload: float
    temporal_margin_sec: float
    recoverable_tasks: int
    total_lost_tasks: int
    

@dataclass
class OODADecision:
    """OODA cycle decision output"""
    strategy: RecoveryStrategy
    reallocation_plan: Dict[int, List[int]]  # UAV ID -> Task IDs
    rationale: str
    metrics: Dict[str, float]
    execution_time_ms: float
    phase_timings: Dict[str, float] = field(default_factory=dict)  # Phase-specific timing breakdown


class OODAEngine:
    """
    OODA Loop Engine implementing the four-phase decision cycle
    for fault-tolerant mission control
    """

    def __init__(self, config: dict, dashboard_bridge=None, mission_context: Optional[MissionContext] = None):
        self.config = config
        self.phase = OODAPhase.IDLE
        self.cycle_start_time = 0
        self.phase_timeouts = config['ooda_engine']['phase_timeouts']
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

    def set_mission_context(self, context: MissionContext):
        """Update mission context (resets optimizer)"""
        self.mission_context = context
        self._objective_fn = None
        self._optimizer = None
        logger.info(f"Mission context updated: {context.mission_type.value}")

    def _get_optimizer(self, mission_db, constraint_validator) -> Tuple[ObjectiveFunction, AllocationOptimizer]:
        """Get or create optimizer for current mission context"""
        if self._objective_fn is None or self._optimizer is None:
            # Determine mission type
            if self.mission_context:
                context = self.mission_context
            else:
                # Try to infer from mission_db or config
                mission_type = self.config.get('mission_context', {}).get('mission_type', 'surveillance')
                self._objective_fn, self._optimizer = create_optimizer(
                    mission_type, mission_db, constraint_validator
                )
                return self._objective_fn, self._optimizer

            self._objective_fn = ObjectiveFunction(context, mission_db, constraint_validator)
            self._optimizer = AllocationOptimizer(self._objective_fn, context)

        return self._objective_fn, self._optimizer
        
    def trigger_ooda_cycle(self, fleet_state: FleetState, mission_db, 
                           constraint_validator) -> OODADecision:
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
        
        logger.info(f"OODA Cycle #{self.cycle_count} triggered - "
                   f"{len(fleet_state.failed_uavs)} UAV(s) failed")
        
        try:
            # Phase 1: OBSERVE
            observed_state = self._observe_phase(fleet_state, mission_db)
            
            # Phase 2: ORIENT
            impact = self._orient_phase(observed_state, mission_db)
            
            # Phase 3: DECIDE
            decision = self._decide_phase(impact, observed_state, 
                                         mission_db, constraint_validator)
            
            # Phase 4: ACT
            self._act_phase(decision, mission_db)
            
            # Record execution time
            decision.execution_time_ms = (time.time() - self.cycle_start_time) * 1000
            
            logger.info(f"OODA Cycle completed: {decision.strategy.value} "
                       f"in {decision.execution_time_ms:.1f}ms")
            
            return decision
            
        except Exception as e:
            logger.error(f"OODA cycle failed: {e}", exc_info=True)
            return OODADecision(
                strategy=RecoveryStrategy.OPERATOR_ESCALATION,
                reallocation_plan={},
                rationale=f"OODA cycle exception: {str(e)}",
                metrics={},
                execution_time_ms=(time.time() - self.cycle_start_time) * 1000
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
                phase='observe',
                cycle_num=self.cycle_count,
                details={
                    'operational_uavs': fleet_state.operational_uavs,
                    'failed_uavs': fleet_state.failed_uavs,
                    'lost_tasks': fleet_state.lost_tasks
                }
            )

        # Aggregate fleet state
        # Identify failed vehicles
        # Extract lost tasks

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.OBSERVE].append(elapsed)

        if elapsed > self.phase_timeouts['observe']:
            logger.warning(f"Observe phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Observe complete: {elapsed*1000:.1f}ms",
                phase='observe',
                cycle_num=self.cycle_count,
                duration_ms=elapsed*1000
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
                phase='orient',
                cycle_num=self.cycle_count
            )

        # Calculate coverage loss
        total_tasks = len(mission_db.tasks)
        lost_tasks = len(fleet_state.lost_tasks)
        coverage_loss = (lost_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Fleet capacity analysis
        battery_spare = self._calculate_battery_spare_capacity(
            fleet_state, mission_db
        )
        payload_spare = self._calculate_payload_spare_capacity(
            fleet_state, mission_db
        )

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
            total_lost_tasks=lost_tasks
        )

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.ORIENT].append(elapsed)

        if elapsed > self.phase_timeouts['orient']:
            logger.warning(f"Orient phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Orient complete: {coverage_loss:.1f}% coverage loss, "
                f"{recoverable}/{lost_tasks} tasks recoverable",
                phase='orient',
                cycle_num=self.cycle_count,
                duration_ms=elapsed*1000,
                details={
                    'coverage_loss': coverage_loss,
                    'battery_spare': battery_spare,
                    'payload_spare': payload_spare,
                    'temporal_margin': temporal_margin,
                    'recoverable_tasks': recoverable,
                    'total_lost_tasks': lost_tasks
                }
            )

        return impact
    
    def _decide_phase(self, impact: MissionImpact, fleet_state: FleetState,
                     mission_db, constraint_validator) -> OODADecision:
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

            # Extended metrics including optimization details
            metrics = {
                'recovery_rate': coverage,
                'coverage_loss': impact.coverage_loss_percent,
                'battery_spare': impact.fleet_capacity_battery,
                'temporal_margin': impact.temporal_margin_sec,
                'objective_score': objective_score,
                'optimization_time_ms': opt_result.optimization_time_ms,
                'optimization_iterations': opt_result.iterations,
                'optimality_gap_estimate': opt_result.optimality_gap_estimate,
                'unallocated_count': len(opt_result.unallocated_tasks)
            }
        else:
            # No tasks to reallocate or no operational UAVs
            strategy = RecoveryStrategy.OPERATOR_ESCALATION
            reallocation_plan = {}
            rationale = "No tasks to reallocate or no operational UAVs available."
            metrics = {
                'recovery_rate': 0,
                'coverage_loss': impact.coverage_loss_percent,
                'battery_spare': impact.fleet_capacity_battery,
                'temporal_margin': impact.temporal_margin_sec
            }

        decision = OODADecision(
            strategy=strategy,
            reallocation_plan=reallocation_plan,
            rationale=rationale,
            metrics=metrics,
            execution_time_ms=0  # Will be set later
        )

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.DECIDE].append(elapsed)

        if elapsed > self.phase_timeouts['decide']:
            logger.warning(f"Decide phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Decide complete: {strategy.value} - {rationale}",
                phase='decide',
                cycle_num=self.cycle_count,
                duration_ms=elapsed*1000,
                details={
                    'strategy': strategy.value,
                    'recovery_rate': metrics.get('recovery_rate', 0),
                    'reallocation_count': len(reallocation_plan),
                    'objective_score': metrics.get('objective_score', 0),
                    'optimality_gap': metrics.get('optimality_gap_estimate', 0)
                }
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
                phase='act',
                cycle_num=self.cycle_count
            )

        # Commit reallocation to mission database
        if decision.reallocation_plan:
            mission_db.commit_reallocation(decision.reallocation_plan)

        # Mission updates will be dispatched by fleet manager

        elapsed = time.time() - phase_start
        self.phase_times[OODAPhase.ACT].append(elapsed)

        if elapsed > self.phase_timeouts['act']:
            logger.warning(f"Act phase timeout: {elapsed:.3f}s")

        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"Act complete: Strategy executed in {elapsed*1000:.1f}ms",
                phase='act',
                cycle_num=self.cycle_count,
                duration_ms=elapsed*1000
            )

        self.phase = OODAPhase.IDLE
    
    def _calculate_battery_spare_capacity(self, fleet_state: FleetState,
                                          mission_db) -> float:
        """Calculate total spare battery capacity across fleet"""
        safety_reserve = self.config['constraints']['battery_safety_reserve_percent'] / 100
        spare_capacity = 0
        
        for uav_id in fleet_state.operational_uavs:
            current_battery = fleet_state.uav_battery[uav_id]
            committed_tasks = mission_db.get_uav_tasks(uav_id)
            
            # Estimate committed energy (simplified)
            committed_energy = len(committed_tasks) * 5  # 5% per task estimate
            
            spare = current_battery - committed_energy - (safety_reserve * 100)
            spare_capacity += max(0, spare)
            
        return spare_capacity
    
    def _calculate_payload_spare_capacity(self, fleet_state: FleetState,
                                          mission_db) -> float:
        """Calculate total spare payload capacity across fleet"""
        spare_capacity = 0
        
        for uav_id in fleet_state.operational_uavs:
            if uav_id in fleet_state.uav_payloads:
                spare_capacity += fleet_state.uav_payloads[uav_id]
                
        return spare_capacity
    
    def _calculate_temporal_margin(self, mission_db) -> float:
        """Calculate time margin until nearest deadline"""
        current_time = time.time()
        min_margin = float('inf')

        for task in mission_db.tasks.values():
            if task.deadline:
                margin = task.deadline - current_time
                min_margin = min(min_margin, margin)

        return min_margin if min_margin != float('inf') else 0
    
    def _estimate_recoverable_tasks(self, fleet_state: FleetState,
                                   mission_db, battery_spare: float,
                                   payload_spare: float) -> int:
        """Estimate number of lost tasks that can be recovered"""
        recoverable = 0
        
        for task_id in fleet_state.lost_tasks:
            task = mission_db.get_task(task_id)
            
            # Simple heuristic: check if any UAV has spare capacity
            if battery_spare > 5 and (not task.payload_kg or payload_spare > task.payload_kg):
                recoverable += 1
                battery_spare -= 5  # Rough estimate
                if task.payload_kg:
                    payload_spare -= task.payload_kg
                    
        return recoverable
    
    def _plan_reallocation(self, fleet_state: FleetState, impact: MissionImpact,
                          mission_db, constraint_validator) -> Dict[int, List[int]]:
        """
        Plan task reallocation using greedy constraint-aware assignment
        (Simplified implementation - full algorithm in reallocation_planner.py)
        """
        reallocation = {}
        lost_tasks = sorted(
            [mission_db.get_task(tid) for tid in fleet_state.lost_tasks],
            key=lambda t: t.priority, 
            reverse=True
        )
        
        for task in lost_tasks:
            # Find nearest operational UAV
            best_uav = None
            min_dist = float('inf')
            
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
    
    def get_performance_stats(self) -> Dict[str, float]:
        """Get OODA cycle performance statistics"""
        stats = {
            'total_cycles': self.cycle_count,
            'avg_cycle_time_ms': 0
        }
        
        for phase, times in self.phase_times.items():
            if times:
                stats[f'avg_{phase.value}_ms'] = np.mean(times) * 1000
                stats[f'max_{phase.value}_ms'] = np.max(times) * 1000
                
        return stats
