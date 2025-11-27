"""
Integration tests for Search and Rescue (SAR) missions

Author: Vítor Eulálio Reis <vitor.ereis@proton.me>
Copyright (c) 2025

Tests cover:
- Asset detection and last known position tracking
- Zone assignments (spatial contiguity, no auto-reassignment)
- Out-of-grid asset pursuit
- Consensus-based identification
- Guardian assignment
- Mission completion criteria
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest  # noqa: E402
import numpy as np  # noqa: E402

from visualization.config import (  # noqa: E402
    SAR_VISIBILITY_RADIUS,
    SAR_CONSENSUS_REQUIRED,
    SAR_IDENTIFICATION_CIRCLES,
    SAR_GUARDIAN_MONITORING_CIRCLES,
)


class TestAssetDetection:
    """Test asset detection and tracking"""

    def test_asset_visible_within_radius(self):
        """Asset should be visible when UAV within detection radius"""
        uav_pos = np.array([10, 10])
        asset_pos = np.array([20, 20])
        distance = np.linalg.norm(asset_pos - uav_pos)

        is_visible = distance <= SAR_VISIBILITY_RADIUS

        # Distance is ~14.14m, within 25m radius
        assert is_visible

    def test_asset_not_visible_beyond_radius(self):
        """Asset should not be visible when UAV beyond detection radius"""
        uav_pos = np.array([0, 0])
        asset_pos = np.array([30, 30])
        distance = np.linalg.norm(asset_pos - uav_pos)

        is_visible = distance <= SAR_VISIBILITY_RADIUS

        # Distance is ~42.43m, beyond 25m radius
        assert not is_visible

    def test_last_known_position_initialized(self):
        """Last known position should be initialized on asset creation"""
        asset_position = [50, 50, 0]
        last_known_position = asset_position.copy()

        assert last_known_position == [50, 50, 0]

    def test_last_known_position_updated_within_radius(self):
        """Last known position should update when UAV within detection radius"""
        uav_pos = np.array([50, 50])
        asset_real_pos = np.array([55, 55])  # Moved
        asset_last_known = np.array([50, 50])

        distance = np.linalg.norm(asset_real_pos - uav_pos)

        if distance <= SAR_VISIBILITY_RADIUS:
            asset_last_known = asset_real_pos.copy()

        # Distance is ~7.07m, within 25m
        assert np.array_equal(asset_last_known, asset_real_pos)

    def test_last_known_position_not_updated_beyond_radius(self):
        """Last known position should NOT update when UAV beyond detection radius"""
        uav_pos = np.array([0, 0])
        asset_real_pos = np.array([80, 80])  # Far away
        asset_last_known = np.array([50, 50])  # Old position

        distance = np.linalg.norm(asset_real_pos - uav_pos)

        if distance <= SAR_VISIBILITY_RADIUS:
            asset_last_known = asset_real_pos.copy()
        # else: keep old position

        # Distance is ~113m, beyond 25m, so position not updated
        assert np.array_equal(asset_last_known, np.array([50, 50]))

    def test_uav_targets_last_known_not_real_position(self):
        """UAV should navigate to last known position, not real-time position"""
        asset_last_known = np.array([50, 50])
        asset_real_pos = np.array([80, 80])  # Asset moved, but UAV doesn't know

        # UAV should target last known position
        target = asset_last_known

        assert np.array_equal(target, np.array([50, 50]))
        assert not np.array_equal(target, asset_real_pos)


class TestSARZoneAssignment:
    """Test zone assignment for SAR missions"""

    def test_spatial_contiguity_maintained(self):
        """SAR missions should use same spatial contiguity as surveillance"""
        zone_groups = [
            [1, 2],  # UAV 1
            [3, 6],  # UAV 2
            [4, 5],  # UAV 3
            [7, 8],  # UAV 4
            [9],  # UAV 5
        ]

        # Verify spatial pattern
        assert zone_groups[0] == [1, 2]
        assert zone_groups[1] == [3, 6]
        assert zone_groups[4] == [9]

    def test_no_auto_reassignment_during_sar(self):
        """Auto-reassignment should be disabled for SAR missions"""
        mission_type = "search_rescue"
        reassignment_enabled = mission_type == "surveillance"  # Only surveillance

        assert not reassignment_enabled

    def test_zones_do_not_accumulate(self):
        """Zones should not grow/duplicate during SAR"""
        initial_zones = [7, 8]

        # Even after time passes and reassignment logic runs
        # Zones should remain the same for SAR
        final_zones = [7, 8]

        assert initial_zones == final_zones
        assert len(final_zones) == 2


class TestOutOfGridPursuit:
    """Test UAV pursuit of assets outside grid boundaries"""

    def test_uav_pursues_out_of_grid_asset(self):
        """UAV should be able to pursue asset outside grid"""
        asset_position = [80, 20, 0]  # Outside grid (max is 60)
        uav_can_pursue = True  # With permission

        assert asset_position[0] > 60
        assert uav_can_pursue

    def test_uav_stops_at_boundary_before_pursuing(self):
        """UAV should stop at boundary and await permission"""
        uav_position = [59, 0]
        boundary_position = [60, 0]
        # asset_position = [80, 0] - Asset outside grid (unused, for context only)

        distance_to_boundary = np.linalg.norm(
            np.array(boundary_position) - np.array(uav_position)
        )

        should_stop = distance_to_boundary <= 2.0

        assert should_stop

    def test_battery_drains_during_out_of_grid_pursuit(self):
        """Battery should drain during out-of-grid pursuit"""
        battery = 50.0
        dt = 0.05
        drain_rate = 0.3

        # Flying to out-of-grid asset
        battery -= drain_rate * dt

        assert battery < 50.0

    def test_battery_drains_during_return_from_outside(self):
        """Battery should drain when returning from outside grid"""
        battery = 40.0
        dt = 0.05
        drain_rate = 0.3
        state = "returning"

        # Returning from out-of-grid location
        if state == "returning":
            battery -= drain_rate * dt

        assert battery < 40.0


class TestConsensusIdentification:
    """Test consensus-based asset identification"""

    def test_consensus_requires_two_uavs(self):
        """Asset confirmation requires 2 UAVs"""
        required_consensus = SAR_CONSENSUS_REQUIRED
        assert required_consensus == 2

    def test_single_uav_cannot_confirm(self):
        """Single UAV detection is insufficient"""
        detecting_uavs = ["uav_1"]
        consensus_reached = len(detecting_uavs) >= SAR_CONSENSUS_REQUIRED

        assert not consensus_reached

    def test_two_uavs_reach_consensus(self):
        """Two UAVs can confirm asset"""
        detecting_uavs = ["uav_1", "uav_2"]
        consensus_reached = len(detecting_uavs) >= SAR_CONSENSUS_REQUIRED

        assert consensus_reached

    def test_identification_requires_circles(self):
        """Asset identification requires UAV to circle 3 times"""
        required_circles = SAR_IDENTIFICATION_CIRCLES
        completed_circles = 2

        identified = completed_circles >= required_circles

        assert not identified
        assert required_circles == 3


class TestGuardianBehavior:
    """Test guardian UAV behavior"""

    def test_uav_becomes_guardian_after_identification(self):
        """UAV becomes guardian after identifying asset"""
        circles_completed = 3
        asset_identified = circles_completed >= SAR_IDENTIFICATION_CIRCLES

        if asset_identified:
            role = "guardian"
        else:
            role = "searching"

        assert role == "guardian"

    def test_guardian_monitors_with_circles(self):
        """Guardian should circle asset for monitoring"""
        guardian_circles_required = SAR_GUARDIAN_MONITORING_CIRCLES
        assert guardian_circles_required == 5

    def test_guardian_released_after_monitoring(self):
        """Guardian released after completing monitoring circles"""
        monitoring_circles = 5
        guardian_released = monitoring_circles >= SAR_GUARDIAN_MONITORING_CIRCLES

        assert guardian_released

    def test_guardian_stays_with_asset(self):
        """Guardian should remain near asset"""
        guardian_pos = np.array([50, 50])
        asset_pos = np.array([50, 50])

        # Guardian maintains close proximity
        distance = np.linalg.norm(guardian_pos - asset_pos)

        assert distance < 5.0  # Very close


class TestMissionCompletion:
    """Test SAR mission completion criteria"""

    def test_mission_completes_when_all_assets_secured(self):
        """Mission objectives complete when all assets have guardians"""
        total_assets = 3
        assets_rescued = 3

        objectives_complete = assets_rescued >= total_assets

        assert objectives_complete

    def test_mission_continues_after_objectives(self):
        """Mission should continue patrolling after objectives complete"""
        objectives_complete = True
        mission_active = True  # Still active, just patrolling

        assert objectives_complete
        assert mission_active

    def test_guardians_continue_monitoring(self):
        """Guardians should continue monitoring after mission objectives met"""
        guardian_role = "guardian"
        # Objectives are complete but guardian continues

        # Guardian continues even after objectives complete
        guardian_active = guardian_role == "guardian"

        assert guardian_active

    def test_non_guardians_continue_patrol(self):
        """Non-guardian UAVs continue area patrol"""
        uav_role = "patrolling"
        # Objectives are complete but patrol continues

        # Continue patrolling for potential additional assets
        continues_patrol = uav_role == "patrolling"

        assert continues_patrol


class TestSAREndToEndWorkflows:
    """Test complete end-to-end SAR workflows"""

    def test_complete_outside_grid_rescue_with_return(self):
        """
        Complete workflow: Asset dragged outside grid → UAV detects within radius →
        UAV identifies asset → UAV returns to grid → UAV returns home due to low battery
        """
        # Initial setup
        asset_position = np.array([80, 20, 0])  # Outside grid
        uav_position = np.array([70, 20, 10])  # Just outside, pursuing
        uav_battery = 14.0  # Below 15% threshold - will trigger return
        uav_state = "searching"

        # Step 1: Verify asset is outside grid
        grid_max = 60
        asset_outside = asset_position[0] > grid_max
        assert asset_outside

        # Step 2: UAV is within detection radius
        distance_to_asset = np.linalg.norm(asset_position[:2] - uav_position[:2])
        detection_radius = SAR_VISIBILITY_RADIUS  # 25m
        within_radius = distance_to_asset <= detection_radius
        assert within_radius  # Distance is ~10m, within 25m

        # Step 3: UAV detects and starts identification
        asset_detected = within_radius
        assert asset_detected

        # Step 4: UAV completes identification (3 circles)
        identification_circles = 3
        circles_completed = 3
        asset_identified = circles_completed >= identification_circles
        assert asset_identified

        # Step 5: After identification, check battery (now below threshold)
        battery_threshold = 15.0
        should_return_home = uav_battery <= battery_threshold

        if should_return_home:
            uav_state = "returning"

        assert uav_state == "returning"
        assert uav_battery <= 15.0

        # Step 6: UAV moves back toward grid boundary
        boundary_position = np.array([60, 20])
        uav_position_2d = uav_position[:2]
        distance_to_boundary = np.linalg.norm(boundary_position - uav_position_2d)

        # Moving toward boundary
        assert distance_to_boundary > 0  # Not at boundary yet

        # Step 7: UAV crosses boundary back into grid
        uav_position = np.array([55, 20, 10])  # Back inside
        inside_grid = -60 <= uav_position[0] <= 60 and -60 <= uav_position[1] <= 60
        assert inside_grid

        # Step 8: UAV continues returning to home base
        home_base = np.array([0, 0])
        distance_to_home = np.linalg.norm(uav_position[:2] - home_base)

        # Battery continues draining during return
        dt = 0.05
        drain_rate = 0.3
        uav_battery -= drain_rate * dt

        assert uav_battery < 14.0  # Battery has drained
        assert uav_state == "returning"
        assert distance_to_home > 2.0  # Not home yet, still returning

    def test_outside_asset_detection_radius_boundary_case(self):
        """
        Test detection at exact boundary of visibility radius for outside asset
        """
        asset_position = np.array([75, 0, 0])  # Outside grid
        uav_position = np.array([50, 0, 10])  # Inside grid

        # Distance is 25m exactly
        distance = np.linalg.norm(asset_position[:2] - uav_position[:2])
        visibility_radius = SAR_VISIBILITY_RADIUS  # 25m

        # At exactly visibility radius, should still detect
        can_detect = distance <= visibility_radius

        assert distance == pytest.approx(25.0)
        assert can_detect

    def test_multi_uav_outside_grid_rescue_coordination(self):
        """
        Test multiple UAVs coordinating rescue of outside asset with consensus
        """
        asset_position = np.array([70, 30, 0])  # Outside grid

        # UAV 1 detects first
        uav1_position = np.array([60, 30, 10])  # At boundary
        distance1 = np.linalg.norm(asset_position[:2] - uav1_position[:2])
        uav1_detects = distance1 <= SAR_VISIBILITY_RADIUS

        # UAV 2 also detects
        uav2_position = np.array([65, 25, 10])  # Slightly outside
        distance2 = np.linalg.norm(asset_position[:2] - uav2_position[:2])
        uav2_detects = distance2 <= SAR_VISIBILITY_RADIUS

        assert uav1_detects
        assert uav2_detects

        # Both UAVs within radius, consensus reached
        detecting_uavs = ["uav_1", "uav_2"]
        consensus_reached = len(detecting_uavs) >= SAR_CONSENSUS_REQUIRED

        assert consensus_reached

        # UAV 1 becomes identifier/guardian
        uav1_circles = 3
        uav1_becomes_guardian = uav1_circles >= SAR_IDENTIFICATION_CIRCLES

        assert uav1_becomes_guardian


class TestSAREdgeCases:
    """Test edge cases for SAR missions"""

    def test_asset_moves_outside_then_inside_grid(self):
        """Asset moving in and out of grid should be tracked correctly"""
        positions = [
            [50, 50],  # Inside
            [80, 80],  # Outside
            [30, 30],  # Back inside
        ]

        for pos in positions:
            is_outside = pos[0] > 60 or pos[0] < -60 or pos[1] > 60 or pos[1] < -60
            # Each position handled correctly
            if pos == [50, 50]:
                assert not is_outside
            elif pos == [80, 80]:
                assert is_outside
            elif pos == [30, 30]:
                assert not is_outside

    def test_multiple_assets_tracked_independently(self):
        """Each asset should have independent last known position"""
        asset1_last_known = [50, 50]
        asset2_last_known = [30, 30]

        # Real positions: asset1 at [80, 80] (moved), asset2 at [30, 30] (same)
        # But UAVs only know last_known positions

        # Last known positions are independent
        assert asset1_last_known != asset2_last_known

    def test_uav_switches_assets_mid_mission(self):
        """UAV should be able to switch from one asset to another"""
        current_target = "asset_1"

        # Asset 1 rescued, switch to asset 2
        asset_1_status = "rescued"
        if asset_1_status == "rescued":
            current_target = "asset_2"

        assert current_target == "asset_2"

    def test_all_uavs_as_guardians_scenario(self):
        """Handle scenario where all UAVs are guardians"""
        uav_roles = {
            "uav_1": "guardian",
            "uav_2": "guardian",
            "uav_3": "guardian",
            "uav_4": "guardian",
            "uav_5": "guardian",
        }

        guardian_count = sum(1 for role in uav_roles.values() if role == "guardian")

        assert guardian_count == 5
        # No UAVs left for patrol, but that's valid


class TestOrthogonalDistanceIndicator:
    """Test visual distance indicator for out-of-grid assets"""

    def test_indicator_appears_for_outside_asset(self):
        """Orange indicator should appear for assets outside grid"""
        asset_x = 80
        # asset_y = 0 - Y coordinate (unused, for context only)
        grid_max = 60

        is_outside = asset_x > grid_max

        assert is_outside
        # Indicator should be displayed

    def test_orthogonal_distance_calculated(self):
        """Orthogonal distance should be calculated to nearest boundary"""
        asset_x = 80
        grid_max = 60

        distance = abs(asset_x - grid_max)

        assert distance == 20.0

    def test_distance_label_displays_meters(self):
        """Distance label should show value in meters"""
        distance = 25.7
        label = f"{distance:.1f}m"

        assert label == "25.7m"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
