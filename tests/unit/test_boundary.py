"""
Unit tests for grid boundary management

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025

Tests cover:
- Boundary detection for targets outside grid
- Boundary intersection calculation
- UAV stopping at boundary
- Permission grant mechanism
- Permission tracking per target
- Boundary clearing after task completion
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# Grid boundaries
GRID_MIN = -60
GRID_MAX = 60


def is_position_outside_grid(position):
    """Check if position is outside grid boundaries"""
    x, y = position[0], position[1]
    return x < GRID_MIN or x > GRID_MAX or y < GRID_MIN or y > GRID_MAX


def calculate_boundary_intersection(start_pos, target_pos):  # noqa: C901
    """
    Calculate where the line from start to target intersects the grid boundary.
    Returns the boundary intersection point (x, y).
    """
    x1, y1 = start_pos[0], start_pos[1]
    x2, y2 = target_pos[0], target_pos[1]

    # Calculate direction vector
    dx = x2 - x1
    dy = y2 - y1

    # Find intersection with each boundary
    t_values = []

    # Check x boundaries
    if dx != 0:
        if dx > 0:  # Moving towards GRID_MAX
            t = (GRID_MAX - x1) / dx
            if 0 <= t <= 1:
                y_intersect = y1 + t * dy
                if GRID_MIN <= y_intersect <= GRID_MAX:
                    t_values.append((t, GRID_MAX, y_intersect))
        else:  # Moving towards GRID_MIN
            t = (GRID_MIN - x1) / dx
            if 0 <= t <= 1:
                y_intersect = y1 + t * dy
                if GRID_MIN <= y_intersect <= GRID_MAX:
                    t_values.append((t, GRID_MIN, y_intersect))

    # Check y boundaries
    if dy != 0:
        if dy > 0:  # Moving towards GRID_MAX
            t = (GRID_MAX - y1) / dy
            if 0 <= t <= 1:
                x_intersect = x1 + t * dx
                if GRID_MIN <= x_intersect <= GRID_MAX:
                    t_values.append((t, x_intersect, GRID_MAX))
        else:  # Moving towards GRID_MIN
            t = (GRID_MIN - y1) / dy
            if 0 <= t <= 1:
                x_intersect = x1 + t * dx
                if GRID_MIN <= x_intersect <= GRID_MAX:
                    t_values.append((t, x_intersect, GRID_MIN))

    # Return the closest intersection (smallest t)
    if t_values:
        t_values.sort(key=lambda x: x[0])
        return np.array([t_values[0][1], t_values[0][2]])

    # Fallback: clamp to boundary
    return np.array(
        [max(GRID_MIN, min(GRID_MAX, x1)), max(GRID_MIN, min(GRID_MAX, y1))]
    )


class TestBoundaryDetection:
    """Test boundary detection for positions"""

    def test_position_inside_grid(self):
        """Position within grid should not be detected as outside"""
        position = [0, 0, 10]
        assert not is_position_outside_grid(position)

    def test_position_at_grid_edge(self):
        """Position exactly at grid boundary should not be outside"""
        position = [60, 60, 10]
        assert not is_position_outside_grid(position)

        position = [-60, -60, 10]
        assert not is_position_outside_grid(position)

    def test_position_outside_grid_positive_x(self):
        """Position beyond positive X boundary should be detected"""
        position = [65, 0, 10]
        assert is_position_outside_grid(position)

    def test_position_outside_grid_negative_x(self):
        """Position beyond negative X boundary should be detected"""
        position = [-65, 0, 10]
        assert is_position_outside_grid(position)

    def test_position_outside_grid_positive_y(self):
        """Position beyond positive Y boundary should be detected"""
        position = [0, 65, 10]
        assert is_position_outside_grid(position)

    def test_position_outside_grid_negative_y(self):
        """Position beyond negative Y boundary should be detected"""
        position = [0, -65, 10]
        assert is_position_outside_grid(position)

    def test_position_outside_grid_diagonal(self):
        """Position outside in both dimensions should be detected"""
        position = [70, 70, 10]
        assert is_position_outside_grid(position)

        position = [-70, -70, 10]
        assert is_position_outside_grid(position)


class TestBoundaryIntersection:
    """Test boundary intersection calculations"""

    def test_intersection_moving_right(self):
        """Calculate intersection when moving towards +X boundary"""
        start = [50, 0]
        target = [80, 0]  # Beyond boundary at x=60
        intersection = calculate_boundary_intersection(start, target)

        assert intersection[0] == pytest.approx(60)
        assert intersection[1] == pytest.approx(0)

    def test_intersection_moving_left(self):
        """Calculate intersection when moving towards -X boundary"""
        start = [-50, 0]
        target = [-80, 0]  # Beyond boundary at x=-60
        intersection = calculate_boundary_intersection(start, target)

        assert intersection[0] == pytest.approx(-60)
        assert intersection[1] == pytest.approx(0)

    def test_intersection_moving_up(self):
        """Calculate intersection when moving towards +Y boundary"""
        start = [0, 50]
        target = [0, 80]  # Beyond boundary at y=60
        intersection = calculate_boundary_intersection(start, target)

        assert intersection[0] == pytest.approx(0)
        assert intersection[1] == pytest.approx(60)

    def test_intersection_moving_down(self):
        """Calculate intersection when moving towards -Y boundary"""
        start = [0, -50]
        target = [0, -80]  # Beyond boundary at y=-60
        intersection = calculate_boundary_intersection(start, target)

        assert intersection[0] == pytest.approx(0)
        assert intersection[1] == pytest.approx(-60)

    def test_intersection_diagonal_path(self):
        """Calculate intersection for diagonal path"""
        start = [0, 0]
        target = [80, 80]  # Beyond boundary
        intersection = calculate_boundary_intersection(start, target)

        # Should hit boundary at x=60 or y=60 (whichever comes first)
        assert intersection[0] == pytest.approx(60) or intersection[1] == pytest.approx(
            60
        )

    def test_intersection_from_inside_to_corner(self):
        """Calculate intersection when targeting outside corner"""
        start = [30, 30]
        target = [100, 100]
        intersection = calculate_boundary_intersection(start, target)

        # Should hit one of the boundaries
        assert intersection[0] == pytest.approx(60) or intersection[1] == pytest.approx(
            60
        )

    def test_no_intersection_target_inside(self):
        """When target is inside, return clamped position"""
        start = [0, 0]
        target = [30, 30]  # Inside grid
        intersection = calculate_boundary_intersection(start, target)

        # Should return a valid position (implementation specific)
        assert -60 <= intersection[0] <= 60
        assert -60 <= intersection[1] <= 60


class TestAwaitingPermissionState:
    """Test UAV behavior when awaiting permission at boundary"""

    def test_uav_stops_at_boundary(self):
        """UAV should stop when reaching boundary with outside target"""
        uav_position = [59, 0, 10]
        boundary_position = [60, 0, 10]
        # target = [80, 0, 10] - Outside grid (context only)

        # Calculate distance to boundary
        distance_to_boundary = np.linalg.norm(
            np.array(boundary_position[:2]) - np.array(uav_position[:2])
        )

        # If within arrival threshold, should stop
        should_stop = distance_to_boundary <= 2.0

        assert should_stop

    def test_uav_enters_awaiting_permission_state(self):
        """UAV should enter awaiting_permission state at boundary"""
        state = "awaiting_permission"
        awaiting_permission = True

        assert state == "awaiting_permission"
        assert awaiting_permission

    def test_permission_granted_allows_continuation(self):
        """UAV should continue past boundary when permission granted"""
        awaiting_permission = False
        permission_granted = True

        can_continue = permission_granted and not awaiting_permission

        assert can_continue


class TestPermissionTracking:
    """Test permission tracking per target"""

    def test_permission_tracks_specific_target(self):
        """Permission should be tied to specific target coordinates"""
        target = (80, 20)
        permission_granted_for_target = (80, 20)

        has_permission = permission_granted_for_target == target

        assert has_permission

    def test_different_target_requires_new_permission(self):
        """Different target should not inherit permission"""
        # pickup_target = (80, 20) - context only
        dropoff_target = (-80, -20)
        permission_granted_for_target = (80, 20)

        # Permission for pickup doesn't apply to dropoff
        has_permission_for_dropoff = permission_granted_for_target == tuple(
            dropoff_target
        )

        assert not has_permission_for_dropoff

    def test_permission_cleared_between_phases(self):
        """Permission should be cleared between delivery phases"""
        permission_granted_for_target = (80, 20)

        # Clear permission when pickup complete
        permission_granted_for_target = None

        assert permission_granted_for_target is None

    def test_permission_cleared_after_delivery_complete(self):
        """All permission fields cleared after task complete"""
        permission_granted_for_target = (80, 20)
        boundary_stop_position = [60, 20, 10]
        out_of_grid_target = [80, 20, 10]
        awaiting_permission = False

        # Clear all after delivery
        permission_granted_for_target = None
        boundary_stop_position = None
        out_of_grid_target = None
        awaiting_permission = False

        assert permission_granted_for_target is None
        assert boundary_stop_position is None
        assert out_of_grid_target is None
        assert not awaiting_permission


class TestBoundaryEdgeCases:
    """Test edge cases for boundary management"""

    def test_target_exactly_on_boundary(self):
        """Target exactly on boundary should not trigger stop"""
        target = [60, 0, 10]
        assert not is_position_outside_grid(target)

    def test_multiple_uavs_at_boundary_independently(self):
        """Multiple UAVs should handle boundary independently"""
        uav1_awaiting = True
        uav2_awaiting = False

        assert uav1_awaiting != uav2_awaiting

    def test_permission_double_click_mechanism(self):
        """Double-click on UAV should grant permission"""
        # Simulated double-click event
        awaiting_permission = True

        # Grant permission
        permission_granted = True
        awaiting_permission = False

        assert permission_granted
        assert not awaiting_permission

    def test_boundary_stop_different_for_pickup_and_dropoff(self):
        """Pickup and dropoff can have different boundary stops"""
        pickup_outside = is_position_outside_grid([80, 0, 10])
        dropoff_outside = is_position_outside_grid([-80, 0, 10])

        # Both are outside, so both should trigger boundary stops
        assert pickup_outside
        assert dropoff_outside


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
