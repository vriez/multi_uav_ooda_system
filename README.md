# Constraint-Aware Fault-Tolerant Multi-Agent UAV System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-169%20passed-brightgreen.svg)](#testing)
[![License](https://img.shields.io/badge/license-Academic-lightgrey.svg)](#license)

> **OODA loop demonstration platform for autonomous drone fleet management with real-time failure recovery.**

<p align="center">
  <img src="docs/images/dashboard_screenshot.png" alt="Dashboard Screenshot" width="600">
</p>

## Quick Start

```bash
# 1. Clone and enter directory
git clone https://github.com/vriez/uav_system.git
cd uav_system

# 2. Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install dependencies
uv sync

# 4. Run the dashboard
make dash
```

**Open browser:** http://localhost:8085

---

## System Architecture

```mermaid
flowchart TB
    subgraph GCS["Ground Control Station (Port 5555)"]
        FM[Fleet Monitor<br/>2 Hz Telemetry]
        OODA[OODA Engine]
        MM[Mission Manager]
        CV[Constraint Validator]

        FM --> OODA
        OODA --> MM
        MM --> CV
        CV --> OODA
    end

    subgraph Dashboard["Web Dashboard (Port 8085)"]
        FLASK[Flask + SocketIO]
        MAP[Interactive Map]
        LOG[Event Log]
    end

    subgraph Fleet["UAV Fleet"]
        UAV1[UAV 1<br/>6-DOF Dynamics]
        UAV2[UAV 2<br/>6-DOF Dynamics]
        UAV3[UAV 3<br/>6-DOF Dynamics]
        UAV4[...]
    end

    GCS <-->|TCP/IP JSON-RPC| Fleet
    GCS -->|WebSocket| Dashboard
```

## OODA Loop Decision Cycle

When a UAV failure is detected, the system executes a four-phase decision cycle:

```mermaid
flowchart LR
    O[OBSERVE<br/>Collect Telemetry] --> OR[ORIENT<br/>Analyze Impact]
    OR --> D[DECIDE<br/>Optimize Allocation]
    D --> A[ACT<br/>Dispatch Commands]
    A -.->|Next Cycle| O

    style O fill:#e1f5fe
    style OR fill:#fff3e0
    style D fill:#f3e5f5
    style A fill:#e8f5e9
```

| Phase | Duration | Actions |
|-------|----------|---------|
| **Observe** | ~0.3ms | Aggregate fleet telemetry, detect anomalies |
| **Orient** | ~0.3ms | Assess mission impact, identify affected tasks |
| **Decide** | ~0.4ms | Greedy allocation + local search optimization |
| **Act** | ~0.2ms | Dispatch task updates to operational UAVs |

**Total cycle time: 0.2-1.2 milliseconds** (~4,000× faster than human reaction)

---

## Mission Scenarios

```mermaid
graph TD
    subgraph S["Surveillance"]
        S1[5 UAVs]
        S2[9 Patrol Zones]
        S3[3x3 Grid - 120m x 120m]
    end

    subgraph R["Search & Rescue"]
        R1[5 UAVs]
        R2[9 Search Zones]
        R3[Golden Hour Constraint]
    end

    subgraph D["Medical Delivery"]
        D1[3 UAVs]
        D2[5 Packages]
        D3[Payload Constraints]
    end
```

| Scenario | Fleet | Tasks | Key Constraint |
|----------|-------|-------|----------------|
| **Surveillance** | 5 UAVs | 9 zones | Zone contiguity |
| **Search & Rescue** | 5 UAVs | 9 zones | Time-critical (golden hour) |
| **Medical Delivery** | 3 UAVs | 5 packages | Payload capacity (kg) |

---

## Failure Detection & Recovery

```mermaid
sequenceDiagram
    participant UAV as UAV Fleet
    participant FM as Fleet Monitor
    participant OODA as OODA Engine
    participant MM as Mission Manager

    UAV->>FM: Telemetry (2 Hz)
    Note over FM: Detect: Timeout > 1.5s
    FM->>OODA: UAV-3 FAILED

    rect rgb(255, 240, 240)
        Note over OODA: OODA Cycle Triggered
        OODA->>OODA: Observe fleet state
        OODA->>OODA: Orient: 3 tasks orphaned
        OODA->>MM: Request reallocation
        MM->>OODA: Optimized assignment
        OODA->>UAV: Dispatch to UAV-1, UAV-2
    end

    UAV->>FM: Acknowledge new tasks
```

### Failure Modes Detected

| Mode | Detection Method | Threshold |
|------|------------------|-----------|
| **Communication Loss** | Heartbeat timeout | > 1.5 seconds |
| **Battery Anomaly** | Discharge rate spike | > 5% per 30s |
| **Position Jump** | GPS discontinuity | > 100m sudden move |
| **Altitude Violation** | Boundary check | > 50m deviation |

---

## Reproducibility Guide

### Prerequisites

- **Python 3.11+**
- **uv** (recommended) or pip
- **Git**

### Step-by-Step Setup

```bash
# Clone repository
git clone https://github.com/vriez/uav_system.git
cd uav_system

# Option A: Using uv (recommended - 100x faster)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Option B: Using pip
pip install -r requirements.txt
```

### Verify Installation

```bash
# Run test suite (169 tests, ~0.22s)
make test

# Expected output:
# ==================== 169 passed in 0.22s ====================
```

### Run Experiments

```bash
# Run all baseline comparison experiments
make experiments

# Or run individually
uv run python run_experiments.py
```

### Launch Modes

| Command | Description | Use Case |
|---------|-------------|----------|
| `make dash` | Dashboard only | Quick demo, presentations |
| `make gui` | Full system + GUI | Development, testing |
| `make launch` | Full system (headless) | Automation, CI/CD |
| `make gcs` | GCS server only | Manual UAV connection |

---

## Project Structure

```
uav_system/
├── gcs/                    # Ground Control Station
│   ├── ooda_engine.py      # Core OODA loop implementation
│   ├── fleet_monitor.py    # Telemetry & failure detection
│   ├── constraint_validator.py
│   └── mission_manager.py
├── uav/                    # UAV Simulation
│   ├── simulation.py       # 6-DOF dynamics, PID control
│   └── client.py           # GCS communication
├── visualization/          # Web Dashboard
│   └── web_dashboard.py    # Flask + SocketIO
├── config/                 # Configuration
│   ├── gcs_config.yaml     # OODA parameters
│   └── uav_config.yaml     # UAV dynamics
├── missions/               # Mission definitions
│   └── test_scenario.yaml
├── tests/                  # Test suite (169 tests)
│   ├── unit/
│   ├── integration/
│   └── regression/
└── docs/                   # Documentation
```

---

## Key Configuration Parameters

### GCS (`config/gcs_config.yaml`)

```yaml
ooda_engine:
  telemetry_rate_hz: 2.0          # Fleet polling frequency
  timeout_threshold_sec: 1.5       # Failure detection threshold

constraints:
  battery_safety_reserve_percent: 20.0

collision_avoidance:
  safety_buffer_meters: 15.0
```

### UAV (`config/uav_config.yaml`)

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

---

## Testing

```bash
# Full test suite
make test

# By category
make test-unit         # 53 unit tests
make test-integration  # 81 integration tests
make test-regression   # 15 regression tests

# With coverage report
make test-coverage

# Specific tests
uv run pytest -k "battery"
uv run pytest tests/integration/ -k "surveillance" -vv
```

---

## Constraint Validation Flow

```mermaid
flowchart TD
    START[Task Assignment Request] --> B{Battery Check}
    B -->|Insufficient| REJECT1[REJECT: Low Battery]
    B -->|OK| P{Payload Check}
    P -->|Overweight| REJECT2[REJECT: Payload Exceeded]
    P -->|OK| G{Grid Boundary}
    G -->|Outside + No Permission| REJECT3[REJECT: Out of Bounds]
    G -->|OK or Permitted| C{Collision Check}
    C -->|Conflict| REJECT4[REJECT: Path Conflict]
    C -->|Clear| ACCEPT[ACCEPT Assignment]

    style ACCEPT fill:#c8e6c9
    style REJECT1 fill:#ffcdd2
    style REJECT2 fill:#ffcdd2
    style REJECT3 fill:#ffcdd2
    style REJECT4 fill:#ffcdd2
```

---

## Experimental Results Summary

| Experiment | Strategy | Coverage | Time | Safe |
|------------|----------|----------|------|------|
| S5 Surveillance | OODA | 100% | 0.66ms | Yes |
| R5 Search & Rescue | OODA | 100% | 1.17ms | Yes |
| R6 SAR Out-of-Grid | OODA | 100% | 0.29ms | Yes |
| D6 Delivery | OODA | 0%* | 0.16ms | Yes |
| D7 Delivery Out-of-Grid | OODA | 0%* | 0.42ms | Yes |

*\*Correct behavior: escalates to operator when constraints prevent safe reallocation*

**Key Finding:** Greedy strategies achieve 100% coverage but violate safety constraints. OODA prioritizes safety over coverage.

---

## Troubleshooting

<details>
<summary><b>UAVs won't connect</b></summary>

- Ensure GCS is running first: `make gcs`
- Check port availability: `lsof -i :5555`
- Verify `gcs_config.yaml` host/port settings

</details>

<details>
<summary><b>Dashboard not loading</b></summary>

- Check port 8085: `lsof -i :8085`
- Clear browser cache
- Check Flask logs for errors

</details>

<details>
<summary><b>OODA cycle not triggering</b></summary>

- Enable debug logging: `LOG_LEVEL=DEBUG make gui`
- Verify UAV has assigned tasks
- Check failure detection thresholds in config

</details>

---

## References

- **Thesis:** "Constraint-Aware Fault-Tolerant Control for Multi-Agent UAV Systems"
- **Quadcopter Dynamics:** Adapted from [bobzwik/Quadcopter_SimCon](https://github.com/bobzwik/Quadcopter_SimCon)

---

## Author

**Vítor Eulálio Reis**

Developed as part of the Specialization in Aeronautical Systems at the School of Engineering of São Carlos, University of São Paulo (EESC-USP).

---

## AI Disclosure

This project was developed with assistance from large language models:

- **Claude** (Anthropic): Software development, experimentation, UI design
- **Gemini** (Google): Literature survey, linguistic refinement
- **ChatGPT** (OpenAI): Simulated peer review

All technical decisions, system architecture, and algorithm design are the author's own work.

---

## License

See project specifications document.
