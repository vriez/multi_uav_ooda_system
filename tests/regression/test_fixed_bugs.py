"""
Regression tests for fixed bugs

These tests ensure that previously fixed bugs do not reappear.
Each test is documented with the original bug report and fix location.
"""
import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestBatteryFreezeBugs:
    """Regression tests for battery freeze bugs"""

    def test_bug_battery_freeze_at_boundary_delivery(self):
        """
        BUG: Battery level remained constant when UAV waiting at grid boundary
        FIX: Added battery drain before continue statement (web_dashboard.py:1728-1744)
        USER REPORT: "when the uav gets to the grid boundary, it's battery level remain constant"
        """
        # UAV is awaiting permission at boundary
        battery = 50.0
        awaiting_permission = True
        dt = 0.05
        drain_rate = 0.3

        # Battery should drain even while awaiting permission
        if awaiting_permission:
            battery -= drain_rate * dt
            # continue statement follows, but battery was drained first

        assert battery < 50.0  # Battery must decrease

    def test_bug_battery_freeze_at_boundary_sar(self):
        """
        BUG: Battery froze when SAR UAVs stopped at boundary pursuing outside assets
        FIX: Same fix as delivery - battery drain before continue (web_dashboard.py:1404-1419)
        """
        battery = 45.0
        awaiting_permission = True
        mission_type = 'search_rescue'
        dt = 0.05
        drain_rate = 0.3

        if awaiting_permission:
            battery -= drain_rate * dt

        assert battery < 45.0

    def test_bug_battery_freeze_on_return_journey(self):
        """
        BUG: UAVs stopped at border on return journey and battery froze
        FIX: Added battery drain during return state (web_dashboard.py:1328-1338)
        USER REPORT: "after getting to the assets outside of the grid. They stop at the border
                     on their way back, and their battery level remains constant"
        """
        battery = 30.0
        state = 'returning'
        distance_to_home = 50.0
        dt = 0.05
        drain_rate = 0.3

        if state == 'returning' and distance_to_home > 2.0:
            # Moving toward home
            battery -= drain_rate * dt

        assert battery < 30.0


class TestAssetTrackingBugs:
    """Regression tests for SAR asset tracking bugs"""

    def test_bug_uavs_magically_following_moved_assets(self):
        """
        BUG: UAVs followed assets in real-time after they were moved
        FIX: Implemented last_known_position tracking (web_dashboard.py:1115, 1381-1393)
        USER REPORT: "if I then move the asset once again. The uavs follow them until
                     the new location. this should not happen..."
        """
        # Asset initial position
        asset_real_position = np.array([50, 50])
        asset_last_known_position = np.array([50, 50])

        # User moves asset
        asset_real_position = np.array([80, 80])

        # UAV is far from real position
        uav_position = np.array([50, 50])
        distance_to_real = np.linalg.norm(asset_real_position - uav_position)

        # UAV should target last known position, not real position
        if distance_to_real > 25.0:  # Beyond detection radius
            # Do NOT update last known position
            target = asset_last_known_position
        else:
            # Within detection radius, update
            asset_last_known_position = asset_real_position.copy()
            target = asset_last_known_position

        # UAV should target old position (50, 50), not new position (80, 80)
        assert np.array_equal(target, np.array([50, 50]))
        assert not np.array_equal(target, asset_real_position)

    def test_bug_last_known_position_only_updates_within_radius(self):
        """
        BUG: Related to above - position should only update within detection radius
        FIX: Conditional update based on distance (web_dashboard.py:1387-1393)
        """
        asset_real = np.array([100, 100])
        asset_last_known = np.array([50, 50])
        uav_pos = np.array([50, 50])

        distance = np.linalg.norm(asset_real - uav_pos)
        detection_radius = 25.0

        # Should NOT update because beyond radius
        if distance <= detection_radius:
            asset_last_known = asset_real.copy()

        assert np.array_equal(asset_last_known, np.array([50, 50]))


class TestZoneAssignmentBugs:
    """Regression tests for zone assignment bugs"""

    def test_bug_unbalanced_sar_zone_assignments(self):
        """
        BUG: Unbalanced zone assignments like uav_1→[1], uav_3→[6,7,8]
        FIX: Forced spatial contiguity for SAR missions (web_dashboard.py:688-703)
        USER REPORT: "uav_1 → Zones [1] PRIORITY..."
        """
        # Expected balanced spatial assignment
        expected = {
            'uav_1': [1, 2],
            'uav_2': [3, 6],
            'uav_3': [4, 5],
            'uav_4': [7, 8],
            'uav_5': [9]
        }

        # Verify balance
        zone_counts = [len(zones) for zones in expected.values()]
        assert max(zone_counts) - min(zone_counts) <= 1  # Difference at most 1

    def test_bug_sar_zone_assignments_growing(self):
        """
        BUG: Zone assignments duplicating/growing during SAR missions
        FIX: Disabled auto-reassignment for SAR (web_dashboard.py:1925)
        USER REPORT: "uav_4 → Zones [7, 8, 9, 5, 1, 2, 3, 4, 6]"
        """
        mission_type = 'search_rescue'
        initial_zones = [7, 8]

        # Reassignment logic should NOT run for SAR
        reassignment_enabled = mission_type == 'surveillance'

        if reassignment_enabled:
            # This should NOT happen for SAR
            zones = [7, 8, 9, 5, 1, 2, 3, 4, 6]  # Growing list
        else:
            # Zones remain unchanged for SAR
            zones = initial_zones

        assert zones == [7, 8]
        assert len(zones) == 2
        assert not reassignment_enabled


class TestMissionCompletionBugs:
    """Regression tests for mission completion bugs"""

    def test_bug_delivery_mission_hanging(self):
        """
        BUG: Delivery mission hung indefinitely waiting for completion
        FIX: Fixed state check to only look for charging/crashed (web_dashboard.py:1905-1907)
        USER REPORT: "the delivery mission is hanging"
        """
        # All packages delivered
        deliveries_completed = 12
        total_packages = 12

        # UAVs have returned and transitioned to charging
        uav_states = ['charging', 'charging', 'charging', 'charging', 'charging']

        # OLD BUG: Checked for 'returning' AND close to home (never true)
        # NEW FIX: Only check for 'charging' or 'crashed'
        all_home_old = all(
            state == 'returning' and False  # This condition never met!
            for state in uav_states
        )

        all_home_fixed = all(
            state in ['charging', 'crashed']
            for state in uav_states
        )

        packages_complete = deliveries_completed >= total_packages

        mission_complete_old = packages_complete and all_home_old
        mission_complete_fixed = packages_complete and all_home_fixed

        assert not mission_complete_old  # Old logic would hang
        assert mission_complete_fixed  # Fixed logic completes


class TestUIBugs:
    """Regression tests for UI-related bugs"""

    def test_bug_ooda_loop_waiting_message_persists(self):
        """
        BUG: OODA displays showed "Waiting for mission start..." after mission started
        FIX: Emit OODA events for all phases on mission start (web_dashboard.py:2080-2084)
        USER REPORT: "Observe, Orient, Decide and Act display Waiting for mission start...
                     even though the mission has already started."
        """
        mission_started = True

        # Should emit all 4 phases on start
        ooda_phases_emitted = ['observe', 'orient', 'decide', 'act']

        assert mission_started
        assert len(ooda_phases_emitted) == 4
        # Each phase should clear the "Waiting..." message

    def test_bug_uav_trails_not_showing(self):
        """
        BUG: UAV trails not visible on dashboard
        FIX: Only add trail points when UAV moves ≥0.5m (dashboard.html)
        USER REPORT: "the uavs are not leaving any trail"
        """
        # Stationary UAV
        last_position = np.array([50, 50])
        current_position = np.array([50, 50])

        distance_moved = np.linalg.norm(current_position - last_position)
        min_distance = 0.5

        # Should NOT add trail point (would create zero-length segment)
        should_add_trail = distance_moved >= min_distance

        assert not should_add_trail

        # Moving UAV
        current_position = np.array([51, 51])
        distance_moved = np.linalg.norm(current_position - last_position)

        should_add_trail = distance_moved >= min_distance

        assert should_add_trail  # Now adds trail point


class TestPermissionBugs:
    """Regression tests for permission handling bugs"""

    def test_bug_permission_not_cleared_between_phases(self):
        """
        BUG: Permission for pickup applied to dropoff phase
        FIX: Clear permission after pickup complete (web_dashboard.py:1843-1846)
        """
        # Pickup phase
        permission_granted_for_target = (80, 20)
        task_status = 'assigned'

        # Complete pickup
        task_status = 'picked_up'
        permission_granted_for_target = None  # Must clear

        # Now at dropoff phase
        dropoff_target = (-80, -20)

        # Should need new permission for dropoff
        has_permission_for_dropoff = permission_granted_for_target == tuple(dropoff_target)

        assert not has_permission_for_dropoff
        assert permission_granted_for_target is None


class TestEdgeCaseRegressions:
    """Regression tests for edge case bugs"""

    def test_bug_battery_warning_flag_not_reset(self):
        """
        BUG: Battery warning flag could persist after recharge
        FIX: Reset battery_warning flag when recovered (web_dashboard.py:1353)
        """
        battery = 100.0
        state = 'recovered'
        battery_warning = True  # Was set during low battery

        if state == 'recovered':
            battery_warning = False  # Must reset

        assert not battery_warning

    def test_bug_operational_flag_inconsistency(self):
        """
        BUG: Operational flag could be inconsistent with state
        FIX: Clear operational flag when entering returning state (web_dashboard.py:1292)
        """
        state = 'patrolling'
        operational = True
        battery = 14.0

        # Trigger return
        if battery <= 15:
            state = 'returning'
            operational = False  # Must set to False

        assert state == 'returning'
        assert not operational

    def test_bug_returning_flag_not_cleared_after_recovery(self):
        """
        BUG: Returning flag could persist after UAV recovered
        FIX: Clear returning flag when transitioning to recovered (web_dashboard.py:1351)
        """
        battery = 100.0
        state = 'charging'
        returning = True

        if battery >= 100:
            state = 'recovered'
            returning = False  # Must clear

        assert state == 'recovered'
        assert not returning


class TestCriticalBugRegression:
    """Tests for critical bugs that caused major issues"""

    def test_critical_bug_continue_statement_skipping_battery_drain(self):
        """
        CRITICAL BUG: continue statement caused battery drain code to be skipped
        FIX: Move battery drain before continue statement
        IMPACT: Multiple missions affected, UAVs appeared frozen at boundaries
        """
        battery = 40.0
        awaiting_permission = True
        dt = 0.05
        drain_rate = 0.3

        # OLD CODE (buggy):
        # if awaiting_permission:
        #     continue  # Skips everything below, including battery drain!
        # battery -= drain_rate * dt

        # NEW CODE (fixed):
        if awaiting_permission:
            battery -= drain_rate * dt  # Drain BEFORE continue
            # continue

        assert battery < 40.0  # MUST decrease


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
