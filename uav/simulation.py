"""
UAV Simulation Engine - Complete vehicle system with physics and control
Based on Quadcopter_SimCon codebase
"""

import numpy as np
import logging
from scipy.integrate import odeint
from typing import List, Optional
import time

logger = logging.getLogger(__name__)


class QuadcopterDynamics:
    """
    Quadcopter 6-DOF dynamics with quaternion representation
    Simplified from Quadcopter_SimCon for demonstration
    """

    def __init__(self, config: dict):
        # Physical parameters
        self.mass = config["dynamics"]["mass_kg"]
        self.arm_length = config["dynamics"]["arm_length_m"]
        self.Ixx, self.Iyy, self.Izz = config["dynamics"]["inertia_matrix"]
        self.drag_coeff = config["dynamics"]["drag_coefficient"]

        # Motor parameters
        self.motor_time_constant = config["dynamics"]["motor_time_constant"]
        self.k_thrust = 1.0e-6  # Thrust coefficient (N/(rad/s)^2)
        self.k_torque = 1.0e-7  # Torque coefficient (Nm/(rad/s)^2)

        # Gravity
        self.g = 9.81

    def state_derivative(
        self, state: np.ndarray, t: float, motor_speeds: np.ndarray
    ) -> np.ndarray:
        """
        Calculate state derivatives for ODE integration
        State: [x, y, z, qw, qx, qy, qz, vx, vy, vz, p, q, r, w1, w2, w3, w4]
        """
        # Extract state variables
        pos = state[0:3]
        quat = state[3:7]  # [qw, qx, qy, qz]
        vel = state[7:10]
        omega = state[10:13]  # Angular velocity in body frame
        motor_w = state[13:17]  # Motor angular velocities

        # Normalize quaternion
        quat = quat / np.linalg.norm(quat)
        qw, qx, qy, qz = quat

        # Rotation matrix from body to world
        R = np.array(
            [
                [
                    1 - 2 * (qy**2 + qz**2),
                    2 * (qx * qy - qw * qz),
                    2 * (qx * qz + qw * qy),
                ],
                [
                    2 * (qx * qy + qw * qz),
                    1 - 2 * (qx**2 + qz**2),
                    2 * (qy * qz - qw * qx),
                ],
                [
                    2 * (qx * qz - qw * qy),
                    2 * (qy * qz + qw * qx),
                    1 - 2 * (qx**2 + qy**2),
                ],
            ]
        )

        # Forces in body frame
        thrust = self.k_thrust * np.sum(motor_w**2)
        F_body = np.array([0, 0, thrust])

        # Drag force (proportional to velocity squared)
        drag = -self.drag_coeff * vel * np.linalg.norm(vel)

        # Total force in world frame
        F_world = R @ F_body + drag + np.array([0, 0, -self.mass * self.g])

        # Linear acceleration
        acc = F_world / self.mass

        # Torques from motors (simplified X-configuration)
        L = self.arm_length
        w1, w2, w3, w4 = motor_w
        tau_roll = L * self.k_thrust * (-(w1**2) + w2**2 + w3**2 - w4**2)
        tau_pitch = L * self.k_thrust * (-(w1**2) - w2**2 + w3**2 + w4**2)
        tau_yaw = self.k_torque * (-(w1**2) + w2**2 - w3**2 + w4**2)

        torques = np.array([tau_roll, tau_pitch, tau_yaw])

        # Angular acceleration (Euler's equations)
        p, q, r = omega
        alpha_x = (torques[0] + (self.Iyy - self.Izz) * q * r) / self.Ixx
        alpha_y = (torques[1] + (self.Izz - self.Ixx) * p * r) / self.Iyy
        alpha_z = (torques[2] + (self.Ixx - self.Iyy) * p * q) / self.Izz
        alpha = np.array([alpha_x, alpha_y, alpha_z])

        # Quaternion derivative
        omega_quat = np.array([0, p, q, r])
        quat_dot = 0.5 * self._quaternion_multiply(quat, omega_quat)

        # Motor dynamics (first-order)
        motor_cmd = motor_speeds  # Commanded speeds
        motor_dot = (motor_cmd - motor_w) / self.motor_time_constant

        # Assemble derivative
        state_dot = np.concatenate(
            [
                vel,  # Position derivative
                quat_dot,  # Quaternion derivative
                acc,  # Velocity derivative
                alpha,  # Angular velocity derivative
                motor_dot,  # Motor speed derivative
            ]
        )

        return state_dot

    def _quaternion_multiply(self, q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        """Multiply two quaternions"""
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2

        return np.array(
            [
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ]
        )


class CascadePIDController:
    """
    Cascade PID controller: Position -> Velocity -> Attitude -> Rate
    """

    def __init__(self, config: dict):
        self.pos_gains = np.array(config["control"]["position_gains"]["kp"])
        self.vel_kp = np.array(config["control"]["velocity_gains"]["kp"])
        self.vel_ki = np.array(config["control"]["velocity_gains"]["ki"])
        self.vel_kd = np.array(config["control"]["velocity_gains"]["kd"])
        self.att_gains = np.array(config["control"]["attitude_gains"]["kp"])
        self.rate_kp = np.array(config["control"]["rate_gains"]["kp"])
        self.rate_kd = np.array(config["control"]["rate_gains"]["kd"])

        self.vel_integral = np.zeros(3)
        self.max_tilt = 45.0 * np.pi / 180  # rad

    def compute_control(self, state: dict, setpoint: dict, dt: float) -> np.ndarray:
        """
        Compute motor commands from current state and setpoint
        Returns: motor_speeds [w1, w2, w3, w4] in rad/s
        """
        # Position control -> velocity setpoint
        pos_error = setpoint["position"] - state["position"]
        vel_sp = self.pos_gains * pos_error
        vel_sp = np.clip(vel_sp, -10, 10)  # Limit velocity

        # Velocity control -> thrust and attitude
        vel_error = vel_sp - state["velocity"]
        self.vel_integral += vel_error * dt
        self.vel_integral = np.clip(self.vel_integral, -5, 5)

        acc_sp = (
            self.vel_kp * vel_error
            + self.vel_ki * self.vel_integral
            + self.vel_kd
            * (vel_error - getattr(self, "prev_vel_error", vel_error))
            / dt
        )
        self.prev_vel_error = vel_error

        # Convert acceleration to thrust and desired attitude
        thrust = (acc_sp[2] + 9.81) * 1.5  # mass * (az + g)
        thrust = max(0, min(thrust, 50))  # Limit thrust

        # Desired attitude from lateral acceleration
        roll_des = np.arctan2(acc_sp[1], 9.81)
        pitch_des = np.arctan2(-acc_sp[0], 9.81)
        yaw_des = setpoint.get("yaw", 0)

        roll_des = np.clip(roll_des, -self.max_tilt, self.max_tilt)
        pitch_des = np.clip(pitch_des, -self.max_tilt, self.max_tilt)

        # Attitude control -> rate setpoint (simplified)
        att_error = np.array(
            [
                roll_des - self._get_roll(state["attitude"]),
                pitch_des - self._get_pitch(state["attitude"]),
                yaw_des - self._get_yaw(state["attitude"]),
            ]
        )
        rate_sp = self.att_gains * att_error

        # Rate control -> moments
        rate_error = rate_sp - state["angular_velocity"]
        moments = self.rate_kp * rate_error

        # Mixer: [thrust, moments] -> motor speeds
        motor_speeds = self._mixer(thrust, moments)

        return motor_speeds

    def _get_roll(self, quat):
        """Extract roll from quaternion"""
        qw, qx, qy, qz = quat
        return np.arctan2(2 * (qw * qx + qy * qz), 1 - 2 * (qx**2 + qy**2))

    def _get_pitch(self, quat):
        """Extract pitch from quaternion"""
        qw, qx, qy, qz = quat
        return np.arcsin(2 * (qw * qy - qz * qx))

    def _get_yaw(self, quat):
        """Extract yaw from quaternion"""
        qw, qx, qy, qz = quat
        return np.arctan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy**2 + qz**2))

    def _mixer(self, thrust: float, moments: np.ndarray) -> np.ndarray:
        """
        Convert thrust and moments to motor speeds
        X-configuration mixer
        """
        # Simplified mixer (should use proper allocation matrix)
        base_speed = np.sqrt(max(0, thrust / 4))

        w1 = base_speed - moments[0] - moments[1] - moments[2]
        w2 = base_speed + moments[0] - moments[1] + moments[2]
        w3 = base_speed + moments[0] + moments[1] - moments[2]
        w4 = base_speed - moments[0] + moments[1] + moments[2]

        motor_speeds = np.array([w1, w2, w3, w4])
        motor_speeds = np.clip(motor_speeds, 0, 800)  # rad/s limits

        return motor_speeds


class UAVSimulation:
    """
    Complete UAV simulation with dynamics, control, and sensors
    """

    def __init__(self, uav_id: int, config: dict, initial_position: np.ndarray):
        self.uav_id = uav_id
        self.config = config

        # Initialize state: [pos, quat, vel, omega, motor_w]
        self.state = np.zeros(17)
        self.state[0:3] = initial_position  # Position
        self.state[3] = 1.0  # Quaternion (identity)

        # Components
        self.dynamics = QuadcopterDynamics(config)
        self.controller = CascadePIDController(config)

        # Battery model
        self.battery_capacity = config["battery"]["capacity_wh"]
        self.battery_soc = 100.0  # State of charge (%)

        # Mission state
        self.waypoints: List[np.ndarray] = []
        self.current_waypoint_idx = 0
        self.is_flying = False

        # Timing
        self.dt = 0.01  # 100 Hz simulation
        self.last_update = time.time()

    def update(self):
        """Update simulation by one timestep"""
        current_time = time.time()
        dt = current_time - self.last_update
        self.last_update = current_time

        if not self.is_flying:
            return

        # Get current waypoint target
        if self.current_waypoint_idx < len(self.waypoints):
            target = self.waypoints[self.current_waypoint_idx]
        else:
            target = self.state[0:3]  # Hold position

        # Prepare state dict for controller
        state_dict = {
            "position": self.state[0:3],
            "attitude": self.state[3:7],
            "velocity": self.state[7:10],
            "angular_velocity": self.state[10:13],
        }

        setpoint = {"position": target, "yaw": 0}

        # Compute control
        motor_speeds = self.controller.compute_control(state_dict, setpoint, dt)

        # Integrate dynamics
        self.state = odeint(
            self.dynamics.state_derivative,
            self.state,
            [0, self.dt],
            args=(motor_speeds,),
        )[-1]

        # Normalize quaternion
        self.state[3:7] /= np.linalg.norm(self.state[3:7])

        # Update battery
        self._update_battery(dt, motor_speeds)

        # Check waypoint reached
        if np.linalg.norm(self.state[0:3] - target) < 2.0:
            if self.current_waypoint_idx < len(self.waypoints) - 1:
                self.current_waypoint_idx += 1

    def _update_battery(self, dt: float, motor_speeds: np.ndarray):
        """Update battery state of charge"""
        # Power consumption (simplified)
        power = 0.001 * np.sum(motor_speeds**2)  # Watts
        energy = power * dt / 3600  # Wh

        self.battery_soc -= (energy / self.battery_capacity) * 100
        self.battery_soc = max(0, self.battery_soc)

    def set_waypoints(self, waypoints: List[np.ndarray]):
        """Set new waypoint sequence"""
        self.waypoints = waypoints
        self.current_waypoint_idx = 0
        self.is_flying = True
        logger.info(f"UAV {self.uav_id} received {len(waypoints)} waypoints")

    def get_telemetry(self) -> dict:
        """Get current telemetry"""
        return {
            "uav_id": self.uav_id,
            "position": self.state[0:3].tolist(),
            "attitude": self.state[3:7].tolist(),
            "velocity": self.state[7:10].tolist(),
            "battery_soc": self.battery_soc,
            "is_flying": self.is_flying,
            "active_tasks": [],
        }
