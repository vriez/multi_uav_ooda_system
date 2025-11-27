# Constraint-Aware Fault-Tolerant Multi-Agent UAV System

Interactive OODA loop demonstration platform for autonomous fleet management.

## Quick Start

### With uv (Recommended - Fast!)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (100x faster than pip!)
uv sync

# Run the dashboard
uv run run_dashboard.py
# Or even shorter:
make dash
```

### With pip (Traditional)

```bash
pip install -r requirements.txt
python run_dashboard.py
```

Open browser: **http://localhost:8085**

## How to Use

1. **Select Scenario** - Choose from Surveillance, Search & Rescue, or Delivery
2. **Start Mission** - Press "Start Mission" to launch UAVs
3. **Inject Failure** - Click failure buttons OR click any UAV on map
4. **Watch OODA** - See real-time task reallocation

## Features

- **3 Mission Scenarios** with different fleet sizes and tasks
- **Playback Controls** - Start/Pause/Stop mission execution
- **Failure Injection** - Battery, GPS, Comm, Motor failures
- **Interactive Map** - Click UAVs to fail them
- **Live Stats** - Fleet status, completion, OODA cycles
- **Event Log** - Real-time OODA loop decisions

## Mission Scenarios

**Surveillance**: 5 UAVs covering 8 surveillance zones  
**Search & Rescue**: 4 UAVs, 3 priority zones, time-critical  
**Medical Delivery**: 6 UAVs, 10 deliveries, payload constraints

## What You'll See

When you inject a failure:
1. UAV turns red and stops
2. OODA event: "UAV X FAILED"
3. OODA Cycle triggers
4. Tasks reallocated to operational UAVs
5. Fleet continues mission

## Full System (Advanced)

For complete GCS + UAV simulation:

```bash
make gui
# or: uv run launch_with_gui.py
# or: python launch_with_gui.py
```

This runs the full backend with realistic physics, battery models, and distributed UAV processes.

## Quick Command Reference

| Command | What It Does | Speed |
|---------|-------------|-------|
| `make dash` | Dashboard only (demo mode) | Fastest |
| `make gui` | Full system with GUI | Fast |
| `make launch` | Full system (programmatic) | Fast |
| `make gcs` | GCS only | Fast |
| `make test` | Run test suite | - |
| `make help` | Show all commands | - |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Ground Control Station                      │
│  ┌────────────┐  ┌──────────┐  ┌─────────────────────────┐ │
│  │ OODA Engine│  │  Fleet   │  │  Mission Manager        │ │
│  │  Observe   │◄─┤ Monitor  │◄─┤  Task Database          │ │
│  │  Orient    │  │          │  │  Constraint Validator   │ │
│  │  Decide    │  │ Failure  │  └─────────────────────────┘ │
│  │  Act       │──┤ Detection│                               │
│  └────────────┘  └──────────┘                               │
└─────────────────────────┬───────────────────────────────────┘
                          │ TCP/IP (JSON-RPC)
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────▼─────┐    ┌────▼─────┐    ┌────▼─────┐
    │  UAV 1   │    │  UAV 2   │    │  UAV 3   │
    │ Dynamics │    │ Dynamics │    │ Dynamics │
    │ Control  │    │ Control  │    │ Control  │
    │ Sensors  │    │ Sensors  │    │ Sensors  │
    └──────────┘    └──────────┘    └──────────┘
```

## Quick Start

### Installation

**With uv (Recommended):**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies with lockfile (reproducible builds)
uv sync

# Or install with development tools
uv sync --group dev

# Verify structure
ls -la gcs/ uav/ config/ missions/
```

**With pip (Traditional):**
```bash
# Install dependencies
pip install -r requirements.txt

# Verify structure
ls -la gcs/ uav/ config/ missions/
```

### Running the System

**Option 1: Quick Commands (Shortest)**
```bash
make gui        # Launch with GUI (full system)
make dash       # Dashboard only (fastest demo)
make launch     # Full system programmatic
make gcs        # GCS only
```

**Option 2: uv Commands**
```bash
# Launch with GUI
uv run launch_with_gui.py

# Dashboard only
uv run run_dashboard.py

# Full system
uv run launch.py

# Or with traditional python
python launch.py  # (if dependencies installed)
```

**Option 3: Manual Launch (Multiple Terminals)**

Terminal 1 (GCS):
```bash
uv run python -m gcs.main
# or: make gcs
```

Terminal 2-6 (UAVs):
```bash
uv run python -m uav.client 1 0 0 10
uv run python -m uav.client 2 20 0 10
uv run python -m uav.client 3 40 0 10
uv run python -m uav.client 4 0 20 10
uv run python -m uav.client 5 20 20 10
```

### Testing Failure Response

To inject a failure and observe OODA loop response:
1. Kill a UAV process (Ctrl+C on UAV terminal)
2. Watch GCS detect failure and execute OODA cycle
3. Observe task reallocation to remaining UAVs

## System Components

### Ground Control Station (`gcs/`)
- `main.py` - Main GCS controller
- `ooda_engine.py` - Four-phase OODA decision cycle
- `fleet_monitor.py` - Telemetry collection & failure detection
- `constraint_validator.py` - Battery/payload/time verification
- `mission_manager.py` - Task database & assignment

### UAV Simulation (`uav/`)
- `client.py` - GCS communication client
- `simulation.py` - 6-DOF dynamics & PID control

### Configuration (`config/`)
- `gcs_config.yaml` - GCS parameters
- `uav_config.yaml` - UAV dynamics & control gains

### Missions (`missions/`)
- `test_scenario.yaml` - Sample mission with 8 tasks

## Configuration

### Key GCS Parameters
```yaml
ooda_engine:
  telemetry_rate_hz: 2.0          # Fleet polling rate
  timeout_threshold_sec: 1.5       # Communication timeout
  
constraints:
  battery_safety_reserve_percent: 20.0
  
collision_avoidance:
  safety_buffer_meters: 15.0
```

### Key UAV Parameters
```yaml
dynamics:
  mass_kg: 1.5
  arm_length_m: 0.225
  
battery:
  capacity_wh: 100.0
  efficiency_m_per_wh: 150.0
  
control:
  position_gains: [2.0, 2.0, 5.0]
```

## Mission Scenarios

Create custom missions in `missions/`:

```yaml
tasks:
  - type: surveillance
    position: [50, 50, 20]
    priority: 80
    zone_id: 1
    duration_sec: 120
    
  - type: delivery
    position: [100, 80, 10]
    priority: 85
    payload_kg: 2.5
    deadline: 900
```

## Features Implemented

**OODA Loop Engine**
- Observe: Fleet state aggregation
- Orient: Mission impact analysis
- Decide: Recovery strategy selection
- Act: Task reallocation dispatch

**Multi-Modal Failure Detection**
- Communication timeout (1.5s)
- Battery anomaly detection
- Position discontinuity
- Altitude violations

**Constraint-Aware Allocation**
- Battery capacity verification
- Payload constraint checking
- Temporal deadline validation
- Collision avoidance (15m buffer)

**UAV Simulation**
- Quaternion-based 6-DOF dynamics
- Cascade PID control
- Battery discharge modeling
- GPS/IMU sensor simulation

## Performance Metrics

The system logs:
- OODA cycle execution time (target: <6s)
- Phase breakdowns (Observe/Orient/Decide/Act)
- Recovery success rate
- Fleet utilization

## Architecture Details

### Communication Protocol
- TCP/IP with JSON-RPC 2.0
- 2 Hz bidirectional telemetry
- Asynchronous command dispatch

### State Management
- Centralized mission database
- Distributed UAV simulations
- Eventual consistency model

### Failure Modes Supported
- Communication loss
- Battery depletion
- GPS anomalies
- Motor failures (simulated)

## Extending the System

### Adding New Mission Types
1. Extend `TaskType` enum in `mission_manager.py`
2. Update constraint validation logic
3. Create mission scenario YAML

### Custom Failure Injection
Modify `UAVSimulation` to inject:
- Battery failures
- GPS errors
- Communication drops
- Motor degradation

### Advanced Controllers
Implement in `uav/simulation.py`:
- Trajectory following
- Obstacle avoidance
- Formation control

## Troubleshooting

**UAVs won't connect:**
- Check GCS is running first
- Verify port 5555 is available: `lsof -i :5555`
- Check `gcs_config.yaml` host/port settings
- Ensure firewall allows local connections

**OODA cycle not triggering:**
- Verify failure detection thresholds in `gcs_config.yaml`
- Check telemetry rate configuration (default: 2 Hz)
- Enable DEBUG logging: `LOG_LEVEL=DEBUG python launch.py`
- Confirm UAV has active tasks assigned

**Battery depleting too fast:**
- Adjust `battery.efficiency_m_per_wh` in `uav_config.yaml` (default: 150)
- Reduce mission distance/duration
- Lower control gains (less aggressive maneuvers)

**UAVs disappear during SAR mission:**
- Check grid boundary settings in `gcs_config.yaml`
- Verify SAR zone coordinates are within grid bounds
- UAVs outside grid without `out_of_grid` permission will be rejected
- See `constraint_validator.py` for boundary checking logic

**UAV not turning red on failure:**
- Ensure dashboard bridge is connected
- Check browser console for WebSocket errors
- Verify failure callbacks are registered in FleetMonitor
- Dashboard updates require SocketIO connection

**Tasks not being reallocated:**
- Check constraint validator logs for rejection reasons
- Verify remaining UAVs have sufficient battery
- Ensure tasks are within operational grid
- Check payload constraints for delivery missions

**High OODA cycle latency (>3s):**
- Reduce `max_local_search_iterations` in mission context
- Lower `optimization_budget_ms` parameter
- Check for network latency in telemetry polling
- Consider reducing fleet size for faster optimization

**Dashboard not loading:**
- Verify Flask server is running on port 8085
- Check for port conflicts: `lsof -i :8085`
- Clear browser cache and reload
- Check Flask logs for startup errors

For detailed configuration options, see [docs/configuration.md](docs/configuration.md).

## Documentation

Detailed documentation is available in the `docs/` directory:

| Document | Description |
|----------|-------------|
| [Configuration Guide](docs/configuration.md) | All configurable parameters |
| [Architecture](docs/architecture.md) | System design and data flow |
| [Algorithms](docs/algorithms.md) | OODA algorithms and optimization |
| [Testing Guide](docs/testing.md) | Running and writing tests |
| [Contributing](CONTRIBUTING.md) | Development workflow |

## Development Status

**Completed:**
- Core OODA engine
- Fleet monitoring
- Constraint validation
- UAV simulation
- Mission management
- TCP/IP communication
- Web dashboard

**Future Work:**
- Unity visualization client
- Advanced path planning (TSP)
- Real hardware integration
- Multi-GCS coordination

## References

Based on thesis: "Constraint-Aware Fault-Tolerant Control for Multi-Agent UAV Systems"

Quadcopter dynamics adapted from: [bobzwik/Quadcopter_SimCon](https://github.com/bobzwik/Quadcopter_SimCon)

## Author

**Vítor Eulálio Reis** - [vitor.ereis@proton.me](mailto:vitor.ereis@proton.me)

Developed as part of the Specialization in Aeronautical Systems at the School of Engineering of São Carlos, University of São Paulo (EESC-USP).

## License

See project specifications document.
