"""
UAV Client - Connects to GCS and runs simulation

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025
"""

import socket
import json
import threading
import logging
import yaml
import time
import numpy as np
from uav.simulation import UAVSimulation

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class UAVClient:
    """UAV client managing simulation and GCS communication"""

    def __init__(self, uav_id: int, config_path: str, initial_position: np.ndarray):
        self.uav_id = uav_id

        # Load configuration
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Initialize simulation
        self.simulation = UAVSimulation(uav_id, self.config, initial_position)

        # Communication
        self.socket: socket.socket = None
        self.connected = False
        self.running = False

    def connect(self):
        """Connect to GCS"""
        host = self.config["communication"]["gcs_host"]
        port = self.config["communication"]["gcs_port"]

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))

            # Send registration
            register_msg = {
                "jsonrpc": "2.0",
                "method": "register",
                "params": {"uav_id": self.uav_id},
                "id": 1,
            }
            self.socket.sendall(json.dumps(register_msg).encode() + b"\n")

            # Wait for confirmation
            data = self.socket.recv(4096)
            response = json.loads(data.decode())

            if response.get("result", {}).get("status") == "registered":
                self.connected = True
                logger.info(f"UAV {self.uav_id} connected to GCS")
                return True
            else:
                logger.error(f"Registration failed: {response}")
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def start(self):
        """Start UAV operations"""
        if not self.connected:
            logger.error("Not connected to GCS")
            return

        self.running = True

        # Start message handler
        threading.Thread(target=self._message_handler, daemon=True).start()

        # Start simulation loop
        self._simulation_loop()

    def stop(self):
        """Stop UAV"""
        self.running = False
        if self.socket:
            self.socket.close()
        logger.info(f"UAV {self.uav_id} stopped")

    def _simulation_loop(self):
        """Main simulation loop"""
        while self.running:
            # Update simulation
            self.simulation.update()
            time.sleep(0.01)  # 100 Hz

    def _message_handler(self):
        """Handle incoming messages from GCS"""
        buffer = ""

        while self.running:
            try:
                self.socket.settimeout(1.0)
                data = self.socket.recv(4096)

                if not data:
                    logger.warning("Connection closed by GCS")
                    break

                buffer += data.decode()

                # Process complete messages
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self._process_message(json.loads(line))

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Message handler error: {e}")
                break

    def _process_message(self, message: dict):
        """Process message from GCS"""
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        if method == "get_telemetry":
            # Respond with telemetry
            telemetry = self.simulation.get_telemetry()
            response = {"jsonrpc": "2.0", "result": telemetry, "id": msg_id}
            self.socket.sendall(json.dumps(response).encode() + b"\n")

        elif method == "update_mission":
            # Update waypoints
            waypoints = [np.array(wp) for wp in params["waypoints"]]
            self.simulation.set_waypoints(waypoints)
            logger.info(
                f"UAV {self.uav_id} mission updated: {len(waypoints)} waypoints"
            )


def main():
    """Run UAV client"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m uav.client <uav_id> [x y z]")
        sys.exit(1)

    uav_id = int(sys.argv[1])

    # Initial position
    if len(sys.argv) >= 5:
        position = np.array(
            [float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])]
        )
    else:
        position = np.array([uav_id * 10.0, 0, 10.0])

    client = UAVClient(uav_id, "config/uav_config.yaml", position)

    if client.connect():
        try:
            logger.info(f"UAV {uav_id} starting...")
            client.start()
        except KeyboardInterrupt:
            logger.info("Stopping UAV")
            client.stop()
    else:
        logger.error("Failed to connect to GCS")


if __name__ == "__main__":
    main()
