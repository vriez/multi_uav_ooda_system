# OODA Metrics Display Behavior

## When Metrics Appear

The OODA Loop Monitor displays different metrics at different times:

### Always Updated (Real-Time)
These update continuously from telemetry, even when no OODA cycle is running:

[PASS] **Fleet Status Section:**
- **Operational UAVs** - Updates every telemetry cycle (~0.5s)
- **Failed UAVs** - Updates every telemetry cycle (~0.5s)

### Updated Only During OODA Cycles
These metrics **only appear when an OODA cycle runs** (i.e., when a UAV fails and triggers recovery):

🔄 **Decision Quality Section:**
- **Recovery Rate** - Calculated during DECIDE phase
- **Tasks Recovered** - Number of tasks successfully reallocated
- **Coverage Loss** - Mission coverage lost due to failure
- **Objective Score** - Optimization quality metric

🔄 **Fleet Status Section (Advanced):**
- **Battery Spare** - Calculated during ORIENT phase (spare capacity analysis)
- **Payload Spare** - Calculated during ORIENT phase

🔄 **Optimization Section:**
- **Opt. Time** - Time spent in optimization algorithm
- **Iterations** - Number of local search iterations
- **Optimality Gap** - Distance from theoretical optimum

## Why This Behavior?

This is **intentional and correct** because:

1. **No OODA Cycle = No Decision Metrics**
   - When the system is running normally (no failures), there's no decision being made
   - Metrics like "recovery rate" and "objective score" don't exist until a recovery is attempted

2. **Battery/Payload Spare Requires Analysis**
   - These aren't simple telemetry values - they require analyzing:
     - Current battery levels
     - Committed tasks and their energy requirements
     - Safety reserves (20% battery margin)
     - Available payload capacity after current assignments
   - This analysis only happens during the ORIENT phase of an OODA cycle

3. **Optimization Metrics Only Exist During Optimization**
   - When no failure occurs, no optimization runs
   - These metrics are meaningless outside of an active DECIDE phase

## How to See the Metrics

### Option 1: Wait for a Natural Failure
- Run a mission normally
- When a UAV's battery gets low or a failure occurs
- The OODA loop will trigger automatically
- All metrics will populate

### Option 2: Trigger a Manual Failure (for testing)
- Start a mission with the dashboard
- Use the dashboard controls to manually fail a UAV
- The OODA cycle will trigger
- Metrics will appear immediately

### Option 3: Run the Experiments
```bash
make experiments
```
This will execute test scenarios with simulated failures and you'll see all metrics in action.

## Display States

### Before First OODA Cycle
```
DECISION QUALITY
├─ Recovery Rate:     -
├─ Tasks Recovered:   -
├─ Coverage Loss:     -
└─ Objective Score:   -

FLEET STATUS
├─ Operational:       5  ← Real-time
├─ Failed:            0  ← Real-time
├─ Battery Spare:     -
└─ Payload Spare:     -

OPTIMIZATION
├─ Opt. Time:         -
├─ Iterations:        -
└─ Optimality Gap:    -
```

### After OODA Cycle Runs
```
DECISION QUALITY
├─ Recovery Rate:     100.0%
├─ Tasks Recovered:   2/2
├─ Coverage Loss:     12.5%
└─ Objective Score:   0.505

FLEET STATUS
├─ Operational:       3
├─ Failed:            2
├─ Battery Spare:     115.0 Wh
└─ Payload Spare:     0.0 kg

OPTIMIZATION
├─ Opt. Time:         0.26ms
├─ Iterations:        2
└─ Optimality Gap:    0.00%
```

## Technical Details

### Data Flow

**Real-time Telemetry (every ~0.5s):**
```
Web Dashboard → socket.on('update') → Updates Operational/Failed counts
```

**OODA Event (only on failure):**
```
UAV Failure Detected
    ↓
OODA Engine Triggered
    ↓ (Observe phase)
Fleet telemetry collected
    ↓ (Orient phase)
Battery/Payload spare calculated
    ↓ (Decide phase)
Recovery planned, metrics generated
    ↓ (Act phase)
Decision executed
    ↓
Dashboard Bridge → socket.emit('ooda_event', {metrics: {...}})
    ↓
Browser → socket.on('ooda_event') → updateEnhancedOodaMetrics()
    ↓
All metrics displayed ✅
```

## Verifying It Works

1. **Start the dashboard:**
   ```bash
   make dash
   ```

2. **In another terminal, run experiments:**
   ```bash
   make experiments
   ```

3. **Watch the OODA Monitor:**
   - Initially shows "-" for most metrics (correct!)
   - When experiment triggers failures, metrics populate
   - Values update in real-time during OODA cycles

## Summary

**This is not a bug** - it's the expected behavior:
- [PASS] Fleet status (operational/failed) updates continuously
- [PASS] Decision metrics appear only when decisions are made
- [PASS] Optimization metrics appear only when optimization runs
- [PASS] Display shows "-" when data isn't available yet

The metrics **will** populate as soon as the first OODA cycle runs!
