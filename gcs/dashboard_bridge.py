"""
Dashboard Bridge - Streams GCS telemetry to web dashboard
"""

import socket
import threading
import json
import logging
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)


class DashboardBridge:
    """Bridge between GCS and web dashboard"""

    def __init__(self, gcs, socketio: SocketIO):
        self.gcs = gcs
        self.socketio = socketio
        self.running = False
        self.update_thread = None

    def start(self):
        """Start streaming telemetry to dashboard"""
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        logger.info("Dashboard bridge started")

    def stop(self):
        """Stop streaming"""
        self.running = False

    def _update_loop(self):
        """Send updates to connected dashboard clients"""
        while self.running:
            try:
                # Get current status
                status = self.gcs.get_status()

                # Get UAV telemetry
                uavs = {}
                for uav_id, uav_status in self.gcs.fleet_monitor.uavs.items():
                    uavs[uav_id] = {
                        "position": uav_status.position.tolist(),
                        "battery": uav_status.battery_soc,
                        "operational": uav_status.is_operational,
                    }

                # Get tasks
                tasks = {}
                for task_id, task in self.gcs.mission_db.tasks.items():
                    tasks[task_id] = {
                        "position": task.position.tolist(),
                        "type": task.type.value,
                        "priority": task.priority,
                        "status": task.status.value,
                    }

                # Broadcast to all connected clients
                self.socketio.emit("telemetry", {"uavs": uavs, "tasks": tasks})

                self.socketio.emit(
                    "update",
                    {
                        "fleet": status["fleet"],
                        "mission": status["mission"],
                        "ooda_stats": status["ooda"],
                    },
                )

            except Exception as e:
                logger.error(f"Dashboard update error: {e}")

            import time

            time.sleep(0.5)

    def notify_ooda_event(
        self,
        event_message: str,
        is_critical: bool = False,
        phase: str = None,
        uav_id: int = None,
        cycle_num: int = None,
        duration_ms: float = None,
        details: dict = None,
        metrics: dict = None,
    ):
        """
        Send OODA event notification to dashboard

        Args:
            event_message: Event description
            is_critical: Whether this is a critical event
            phase: OODA phase (observe, orient, decide, act)
            uav_id: Optional UAV ID involved
            cycle_num: OODA cycle number
            duration_ms: Phase duration in milliseconds
            details: Phase-specific details
            metrics: Enhanced OODA metrics (decision quality, fleet status, optimization)
        """
        event_data = {
            "message": event_message,
            "critical": is_critical,
            "phase": phase,
            "uav_id": uav_id,
            "cycle_num": cycle_num,
            "duration_ms": duration_ms,
            "details": details or {},
            "timestamp": __import__("time").time(),
        }

        if metrics is not None:
            event_data["metrics"] = metrics

        self.socketio.emit("ooda_event", event_data)
