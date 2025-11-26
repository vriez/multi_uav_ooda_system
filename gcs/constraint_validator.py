"""
Constraint Validator - Sequential verification of battery, payload, and time constraints
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class ConstraintValidator:
    """
    Validates constraints for task assignments using sequential checking:
    1. Battery constraints
    2. Payload constraints (cargo missions only)
    3. Time constraints
    """

    def __init__(self, config: dict):
        self.config = config
        self.battery_safety_reserve = (
            config["constraints"]["battery_safety_reserve_percent"] / 100
        )
        self.battery_efficiency = 150.0  # meters per Wh (from UAV config)

        # Grid boundary constraints (default: 3000m x 2000m operational area)
        self.grid_bounds = config.get(
            "grid_bounds", {"x_min": 0, "x_max": 3000, "y_min": 0, "y_max": 2000}
        )

    def check_all_constraints(
        self, uav_id: int, task_id: int, fleet_state, mission_db
    ) -> bool:
        """
        Sequential constraint validation
        Returns True if all constraints satisfied
        """
        # Check grid boundary first (safety critical)
        if not self.check_grid_boundary_constraint(
            uav_id, task_id, fleet_state, mission_db
        ):
            return False

        # Check battery (most common limiting factor)
        if not self.check_battery_constraint(uav_id, task_id, fleet_state, mission_db):
            return False

        # Check payload (cargo missions only)
        task = mission_db.get_task(task_id)
        if hasattr(task, "payload_kg") and task.payload_kg:
            if not self.check_payload_constraint(
                uav_id, task_id, fleet_state, mission_db
            ):
                return False

        # Check temporal constraints
        if not self.check_time_constraint(uav_id, task_id, fleet_state, mission_db):
            return False

        return True

    def check_grid_boundary_constraint(
        self, uav_id: int, task_id: int, fleet_state, mission_db
    ) -> bool:
        """
        Verify task destination is within operational grid boundaries.
        UAVs with out_of_grid_permission can operate outside bounds.
        """
        task = mission_db.get_task(task_id)
        task_position = task.position

        x, y = task_position[0], task_position[1]
        bounds = self.grid_bounds

        is_within_grid = (
            bounds["x_min"] <= x <= bounds["x_max"]
            and bounds["y_min"] <= y <= bounds["y_max"]
        )

        if is_within_grid:
            return True

        # Task is outside grid - check if UAV has permission
        has_permission = fleet_state.uav_permissions.get(uav_id, {}).get(
            "out_of_grid", False
        )

        if has_permission:
            logger.debug(
                f"UAV {uav_id} has out-of-grid permission for task {task_id} at ({x:.0f}, {y:.0f})"
            )
            return True
        else:
            logger.debug(
                f"UAV {uav_id} cannot reach task {task_id} at ({x:.0f}, {y:.0f}) - outside grid "
                f"[{bounds['x_min']}-{bounds['x_max']}, {bounds['y_min']}-{bounds['y_max']}] "
                f"and no out-of-grid permission"
            )
            return False

    def check_battery_constraint(
        self, uav_id: int, task_id: int, fleet_state, mission_db
    ) -> bool:
        """
        Verify UAV has sufficient battery for task after accounting for
        committed tasks and safety reserve
        """
        uav_battery = fleet_state.uav_battery[uav_id]
        uav_position = fleet_state.uav_positions[uav_id]

        # Get task details
        task = mission_db.get_task(task_id)
        task_position = task.position

        # Calculate distance to task
        distance = np.linalg.norm(task_position - uav_position)

        # Estimate energy required (simplified model)
        # Includes: travel to task + task execution + return margin
        energy_required_wh = distance * 2 / self.battery_efficiency  # Round trip

        # Get committed energy from existing tasks
        committed_tasks = mission_db.get_uav_tasks(uav_id)
        committed_energy = self._estimate_committed_energy(
            uav_id, committed_tasks, uav_position, mission_db
        )

        # Calculate battery capacity (assuming 100 Wh nominal)
        battery_capacity_wh = 100.0
        available_energy = (uav_battery / 100) * battery_capacity_wh

        # Check if spare capacity sufficient
        spare_capacity = (
            available_energy
            - committed_energy
            - (self.battery_safety_reserve * battery_capacity_wh)
        )

        if spare_capacity >= energy_required_wh:
            logger.debug(
                f"UAV {uav_id} battery OK for task {task_id}: "
                f"{spare_capacity:.1f} Wh spare, {energy_required_wh:.1f} Wh needed"
            )
            return True
        else:
            logger.debug(
                f"UAV {uav_id} insufficient battery for task {task_id}: "
                f"{spare_capacity:.1f} Wh spare, {energy_required_wh:.1f} Wh needed"
            )
            return False

    def check_payload_constraint(
        self, uav_id: int, task_id: int, fleet_state, mission_db
    ) -> bool:
        """
        Verify UAV has sufficient payload capacity (cargo missions only)
        """
        if uav_id not in fleet_state.uav_payloads:
            return True  # No payload tracking

        available_payload = fleet_state.uav_payloads[uav_id]
        task = mission_db.get_task(task_id)
        required_payload = getattr(task, "payload_kg", 0)

        if available_payload >= required_payload:
            logger.debug(
                f"UAV {uav_id} payload OK for task {task_id}: "
                f"{available_payload:.1f} kg available, {required_payload:.1f} kg needed"
            )
            return True
        else:
            logger.debug(
                f"UAV {uav_id} insufficient payload for task {task_id}: "
                f"{available_payload:.1f} kg available, {required_payload:.1f} kg needed"
            )
            return False

    def check_time_constraint(
        self, uav_id: int, task_id: int, fleet_state, mission_db
    ) -> bool:
        """
        Verify task can complete before deadline given current mission state
        """
        import time

        task = mission_db.get_task(task_id)
        if not hasattr(task, "deadline") or not task.deadline:
            return True  # No deadline

        current_time = time.time()
        uav_position = fleet_state.uav_positions[uav_id]

        # Estimate time to reach task
        distance = np.linalg.norm(task.position - uav_position)
        avg_velocity = 10.0  # m/s
        travel_time = distance / avg_velocity

        # Estimate task execution time
        execution_time = getattr(task, "duration_sec", 60)

        # Total time needed
        total_time = travel_time + execution_time

        # Time until deadline
        time_available = task.deadline - current_time

        if time_available >= total_time:
            logger.debug(
                f"UAV {uav_id} time OK for task {task_id}: "
                f"{time_available:.0f}s available, {total_time:.0f}s needed"
            )
            return True
        else:
            logger.debug(
                f"UAV {uav_id} insufficient time for task {task_id}: "
                f"{time_available:.0f}s available, {total_time:.0f}s needed"
            )
            return False

    def _estimate_committed_energy(
        self, uav_id: int, task_ids: list, uav_position: np.ndarray, mission_db
    ) -> float:
        """Estimate total energy required for committed tasks"""
        if not task_ids:
            return 0

        total_energy = 0
        current_pos = uav_position.copy()

        # Simple sequential path energy estimation
        for task_id in task_ids:
            task = mission_db.get_task(task_id)
            distance = np.linalg.norm(task.position - current_pos)
            total_energy += distance / self.battery_efficiency
            current_pos = task.position.copy()

        return total_energy

    def check_collision_avoidance(
        self, uav_id: int, waypoints: list, fleet_state, mission_db
    ) -> bool:
        """
        Verify trajectory maintains safety buffer from other UAVs
        (Simplified - full implementation would use spatial-temporal checks)
        """
        safety_buffer = self.config["collision_avoidance"]["safety_buffer_meters"]

        # Check against other operational UAVs
        for other_id in fleet_state.operational_uavs:
            if other_id == uav_id:
                continue

            other_pos = fleet_state.uav_positions[other_id]

            # Check each waypoint
            for wp in waypoints:
                distance = np.linalg.norm(wp - other_pos)
                if distance < safety_buffer:
                    logger.warning(
                        f"Collision risk between UAV {uav_id} and {other_id}: "
                        f"{distance:.1f}m < {safety_buffer}m"
                    )
                    return False

        return True
