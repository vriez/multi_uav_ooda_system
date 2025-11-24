"""
Ground Control Station - Main controller integrating OODA, fleet monitoring, and mission management
"""
import socket
import threading
import logging
import yaml
import time
import json
from typing import Dict, Optional

from gcs.ooda_engine import OODAEngine
from gcs.fleet_monitor import FleetMonitor
from gcs.constraint_validator import ConstraintValidator
from gcs.mission_manager import MissionDatabase, TaskType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dashboard integration (optional)
try:
    from flask_socketio import SocketIO
    from gcs.dashboard_bridge import DashboardBridge
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
    logger.info("Dashboard not available (Flask not installed)")


class GroundControlStation:
    """
    Main GCS controller - coordinates all subsystems
    """
    
    def __init__(self, config_path: str):
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        # Dashboard bridge (optional) - Initialize early so OODA can use it
        self.dashboard_bridge = None
        self.socketio = None

        # Initialize subsystems
        self.ooda_engine = OODAEngine(self.config, dashboard_bridge=None)  # Will be set later
        self.fleet_monitor = FleetMonitor(self.config)
        self.constraint_validator = ConstraintValidator(self.config)
        self.mission_db = MissionDatabase()

        # Communication
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.accept_thread: Optional[threading.Thread] = None
        
        # Register failure callback
        self.fleet_monitor.add_failure_callback(self.on_uav_failure)

    def set_dashboard_bridge(self, dashboard_bridge):
        """Connect dashboard bridge to GCS and OODA engine"""
        self.dashboard_bridge = dashboard_bridge
        self.ooda_engine.dashboard_bridge = dashboard_bridge

    def start(self):
        """Start GCS server"""
        host = self.config['communication']['server_host']
        port = self.config['communication']['server_port']
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(self.config['fleet']['max_uavs'])
        
        logger.info(f"GCS listening on {host}:{port}")
        
        self.running = True
        self.accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
        self.accept_thread.start()
        
        # Start fleet monitoring
        self.fleet_monitor.start_monitoring()
        
    def stop(self):
        """Shutdown GCS"""
        logger.info("Shutting down GCS")
        self.running = False
        self.fleet_monitor.stop_monitoring()
        
        if self.server_socket:
            self.server_socket.close()
            
    def _accept_connections(self):
        """Accept incoming UAV connections"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                conn, addr = self.server_socket.accept()
                logger.info(f"Connection from {addr}")
                
                # Handle registration
                threading.Thread(
                    target=self._handle_registration,
                    args=(conn, addr),
                    daemon=True
                ).start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")
                    
    def _handle_registration(self, conn: socket.socket, addr):
        """Handle UAV registration"""
        try:
            # Receive registration message
            data = conn.recv(4096)
            msg = json.loads(data.decode())
            
            if msg.get('method') == 'register':
                uav_id = msg['params']['uav_id']
                self.fleet_monitor.register_uav(uav_id, conn)
                
                # Send confirmation
                response = {
                    'jsonrpc': '2.0',
                    'result': {'status': 'registered'},
                    'id': msg.get('id')
                }
                conn.sendall(json.dumps(response).encode() + b'\n')
                logger.info(f"UAV {uav_id} registered")
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            conn.close()
            
    def on_uav_failure(self, uav_id: int, failure_type: str):
        """
        Callback triggered when fleet monitor detects UAV failure
        Initiates OODA cycle
        """
        logger.critical(f"UAV {uav_id} FAILED: {failure_type}")
        
        # Notify dashboard
        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"UAV {uav_id} FAILED: {failure_type}", 
                is_critical=True
            )
        
        # Get current fleet state
        fleet_state = self.fleet_monitor.get_fleet_state()
        
        # Trigger OODA cycle
        decision = self.ooda_engine.trigger_ooda_cycle(
            fleet_state,
            self.mission_db,
            self.constraint_validator
        )
        
        # Notify dashboard of OODA decision
        if self.dashboard_bridge:
            self.dashboard_bridge.notify_ooda_event(
                f"OODA: {decision.strategy.value} - {decision.rationale}"
            )
        
        # Dispatch mission updates
        self._dispatch_mission_updates(decision.reallocation_plan)
        
        # Log decision
        logger.info(f"OODA Decision: {decision.strategy.value}")
        logger.info(f"Rationale: {decision.rationale}")
        logger.info(f"Metrics: {decision.metrics}")
        
    def _dispatch_mission_updates(self, reallocation_plan: Dict[int, list]):
        """Send updated missions to affected UAVs"""
        for uav_id, task_ids in reallocation_plan.items():
            waypoints = []
            for task_id in task_ids:
                task = self.mission_db.get_task(task_id)
                if task:
                    waypoints.append(task.position.tolist())
                    
            # Send update command
            self._send_command(uav_id, 'update_mission', {
                'waypoints': waypoints,
                'task_ids': task_ids
            })
            
    def _send_command(self, uav_id: int, method: str, params: dict):
        """Send command to specific UAV"""
        if uav_id not in self.fleet_monitor.connections:
            logger.warning(f"Cannot send to UAV {uav_id}: not connected")
            return
            
        try:
            conn = self.fleet_monitor.connections[uav_id]
            message = {
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': int(time.time() * 1000)
            }
            conn.sendall(json.dumps(message).encode() + b'\n')
            logger.debug(f"Sent {method} to UAV {uav_id}")
            
        except Exception as e:
            logger.error(f"Error sending to UAV {uav_id}: {e}")
            
    def load_mission(self, scenario_file: str):
        """Load mission scenario"""
        with open(scenario_file, 'r') as f:
            scenario = yaml.safe_load(f)
        self.mission_db.load_mission_scenario(scenario)
        logger.info(f"Loaded mission from {scenario_file}")
        
    def get_status(self) -> dict:
        """Get GCS status"""
        operational, failed = self.fleet_monitor.get_uav_count()
        mission_stats = self.mission_db.get_mission_stats()
        ooda_stats = self.ooda_engine.get_performance_stats()
        
        return {
            'fleet': {
                'operational': operational,
                'failed': failed,
                'total': operational + failed
            },
            'mission': mission_stats,
            'ooda': ooda_stats
        }


def main():
    """Run GCS"""
    import numpy as np
    
    # Initialize GCS
    gcs = GroundControlStation('config/gcs_config.yaml')
    
    # Create simple test mission
    for i in range(10):
        gcs.mission_db.add_task(
            task_type=TaskType.SURVEILLANCE,
            position=np.random.rand(3) * 100,
            priority=np.random.rand() * 100
        )
    
    # Start GCS
    gcs.start()
    
    try:
        logger.info("GCS running. Press Ctrl+C to stop.")
        while True:
            time.sleep(5)
            status = gcs.get_status()
            logger.info(f"Status: {status['fleet']['operational']} operational UAVs, "
                       f"{status['mission']['completion_percent']:.1f}% complete")
    except KeyboardInterrupt:
        logger.info("Stopping GCS")
        gcs.stop()


if __name__ == '__main__':
    main()
