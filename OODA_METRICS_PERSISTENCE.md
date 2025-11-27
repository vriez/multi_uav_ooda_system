# OODA Metrics Persistence

## Overview

The OODA Loop Monitor dashboard now displays metrics **persistently throughout the simulation runtime**. Once metrics are generated during an OODA cycle, they remain visible in the dashboard until updated by subsequent cycles or the server is restarted.

## Key Features

### 1. Persistent Storage

Metrics are stored in the backend (`web_dashboard.py`) when emitted:

```python
# Global storage (in visualization/web_dashboard.py)
latest_ooda_metrics = None      # Stores last metric values
latest_ooda_timestamp = None    # Timestamp of last update

# Storage occurs in emit_ooda() when metrics are provided
if metrics is not None:
    event_data['metrics'] = metrics
    latest_ooda_metrics = metrics.copy()
    latest_ooda_timestamp = time.time()
```

### 2. New Client Restoration

When a dashboard client connects (or refreshes), stored metrics are automatically sent:

```python
@socketio.on('connect')
def handle_connect():
    # ... send initial telemetry ...

    # Restore latest OODA metrics if available
    if latest_ooda_metrics is not None:
        emit('ooda_event', {
            'phase': 'restore',
            'message': 'Restored latest OODA metrics',
            'metrics': latest_ooda_metrics,
            'timestamp': latest_ooda_timestamp
        })
```

### 3. Display Persistence

The dashboard HTML only updates metrics when new values arrive - it does NOT reset them to "-" between cycles:

```javascript
// metrics persist in DOM until updated
if (e.metrics) {
    updateEnhancedOodaMetrics(e.metrics);  // Only updates provided values
}
```

## Behavior Summary

| Scenario | Metric Display Behavior |
|----------|------------------------|
| **Before first OODA cycle** | Shows "-" (no data yet) |
| **After first OODA cycle** | Shows real values (e.g., "100.0%", "2/2") |
| **Between OODA cycles** | **Retains last values** (does NOT reset to "-") |
| **During subsequent cycles** | Updates to new values |
| **Dashboard refresh** | **Restores last values** (persists across refreshes) |
| **Server restart** | Resets to "-" (fresh start) |

## Example Timeline

```
Time    Event                           Dashboard Display
────────────────────────────────────────────────────────────
0.0s    Dashboard starts                All metrics: "-"
5.0s    UAV 1 fails
5.5s    OODA cycle completes            Recovery Rate: 100.0%
                                        Tasks Recovered: 2/2
                                        Coverage Loss: 12.5%
                                        (all metrics populate)

10.0s   Normal operations               Metrics STILL SHOW:
20.0s   (no failures)                   Recovery Rate: 100.0%
30.0s                                   Tasks Recovered: 2/2
                                        (values persist!)

35.0s   User refreshes dashboard        Metrics RESTORED:
                                        Recovery Rate: 100.0%
                                        (backend resends values)

45.0s   UAV 3 fails
45.5s   OODA cycle completes            Metrics UPDATE:
                                        Recovery Rate: 95.0%
                                        Tasks Recovered: 3/3
```

## Persistence Lifecycle

### Data Flow During OODA Cycle

```
OODA Engine (_decide_phase)
    ↓ [generates comprehensive metrics]
Dashboard Bridge (notify_ooda_event)
    ↓ [forwards via Socket.IO]
Web Dashboard Backend (emit_ooda)
    ↓ [stores in latest_ooda_metrics]
    ↓ [emits to all connected clients]
Browser JavaScript (socket.on('ooda_event'))
    ↓ [calls updateEnhancedOodaMetrics()]
Dashboard Display
    ✓ [metrics visible to operator]
```

### Persistence Across Refreshes

```
User refreshes browser
    ↓
Browser reconnects to server
    ↓
handle_connect() triggered
    ↓
Checks if latest_ooda_metrics exists
    ↓ [if yes]
Emits 'ooda_event' with phase='restore'
    ↓
Browser receives and displays metrics
    ✓ [user sees same metrics before refresh]
```

## What Metrics Persist?

All **enhanced OODA metrics** persist:

### Decision Quality
- `recovery_rate` - % of lost tasks recovered
- `tasks_recovered` - Number of tasks reallocated
- `tasks_lost` - Total tasks lost
- `coverage_loss` - Mission coverage impact (%)
- `objective_score` - Optimization quality

### Fleet Status
- `operational_uavs` - Active UAV count
- `failed_uavs` - Failed UAV count
- `battery_spare` - Available battery capacity (Wh)
- `payload_spare` - Available payload capacity (kg)

### Optimization Performance
- `optimization_time_ms` - Solver execution time
- `optimization_iterations` - Local search iterations
- `optimality_gap_estimate` - Distance from optimal (%)

### Other Metrics
- `temporal_margin` - Time buffer (seconds)
- `recoverable_tasks` - Tasks within constraints
- `affected_zones` - Number of zones impacted

## What Does NOT Persist?

The following are **NOT** persisted (intentional design):

1. **OODA Cycle Timing Metrics** - Reset on mission start
   - Last/Avg/Min/Max cycle times
   - Phase timing averages

2. **Event Log** - Cleared on simulation clear

3. **Mission Metrics** - Reset on new mission
   - Targets found, deliveries completed, etc.

## Testing Persistence

### Manual Test

1. **Start dashboard:**
   ```bash
   make dash
   ```

2. **In another terminal, start a mission:**
   ```bash
   make gui  # or make launch
   ```

3. **Trigger a failure:**
   - Wait for a UAV to fail naturally (battery depletion)
   - OR manually fail a UAV via dashboard controls

4. **Observe metrics populate:**
   - All enhanced metrics should show real values

5. **Wait (no more failures):**
   - Metrics should REMAIN visible (not reset to "-")

6. **Refresh the dashboard:**
   - Metrics should RESTORE to same values

### Automated Test

```bash
python test_metrics_persistence.py
```

This test verifies:
- [PASS] Metrics stored when OODA event emitted
- [PASS] Metrics sent to new clients on connection
- [PASS] Metrics update with subsequent cycles
- [PASS] Metrics persist when non-metric events occur

## Implementation Files

| File | Changes Made |
|------|-------------|
| [visualization/web_dashboard.py](visualization/web_dashboard.py) | Added `latest_ooda_metrics` and `latest_ooda_timestamp` global storage (lines 219-220)<br>Modified `emit_ooda()` to store metrics (lines 2308-2326)<br>Enhanced `handle_connect()` to restore metrics (lines 2344-2354) |
| [visualization/templates/dashboard.html](visualization/templates/dashboard.html) | No changes needed - already handles persistence correctly |
| [gcs/dashboard_bridge.py](gcs/dashboard_bridge.py) | Already forwards metrics from OODA engine (lines 77-108) |
| [gcs/ooda_engine.py](gcs/ooda_engine.py) | Already generates comprehensive metrics (line 458) |

## Benefits

### For Operators
- **Continuous Visibility**: Always see the last decision quality, even during normal operations
- **No Data Loss**: Metrics survive dashboard refreshes
- **Historical Context**: Understand the last recovery action at any time

### For Development
- **Easier Debugging**: Metrics remain visible for analysis
- **Better Testing**: Can verify metric accuracy without timing constraints
- **Clearer State**: Dashboard always reflects last known OODA state

## Configuration

No configuration needed - persistence is automatic and always enabled.

To **disable persistence** (return to ephemeral behavior), modify:

```python
# In visualization/web_dashboard.py, comment out storage:
# if metrics is not None:
#     event_data['metrics'] = metrics
#     # latest_ooda_metrics = metrics.copy()  # DISABLED
#     # latest_ooda_timestamp = time.time()    # DISABLED
```

## Backward Compatibility

**Fully backward compatible**:
- Existing code continues to work without modification
- If metrics are not provided, nothing is stored (graceful degradation)
- Old dashboards connecting to new backend receive metrics seamlessly
- No breaking changes to APIs or protocols

## Future Enhancements

Potential improvements:

1. **Metric History**: Store last N metric snapshots for trend analysis
2. **Persistence to Disk**: Survive server restarts (optional config)
3. **Metric Staleness Indicator**: Show age of displayed metrics
4. **Selective Persistence**: Allow operators to "pin" specific metric snapshots
5. **Export to CSV**: Download metric history for offline analysis

## Summary

**OODA metrics now persist throughout the simulation runtime**, providing operators with continuous visibility into decision quality, fleet status, and optimization performance. Metrics remain visible between OODA cycles and survive dashboard refreshes, ensuring operators always have context about the system's last autonomous decision.
