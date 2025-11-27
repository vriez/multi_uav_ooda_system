"""
Fleet Monitor - UAV telemetry collection and multi-modal failure detection.

Author: Vítor Eulálio Reis <vitor.reis@proton.me>
Copyright (c) 2025

This module implements real-time fleet monitoring with automatic failure detection.
It polls UAVs for telemetry at a configurable rate and triggers OODA cycles when
anomalies are detected.

Failure Detection Methods:
    1. Communication Timeout: No response within timeout threshold (default 1.5s)
    2. Battery Anomaly: Discharge rate exceeds threshold (default 5%/30s)
    3. Position Discontinuity: Position jump exceeds threshold (default 100m)
    4. Altitude Violation: Altitude outside safe envelope (5m-120m)

Key Classes:
    FleetMonitor: Main monitoring class with failure detection
    UAVStatus: Individual UAV state tracking with history

Usage:
    >>> monitor = FleetMonitor(config)
    >>> monitor.add_failure_callback(ooda_engine.on_failure)
    >>> monitor.start_monitoring()
    >>>
    >>> # Register new UAV
    >>> monitor.register_uav(uav_id=1, connection=socket)
    >>>
    >>> # Get fleet snapshot
    >>> state = monitor.get_fleet_state()

Threading Model:
    FleetMonitor runs a background thread that polls UAVs at the configured
    telemetry rate. Failure callbacks are invoked from this thread.
"""

import time
import socket
import json
import logging
import threading
from typing import Dict, List, Callable
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class UAVStatus:
    """
    Track individual UAV status and telemetry history.

    Maintains current state and historical data for anomaly detection.
    Battery and position history are kept for detecting sudden changes
    that indicate failures.

    Attributes:
        uav_id: Unique identifier for this UAV
        is_connected: Whether UAV has active connection
        is_operational: Whether UAV is functioning normally
        last_telemetry_time: Unix timestamp of last telemetry update
        position: Current [x, y, z] position in meters
        attitude: Current attitude as quaternion [w, x, y, z]
        battery_soc: Battery state-of-charge (0-100%)
        payload_capacity: Available payload capacity in kg
        active_tasks: List of task IDs currently assigned
        failure_mode: Type of failure if not operational (e.g., 'battery_anomaly')
        battery_history: Deque of (timestamp, soc) tuples for anomaly detection
        position_history: Deque of position arrays for discontinuity detection
    """

    def __init__(self, uav_id: int):
        self.uav_id = uav_id
        self.is_connected = False
        self.is_operational = True
        self.last_telemetry_time = 0
        self.position = np.zeros(3)
        self.attitude = np.array([1, 0, 0, 0])  # Quaternion
        self.battery_soc = 100.0
        self.payload_capacity = 0.0
        self.active_tasks = []
        self.failure_mode = None

        # Historical data for anomaly detection
        self.battery_history = deque(maxlen=60)  # 30 seconds at 2 Hz
        self.position_history = deque(maxlen=10)

    def update_telemetry(self, telemetry: dict):
        """Update from telemetry packet"""
        self.last_telemetry_time = time.time()
        self.position = np.array(telemetry["position"])
        self.attitude = np.array(telemetry.get("attitude", [1, 0, 0, 0]))
        self.battery_soc = telemetry["battery_soc"]
        self.payload_capacity = telemetry.get("payload_capacity", 0.0)
        self.active_tasks = telemetry.get("active_tasks", [])

        # Store for anomaly detection
        self.battery_history.append((time.time(), self.battery_soc))
        self.position_history.append(self.position.copy())


class FleetMonitor:
    """
    Fleet monitoring system with multi-modal failure detection
    """

    def __init__(self, config: dict):
        self.config = config
        self.uavs: Dict[int, UAVStatus] = {}
        self.connections: Dict[int, socket.socket] = {}

        self.telemetry_rate = config["ooda_engine"]["telemetry_rate_hz"]
        self.timeout_threshold = config["ooda_engine"]["timeout_threshold_sec"]

        self.anomaly_thresholds = config["constraints"]["anomaly_thresholds"]

        self.running = False
        self.monitor_thread = None
        self.failure_callbacks: List[Callable] = []

    def register_uav(self, uav_id: int, connection: socket.socket):
        """Register new UAV connection"""
        self.uavs[uav_id] = UAVStatus(uav_id)
        self.connections[uav_id] = connection
        self.uavs[uav_id].is_connected = True
        logger.info(f"UAV {uav_id} registered")

    def unregister_uav(self, uav_id: int):
        """Remove UAV from fleet"""
        if uav_id in self.connections:
            self.connections[uav_id].close()
            del self.connections[uav_id]
        if uav_id in self.uavs:
            del self.uavs[uav_id]
        logger.info(f"UAV {uav_id} unregistered")

    def add_failure_callback(self, callback: Callable):
        """Register callback for failure events"""
        self.failure_callbacks.append(callback)

    def start_monitoring(self):
        """Start continuous fleet monitoring"""
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self.monitor_thread.start()
        logger.info("Fleet monitoring started")

    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("Fleet monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop - polls telemetry at configured rate"""
        poll_interval = 1.0 / self.telemetry_rate

        while self.running:
            loop_start = time.time()

            # Poll all UAVs
            for uav_id in list(self.uavs.keys()):
                try:
                    self._poll_uav(uav_id)
                    self._check_failures(uav_id)
                except Exception as e:
                    logger.error(f"Error monitoring UAV {uav_id}: {e}")

            # Maintain poll rate
            elapsed = time.time() - loop_start
            if elapsed < poll_interval:
                time.sleep(poll_interval - elapsed)

    def _poll_uav(self, uav_id: int):
        """Request telemetry from specific UAV"""
        if uav_id not in self.connections:
            return

        uav = self.uavs[uav_id]
        conn = self.connections[uav_id]

        try:
            # Request telemetry
            request = {
                "jsonrpc": "2.0",
                "method": "get_telemetry",
                "id": int(time.time() * 1000),
            }
            conn.sendall(json.dumps(request).encode() + b"\n")

            # Set timeout for response
            conn.settimeout(self.timeout_threshold)
            data = conn.recv(4096)

            if data:
                response = json.loads(data.decode())
                if "result" in response:
                    uav.update_telemetry(response["result"])

        except socket.timeout:
            logger.warning(f"Timeout receiving telemetry from UAV {uav_id}")
            self._handle_timeout_failure(uav_id)
        except Exception as e:
            logger.error(f"Communication error with UAV {uav_id}: {e}")

    def _check_failures(self, uav_id: int):
        """Multi-modal failure detection"""
        uav = self.uavs[uav_id]
        current_time = time.time()

        # 1. Timeout detection
        if current_time - uav.last_telemetry_time > self.timeout_threshold:
            self._handle_timeout_failure(uav_id)
            return

        # 2. Battery anomaly detection
        if self._detect_battery_anomaly(uav):
            self._handle_battery_failure(uav_id)
            return

        # 3. Position discontinuity
        if self._detect_position_anomaly(uav):
            self._handle_position_failure(uav_id)
            return

        # 4. Altitude violation
        if self._detect_altitude_violation(uav):
            self._handle_altitude_failure(uav_id)
            return

    def _detect_battery_anomaly(self, uav: UAVStatus) -> bool:
        """Detect abnormal battery discharge rate"""
        if len(uav.battery_history) < 5:
            return False

        # Check discharge rate over last 30 seconds
        recent = list(uav.battery_history)[-60:]  # Up to 30s at 2 Hz
        if len(recent) < 2:
            return False

        time_diff = recent[-1][0] - recent[0][0]
        battery_diff = recent[0][1] - recent[-1][1]

        if time_diff > 0:
            discharge_rate = (battery_diff / time_diff) * 30  # % per 30 seconds
            threshold = self.anomaly_thresholds["battery_discharge_rate"]

            if discharge_rate > threshold:
                logger.warning(
                    f"UAV {uav.uav_id} abnormal discharge: "
                    f"{discharge_rate:.1f}%/30s"
                )
                return True

        return False

    def _detect_position_anomaly(self, uav: UAVStatus) -> bool:
        """Detect position discontinuities"""
        if len(uav.position_history) < 2:
            return False

        # Check jump between consecutive positions
        pos_diff = np.linalg.norm(uav.position_history[-1] - uav.position_history[-2])

        threshold = self.anomaly_thresholds["position_discontinuity"]
        max_expected = 15.0 * (1.0 / self.telemetry_rate)  # 15 m/s max velocity

        if pos_diff > min(threshold, max_expected):
            logger.warning(
                f"UAV {uav.uav_id} position discontinuity: " f"{pos_diff:.1f}m"
            )
            return True

        return False

    def _detect_altitude_violation(self, uav: UAVStatus) -> bool:
        """Detect altitude constraint violations"""
        altitude = uav.position[2]
        threshold = self.anomaly_thresholds["altitude_deviation"]

        # Check against configured limits (simplified)
        max_altitude = 120.0
        min_altitude = 5.0

        if altitude > max_altitude + threshold or altitude < min_altitude - threshold:
            logger.warning(f"UAV {uav.uav_id} altitude violation: {altitude:.1f}m")
            return True

        return False

    def _handle_timeout_failure(self, uav_id: int):
        """Handle communication timeout"""
        if uav_id not in self.uavs:
            return

        uav = self.uavs[uav_id]
        if uav.is_operational:
            uav.is_operational = False
            uav.failure_mode = "communication_timeout"
            logger.error(f"UAV {uav_id} FAILED: Communication timeout")
            self._trigger_failure_callbacks(uav_id, "timeout")

    def _handle_battery_failure(self, uav_id: int):
        """Handle battery anomaly"""
        uav = self.uavs[uav_id]
        if uav.is_operational:
            uav.is_operational = False
            uav.failure_mode = "battery_anomaly"
            logger.error(f"UAV {uav_id} FAILED: Battery anomaly")
            self._trigger_failure_callbacks(uav_id, "battery")

    def _handle_position_failure(self, uav_id: int):
        """Handle position anomaly"""
        uav = self.uavs[uav_id]
        if uav.is_operational:
            uav.is_operational = False
            uav.failure_mode = "position_anomaly"
            logger.error(f"UAV {uav_id} FAILED: Position anomaly")
            self._trigger_failure_callbacks(uav_id, "position")

    def _handle_altitude_failure(self, uav_id: int):
        """Handle altitude violation"""
        uav = self.uavs[uav_id]
        if uav.is_operational:
            uav.is_operational = False
            uav.failure_mode = "altitude_violation"
            logger.error(f"UAV {uav_id} FAILED: Altitude violation")
            self._trigger_failure_callbacks(uav_id, "altitude")

    def _trigger_failure_callbacks(self, uav_id: int, failure_type: str):
        """Notify all registered failure handlers"""
        for callback in self.failure_callbacks:
            try:
                callback(uav_id, failure_type)
            except Exception as e:
                logger.error(f"Failure callback error: {e}")

    def get_fleet_state(self):
        """Get complete fleet state snapshot"""
        from gcs.ooda_engine import FleetState

        operational = [uid for uid, uav in self.uavs.items() if uav.is_operational]
        failed = [uid for uid, uav in self.uavs.items() if not uav.is_operational]

        positions = {uid: uav.position for uid, uav in self.uavs.items()}
        battery = {uid: uav.battery_soc for uid, uav in self.uavs.items()}
        payloads = {uid: uav.payload_capacity for uid, uav in self.uavs.items()}

        # Collect lost tasks from failed UAVs
        lost_tasks = []
        for uid in failed:
            lost_tasks.extend(self.uavs[uid].active_tasks)

        return FleetState(
            timestamp=time.time(),
            operational_uavs=operational,
            failed_uavs=failed,
            uav_positions=positions,
            uav_battery=battery,
            uav_payloads=payloads,
            lost_tasks=lost_tasks,
        )

    def get_uav_count(self) -> tuple:
        """Get operational and failed UAV counts"""
        operational = sum(1 for uav in self.uavs.values() if uav.is_operational)
        failed = sum(1 for uav in self.uavs.values() if not uav.is_operational)
        return operational, failed
