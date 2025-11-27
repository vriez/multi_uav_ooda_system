# Quick Start: Seeing OODA Metrics Populate

## Current Situation

You're seeing "-" for metrics because **no OODA cycle has run yet**. This is correct behavior!

```
Operational: 2    ← UAVs are working fine
Failed: 0         ← No failures = No OODA cycle needed
```

The metrics will populate as soon as an OODA cycle triggers.

## How to Trigger OODA Cycle & See Metrics

### Method 1: Use Dashboard Controls (Easiest)

If your dashboard has manual failure controls:

1. **Open dashboard**: http://localhost:8085
2. **Find UAV controls**: Look for "Manual Controls" or "UAV Actions"
3. **Fail a UAV**: Click "Fail UAV" or similar button
4. **Watch metrics populate**: All "-" will change to real values

### Method 2: Run Full System with Automatic Failures

**Terminal 1** (if not already running):
```bash
make dash
```

**Terminal 2**:
```bash
make gui
# or
make launch
```

**What happens**:
- Mission starts with UAVs
- UAVs execute tasks
- Eventually a UAV will fail (battery low or simulated)
- OODA cycle triggers automatically
- **Dashboard metrics populate**

### Method 3: Run Experiments (Guaranteed OODA Cycles)

```bash
# Keep dashboard running in Terminal 1
make dash

# In Terminal 2, run experiments
make experiments
```

**Note**: Experiments create their own OODA engines, so metrics won't show in dashboard. Use Method 1 or 2 instead.

### Method 4: Use Demo Script (Programmatic)

```bash
# Terminal 1: Start GCS
make gcs

# Terminal 2: Start Dashboard
make dash

# Terminal 3: Trigger OODA cycle
python trigger_ooda_demo.py
```

This will:
1. Start a mission
2. Fail a UAV programmatically
3. Trigger OODA cycle
4. Metrics populate in dashboard

## What You'll See After OODA Triggers

### Before (Current State)
```
DECISION QUALITY
├─ Recovery Rate:     -
├─ Tasks Recovered:   -
├─ Coverage Loss:     -
└─ Objective Score:   -

FLEET STATUS
├─ Operational:       2
├─ Failed:            0
├─ Battery Spare:     -
└─ Payload Spare:     -
```

### After (OODA Cycle Runs)
```
DECISION QUALITY
├─ Recovery Rate:     100.0%  ✅
├─ Tasks Recovered:   2/2     ✅
├─ Coverage Loss:     12.5%   ✅
└─ Objective Score:   0.505   ✅

FLEET STATUS
├─ Operational:       2       ✅
├─ Failed:            1       ✅
├─ Battery Spare:     115.0 Wh ✅
└─ Payload Spare:     0.0 kg  ✅
```

## Testing Persistence

Once metrics populate:

1. **Wait** (don't do anything for 30 seconds)
   - Metrics should **remain visible** (not reset to "-")

2. **Refresh dashboard** (press F5)
   - Metrics should **restore** to same values

3. **Trigger another failure**
   - Metrics should **update** to new values

## Why Metrics Show "-" Initially

This is **correct and expected**:

| Condition | Display | Reason |
|-----------|---------|--------|
| No OODA cycles yet | "-" | No data available |
| OODA cycle runs | Real values | Metrics generated |
| Normal operations | Persists | Last values retained |
| Dashboard refresh | Restored | Backend resends |
| Server restart | "-" | Fresh start |

## Common Questions

**Q: Why aren't metrics showing?**
A: No OODA cycle has run yet. Trigger a failure or wait for natural battery depletion.

**Q: I ran experiments but dashboard shows "-"**
A: Experiments run standalone without dashboard connection. Use Method 1 or 2 instead.

**Q: How long until a natural failure?**
A: Depends on battery drain rate. Usually 30-60 seconds of mission runtime.

**Q: Can I force a failure immediately?**
A: Yes! Use dashboard controls or the demo script ([trigger_ooda_demo.py](trigger_ooda_demo.py)).

## Recommended Workflow

**Best way to see metrics**:

```bash
# Terminal 1
make dash

# Terminal 2
make gui
```

Then in the GUI window:
- Watch UAVs execute mission
- Wait for a UAV to fail (or manually trigger)
- Dashboard metrics will populate automatically
- Metrics persist throughout mission

## Summary

The implementation is working correctly! You're seeing "-" because:

✅ **No UAV has failed** → No OODA cycle needed → No metrics generated yet
✅ **Once a failure occurs** → OODA cycle runs → Metrics populate
✅ **Metrics will persist** → Between cycles and across refreshes

Just trigger any failure to see the metrics in action!
