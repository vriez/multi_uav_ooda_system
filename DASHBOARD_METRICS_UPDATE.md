# Dashboard OODA Metrics Enhancement

## Overview

Enhanced the web dashboard's OODA Loop Monitor to display comprehensive real-time metrics collected from the OODA engine, providing operators with detailed insights into decision quality, fleet status, and optimization performance.

## Changes Summary

### 1. Frontend (Dashboard HTML/JavaScript)

**File:** [visualization/templates/dashboard.html](visualization/templates/dashboard.html)

#### Added Metrics Sections

Three new metric panels were added to the OODA Loop Monitor:

##### Decision Quality Metrics (Lines 1177-1198)
- **Recovery Rate** - Percentage of lost tasks successfully recovered
- **Tasks Recovered** - Ratio of recovered tasks (e.g., "1/1")
- **Coverage Loss** - Mission coverage lost due to failure
- **Objective Score** - Optimization objective function value

##### Fleet Status Metrics (Lines 1200-1221)
- **Operational UAVs** - Number of operational UAVs
- **Failed UAVs** - Number of failed UAVs
- **Battery Spare** - Total spare battery capacity (Wh)
- **Payload Spare** - Total spare payload capacity (kg)

##### Optimization Metrics (Lines 1223-1240)
- **Opt. Time** - Optimization execution time
- **Iterations** - Number of local search iterations
- **Optimality Gap** - Estimated gap from optimal solution

#### Added JavaScript Function (Lines 1756-1823)

```javascript
function updateEnhancedOodaMetrics(metrics)
```

Handles real-time updates of all enhanced metrics from backend, including:
- Safe value formatting with fallbacks
- Proper unit display (%, Wh, kg, ms/s)
- Percentage conversion for optimality gap

#### Modified Event Handler (Lines 2389-2392)

```javascript
socket.on('ooda_event', e => {
    // ... existing code ...
    if (e.metrics) {
        updateEnhancedOodaMetrics(e.metrics);
    }
});
```

### 2. Backend (OODA Engine)

**File:** [gcs/ooda_engine.py](gcs/ooda_engine.py)

#### Enhanced OODA Decision Output (Line 458)

Modified the `_decide_phase` method to send comprehensive metrics to the dashboard:

```python
if self.dashboard_bridge:
    self.dashboard_bridge.notify_ooda_event(
        # ... existing parameters ...
        metrics=metrics  # Send all enhanced metrics
    )
```

The `metrics` dictionary now includes:

**Decision Quality:**
- `recovery_rate`, `coverage_loss`, `tasks_recovered`, `tasks_lost`, `unallocated_count`

**Fleet Capacity:**
- `battery_spare`, `payload_spare`, `operational_uavs`, `failed_uavs`

**Temporal:**
- `temporal_margin`, `recoverable_tasks`

**Optimization:**
- `objective_score`, `optimization_time_ms`, `optimization_iterations`, `optimality_gap_estimate`

**Mission Impact:**
- `affected_zones`

### 3. Dashboard Bridge

**File:** [gcs/dashboard_bridge.py](gcs/dashboard_bridge.py)

#### Updated Event Notification (Lines 77-108)

Extended `notify_ooda_event()` method signature to accept metrics:

```python
def notify_ooda_event(self, event_message: str, is_critical: bool = False,
                      phase: str = None, uav_id: int = None,
                      cycle_num: int = None, duration_ms: float = None,
                      details: dict = None, metrics: dict = None):
```

The metrics are now properly forwarded to connected dashboard clients via Socket.IO.

### 4. Web Dashboard Backend (Optional)

**File:** [visualization/web_dashboard.py](visualization/web_dashboard.py)

#### Enhanced emit_ooda Function (Lines 2291-2321)

Updated to accept and forward metrics:

```python
def emit_ooda(phase, message, critical=False, cycle_num=None,
              duration_ms=None, details=None, metrics=None):
```

## Data Flow

```
OODA Engine (_decide_phase)
    ↓ [calls with metrics dict]
Dashboard Bridge (notify_ooda_event)
    ↓ [Socket.IO emit]
Web Dashboard Backend (emit_ooda)
    ↓ [WebSocket]
Browser (socket.on('ooda_event'))
    ↓ [calls if e.metrics]
updateEnhancedOodaMetrics()
    ↓ [updates DOM]
Visual Display in Browser
```

## Visual Layout

The OODA Loop Monitor now displays metrics in this order:

1. **Cycle Count** (centered, large)
2. **Cycle Timing Metrics** (last, avg, min, max)
3. **Phase Averages** (Observe, Orient, Decide, Act)
4. **Decision Quality** ✨ NEW
5. **Fleet Status** ✨ NEW
6. **Optimization** ✨ NEW
7. **Sequential OODA Steps** (visual phase indicators)
8. **Status Bar** (IDLE/ACTIVE)
9. **Recent Events Log**

## Testing

All existing tests pass:
```bash
$ uv run pytest tests/integration/ -k ooda
======================= 2 passed in 0.05s =======================
```

## Usage

When the system executes an OODA cycle:

1. The OODA engine collects comprehensive metrics during the DECIDE phase
2. Metrics are sent to the dashboard in real-time via WebSocket
3. The dashboard automatically updates all metric displays
4. Operators can monitor:
   - How effectively tasks are being recovered
   - Current fleet capacity and constraints
   - Optimization performance and quality
   - Decision-making speed and efficiency

## Benefits

- **Real-time Visibility**: Operators see detailed metrics as decisions are made
- **Decision Quality Insight**: Track recovery rates and coverage impact
- **Resource Awareness**: Monitor battery and payload capacity in real-time
- **Optimization Transparency**: See how quickly and effectively the system optimizes
- **Performance Monitoring**: Track cycle times and phase breakdown
- **Troubleshooting**: Identify bottlenecks or constraint violations quickly

## Backward Compatibility

All changes are fully backward compatible:
- Existing code continues to work without modification
- Metrics parameter is optional (defaults to None)
- Dashboard gracefully handles missing metrics
- No breaking changes to APIs or data structures

## Future Enhancements

Potential additions:
- Historical metrics graphs (time-series visualization)
- Aggregate statistics over multiple cycles
- Threshold-based alerts (e.g., low recovery rate warnings)
- Export metrics to CSV/JSON for offline analysis
- Comparison between different mission types
