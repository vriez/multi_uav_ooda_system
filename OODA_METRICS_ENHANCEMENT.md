# OODA Loop Metrics Enhancement

## Overview

Enhanced the OODA engine to provide comprehensive metric tracking across all phases, decision quality, and aggregate performance statistics.

## Changes Made

### 1. Enhanced OODADecision Dataclass

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py#L61-L69)

Added `phase_timings` field to track breakdown of execution time across OODA phases:

```python
@dataclass
class OODADecision:
    strategy: RecoveryStrategy
    reallocation_plan: Dict[int, List[int]]
    rationale: str
    metrics: Dict[str, float]
    execution_time_ms: float
    phase_timings: Dict[str, float] = field(default_factory=dict)  # NEW
```

### 2. Comprehensive Metrics Collection

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py#L366-L392)

Expanded metrics dictionary to include:

#### Decision Quality Metrics
- `recovery_rate` - Percentage of lost tasks successfully recovered
- `coverage_loss` - Mission coverage lost due to failure
- `tasks_recovered` - Number of tasks successfully reallocated
- `tasks_lost` - Total number of tasks lost in failure
- `unallocated_count` - Tasks that couldn't be reallocated

#### Fleet Capacity Metrics
- `battery_spare` - Total spare battery capacity (Wh)
- `payload_spare` - Total spare payload capacity (kg)
- `operational_uavs` - Number of operational UAVs
- `failed_uavs` - Number of failed UAVs

#### Temporal Metrics
- `temporal_margin` - Time until nearest task deadline (seconds)
- `recoverable_tasks` - Estimated number of recoverable tasks

#### Optimization Metrics
- `objective_score` - Objective function value
- `optimization_time_ms` - Time spent in optimization
- `optimization_iterations` - Number of local search iterations
- `optimality_gap_estimate` - Estimated gap from optimal solution

#### Mission Impact Metrics
- `affected_zones` - Number of zones affected by failure

### 3. Phase Timing Breakdown

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py#L129-L206)

Modified `trigger_ooda_cycle()` to track individual phase timings:

- `observe_ms` - Observation phase duration
- `orient_ms` - Orient phase duration
- `decide_ms` - Decision phase duration
- `act_ms` - Action phase duration

Enhanced logging output now shows phase breakdown:
```
OODA Cycle completed: full_reallocation in 0.49ms (O:0.00 O:0.02 D:0.45 A:0.01)
```

### 4. Aggregate Statistics Tracking

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py#L97-L101)

Added instance variables to track aggregate metrics across multiple cycles:

```python
# Aggregate metrics tracking
self.total_tasks_recovered = 0
self.total_tasks_lost = 0
self.recovery_rates = []
self.objective_scores = []
```

### 5. Enhanced Performance Statistics

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py#L589-L655)

Completely rewrote `get_performance_stats()` to provide comprehensive statistics:

#### Cycle Statistics
- `total_cycles` - Total OODA cycles executed
- `total_tasks_lost` - Aggregate tasks lost across all cycles
- `total_tasks_recovered` - Aggregate tasks recovered
- `overall_recovery_rate` - Overall recovery percentage

#### Cycle Timing Statistics
- `avg_cycle_time_ms` - Average total cycle time
- `max_cycle_time_ms` - Maximum cycle time observed
- `min_cycle_time_ms` - Minimum cycle time observed
- `std_cycle_time_ms` - Standard deviation of cycle times

#### Phase-Specific Statistics
For each phase (observe, orient, decide, act):
- `avg_[phase]_ms` - Average phase duration
- `max_[phase]_ms` - Maximum phase duration
- `min_[phase]_ms` - Minimum phase duration
- `std_[phase]_ms` - Standard deviation of phase duration

#### Decision Quality Statistics
- `avg_recovery_rate` - Average recovery rate across cycles
- `max_recovery_rate` - Best recovery rate achieved
- `min_recovery_rate` - Worst recovery rate
- `std_recovery_rate` - Recovery rate variability

#### Objective Score Statistics
- `avg_objective_score` - Average optimization objective score
- `max_objective_score` - Best objective score achieved
- `min_objective_score` - Worst objective score
- `std_objective_score` - Objective score variability

## Usage Example

```python
from gcs.ooda_engine import OODAEngine, FleetState
from gcs.constraint_validator import ConstraintValidator
from gcs.objective_function import MissionContext

# Initialize OODA engine
ooda_engine = OODAEngine(config)
ooda_engine.set_mission_context(MissionContext.for_surveillance())

# Execute OODA cycle
decision = ooda_engine.trigger_ooda_cycle(
    fleet_state, mission_db, constraint_validator
)

# Access comprehensive metrics
print(f"Execution Time: {decision.execution_time_ms:.2f}ms")
print(f"Phase Breakdown: {decision.phase_timings}")
print(f"Recovery Rate: {decision.metrics['recovery_rate']:.1f}%")
print(f"Objective Score: {decision.metrics['objective_score']:.3f}")

# Get aggregate statistics after multiple cycles
stats = ooda_engine.get_performance_stats()
print(f"Average Cycle Time: {stats['avg_cycle_time_ms']:.2f}ms")
print(f"Overall Recovery Rate: {stats['overall_recovery_rate']:.1f}%")
```

## Test Results

All 202 existing tests pass successfully:

```bash
$ uv run pytest tests/ -v
============================= 202 passed in 0.39s ==============================
```

## Demonstration Script

A demonstration script is available at [test_enhanced_metrics.py](test_enhanced_metrics.py) that shows:

1. Creation of a surveillance mission scenario
2. Execution of two OODA cycles with UAV failures
3. Display of all enhanced metrics
4. Export of metrics to JSON format

Run with:
```bash
uv run python test_enhanced_metrics.py
```

Output is saved to `enhanced_metrics_output.json`.

## Performance Impact

The enhanced metrics collection adds minimal overhead:
- Average cycle time remains sub-millisecond (~0.4ms)
- No impact on decision quality or optimization
- Metrics are collected passively during normal execution

## Benefits

1. **Comprehensive Visibility** - Full insight into OODA loop performance
2. **Phase-Level Analysis** - Identify bottlenecks in specific phases
3. **Decision Quality Tracking** - Monitor recovery rates and optimization effectiveness
4. **Long-Term Trends** - Aggregate statistics for system health monitoring
5. **Research & Validation** - Rich data for experimental analysis
6. **Debugging** - Detailed metrics aid in troubleshooting and tuning

## Backward Compatibility

All changes are backward compatible:
- Existing code continues to work unchanged
- New fields have default values
- Enhanced metrics are additive, not breaking
