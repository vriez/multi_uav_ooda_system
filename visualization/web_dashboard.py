"""
Realistic Mission Completion Assistance - Web Dashboard

Author: Vítor EULÁLIO REIS

Advanced multi-UAV coordination system with workload distribution,
recovery management, and mission-specific behavioral adaptations.
"""
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import time
import numpy as np
from collections import defaultdict
import logging

# Import configuration constants
# Support both direct script execution and module execution
try:
    # When run as module: python -m visualization.web_dashboard
    from .config import (
        # Simulation timing
        LOOP_REAL_INTERVAL,
        TELEMETRY_INTERVAL,
        OODA_LOOP_INTERVAL,
        # UAV performance
        BASE_CRUISE_SPEED,
        BASE_RETURN_SPEED,
        BASE_BATTERY_DRAIN,
        DELIVERY_CRUISE_SPEED,
        DELIVERY_RETURN_SPEED,
        # Thresholds
        WAYPOINT_ARRIVAL_THRESHOLD,
        HOME_ARRIVAL_THRESHOLD,
        HOME_PROXIMITY_THRESHOLD,
        DELIVERY_ARRIVAL_THRESHOLD,
        BATTERY_LOW_THRESHOLD,
        BATTERY_CRITICAL_THRESHOLD,
        BATTERY_FULL_LEVEL,
        BATTERY_CHARGE_RATE,
        # SAR constants
        SAR_VISIBILITY_RADIUS,
        SAR_DETECTION_RADIUS,
        SAR_SEARCH_REDUCTION_RATE,
        SAR_CONSENSUS_REQUIRED,
        SAR_IDENTIFICATION_CIRCLES,
        SAR_GUARDIAN_MONITORING_CIRCLES,
        # Grid and zones
        GRID_SIZE,
        DEFAULT_NUM_ZONES,
        ZONE_COVERAGE_THRESHOLD,
        # Delivery
        DEFAULT_NUM_PACKAGES,
        DELIVERY_TIME_WINDOW,
        DELIVERY_PRIORITY_HIGH,
        DELIVERY_PRIORITY_NORMAL,
        # Patterns
        PATROL_PATTERNS,
        PATTERN_MODES,
        DEFAULT_PATROL_PATTERN,
        DEFAULT_PATTERN_MODE,
        # Scenarios
        SCENARIOS,
        # UAV states
        UAV_STATE_IDLE,
        UAV_STATE_DEPLOYING,
        UAV_STATE_PATROLLING,
        UAV_STATE_RETURNING,
        UAV_STATE_CHARGING,
        UAV_STATE_RECOVERED,
        UAV_STATE_CRASHED,
        UAV_STATE_DELIVERING,
        UAV_STATE_SEARCHING,
        UAV_STATE_AWAITING_PERMISSION,
        VALID_UAV_STATES,
        # Asset states
        ASSET_STATE_UNIDENTIFIED,
        ASSET_STATE_IDENTIFIED,
        ASSET_STATE_RESCUED,
        # Flask/SocketIO config
        FLASK_SECRET_KEY,
        SOCKETIO_PING_TIMEOUT,
        SOCKETIO_PING_INTERVAL,
        SOCKETIO_CORS_ORIGINS,
        # Logging
        LOG_LEVEL,
        LOG_FORMAT,
        # Defaults
        DEFAULT_HOME_BASE,
        DEFAULT_SIMULATION_SPEED,
        DEFAULT_SCENARIO,
        # Workload balancer
        REBALANCE_INTERVAL
    )
except ImportError:
    # When run as script: python visualization/web_dashboard.py
    from config import (
        # Simulation timing
        LOOP_REAL_INTERVAL,
        TELEMETRY_INTERVAL,
        OODA_LOOP_INTERVAL,
        # UAV performance
        BASE_CRUISE_SPEED,
        BASE_RETURN_SPEED,
        BASE_BATTERY_DRAIN,
        DELIVERY_CRUISE_SPEED,
        DELIVERY_RETURN_SPEED,
        # Thresholds
        WAYPOINT_ARRIVAL_THRESHOLD,
        HOME_ARRIVAL_THRESHOLD,
        HOME_PROXIMITY_THRESHOLD,
        DELIVERY_ARRIVAL_THRESHOLD,
        BATTERY_LOW_THRESHOLD,
        BATTERY_CRITICAL_THRESHOLD,
        BATTERY_FULL_LEVEL,
        BATTERY_CHARGE_RATE,
        # SAR constants
        SAR_VISIBILITY_RADIUS,
        SAR_DETECTION_RADIUS,
        SAR_SEARCH_REDUCTION_RATE,
        SAR_CONSENSUS_REQUIRED,
        SAR_IDENTIFICATION_CIRCLES,
        SAR_GUARDIAN_MONITORING_CIRCLES,
        # Grid and zones
        GRID_SIZE,
        DEFAULT_NUM_ZONES,
        ZONE_COVERAGE_THRESHOLD,
        # Delivery
        DEFAULT_NUM_PACKAGES,
        DELIVERY_TIME_WINDOW,
        DELIVERY_PRIORITY_HIGH,
        DELIVERY_PRIORITY_NORMAL,
        # Patterns
        PATROL_PATTERNS,
        PATTERN_MODES,
        DEFAULT_PATROL_PATTERN,
        DEFAULT_PATTERN_MODE,
        # Scenarios
        SCENARIOS,
        # UAV states
        UAV_STATE_IDLE,
        UAV_STATE_DEPLOYING,
        UAV_STATE_PATROLLING,
        UAV_STATE_RETURNING,
        UAV_STATE_CHARGING,
        UAV_STATE_RECOVERED,
        UAV_STATE_CRASHED,
        UAV_STATE_DELIVERING,
        UAV_STATE_SEARCHING,
        UAV_STATE_AWAITING_PERMISSION,
        VALID_UAV_STATES,
        # Asset states
        ASSET_STATE_UNIDENTIFIED,
        ASSET_STATE_IDENTIFIED,
        ASSET_STATE_RESCUED,
        # Flask/SocketIO config
        FLASK_SECRET_KEY,
        SOCKETIO_PING_TIMEOUT,
        SOCKETIO_PING_INTERVAL,
        SOCKETIO_CORS_ORIGINS,
        # Logging
        LOG_LEVEL,
        LOG_FORMAT,
        # Defaults
        DEFAULT_HOME_BASE,
        DEFAULT_SIMULATION_SPEED,
        DEFAULT_SCENARIO,
        # Workload balancer
        REBALANCE_INTERVAL
    )

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
socketio = SocketIO(
    app,
    cors_allowed_origins=SOCKETIO_CORS_ORIGINS,
    ping_timeout=SOCKETIO_PING_TIMEOUT,
    ping_interval=SOCKETIO_PING_INTERVAL,
    max_http_buffer_size=50000000,  # 50MB buffer to handle larger payloads
    async_mode='threading',  # Use threading mode for better payload handling
    logger=False,  # Disable verbose logging to reduce overhead
    engineio_logger=False  # Disable engine.io logging
)

# Track connected clients
connected_clients = set()

# Mission state
mission_active = False
scenario_type = DEFAULT_SCENARIO
simulation_speed = DEFAULT_SIMULATION_SPEED
patrol_pattern = DEFAULT_PATROL_PATTERN
pattern_mode = DEFAULT_PATTERN_MODE

# Timing trackers
last_reassignment_time = time.time()
last_telemetry_time = time.time()
home_base = DEFAULT_HOME_BASE.copy()

# Mission data
uavs = {}
tasks = {}
ooda_count = 0
mission_start_time = 0
mission_metrics = {
    'targets_found': 0,
    'detection_times': [],
    'deliveries_completed': 0,
    'deliveries_on_time': 0,
    'total_packages': 0,
    'final_return_initiated': False,
    'assets_rescued': 0
}

# =============================================================================
# GRID BOUNDARY SAFETY CONSTANTS AND HELPERS
# =============================================================================
GRID_MIN = -60  # Grid boundary minimum (meters)
GRID_MAX = 60   # Grid boundary maximum (meters)

def is_position_outside_grid(position):
    """
    Check if a position is outside the grid boundaries.

    Args:
        position: [x, y] or [x, y, z] position coordinates

    Returns:
        bool: True if position is outside grid bounds, False otherwise
    """
    x, y = position[0], position[1]
    return x < GRID_MIN or x > GRID_MAX or y < GRID_MIN or y > GRID_MAX

def calculate_boundary_intersection(start_pos, target_pos):
    """
    Calculate the intersection point where a line from start to target crosses the grid boundary.

    Args:
        start_pos: [x, y] starting position (inside grid)
        target_pos: [x, y] target position (outside grid)

    Returns:
        [x, y]: Intersection point at grid boundary
    """
    x1, y1 = start_pos[0], start_pos[1]
    x2, y2 = target_pos[0], target_pos[1]

    # Calculate line direction
    dx = x2 - x1
    dy = y2 - y1

    # Find which boundary will be crossed first
    t_min = float('inf')
    boundary_x, boundary_y = x1, y1

    # Check X boundaries
    if dx != 0:
        if dx > 0:  # Moving towards GRID_MAX
            t = (GRID_MAX - x1) / dx
        else:  # Moving towards GRID_MIN
            t = (GRID_MIN - x1) / dx

        if 0 < t < t_min:
            t_min = t
            boundary_x = x1 + t * dx
            boundary_y = y1 + t * dy

    # Check Y boundaries
    if dy != 0:
        if dy > 0:  # Moving towards GRID_MAX
            t = (GRID_MAX - y1) / dy
        else:  # Moving towards GRID_MIN
            t = (GRID_MIN - y1) / dy

        if 0 < t < t_min:
            t_min = t
            boundary_x = x1 + t * dx
            boundary_y = y1 + t * dy

    # Clamp to ensure we don't exceed boundaries due to floating point errors
    boundary_x = max(GRID_MIN, min(GRID_MAX, boundary_x))
    boundary_y = max(GRID_MIN, min(GRID_MAX, boundary_y))

    return [boundary_x, boundary_y]

class WorkloadBalancer:
    """
    Manages UAV workload distribution and rebalancing across mission zones.

    Attributes:
        last_rebalance_time (float): Timestamp of last rebalance operation
        rebalance_interval (float): Seconds between rebalancing attempts
    """
    def __init__(self):
        self.last_rebalance_time = 0
        self.rebalance_interval = REBALANCE_INTERVAL
    
    def compute_zone_contour(self, zone_ids, tasks, pattern=None, mode=None):
        """
        Compute a patrol path based on the selected pattern and mode.
        Patterns: perimeter, lawnmower, spiral, creeping, random, figure8, sector
        Modes: per_zone (pattern per zone), grouped (pattern across combined area, clipped to actual zones)
        """
        global patrol_pattern, pattern_mode
        if pattern is None:
            pattern = patrol_pattern
        if mode is None:
            mode = pattern_mode
            
        if not zone_ids:
            return []
        
        # Get zone centers
        zone_centers = {}
        for zid in zone_ids:
            if zid in tasks:
                zone_centers[zid] = tasks[zid]['center'][:2]
        
        if not zone_centers:
            return []
        
        waypoints = []
        
        if mode == 'grouped' and len(zone_ids) > 1:
            # GROUPED MODE: Generate pattern across bounding box, then clip to actual zones
            min_x = float('inf')
            max_x = float('-inf')
            min_y = float('inf')
            max_y = float('-inf')
            
            # Build list of zone bounds for clipping
            zone_bounds = []
            for zid in zone_ids:
                if zid in tasks:
                    cx, cy = tasks[zid]['center'][:2]
                    size = tasks[zid]['size'] / 2
                    zone_bounds.append({
                        'min_x': cx - size,
                        'max_x': cx + size,
                        'min_y': cy - size,
                        'max_y': cy + size,
                        'cx': cx,
                        'cy': cy,
                        'size': size
                    })
                    min_x = min(min_x, cx - size)
                    max_x = max(max_x, cx + size)
                    min_y = min(min_y, cy - size)
                    max_y = max(max_y, cy + size)
            
            # Generate clipped pattern based on type
            waypoints = self._generate_grouped_pattern(
                pattern, zone_bounds, min_x, max_x, min_y, max_y)
        
        else:
            # PER ZONE MODE: Apply pattern to each zone separately
            ordered_zones = self._order_zones_nearest(zone_centers)
            
            for zid in ordered_zones:
                cx, cy = zone_centers[zid]
                size = tasks[zid]['size'] / 2 - 5
                zone_waypoints = self._generate_pattern_waypoints(pattern, cx, cy, size, size)
                waypoints.extend(zone_waypoints)
        
        return waypoints
    
    def _point_in_zones(self, x, y, zone_bounds, margin=5):
        """Check if a point is inside any of the zones (with margin)."""
        for zb in zone_bounds:
            if (zb['min_x'] - margin <= x <= zb['max_x'] + margin and
                zb['min_y'] - margin <= y <= zb['max_y'] + margin):
                return True
        return False
    
    def _clip_line_to_zones(self, x1, y1, x2, y2, zone_bounds):
        """
        Clip a horizontal or vertical line segment to only include parts inside zones.
        Returns list of (start, end) segments.
        """
        segments = []
        
        # Handle horizontal lines (y1 == y2)
        if abs(y1 - y2) < 0.1:
            y = y1
            x_start, x_end = min(x1, x2), max(x1, x2)
            
            # Find all x-ranges that intersect with zones at this y
            for zb in zone_bounds:
                if zb['min_y'] <= y <= zb['max_y']:
                    seg_start = max(x_start, zb['min_x'])
                    seg_end = min(x_end, zb['max_x'])
                    if seg_start < seg_end:
                        segments.append((seg_start, seg_end, y, y))
        
        # Handle vertical lines (x1 == x2)
        elif abs(x1 - x2) < 0.1:
            x = x1
            y_start, y_end = min(y1, y2), max(y1, y2)
            
            # Find all y-ranges that intersect with zones at this x
            for zb in zone_bounds:
                if zb['min_x'] <= x <= zb['max_x']:
                    seg_start = max(y_start, zb['min_y'])
                    seg_end = min(y_end, zb['max_y'])
                    if seg_start < seg_end:
                        segments.append((x, x, seg_start, seg_end))
        
        return segments
    
    def _generate_grouped_pattern(self, pattern, zone_bounds, min_x, max_x, min_y, max_y):
        """Generate pattern for grouped zones, clipped to actual zone areas."""
        waypoints = []
        margin = 5
        
        if pattern == 'lawnmower':
            # Horizontal rows, clipped to zones
            height = max_y - min_y
            rows = max(4, int(height / 10))
            step = height / rows
            
            for i in range(rows):
                y = max_y - (i * step) - step/2
                
                # Get all segments at this y that are inside zones
                segments = self._clip_line_to_zones(min_x, y, max_x, y, zone_bounds)
                
                # Sort segments by x position
                segments.sort(key=lambda s: s[0])
                
                # Add waypoints for each segment (alternating direction)
                for seg in segments:
                    if i % 2 == 0:
                        waypoints.append([seg[0] + margin, y])
                        waypoints.append([seg[1] - margin, y])
                    else:
                        waypoints.append([seg[1] - margin, y])
                        waypoints.append([seg[0] + margin, y])
        
        elif pattern == 'creeping':
            # Vertical columns, clipped to zones
            width = max_x - min_x
            cols = max(4, int(width / 10))
            step = width / cols
            
            for i in range(cols):
                x = min_x + (i * step) + step/2
                
                # Get all segments at this x that are inside zones
                segments = self._clip_line_to_zones(x, min_y, x, max_y, zone_bounds)
                
                # Sort segments by y position
                segments.sort(key=lambda s: s[2])
                
                # Add waypoints for each segment
                for seg in segments:
                    waypoints.append([x, seg[3] - margin])  # Top of segment
                    waypoints.append([x, seg[2] + margin])  # Bottom of segment
        
        elif pattern == 'perimeter':
            # Visit perimeter of each zone in sequence
            for zb in zone_bounds:
                m = margin
                waypoints.append([zb['min_x'] + m, zb['max_y'] - m])
                waypoints.append([zb['max_x'] - m, zb['max_y'] - m])
                waypoints.append([zb['max_x'] - m, zb['min_y'] + m])
                waypoints.append([zb['min_x'] + m, zb['min_y'] + m])
        
        elif pattern == 'spiral':
            # Spiral within each zone, connected
            for zb in zone_bounds:
                cx, cy = zb['cx'], zb['cy']
                size = zb['size'] - margin
                layers = 3
                for j in range(layers):
                    s = size * (1 - j / layers)
                    if s <= 0:
                        break
                    waypoints.append([cx - s, cy + s])
                    waypoints.append([cx + s, cy + s])
                    waypoints.append([cx + s, cy - s])
                    waypoints.append([cx - s, cy - s])
                waypoints.append([cx, cy])
        
        elif pattern == 'random':
            # Random points within each zone
            for zb in zone_bounds:
                cx, cy = zb['cx'], zb['cy']
                size = zb['size'] - margin
                np.random.seed(int(cx * 100 + cy))
                for _ in range(8):
                    rx = cx + np.random.uniform(-size, size)
                    ry = cy + np.random.uniform(-size, size)
                    waypoints.append([rx, ry])
        
        elif pattern == 'figure8':
            # Figure-8 in each zone
            for zb in zone_bounds:
                cx, cy = zb['cx'], zb['cy']
                s = (zb['size'] - margin) * 0.7
                waypoints.extend([
                    [cx, cy + s], [cx + s, cy + s/2], [cx, cy],
                    [cx - s, cy - s/2], [cx, cy - s], [cx + s, cy - s/2],
                    [cx, cy], [cx - s, cy + s/2]
                ])
        
        elif pattern == 'sector':
            # Radial sweeps in each zone
            for zb in zone_bounds:
                cx, cy = zb['cx'], zb['cy']
                size = zb['size'] - margin
                angles = [0, 45, 90, 135, 180, 225, 270, 315]
                for angle in angles:
                    rad = np.radians(angle)
                    waypoints.append([cx, cy])
                    waypoints.append([cx + size * np.cos(rad), cy + size * np.sin(rad)])
        
        else:
            # Fallback to perimeter
            return self._generate_grouped_pattern('perimeter', zone_bounds, min_x, max_x, min_y, max_y)
        
        return waypoints
    
    def _generate_pattern_waypoints(self, pattern, cx, cy, size_x, size_y):
        """Generate waypoints for a pattern with potentially rectangular area."""
        if pattern == 'perimeter':
            return self._pattern_perimeter(cx, cy, size_x, size_y)
        elif pattern == 'lawnmower':
            return self._pattern_lawnmower(cx, cy, size_x, size_y)
        elif pattern == 'spiral':
            return self._pattern_spiral(cx, cy, size_x, size_y)
        elif pattern == 'creeping':
            return self._pattern_creeping(cx, cy, size_x, size_y)
        elif pattern == 'random':
            return self._pattern_random(cx, cy, size_x, size_y)
        elif pattern == 'figure8':
            return self._pattern_figure8(cx, cy, size_x, size_y)
        elif pattern == 'sector':
            return self._pattern_sector(cx, cy, size_x, size_y)
        else:
            return self._pattern_perimeter(cx, cy, size_x, size_y)
    
    def _order_zones_nearest(self, zone_centers):
        """Order zones using nearest neighbor algorithm."""
        if not zone_centers:
            return []
        
        ordered = []
        remaining = list(zone_centers.keys())
        current = remaining.pop(0)
        ordered.append(current)
        
        while remaining:
            current_pos = zone_centers[current]
            nearest = min(remaining, key=lambda zid: 
                         (zone_centers[zid][0] - current_pos[0])**2 + 
                         (zone_centers[zid][1] - current_pos[1])**2)
            ordered.append(nearest)
            remaining.remove(nearest)
            current = nearest
        
        return ordered
    
    def _pattern_perimeter(self, cx, cy, size_x, size_y=None):
        """Rectangle around zone boundary."""
        if size_y is None:
            size_y = size_x
        return [
            [cx - size_x, cy + size_y],  # Top-left
            [cx + size_x, cy + size_y],  # Top-right
            [cx + size_x, cy - size_y],  # Bottom-right
            [cx - size_x, cy - size_y],  # Bottom-left
        ]
    
    def _pattern_lawnmower(self, cx, cy, size_x, size_y=None, rows=4):
        """Back-and-forth horizontal rows."""
        if size_y is None:
            size_y = size_x
        waypoints = []
        # Scale rows based on area height
        actual_rows = max(4, int(rows * (size_y / 15)))
        step = (2 * size_y) / actual_rows
        for i in range(actual_rows):
            y = cy + size_y - (i * step) - step/2
            if i % 2 == 0:
                waypoints.append([cx - size_x, y])
                waypoints.append([cx + size_x, y])
            else:
                waypoints.append([cx + size_x, y])
                waypoints.append([cx - size_x, y])
        return waypoints
    
    def _pattern_spiral(self, cx, cy, size_x, size_y=None, layers=3):
        """Inward spiral pattern."""
        if size_y is None:
            size_y = size_x
        waypoints = []
        # Scale layers based on area size
        actual_layers = max(3, int(layers * (max(size_x, size_y) / 15)))
        for i in range(actual_layers):
            sx = size_x * (1 - i / actual_layers)
            sy = size_y * (1 - i / actual_layers)
            if sx <= 0 or sy <= 0:
                break
            waypoints.append([cx - sx, cy + sy])  # Top-left
            waypoints.append([cx + sx, cy + sy])  # Top-right
            waypoints.append([cx + sx, cy - sy])  # Bottom-right
            waypoints.append([cx - sx, cy - sy])  # Bottom-left
        waypoints.append([cx, cy])  # End at center
        return waypoints
    
    def _pattern_creeping(self, cx, cy, size_x, size_y=None, cols=4):
        """Parallel vertical lines (top to bottom)."""
        if size_y is None:
            size_y = size_x
        waypoints = []
        # Scale columns based on area width
        actual_cols = max(4, int(cols * (size_x / 15)))
        step = (2 * size_x) / actual_cols
        for i in range(actual_cols):
            x = cx - size_x + (i * step) + step/2
            waypoints.append([x, cy + size_y])  # Top
            waypoints.append([x, cy - size_y])  # Bottom
        return waypoints
    
    def _pattern_random(self, cx, cy, size_x, size_y=None, points=8):
        """Random points within zone."""
        if size_y is None:
            size_y = size_x
        waypoints = []
        # Scale points based on area
        actual_points = max(8, int(points * (size_x * size_y) / 225))
        np.random.seed(int(cx * 100 + cy))  # Consistent randomness per zone
        for _ in range(actual_points):
            rx = cx + np.random.uniform(-size_x, size_x)
            ry = cy + np.random.uniform(-size_y, size_y)
            waypoints.append([rx, ry])
        return waypoints
    
    def _pattern_figure8(self, cx, cy, size_x, size_y=None):
        """Figure-8 pattern through zone center."""
        if size_y is None:
            size_y = size_x
        sx = size_x * 0.7
        sy = size_y * 0.7
        return [
            [cx, cy + sy],           # Top center
            [cx + sx, cy + sy/2],    # Top-right
            [cx, cy],                # Center (cross point)
            [cx - sx, cy - sy/2],    # Bottom-left
            [cx, cy - sy],           # Bottom center
            [cx + sx, cy - sy/2],    # Bottom-right
            [cx, cy],                # Center (cross point)
            [cx - sx, cy + sy/2],    # Top-left
        ]
    
    def _pattern_sector(self, cx, cy, size_x, size_y=None):
        """Radial sweeps from zone center."""
        if size_y is None:
            size_y = size_x
        waypoints = []
        angles = [0, 45, 90, 135, 180, 225, 270, 315]
        for angle in angles:
            rad = np.radians(angle)
            waypoints.append([cx, cy])  # Return to center
            waypoints.append([cx + size_x * np.cos(rad), cy + size_y * np.sin(rad)])
        return waypoints
    
    def assign_initial_workload(self, uavs, tasks):
        """Assign zones to UAVs (spatially contiguous or priority-based)"""
        operational_uavs = [uid for uid, u in uavs.items() if u['operational']]

        if not operational_uavs:
            return []

        # Clear all assignments
        for zone in tasks.values():
            zone['assigned_uavs'] = []
        for uav in uavs.values():
            uav['assigned_zones'] = []
            uav['current_zone_idx'] = 0
            uav['state'] = 'deploying'

        num_zones = len(tasks)
        num_uavs = len(operational_uavs)

        # SPATIAL CONTIGUITY ALLOCATION (Both Surveillance and SAR)
        # Always use spatial allocation for balanced zone assignments
        if num_zones == 9 and num_uavs == 5:
            # Standard 9-zone, 5-UAV layout - spatially contiguous
            zone_groups = [
                [1, 2],      # UAV 1: Top left-middle (2 zones)
                [3, 6],      # UAV 2: Right column (2 zones)
                [4, 5],      # UAV 3: Middle left-center (2 zones)
                [7, 8],      # UAV 4: Bottom left-middle (2 zones)
                [9]          # UAV 5: Bottom right (1 zone)
            ]
        else:
            # Generic: Distribute zones evenly
            zone_groups = [[] for _ in range(num_uavs)]
            for i, zid in enumerate(sorted(tasks.keys())):
                zone_groups[i % num_uavs].append(zid)

        assignments = []
        uav_list = sorted(operational_uavs)

        # Assign groups and compute contours
        for i, uav_id in enumerate(uav_list):
            if i < len(zone_groups):
                assigned = [z for z in zone_groups[i] if z in tasks]
                if not assigned:
                    continue

                uavs[uav_id]['assigned_zones'] = assigned

                # Compute contour for this zone group
                contour_waypoints = self.compute_zone_contour(assigned, tasks)
                uavs[uav_id]['contour_waypoints'] = contour_waypoints
                uavs[uav_id]['waypoint_idx'] = 0

                for zone_id in assigned:
                    tasks[zone_id]['assigned_uavs'].append(uav_id)
                assignments.append(assigned)
                logger.info(f"{uav_id} assigned zones {assigned} ({['priority' if tasks[z].get('priority', 1) > 1 else 'normal' for z in assigned]}) with {len(contour_waypoints)} waypoints")

        return assignments
    
    def reassign_recovered_uav(self, uav_id, uavs, tasks):
        """
        Re-assigns a recovered UAV to ALL unassigned zones first,
        then steals from overloaded UAVs if needed for balance.
        """
        
        if not tasks:
            logger.warning(f"No tasks available to reassign {uav_id}.")
            return []
        
        # 1. Find all unassigned zones (no operational UAV patrolling them)
        unassigned_zones = []
        for zid, task in tasks.items():
            # Skip asset tasks - only process zone tasks
            if task.get('type') == 'asset':
                continue
            # Skip delivery package/zone tasks (string IDs only)
            if isinstance(zid, str) and (zid.startswith('pkg_') or zid.startswith('zone_')):
                continue

            active_uavs = [uid for uid in task.get('assigned_uavs', [])
                          if uid in uavs and uavs[uid]['operational']
                          and uavs[uid]['state'] in ['deploying', 'patrolling', 'searching']]
            if not active_uavs:
                unassigned_zones.append(zid)
        
        # 2. If there are unassigned zones, assign them all to this UAV
        if unassigned_zones:
            # Sort by coverage (lowest first) if available, otherwise by zone ID
            unassigned_zones.sort(key=lambda zid: tasks[zid].get('coverage', 0))
            
            # Limit to reasonable number per UAV (max 2-3 zones)
            zones_to_assign = unassigned_zones[:3]
            
            logger.info(f"{uav_id} taking unassigned zones: {zones_to_assign}")
            
            # Clear old assignments for these zones
            for zid in zones_to_assign:
                tasks[zid]['assigned_uavs'] = []
            
            # Assign zones to recovered UAV
            uavs[uav_id]['assigned_zones'] = zones_to_assign
            for zid in zones_to_assign:
                tasks[zid]['assigned_uavs'].append(uav_id)
            
            log_message = f"{uav_id} assigned to unassigned zones {zones_to_assign}"
        
        else:
            # 3. All zones are covered - steal from the heaviest loaded UAV
            # Find the UAV with the most zones
            operational_uavs = [uid for uid, u in uavs.items() 
                               if u['operational'] and u['state'] in ['deploying', 'patrolling']
                               and len(u['assigned_zones']) > 1]
            
            if operational_uavs:
                heaviest_uav = max(operational_uavs, key=lambda uid: len(uavs[uid]['assigned_zones']))
                
                # Take half of their zones (at least 1)
                zones_to_steal = uavs[heaviest_uav]['assigned_zones'][:len(uavs[heaviest_uav]['assigned_zones'])//2 + 1]
                
                # Remove from heavy UAV
                for zid in zones_to_steal:
                    if zid in uavs[heaviest_uav]['assigned_zones']:
                        uavs[heaviest_uav]['assigned_zones'].remove(zid)
                    if zid in tasks and heaviest_uav in tasks[zid]['assigned_uavs']:
                        tasks[zid]['assigned_uavs'].remove(heaviest_uav)
                
                # Recompute contour for heavy UAV
                uavs[heaviest_uav]['contour_waypoints'] = self.compute_zone_contour(
                    uavs[heaviest_uav]['assigned_zones'], tasks)
                uavs[heaviest_uav]['waypoint_idx'] = 0
                
                # Assign to recovered UAV
                uavs[uav_id]['assigned_zones'] = zones_to_steal
                for zid in zones_to_steal:
                    tasks[zid]['assigned_uavs'].append(uav_id)
                
                log_message = f"{uav_id} stole zones {zones_to_steal} from {heaviest_uav}"
            else:
                # Fallback: just take the least covered zone
                sorted_zones = sorted(tasks.keys(), key=lambda zid: tasks[zid].get('coverage', 0))
                target_zone = sorted_zones[0]
                
                uavs[uav_id]['assigned_zones'] = [target_zone]
                tasks[target_zone]['assigned_uavs'].append(uav_id)
                
                log_message = f"{uav_id} assigned to zone {target_zone} (fallback)"
        
        # 4. Set recovered UAV state and compute patrol path
        uavs[uav_id]['contour_waypoints'] = self.compute_zone_contour(uavs[uav_id]['assigned_zones'], tasks)
        uavs[uav_id]['waypoint_idx'] = 0
        uavs[uav_id]['state'] = 'deploying'
        uavs[uav_id]['operational'] = True
        
        logger.info(log_message)
        return [f"{uav_id} → Zones {uavs[uav_id]['assigned_zones']} (Re-assigned)"]
    
    
    def redistribute_failed_zones(self, failed_zones, operational_uavs, uavs, tasks):
        """Redistribute to nearest neighbor maintaining contiguity"""
        if not failed_zones or not operational_uavs:
            return []
        
        assignments = []
        adjacency = {
            1: [2, 4], 2: [1, 3, 5], 3: [2, 6],
            4: [1, 5, 7], 5: [2, 4, 6, 8], 6: [3, 5, 9],
            7: [4, 8], 8: [5, 7, 9], 9: [6, 8]
        }
        
        # Sort zones by priority: assign zones with fewer adjacent options first
        sorted_zones = sorted(failed_zones, key=lambda z: len(adjacency.get(z, [])))
        
        for failed_zone in sorted_zones:
            candidates = []
            adjacent_zones = adjacency.get(failed_zone, [])
            
            for uav_id in operational_uavs:
                if uavs[uav_id]['battery'] < 20:
                    continue
                
                uav_zones = uavs[uav_id]['assigned_zones']
                has_adjacent = any(z in adjacent_zones for z in uav_zones)
                
                # Score: (adjacency_penalty, current_load)
                adjacency_score = 0 if has_adjacent else 100
                load_score = len(uav_zones)
                
                candidates.append((uav_id, adjacency_score, load_score))
            
            if candidates:
                # Pick best: prefer adjacent zones, then lighter load
                best_uav = min(candidates, key=lambda x: (x[1], x[2]))[0]
                
                uavs[best_uav]['assigned_zones'].append(failed_zone)
                tasks[failed_zone]['assigned_uavs'].append(best_uav)
                
                # Recompute contour (now using the robust bounding box logic)
                new_contour = self.compute_zone_contour(uavs[best_uav]['assigned_zones'], tasks)
                uavs[best_uav]['contour_waypoints'] = new_contour
                uavs[best_uav]['waypoint_idx'] = 0
                
                assignments.append(f"{best_uav} + Zone {failed_zone}")
                logger.info(f"Assigned zone {failed_zone} to {best_uav}")
            else:
                logger.error(f"No candidates for zone {failed_zone}")
        
        return assignments
    
    def get_current_assignments(self, uavs, tasks=None, scenario_type='surveillance'):
        """Get formatted assignments for display"""
        assignments = []

        if scenario_type == 'delivery':
            # Show delivery task assignments with clear status
            for uav_id in sorted(uavs.keys()):
                uav = uavs[uav_id]
                if uav.get('assigned_task'):
                    task_id = uav['assigned_task']
                    if tasks and task_id in tasks:
                        task = tasks[task_id]
                        status = task.get('status', 'unknown')

                        # Status indicators
                        if status == 'assigned':
                            icon = '→'
                            desc = 'Going to pickup'
                        elif status == 'picked_up':
                            icon = '✓'
                            desc = 'Delivering'
                        elif status == 'delivered':
                            icon = '✓'
                            desc = 'Delivered'
                        else:
                            icon = '?'
                            desc = status

                        # Package count
                        delivered = uav.get('packages_delivered', 0)
                        assignments.append(f"{uav_id} {icon} Pkg#{task_id} | {desc} | Total:{delivered}")
                    else:
                        assignments.append(f"{uav_id} → Package #{task_id}")
                elif uav['state'] == 'idle':
                    delivered = uav.get('packages_delivered', 0)
                    assignments.append(f"{uav_id} → IDLE (waiting) | Delivered:{delivered}")
                elif uav['state'] == 'returning':
                    assignments.append(f"{uav_id} → RETURNING TO CHARGE")
                elif uav['state'] == 'charging':
                    assignments.append(f"{uav_id} → CHARGING ({int(uav['battery'])}%)")
                else:
                    assignments.append(f"{uav_id} → {uav['state'].upper()}")
        else:
            # Show zone assignments for surveillance/SAR
            for uav_id in sorted(uavs.keys()):
                uav = uavs[uav_id]
                if uav['assigned_zones']:
                    zone_str = ', '.join(map(str, uav['assigned_zones']))

                    # Check for priority zones in SAR
                    priority_info = ""
                    if tasks and scenario_type == 'search_rescue':
                        has_priority = any(tasks.get(z, {}).get('priority', 1) > 1 for z in uav['assigned_zones'])
                        if has_priority:
                            priority_info = "PRIORITY"

                    assignments.append(f"{uav_id} → Zones [{zone_str}] {priority_info}")
                elif uav['state'] == 'recovered':
                     assignments.append(f"{uav_id} → **RECOVERED / READY TO DEPLOY**")
                elif uav['state'] == 'charging':
                     assignments.append(f"{uav_id} → CHARGING ({int(uav['battery'])}%)")
                elif uav['state'] == 'returning':
                     assignments.append(f"{uav_id} → RETURNING TO BASE")

        return assignments
    
    def ensure_full_coverage(self, uavs, tasks):
        """
        Ensures ALL zones are assigned to at least one operational UAV.
        Called periodically to fix any orphaned zones.
        Returns True if any changes were made.
        """
        # Find operational UAVs that can patrol
        operational_uavs = [uid for uid, u in uavs.items() 
                          if u['operational'] and u['state'] in ['deploying', 'patrolling']]
        
        if not operational_uavs:
            return False
        
        # Find all orphaned zones (no operational UAV assigned)
        orphaned_zones = []
        for zid, task in tasks.items():
            # Skip assets - only process zones
            if task.get('type') == 'asset':
                continue

            active_uavs = [uid for uid in task['assigned_uavs']
                         if uid in uavs and uavs[uid]['operational']
                         and uavs[uid]['state'] in ['deploying', 'patrolling']]
            if not active_uavs:
                orphaned_zones.append(zid)
        
        if not orphaned_zones:
            return False
        
        logger.info(f"Found orphaned zones: {orphaned_zones}, distributing to {operational_uavs}")
        
        # Sort orphaned zones by coverage (lowest first)
        orphaned_zones.sort(key=lambda zid: tasks[zid]['coverage'])
        
        # Distribute orphaned zones to operational UAVs (round-robin, prefer least loaded)
        for zid in orphaned_zones:
            # Find the UAV with fewest zones
            best_uav = min(operational_uavs, key=lambda uid: len(uavs[uid]['assigned_zones']))
            
            # Assign zone
            uavs[best_uav]['assigned_zones'].append(zid)
            tasks[zid]['assigned_uavs'] = [best_uav]  # Clear old and set new
            
            logger.info(f"Assigned orphaned zone {zid} to {best_uav}")
        
        # Recompute contours for all affected UAVs
        for uid in operational_uavs:
            if uavs[uid]['assigned_zones']:
                uavs[uid]['contour_waypoints'] = self.compute_zone_contour(uavs[uid]['assigned_zones'], tasks)
                uavs[uid]['waypoint_idx'] = 0
        
        return True

workload_balancer = WorkloadBalancer()

def init_scenario(scenario, custom_home=None):
    """Initialize mission - ALL UAVs deployed from home base"""
    global uavs, tasks, scenario_type, home_base, mission_start_time, mission_metrics
    scenario_type = scenario
    cfg = SCENARIOS[scenario]
    mission_start_time = time.time()

    # Reset mission metrics
    mission_metrics = {
        'targets_found': 0,
        'detection_times': [],
        'deliveries_completed': 0,
        'deliveries_on_time': 0,
        'total_packages': 0,
        'final_return_initiated': False,  # Track when UAVs sent home after deliveries complete
        'mission_time_limit': cfg.get('time_limit'),
        'mission_type': cfg['mission_type']
    }

    # Set custom home base if provided
    if custom_home:
        home_base = [custom_home[0], custom_home[1], 10]
        logger.info(f"Custom home base set to: {home_base}")

    # Initialize tasks based on scenario type
    tasks = {}

    if scenario == 'surveillance':
        # 3x3 zone grid for continuous coverage
        zones = [
            ([-40, 40], 40),   # Zone 1
            ([0, 40], 40),     # Zone 2
            ([40, 40], 40),    # Zone 3
            ([-40, 0], 40),    # Zone 4
            ([0, 0], 40),      # Zone 5
            ([40, 0], 40),     # Zone 6
            ([-40, -40], 40),  # Zone 7
            ([0, -40], 40),    # Zone 8
            ([40, -40], 40)    # Zone 9
        ]
        for i, (pos, size) in enumerate(zones, 1):
            tasks[i] = {
                'center': pos + [15],
                'size': size,
                'type': 'surveillance',
                'coverage': 0.0,
                'assigned_uavs': [],
                'priority': 1.0
            }

    elif scenario == 'search_rescue':
        # 3x3 zone grid (same as surveillance) with priority areas
        zones = [
            ([-40, 40], 40),   # Zone 1 - HIGH PRIORITY
            ([0, 40], 40),     # Zone 2 - HIGH PRIORITY
            ([40, 40], 40),    # Zone 3 - HIGH PRIORITY
            ([-40, 0], 40),    # Zone 4 - HIGH PRIORITY
            ([0, 0], 40),      # Zone 5 - HIGH PRIORITY
            ([40, 0], 40),     # Zone 6 - HIGH PRIORITY
            ([-40, -40], 40),  # Zone 7
            ([0, -40], 40),    # Zone 8
            ([40, -40], 40)    # Zone 9
        ]
        priority_zones = cfg['priority_zones']

        # Create zone tasks
        for i, (pos, size) in enumerate(zones, 1):
            is_priority = i in priority_zones

            tasks[i] = {
                'center': pos + [15],
                'size': size,
                'type': 'search_rescue',
                'coverage': 0.0,
                'assigned_uavs': [],
                'priority': 3.0 if is_priority else 1.0
            }

        # Generate rescue assets at random positions
        import random
        random.seed(42)  # Reproducible asset placement
        num_assets = cfg['num_assets']

        # Place assets in priority zones
        for i in range(num_assets):
            # Pick a random priority zone
            zone_id = random.choice(priority_zones)
            zone_center = tasks[zone_id]['center'][:2]
            zone_size = tasks[zone_id]['size']

            # Random position within zone boundaries (zone_size is full width/height)
            # Keep assets within 90% of zone to avoid edge cases
            half_size = zone_size / 2.0
            offset_x = random.uniform(-half_size * 0.9, half_size * 0.9)
            offset_y = random.uniform(-half_size * 0.9, half_size * 0.9)

            asset_pos = [zone_center[0] + offset_x, zone_center[1] + offset_y, 0]

            # Use global constant for initial detection radius
            initial_radius = SAR_VISIBILITY_RADIUS

            tasks[f'asset_{i+1}'] = {
                'type': 'asset',
                'position': asset_pos,
                'last_known_position': None,  # Set when first detected (None = undiscovered)
                'search_radius': initial_radius,  # Current search radius (reduces to SAR_DETECTION_RADIUS)
                'searching_uavs': [],  # UAVs currently circling this asset
                'detected_by': [],  # UAVs that have pinpointed this asset
                'detected': False,  # True when first UAV spots the asset
                'pinpointed': False,  # True when search_radius reaches SAR_DETECTION_RADIUS
                'identified': False,  # True when guardian has been assigned (asset location confirmed)
                'rescued': False,
                'rescue_time': None,
                'guardian_uav': None  # UAV assigned to guard this asset
            }

        mission_metrics['total_assets'] = num_assets
        mission_metrics['assets_rescued'] = 0
        mission_metrics['consensus_required'] = cfg['consensus_required']
        logger.info(f"SAR mission: {num_assets} assets placed in priority zones")

    elif scenario == 'delivery':
        # 3x3 zone grid for delivery area visualization
        zones = [
            ([-40, 40], 40),   # Zone 1
            ([0, 40], 40),     # Zone 2
            ([40, 40], 40),    # Zone 3
            ([-40, 0], 40),    # Zone 4
            ([0, 0], 40),      # Zone 5
            ([40, 0], 40),     # Zone 6
            ([-40, -40], 40),  # Zone 7
            ([0, -40], 40),    # Zone 8
            ([40, -40], 40)    # Zone 9
        ]

        # Create zone visualization (not used for routing, just for display)
        for i, (pos, size) in enumerate(zones, 1):
            tasks[f'zone_{i}'] = {
                'center': pos + [15],
                'size': size,
                'type': 'delivery',
                'coverage': 0.0,
                'assigned_uavs': [],
                'priority': 1.0
            }

        # Generate delivery tasks (pickup/dropoff pairs)
        import random
        random.seed(42)
        num_packages = cfg['num_packages']
        time_window = cfg.get('time_window', 600)  # Default 10 minutes

        # Generate random delivery locations
        for i in range(1, num_packages + 1):
            pickup_x = random.uniform(-60, 60)
            pickup_y = random.uniform(-60, 60)
            dropoff_x = random.uniform(-60, 60)
            dropoff_y = random.uniform(-60, 60)

            # Use configured time window for deadlines (with some randomization)
            deadline_offset = random.uniform(time_window * 0.5, time_window * 1.5)

            tasks[f'pkg_{i}'] = {
                'type': 'delivery',
                'pickup': [pickup_x, pickup_y, 10],
                'dropoff': [dropoff_x, dropoff_y, 10],
                'status': 'pending',  # pending, assigned, picked_up, delivered
                'assigned_uav': None,
                'deadline': mission_start_time + deadline_offset,
                'priority': random.uniform(0.5, 2.0)
            }

        mission_metrics['total_packages'] = num_packages
        logger.info(f"Delivery mission: {num_packages} packages generated")

    # Create UAVs - ALL start from centered home base
    uavs = {}
    for i in range(1, cfg['uavs'] + 1):
        uav_id = f"uav_{i}"
        uavs[uav_id] = {
            'position': [home_base[0], home_base[1], home_base[2]],
            'battery': 100,
            'operational': True,
            'state': 'deploying',
            'assigned_zones': [],
            'assigned_task': None,  # For delivery scenario
            'current_zone_idx': 0,
            'patrol_progress': 0.0,
            'returning': False,
            'battery_warning': False,
            'contour_waypoints': [],
            'waypoint_idx': 0,
            'packages_delivered': 0,
            'searching_asset': None,  # Asset ID being searched/circled
            'circle_waypoints': [],  # Waypoints for circling asset
            'circle_angle': 0.0,  # Current angle in circle (for smooth circling)
            'circle_count': 0,  # Number of complete circles around asset
            'guardian_of_asset': None,  # Asset ID if this UAV is guardian (stays circling)
            'guardian_start_time': None,  # Timestamp when UAV became guardian
            'awaiting_permission': False,  # Delivery safety - waiting at boundary for permission
            'boundary_stop_position': None,  # Position where UAV stopped at boundary
            'out_of_grid_target': None,  # The original out-of-grid target position
            'permission_granted_for_target': None  # Target coordinates for which permission was granted
        }

    # Assign workload based on scenario type
    if scenario in ['surveillance', 'search_rescue']:
        # Filter out assets - only pass zone tasks to workload balancer
        zone_tasks = {tid: t for tid, t in tasks.items() if t.get('type') != 'asset'}
        assignments = workload_balancer.assign_initial_workload(uavs, zone_tasks)
        logger.info(f"Zone assignments: {assignments}")
    else:  # delivery
        # Delivery: Distribute packages evenly among UAVs, send idle UAVs home
        package_tasks = {tid: t for tid, t in tasks.items() if tid.startswith('pkg_')}
        num_packages = len(package_tasks)
        num_uavs = len(uavs)

        if num_packages >= num_uavs:
            # Assign one package per UAV initially, rest will be picked up dynamically
            package_list = list(package_tasks.items())
            package_list.sort(key=lambda x: x[1]['priority'], reverse=True)  # Sort by priority

            uav_list = list(uavs.keys())
            # Only assign first num_uavs packages (one per UAV)
            for i, (pkg_id, pkg) in enumerate(package_list[:num_uavs]):
                uav_id = uav_list[i]
                uavs[uav_id]['assigned_task'] = pkg_id
                pkg['status'] = 'assigned'
                pkg['assigned_uav'] = uav_id
                uavs[uav_id]['state'] = 'delivering'
                logger.info(f"{uav_id} pre-assigned package {pkg_id} (priority {pkg['priority']:.2f})")

            # Remaining packages stay as 'pending' for dynamic assignment
            remaining = num_packages - num_uavs
            logger.info(f"Delivery: {num_uavs} packages initially assigned, {remaining} packages pending for dynamic assignment")
        else:
            # More UAVs than packages - assign one package per UAV, send extras home
            package_list = list(package_tasks.items())
            package_list.sort(key=lambda x: x[1]['priority'], reverse=True)

            uav_list = list(uavs.keys())
            for i, (pkg_id, pkg) in enumerate(package_list):
                uav_id = uav_list[i]
                uavs[uav_id]['assigned_task'] = pkg_id
                pkg['status'] = 'assigned'
                pkg['assigned_uav'] = uav_id
                uavs[uav_id]['state'] = 'delivering'
                logger.info(f"{uav_id} pre-assigned package {pkg_id} (priority {pkg['priority']:.2f})")

            # Send remaining UAVs home
            idle_uavs = uav_list[num_packages:]
            for uav_id in idle_uavs:
                uavs[uav_id]['state'] = 'returning'
                uavs[uav_id]['returning'] = True
                logger.info(f"{uav_id} returning to base (no packages available)")

            logger.info(f"Delivery: {num_packages} packages assigned, {len(idle_uavs)} UAVs sent home")

    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    safe_emit('mission_metrics', mission_metrics)

    logger.info(f"All {cfg['uavs']} UAVs deployed from {home_base[:2]} for {scenario} mission")

def simulation_loop():
    """Main simulation loop"""
    global mission_active, simulation_speed, last_reassignment_time, ooda_count, last_telemetry_time, LOOP_REAL_INTERVAL
    
    RECOVERY_THRESHOLD = 80 # Battery level for full recovery
    REASSIGNMENT_INTERVAL = 2 # Seconds to check for recovered UAVs (more frequent)
    COVERAGE_DECAY_RATE = 0.5 # Coverage decays 0.5% per simulated second when unpatrolled
    
    while True:
        if mission_active:
            
            # --- FIXED LOOP INTERVAL LOGIC ---
            dt = LOOP_REAL_INTERVAL * simulation_speed
            current_time = time.time()
            # ---------------------------------
            
            # --- UAV State Management and Movement (Runs at accelerated speed) ---
            for uid, uav in uavs.items():
                
                if uav['state'] == 'crashed':
                    continue
                
                uav['battery_warning'] = uav['battery'] <= 20
                
                # State Transition: PATROL -> RETURN (Automatic low battery return)
                if uav['battery'] <= 15 and not uav['returning'] and uav['operational']:
                    uav['returning'] = True
                    uav['state'] = 'returning'
                    
                    # Store zones before clearing for redistribution
                    abandoned_zones = uav['assigned_zones'].copy()
                    uav['assigned_zones'] = []
                    uav['contour_waypoints'] = []
                    uav['operational'] = False
                    
                    # Remove UAV from zone assignments
                    for zone_id in abandoned_zones:
                        if zone_id in tasks and uid in tasks[zone_id]['assigned_uavs']:
                            tasks[zone_id]['assigned_uavs'].remove(uid)
                    
                    emit_ooda('observe', f'{uid} returning to base (low battery)', critical=False)

                    # IMMEDIATE REDISTRIBUTION: Assign abandoned zones to operational UAVs
                    if abandoned_zones:
                        operational_uavs = [u_id for u_id, u in uavs.items()
                                           if u['operational'] and u['state'] in ['deploying', 'patrolling']]

                        if operational_uavs:
                            assignments = workload_balancer.redistribute_failed_zones(
                                abandoned_zones, operational_uavs, uavs, tasks)
                            if assignments:
                                ooda_count += 1
                                emit_ooda('decide', f'OODA #{ooda_count}: Redistributed zones {abandoned_zones} from {uid}', critical=False)

                    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
                
                # State: RETURNING (Movement and Charging)
                if uav['returning']:
                    dx = home_base[0] - uav['position'][0]
                    dy = home_base[1] - uav['position'][1]
                    dist = np.sqrt(dx**2 + dy**2)

                    logger.debug(f"{uid} RETURNING: position={uav['position'][:2]}, distance_to_home={dist:.1f}m, battery={uav['battery']:.1f}%, operational={uav['operational']}")

                    if dist > HOME_ARRIVAL_THRESHOLD:
                        # Use BASE_RETURN_SPEED (m/s) * dt (simulated seconds)
                        speed_factor = BASE_RETURN_SPEED
                        uav['position'][0] += (dx / dist) * speed_factor * dt
                        uav['position'][1] += (dy / dist) * speed_factor * dt
                        uav['state'] = 'returning'

                        # Battery drains during return flight
                        battery_drain = BASE_BATTERY_DRAIN * dt
                        uav['battery'] -= battery_drain

                        if uav['battery'] <= 0:
                            uav['battery'] = 0
                            uav['operational'] = False
                            uav['state'] = 'crashed'
                            uav['returning'] = False
                            logger.error(f"{uid} battery depleted during return flight")
                            emit_ooda('observe', f'{uid} CRASHED during return (battery exhausted)', critical=True)
                    else:
                        # Snap to home position to prevent floating point drift
                        uav['position'][0] = home_base[0]
                        uav['position'][1] = home_base[1]

                        # Battery charges 1% per simulated second
                        charge_rate = 1.0
                        uav['battery'] = min(100, uav['battery'] + charge_rate * dt)
                        uav['state'] = 'charging'

                        logger.debug(f"{uid} charging: battery={uav['battery']:.1f}%, operational={uav['operational']}, state={uav['state']}")

                        # State Transition: CHARGING -> RECOVERED or IDLE
                        if uav['battery'] >= RECOVERY_THRESHOLD:
                            uav['returning'] = False
                            # For delivery, transition to 'idle' for inline task assignment
                            # For surveillance/SAR, transition to 'recovered' for OODA reassignment
                            if scenario_type == 'delivery':
                                uav['state'] = 'idle'
                            else:
                                uav['state'] = 'recovered'
                            uav['battery_warning'] = False
                            uav['operational'] = True  # Set operational when fully charged
                            logger.info(f"{uid} finished charging, state set to '{uav['state']}'")
                            emit_ooda('observe', f'{uid} fully charged ({uav["battery"]:.0f}%) and ready for redeployment', critical=False)
                    continue
                
                # FAILSAFE: If UAV is at home with low battery - force into charging cycle
                dx = home_base[0] - uav['position'][0]
                dy = home_base[1] - uav['position'][1]
                dist_to_home = np.sqrt(dx**2 + dy**2)
                if dist_to_home < HOME_PROXIMITY_THRESHOLD and uav['battery'] < RECOVERY_THRESHOLD and uav['state'] not in ['patrolling', 'deploying']:
                    uav['returning'] = True
                    uav['state'] = 'charging'
                    uav['operational'] = False
                    uav['position'][0] = home_base[0]
                    uav['position'][1] = home_base[1]
                    logger.warning(f"{uid} failsafe: forcing charging state (battery: {uav['battery']:.1f}%)")
                    continue
                
                # State: RECOVERED or CHARGING or IDLE (Waiting for Reassignment/Task)
                # If UAV is at home and not fully charged, ensure it's charging
                dx = home_base[0] - uav['position'][0]
                dy = home_base[1] - uav['position'][1]
                dist_to_home = np.sqrt(dx**2 + dy**2)

                if uav['state'] in ['recovered', 'charging', 'idle']:
                    # Check if UAV is at home and needs charging
                    if dist_to_home < HOME_ARRIVAL_THRESHOLD and uav['battery'] < 100:
                        # UAV is at home but not fully charged - charge it
                        charge_rate = 1.0
                        uav['battery'] = min(100, uav['battery'] + charge_rate * dt)

                        if uav['state'] != 'charging':
                            uav['state'] = 'charging'
                            logger.info(f"{uid} started charging at home (battery: {uav['battery']:.1f}%)")

                        # Check if charging complete
                        if uav['battery'] >= RECOVERY_THRESHOLD:
                            # For delivery, transition to 'idle' for inline task assignment
                            # For surveillance/SAR, transition to 'recovered' for OODA reassignment
                            if scenario_type == 'delivery':
                                uav['state'] = 'idle'
                            else:
                                uav['state'] = 'recovered'
                            uav['battery_warning'] = False
                            uav['operational'] = True
                            logger.info(f"{uid} charging complete, state set to '{uav['state']}' (battery: {uav['battery']:.1f}%)")

                        # Continue to skip task assignment while still charging
                        continue

                    # For surveillance/SAR: recovered UAVs wait for OODA reassignment
                    # For delivery: idle UAVs can proceed to task assignment below
                    if scenario_type != 'delivery' and uav['state'] in ['recovered', 'charging']:
                        continue

                    # Delivery mission: allow 'idle' UAVs to proceed to task assignment section
                    # (don't continue, let them fall through to delivery logic)

                # State: RETURNING_TO_GRID (Moving back to grid boundary after identifying asset outside)
                if uav['state'] == 'returning_to_grid':
                    # Calculate closest grid boundary point if not already set
                    if uav.get('return_to_grid_target') is None:
                        # Find closest point on grid boundary to current position
                        current_pos = np.array(uav['position'][:2])

                        # Calculate which boundary is closest
                        distances_to_boundaries = [
                            abs(current_pos[0] - GRID_MAX),  # Right boundary
                            abs(current_pos[0] - GRID_MIN),  # Left boundary
                            abs(current_pos[1] - GRID_MAX),  # Top boundary
                            abs(current_pos[1] - GRID_MIN)   # Bottom boundary
                        ]

                        closest_boundary_idx = np.argmin(distances_to_boundaries)

                        if closest_boundary_idx == 0:  # Right
                            target = [GRID_MAX, current_pos[1]]
                        elif closest_boundary_idx == 1:  # Left
                            target = [GRID_MIN, current_pos[1]]
                        elif closest_boundary_idx == 2:  # Top
                            target = [current_pos[0], GRID_MAX]
                        else:  # Bottom
                            target = [current_pos[0], GRID_MIN]

                        # Clamp to grid boundaries
                        target[0] = np.clip(target[0], GRID_MIN, GRID_MAX)
                        target[1] = np.clip(target[1], GRID_MIN, GRID_MAX)

                        uav['return_to_grid_target'] = target
                        logger.info(f"{uid} calculated grid return target: ({target[0]:.1f}, {target[1]:.1f})")

                    # Move toward grid boundary
                    target = uav['return_to_grid_target']
                    dx = target[0] - uav['position'][0]
                    dy = target[1] - uav['position'][1]
                    dist = np.sqrt(dx**2 + dy**2)

                    if dist > WAYPOINT_ARRIVAL_THRESHOLD:
                        # Move toward boundary
                        speed_factor = BASE_CRUISE_SPEED
                        uav['position'][0] += (dx / dist) * speed_factor * dt
                        uav['position'][1] += (dy / dist) * speed_factor * dt
                        uav['position'][2] = 15

                        # Battery drain
                        battery_drain = BASE_BATTERY_DRAIN * dt
                        uav['battery'] -= battery_drain

                        if uav['battery'] <= 0:
                            uav['battery'] = 0
                            uav['operational'] = False
                            uav['state'] = 'crashed'
                            logger.error(f"{uid} crashed while returning to grid (battery exhausted)")
                            emit_ooda('observe', f'{uid} CRASHED returning to grid (battery exhausted)', critical=True)
                    else:
                        # Reached grid boundary - resume patrol
                        uav['state'] = 'recovered'
                        uav['return_to_grid_target'] = None
                        logger.info(f"{uid} reached grid boundary - resuming patrol")
                        emit_ooda('act', f'{uid} returned to grid - resuming patrol', critical=False)

                    continue

                # State: SEARCHING (Circling asset with reducing radius - 3 loops for identification, 5 loops for guardians)
                if uav['state'] == 'searching' and (uav['searching_asset'] or uav['guardian_of_asset']):
                    asset_id = uav['searching_asset'] or uav['guardian_of_asset']
                    if asset_id in tasks:
                        asset = tasks[asset_id]
                        # Use last known position for targeting (not real-time position)
                        asset_pos = np.array(asset['last_known_position'][:2])
                        current_radius = asset['search_radius']

                        # Check if UAV is within detection radius of REAL asset position
                        real_asset_pos = np.array(asset['position'][:2])
                        uav_pos = np.array(uav['position'][:2])
                        distance_to_real_asset = np.linalg.norm(real_asset_pos - uav_pos)

                        # Refine search area as UAV gets closer (narrowing uncertainty)
                        # But don't give exact position until pinpointed
                        if distance_to_real_asset <= SAR_VISIBILITY_RADIUS and not asset['pinpointed']:
                            # Update with refined estimate (less noise as we get closer)
                            uncertainty = max(2, distance_to_real_asset * 0.1)  # Reduce uncertainty as we approach
                            noise = np.random.uniform(-uncertainty, uncertainty, 2)
                            asset['last_known_position'] = (asset['position'].copy() + np.append(noise, [0])).tolist()
                            asset_pos = np.array(asset['last_known_position'][:2])

                        # SAFETY CHECK: Last known position outside grid requires permission
                        asset_outside_grid = is_position_outside_grid(asset['last_known_position'])
                        permission_granted = uav.get('permission_granted_for_target') == tuple(asset_pos)

                        if asset_outside_grid and not permission_granted:
                            # Asset is outside grid - stop at boundary and request permission
                            boundary_pos = calculate_boundary_intersection(uav['position'][:2], asset_pos)
                            boundary_dist = np.linalg.norm(np.array(boundary_pos) - np.array(uav['position'][:2]))

                            if boundary_dist <= WAYPOINT_ARRIVAL_THRESHOLD:
                                # Arrived at boundary - stop and wait for permission
                                if not uav.get('awaiting_permission'):
                                    uav['position'][0] = boundary_pos[0]
                                    uav['position'][1] = boundary_pos[1]
                                    uav['awaiting_permission'] = True
                                    uav['boundary_stop_position'] = boundary_pos.tolist() if hasattr(boundary_pos, 'tolist') else list(boundary_pos)
                                    uav['out_of_grid_target'] = list(asset['last_known_position'])
                                    uav['state'] = 'awaiting_permission'
                                    logger.warning(f"{uid} stopped at boundary - {asset_id} last known at ({asset['last_known_position'][0]:.1f}, {asset['last_known_position'][1]:.1f}) is outside grid")
                                    emit_ooda('observe', f'{uid} BOUNDARY STOP - {asset_id} outside safe zone. Double-click UAV to grant permission.', critical=True)

                                # Battery still drains while hovering at boundary waiting for permission
                                battery_drain = BASE_BATTERY_DRAIN * dt
                                uav['battery'] -= battery_drain

                                if uav['battery'] <= 0:
                                    uav['battery'] = 0
                                    uav['operational'] = False
                                    uav['state'] = 'crashed'
                                    uav['awaiting_permission'] = False
                                    uav['searching_asset'] = None
                                    uav['guardian_of_asset'] = None
                                    uav['guardian_start_time'] = None
                                    logger.error(f"{uid} battery depleted while awaiting permission at boundary")
                                    emit_ooda('observe', f'{uid} CRASHED at boundary (battery exhausted)', critical=True)

                                # Stay at boundary position
                                continue
                            else:
                                # Move toward boundary
                                boundary_dx = boundary_pos[0] - uav['position'][0]
                                boundary_dy = boundary_pos[1] - uav['position'][1]
                                boundary_dist_norm = np.sqrt(boundary_dx**2 + boundary_dy**2)
                                speed_factor = BASE_CRUISE_SPEED
                                uav['position'][0] += (boundary_dx / boundary_dist_norm) * speed_factor * dt
                                uav['position'][1] += (boundary_dy / boundary_dist_norm) * speed_factor * dt
                                uav['position'][2] = 15
                                continue

                        # Generate/update circle waypoints if needed (8 points around circle)
                        num_circle_points = 8
                        if not uav['circle_waypoints'] or len(uav['circle_waypoints']) == 0:
                            # Initial circle generation
                            uav['circle_waypoints'] = []
                            for i in range(num_circle_points):
                                angle = (2 * np.pi * i) / num_circle_points
                                wx = asset_pos[0] + current_radius * np.cos(angle)
                                wy = asset_pos[1] + current_radius * np.sin(angle)
                                uav['circle_waypoints'].append([wx, wy])
                            uav['waypoint_idx'] = 0
                        else:
                            # Update circle waypoints to match shrinking radius
                            for i, wp in enumerate(uav['circle_waypoints']):
                                angle = (2 * np.pi * i) / num_circle_points
                                uav['circle_waypoints'][i] = [
                                    asset_pos[0] + current_radius * np.cos(angle),
                                    asset_pos[1] + current_radius * np.sin(angle)
                                ]

                        # Navigate to current circle waypoint
                        if uav['circle_waypoints']:
                            waypoint_idx = uav.get('waypoint_idx', 0) % len(uav['circle_waypoints'])
                            prev_waypoint_idx = waypoint_idx
                            target_wp = uav['circle_waypoints'][waypoint_idx]
                            target = [target_wp[0], target_wp[1], 15]

                            dx = target[0] - uav['position'][0]
                            dy = target[1] - uav['position'][1]
                            dist = np.sqrt(dx**2 + dy**2)

                            if dist < WAYPOINT_ARRIVAL_THRESHOLD:
                                # Move to next waypoint on circle
                                new_idx = (waypoint_idx + 1) % len(uav['circle_waypoints'])
                                uav['waypoint_idx'] = new_idx

                                # Detect circle completion (wrapped back to 0)
                                if new_idx == 0 and waypoint_idx == len(uav['circle_waypoints']) - 1:
                                    uav['circle_count'] += 1
                                    logger.info(f"{uid} completed circle #{uav['circle_count']} around {asset_id}")

                                    # After 3 circles, asset is identified - return to grid
                                    if uav['circle_count'] >= 3 and uav['guardian_of_asset'] is None:
                                        # Mark asset as identified (no guardian needed - just identify and move on)
                                        asset['identified'] = True
                                        asset['rescued'] = True  # Consider it rescued after identification

                                        # Check if UAV is outside grid - need to return first
                                        uav_outside_grid = is_position_outside_grid(uav['position'])

                                        if uav_outside_grid:
                                            # UAV is outside grid - set state to return to grid boundary
                                            uav['searching_asset'] = None
                                            uav['circle_waypoints'] = []
                                            uav['circle_count'] = 0
                                            uav['state'] = 'returning_to_grid'  # New state for returning to grid
                                            uav['return_to_grid_target'] = None  # Will calculate boundary point

                                            # Clear permission - will need new permission for next out-of-grid asset
                                            uav['permission_granted_for_target'] = None
                                            uav['out_of_grid_target'] = None

                                            # Remove from searching list
                                            if uid in asset['searching_uavs']:
                                                asset['searching_uavs'].remove(uid)

                                            logger.info(f"{uid} identified {asset_id} outside grid - returning to grid boundary")
                                            emit_ooda('orient', f'{uid} identified {asset_id} - returning to grid', critical=False)

                                            # Update mission metrics
                                            if not mission_metrics.get(f'{asset_id}_counted', False):
                                                mission_metrics['assets_rescued'] = mission_metrics.get('assets_rescued', 0) + 1
                                                mission_metrics[f'{asset_id}_counted'] = True
                                        else:
                                            # UAV is inside grid - can immediately resume patrol
                                            uav['searching_asset'] = None
                                            uav['circle_waypoints'] = []
                                            uav['circle_count'] = 0
                                            uav['state'] = 'recovered'  # Set to recovered so it gets reassigned zones

                                            # Remove from searching list
                                            if uid in asset['searching_uavs']:
                                                asset['searching_uavs'].remove(uid)

                                            logger.info(f"{uid} identified {asset_id} inside grid - resuming patrol")
                                            emit_ooda('orient', f'{uid} identified {asset_id} - resuming patrol', critical=False)

                                            # Update mission metrics
                                            if not mission_metrics.get(f'{asset_id}_counted', False):
                                                mission_metrics['assets_rescued'] = mission_metrics.get('assets_rescued', 0) + 1
                                                mission_metrics[f'{asset_id}_counted'] = True
                                    # Guardian monitors for limited time (3 seconds)
                                    elif uav['guardian_of_asset'] == asset_id:
                                        guardian_duration = time.time() - uav.get('guardian_start_time', time.time())

                                        # Release guardian after 3 seconds
                                        if guardian_duration >= 3.0:
                                            logger.info(f"{uid} completed guardian duty for {asset_id} ({guardian_duration:.1f}s) - returning to patrol")
                                            emit_ooda('orient', f'{uid} completed monitoring {asset_id} - returning to patrol', critical=False)

                                            # Asset remains identified and rescued, but no longer has active guardian
                                            # (Asset is considered secured - location confirmed and logged)
                                            asset['guardian_uav'] = None  # Clear guardian reference
                                            uav['guardian_of_asset'] = None
                                            uav['searching_asset'] = None
                                            uav['circle_waypoints'] = []
                                            uav['circle_count'] = 0
                                            uav['guardian_start_time'] = None
                                            uav['state'] = 'recovered'  # Get reassigned to patrol zones

                                            # Remove from searching list
                                            if uid in asset['searching_uavs']:
                                                asset['searching_uavs'].remove(uid)
                            else:
                                # Move toward waypoint
                                speed_factor = BASE_CRUISE_SPEED * 0.8  # Slightly slower when searching
                                uav['position'][0] += (dx / dist) * speed_factor * dt
                                uav['position'][1] += (dy / dist) * speed_factor * dt
                                uav['position'][2] = 15

                            # Battery drain during search
                            battery_drain = BASE_BATTERY_DRAIN * dt
                            uav['battery'] -= battery_drain

                            if uav['battery'] <= 0:
                                uav['battery'] = 0
                                uav['operational'] = False
                                uav['state'] = 'crashed'
                                uav['searching_asset'] = None
                                uav['guardian_of_asset'] = None
                                uav['guardian_start_time'] = None
                                uav['circle_waypoints'] = []
                                # Remove from asset's searching list and guardian
                                if asset_id in tasks:
                                    if uid in tasks[asset_id]['searching_uavs']:
                                        tasks[asset_id]['searching_uavs'].remove(uid)
                                    if tasks[asset_id]['guardian_uav'] == uid:
                                        tasks[asset_id]['guardian_uav'] = None
                                emit_ooda('observe', f'{uid} crashed while searching (battery exhausted)', critical=True)
                    continue

                # State: DEPLOYING/PATROLLING (Normal Mission Logic)
                if not uav['assigned_zones'] or 'contour_waypoints' not in uav or not uav['contour_waypoints']:
                    uav['state'] = 'idle'
                    continue
                
                contour = uav['contour_waypoints']
                
                waypoint_idx = uav.get('waypoint_idx', 0)
                if waypoint_idx >= len(contour):
                    waypoint_idx = 0
                    uav['waypoint_idx'] = 0
                
                target = contour[waypoint_idx] + [15]
                
                dx = target[0] - uav['position'][0]
                dy = target[1] - uav['position'][1]
                dist = np.sqrt(dx**2 + dy**2)

                if dist < WAYPOINT_ARRIVAL_THRESHOLD:
                    next_idx = (waypoint_idx + 1) % len(contour)
                    uav['waypoint_idx'] = next_idx
                    
                    if next_idx == 0:
                        # Coverage increases after completing a full patrol circuit
                        for zone_id in uav['assigned_zones']:
                            if zone_id in tasks:
                                tasks[zone_id]['coverage'] = min(100, tasks[zone_id]['coverage'] + 20)
                else:
                    # Use BASE_CRUISE_SPEED (m/s) * dt (simulated seconds)
                    speed_factor = BASE_CRUISE_SPEED 
                    uav['position'][0] += (dx / dist) * speed_factor * dt
                    uav['position'][1] += (dy / dist) * speed_factor * dt
                    uav['position'][2] = 15
                    
                    if uav['state'] == 'deploying':
                         uav['state'] = 'patrolling'
                
                # Battery drain: BASE_BATTERY_DRAIN (per simulated second) * dt
                battery_drain = BASE_BATTERY_DRAIN * dt
                uav['battery'] -= battery_drain
                
                if uav['battery'] <= 0:
                    uav['battery'] = 0
                    uav['operational'] = False
                    uav['state'] = 'crashed'
                    for zone_id in uav['assigned_zones']:
                        if zone_id in tasks and uid in tasks[zone_id]['assigned_uavs']:
                            tasks[zone_id]['assigned_uavs'].remove(uid)
                    uav['assigned_zones'] = []
                    uav['contour_waypoints'] = []
                    emit_ooda('observe', f'{uid} crashed (battery exhausted)', critical=True)
            
            # --- Scenario-Specific Logic ---
            if scenario_type == 'surveillance' or scenario_type == 'search_rescue':
                # Coverage Decay: Zones decay when not actively patrolled
                for zid, task in tasks.items():
                    # Skip assets - only process zones
                    if task.get('type') == 'asset':
                        continue

                    # Check if zone has any active patrolling UAVs
                    active_uavs = [uid for uid in task['assigned_uavs']
                                  if uid in uavs and uavs[uid]['operational']
                                  and uavs[uid]['state'] in ['patrolling', 'deploying']]
                    if not active_uavs:
                        # Decay coverage when no one is patrolling
                        task['coverage'] = max(0, task['coverage'] - COVERAGE_DECAY_RATE * dt)

                # SAR Asset Search & Rescue Mechanics (circling with radius reduction)
                if scenario_type == 'search_rescue':
                    # Use global constants for detection radii
                    search_reduction_rate = SCENARIOS['search_rescue']['search_reduction_rate']
                    consensus_required = mission_metrics['consensus_required']

                    # Process each asset
                    for asset_id, asset in tasks.items():
                        if not isinstance(asset_id, str) or not asset_id.startswith('asset_'):
                            continue

                        if asset['rescued']:
                            continue

                        asset_pos = np.array(asset['position'][:2])

                        # Check operational UAVs for visibility
                        for uav_id, uav in uavs.items():
                            if not uav['operational']:
                                continue

                            uav_pos = np.array(uav['position'][:2])
                            distance = np.linalg.norm(asset_pos - uav_pos)

                            # UAV enters visibility radius - start circling (use global constant)
                            # Allow UAVs that are 'searching' to detect new assets (not just patrolling/deploying)
                            if distance <= SAR_VISIBILITY_RADIUS and uav['searching_asset'] is None:
                                if uav_id not in asset['searching_uavs'] and uav['state'] in ['patrolling', 'deploying', 'searching']:
                                    # Check if this is first detection or confirmation
                                    is_first_contact = len(asset['searching_uavs']) == 0

                                    # Mark asset as detected on first contact
                                    if is_first_contact:
                                        asset['detected'] = True
                                        # Set approximate last known position (add some noise/uncertainty)
                                        # UAVs don't know exact position, just approximate area
                                        noise = np.random.uniform(-5, 5, 2)  # +/- 5m uncertainty
                                        asset['last_known_position'] = (asset['position'].copy() + np.append(noise, [0])).tolist()

                                    # Assign UAV to search this asset
                                    uav['searching_asset'] = asset_id
                                    uav['state'] = 'searching'
                                    asset['searching_uavs'].append(uav_id)

                                    # Format coordinates (show approximate area, not exact position)
                                    approx_x = round(asset['position'][0] / 10) * 10  # Round to nearest 10m
                                    approx_y = round(asset['position'][1] / 10) * 10
                                    coord_str = f"~[{approx_x:.0f}, {approx_y:.0f}]"

                                    if is_first_contact:
                                        # First UAV to detect this asset
                                        logger.info(f"{uav_id} FIRST CONTACT with {asset_id} in area {coord_str}")
                                        emit_ooda('observe', f'{uav_id} - contact visual in area {coord_str}', critical=False)
                                    else:
                                        # Additional UAVs confirming the contact
                                        logger.info(f"{uav_id} CONFIRMING {asset_id} in area {coord_str}")
                                        emit_ooda('observe', f'{uav_id} - confirming area {coord_str}', critical=False)

                            # UAV is searching this asset - circle and reduce radius
                            if uav['searching_asset'] == asset_id or uav['guardian_of_asset'] == asset_id:
                                # Reduce search radius over time (use global constant)
                                if asset['search_radius'] > SAR_DETECTION_RADIUS:
                                    asset['search_radius'] = max(SAR_DETECTION_RADIUS, asset['search_radius'] - search_reduction_rate * dt)

                                # Check if pinpointed (use global constant)
                                if asset['search_radius'] <= SAR_DETECTION_RADIUS and not asset['pinpointed']:
                                    asset['pinpointed'] = True
                                    # Now we have exact position - update last_known_position
                                    asset['last_known_position'] = list(asset['position'])
                                    # Add all searching UAVs to detected_by
                                    for searching_uav in asset['searching_uavs']:
                                        if searching_uav not in asset['detected_by']:
                                            asset['detected_by'].append(searching_uav)
                                    # Also add guardian if assigned
                                    if asset['guardian_uav'] and asset['guardian_uav'] not in asset['detected_by']:
                                        asset['detected_by'].append(asset['guardian_uav'])

                                    logger.info(f"{asset_id} PINPOINTED with radius {asset['search_radius']:.1f}m!")
                                    emit_ooda('observe', f'{asset_id.upper()} location pinpointed!', critical=False)

                        # Check if guardian assigned for rescue
                        if asset['guardian_uav'] is not None and not asset['rescued']:
                            asset['rescued'] = True
                            asset['rescue_time'] = time.time() - mission_start_time
                            mission_metrics['assets_rescued'] += 1

                            emit_ooda('orient', f'{asset_id.upper()} SECURED! Guardian {asset["guardian_uav"]} assigned (t={asset["rescue_time"]:.1f}s)', critical=False)
                            logger.info(f"{asset_id} secured with guardian {asset['guardian_uav']} after {asset['rescue_time']:.1f}s")

                    # Check mission completion - all assets have guardians assigned
                    if mission_metrics['assets_rescued'] >= mission_metrics.get('total_assets', 0):
                        # Mission is complete - guardians stay with assets
                        # No need to send UAVs home - they remain as guardians
                        pass

            elif scenario_type == 'delivery':
                # Delivery Task Assignment and Execution
                for uid, uav in uavs.items():
                    if not uav['operational']:
                        continue

                    # Skip if returning to charge
                    if uav['returning']:
                        continue

                    # Assign new task if idle or just deployed
                    if uav['assigned_task'] is None and uav['state'] in ['deploying', 'idle', 'patrolling']:
                        # Find highest priority pending task (only package tasks, not zone visualizations)
                        pending_tasks = [(tid, t) for tid, t in tasks.items()
                                       if t.get('status') == 'pending' and tid.startswith('pkg_')]

                        if pending_tasks:
                            # Sort by priority (highest first)
                            pending_tasks.sort(key=lambda x: x[1]['priority'], reverse=True)
                            task_id, task = pending_tasks[0]

                            # Assign task
                            uav['assigned_task'] = task_id
                            task['status'] = 'assigned'
                            task['assigned_uav'] = uid
                            uav['state'] = 'delivering'
                            logger.info(f"{uid} dynamically assigned package {task_id} (priority {task['priority']:.2f}, {len(pending_tasks)-1} packages remaining)")
                        else:
                            # No more tasks - send UAV home
                            uav['state'] = 'returning'
                            uav['returning'] = True
                            logger.info(f"{uid} returning to base (no more packages)")

                    # Execute delivery task
                    if uav['assigned_task'] is not None:
                        task_id = uav['assigned_task']
                        if task_id not in tasks:
                            uav['assigned_task'] = None
                            continue

                        task = tasks[task_id]

                        # Determine target (pickup or dropoff)
                        if task['status'] == 'assigned':
                            target = task['pickup']
                        elif task['status'] == 'picked_up':
                            target = task['dropoff']
                        else:
                            uav['assigned_task'] = None
                            continue

                        # SAFETY CHECK: Check if target is outside grid boundaries
                        target_outside_grid = is_position_outside_grid(target)

                        # If UAV is awaiting permission, don't move until permission is granted
                        if uav['awaiting_permission']:
                            # UAV stays at boundary position, waiting for permission
                            # Battery still drains while hovering at boundary
                            battery_drain = BASE_BATTERY_DRAIN * dt
                            uav['battery'] -= battery_drain

                            if uav['battery'] <= 0:
                                uav['battery'] = 0
                                uav['operational'] = False
                                uav['state'] = 'crashed'
                                uav['awaiting_permission'] = False
                                logger.error(f"{uid} battery depleted while awaiting permission at boundary")
                                emit_ooda('observe', f'{uid} CRASHED at boundary (battery exhausted)', critical=True)

                            # Check for low battery warning
                            if uav['battery'] <= BATTERY_LOW_THRESHOLD and not uav.get('battery_warning'):
                                uav['battery_warning'] = True
                                emit_ooda('observe', f'{uid} LOW BATTERY ({uav["battery"]:.0f}%) while awaiting permission', critical=True)
                                logger.warning(f"{uid} low battery warning while awaiting permission: {uav['battery']:.1f}%")

                            continue

                        # Navigate to target
                        dx = target[0] - uav['position'][0]
                        dy = target[1] - uav['position'][1]
                        dist = np.sqrt(dx**2 + dy**2)

                        if dist > DELIVERY_ARRIVAL_THRESHOLD:
                            # Check if we need to stop at boundary
                            # Skip boundary check if permission was already granted for this specific target
                            permission_granted = uav.get('permission_granted_for_target') == tuple(target[:2])

                            if target_outside_grid and not uav['awaiting_permission'] and not permission_granted:
                                # Calculate boundary intersection point
                                boundary_pos = calculate_boundary_intersection(uav['position'][:2], target[:2])

                                # Check if we're close to the boundary
                                boundary_dx = boundary_pos[0] - uav['position'][0]
                                boundary_dy = boundary_pos[1] - uav['position'][1]
                                boundary_dist = np.sqrt(boundary_dx**2 + boundary_dy**2)

                                if boundary_dist <= DELIVERY_ARRIVAL_THRESHOLD:
                                    # Stop at boundary and enter awaiting_permission state
                                    uav['position'][0] = boundary_pos[0]
                                    uav['position'][1] = boundary_pos[1]
                                    uav['position'][2] = 10
                                    uav['awaiting_permission'] = True
                                    uav['boundary_stop_position'] = boundary_pos.tolist() if hasattr(boundary_pos, 'tolist') else list(boundary_pos)
                                    uav['out_of_grid_target'] = target.tolist() if hasattr(target, 'tolist') else list(target)
                                    uav['state'] = 'awaiting_permission'

                                    target_type = "pickup" if task['status'] == 'assigned' else "dropoff"
                                    logger.warning(f"{uid} stopped at grid boundary ({boundary_pos[0]:.1f}, {boundary_pos[1]:.1f}) - {target_type} destination ({target[0]:.1f}, {target[1]:.1f}) is outside grid. Awaiting permission.")
                                    emit_ooda('observe', f'{uid} BOUNDARY STOP - {target_type} at ({target[0]:.0f}, {target[1]:.0f}) is outside safe zone. Double-click UAV to grant permission.', critical=True)
                                else:
                                    # Move toward boundary
                                    speed_factor = BASE_CRUISE_SPEED
                                    uav['position'][0] += (boundary_dx / boundary_dist) * speed_factor * dt
                                    uav['position'][1] += (boundary_dy / boundary_dist) * speed_factor * dt
                                    uav['position'][2] = 10
                            else:
                                # Normal movement (target is inside grid)
                                speed_factor = BASE_CRUISE_SPEED
                                uav['position'][0] += (dx / dist) * speed_factor * dt
                                uav['position'][1] += (dy / dist) * speed_factor * dt
                                uav['position'][2] = 10

                            # Battery drain during delivery movement
                            battery_drain = BASE_BATTERY_DRAIN * dt
                            uav['battery'] -= battery_drain

                            if uav['battery'] <= 0:
                                uav['battery'] = 0
                                uav['operational'] = False
                                uav['state'] = 'crashed'
                                logger.error(f"{uid} battery depleted during delivery - mission failed")

                            # Check for low battery warning
                            if uav['battery'] <= BATTERY_LOW_THRESHOLD and not uav.get('battery_warning'):
                                uav['battery_warning'] = True
                                emit_ooda('observe', f'{uid} LOW BATTERY ({uav["battery"]:.0f}%) during delivery', critical=True)
                                logger.warning(f"{uid} low battery warning during delivery: {uav['battery']:.1f}%")
                        else:
                            # Arrived at target
                            if task['status'] == 'assigned':
                                # Picked up package
                                task['status'] = 'picked_up'
                                logger.info(f"{uid} picked up package {task_id}")
                                # Clear permission for pickup location - may need permission for dropoff
                                uav['permission_granted_for_target'] = None
                                uav['boundary_stop_position'] = None
                                uav['out_of_grid_target'] = None
                            elif task['status'] == 'picked_up':
                                # Delivered package
                                task['status'] = 'delivered'
                                mission_metrics['deliveries_completed'] += 1
                                uav['packages_delivered'] += 1

                                # Check if on-time
                                current_sim_time = time.time()
                                if current_sim_time <= task['deadline']:
                                    mission_metrics['deliveries_on_time'] += 1

                                uav['assigned_task'] = None
                                uav['state'] = 'idle'
                                # Clear all permission-related fields after delivery complete
                                uav['permission_granted_for_target'] = None
                                uav['boundary_stop_position'] = None
                                uav['out_of_grid_target'] = None
                                uav['awaiting_permission'] = False
                                emit_ooda('act', f'{uid} completed delivery {task_id} ({mission_metrics["deliveries_completed"]}/{mission_metrics["total_packages"]})', critical=False)
                                logger.info(f"{uid} delivered package {task_id} ({mission_metrics['deliveries_completed']}/{mission_metrics['total_packages']} complete) - now idle, ready for next assignment")

                                # Check if all deliveries complete - send all UAVs home
                                if mission_metrics['deliveries_completed'] >= mission_metrics['total_packages']:
                                    # Only send UAVs home once when deliveries complete
                                    if not mission_metrics.get('final_return_initiated', False):
                                        mission_metrics['final_return_initiated'] = True
                                        emit_ooda('act', f' ALL DELIVERIES COMPLETE - Sending all UAVs home', critical=False)
                                        logger.info("All deliveries completed - returning all UAVs to base")

                                        # Send all operational UAVs home
                                        for uav_id, u in uavs.items():
                                            if u['operational'] and u['state'] not in ['returning', 'charging', 'crashed']:
                                                u['state'] = 'returning'
                                                u['returning'] = True
                                                logger.info(f"{uav_id} returning to base after mission completion")

            # --- Auto-stop mission when objectives complete ---
            if scenario_type in ['search_rescue', 'delivery']:
                objectives_complete = False

                if scenario_type == 'search_rescue':
                    # SAR completes when all assets have guardians (but continues patrolling)
                    objectives_complete = mission_metrics['assets_rescued'] >= mission_metrics.get('total_assets', 0)

                    # Only announce completion once
                    if objectives_complete and mission_active and not mission_metrics.get('completion_announced', False):
                        elapsed = time.time() - mission_start_time
                        mission_metrics['completion_announced'] = True

                        emit_ooda('orient', f' All {mission_metrics["total_assets"]} known assets secured! Guardians monitoring, other UAVs continue area patrol (t={elapsed:.1f}s)', critical=False)
                        logger.info(f"SAR objectives complete: all known assets have guardians - continuing patrol")

                        # Continue mission - guardians watch assets, others patrol for additional unknowns

                elif scenario_type == 'delivery':
                    # Delivery completes when all packages delivered AND all UAVs returned home AFTER final return
                    objectives_complete = mission_metrics['deliveries_completed'] >= mission_metrics.get('total_packages', 0)
                    final_return_initiated = mission_metrics.get('final_return_initiated', False)

                    # Only check if all home AFTER we've initiated the final return
                    if objectives_complete and final_return_initiated:
                        # Check if all UAVs are home (charging or crashed)
                        # Note: UAVs transition from 'returning' to 'charging' when they arrive home
                        all_home = all(
                            u['state'] in ['charging', 'crashed']
                            for u in uavs.values()
                        )

                        if all_home and mission_active:
                            elapsed = time.time() - mission_start_time
                            emit_ooda('act', f' DELIVERY MISSION COMPLETE - All UAVs returned home (t={elapsed:.1f}s) - Mission stopped', critical=False)
                            logger.info(f"DELIVERY mission auto-stopped: objectives complete and all UAVs home")
                            mission_active = False

                            # Notify frontend to stop timer and re-enable start button
                            safe_emit('mission_stopped', {
                                'mission_type': scenario_type,
                                'elapsed_time': elapsed,
                                'success': True
                            }, broadcast=True)

            # --- OODA Loop: Re-assignment Check (Surveillance and SAR) ---
            # SAR: Only reassigns recovered UAVs (after guardian duty), doesn't interrupt searching/guardian UAVs
            if scenario_type in ['surveillance', 'search_rescue'] and current_time - last_reassignment_time > REASSIGNMENT_INTERVAL / simulation_speed:

                # FIRST: Ensure all zones are covered (fix any orphaned zones)
                coverage_changed = workload_balancer.ensure_full_coverage(uavs, tasks)
                if coverage_changed:
                    ooda_count += 1
                    emit_ooda('decide', f'OODA #{ooda_count}: Fixed orphaned zones', critical=False)
                    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})

                # THEN: Handle recovered AND idle UAVs (any UAV ready for assignment)
                # Exclude UAVs actively searching or guarding assets in SAR missions
                ready_uavs = [uid for uid, u in uavs.items()
                             if (u['state'] in ['recovered', 'idle']
                                 or (u['state'] == 'patrolling' and not u['assigned_zones']))
                             and not u.get('searching_asset')
                             and not u.get('guardian_of_asset')]

                if ready_uavs:
                    logger.info(f"Found {len(ready_uavs)} UAVs ready for assignment: {ready_uavs}")
                    new_assignments = []
                    for uid in sorted(ready_uavs):
                        assignments = workload_balancer.reassign_recovered_uav(uid, uavs, tasks)
                        new_assignments.extend(assignments)
                        ooda_count += 1

                    # Always update workload display when UAVs are reassigned
                    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
                    emit_ooda('decide', f'OODA #{ooda_count}: {len(ready_uavs)} UAVs deployed', critical=False)

                last_reassignment_time = current_time

            # --- Telemetry and Stats Update (Client Throttled to 10Hz) ---
            if current_time - last_telemetry_time > TELEMETRY_INTERVAL:

                safe_emit('telemetry', {'uavs': uavs, 'tasks': tasks})

                op = sum(1 for u in uavs.values() if u['operational'])
                failed = sum(1 for u in uavs.values() if u['state'] == 'crashed')
                returning = sum(1 for u in uavs.values() if u['returning'] or u['state'] == 'charging' or u['state'] == 'recovered')

                # Calculate average coverage (only for tasks that have coverage field)
                tasks_with_coverage = [t for t in tasks.values() if 'coverage' in t]
                avg_coverage = np.mean([t['coverage'] for t in tasks_with_coverage]) if tasks_with_coverage else 0

                # Calculate mission-specific completion metric
                if scenario_type == 'surveillance':
                    completion = avg_coverage
                elif scenario_type == 'search_rescue':
                    total_assets = mission_metrics.get('total_assets', 1)
                    completion = (mission_metrics['assets_rescued'] / total_assets * 100) if total_assets > 0 else 0
                elif scenario_type == 'delivery':
                    total_packages = mission_metrics.get('total_packages', 1)
                    completion = (mission_metrics['deliveries_completed'] / total_packages * 100) if total_packages > 0 else 0
                else:
                    completion = 0

                safe_emit('update', {
                    'fleet': {'operational': op, 'failed': failed, 'returning': returning},
                    'mission': {'completion_percent': completion},
                    'ooda_stats': {'total_cycles': ooda_count},
                    'metrics': mission_metrics
                })

                last_telemetry_time = current_time # Reset the timer

        
        # --- FIXED SLEEP ---
        time.sleep(LOOP_REAL_INTERVAL)

def safe_emit(event, data, broadcast=False):
    """Safely emit SocketIO events with error handling"""
    try:
        if broadcast:
            socketio.emit(event, data, broadcast=True)
        else:
            socketio.emit(event, data)
    except Exception as e:
        logger.error(f"Failed to emit {event}: {e}")

def emit_ooda(phase, message, critical=False):
    """
    Emit OODA event with explicit phase label.

    Args:
        phase: 'observe', 'orient', 'decide', or 'act'
        message: Event message string
        critical: Whether this is a critical event
    """
    safe_emit('ooda_event', {
        'phase': phase,
        'message': message,
        'critical': critical
    })

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    client_id = request.sid if hasattr(request, 'sid') else 'unknown'
    connected_clients.add(client_id)
    logger.info(f"Client connected: {client_id} (Total: {len(connected_clients)})")

    # Send initial state to newly connected client
    try:
        emit('telemetry', {'uavs': uavs, 'tasks': tasks})
        emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
        emit('pattern_update', {'pattern': patrol_pattern})
        emit('mode_update', {'mode': pattern_mode})
    except Exception as e:
        logger.error(f"Error sending initial state to client: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    try:
        client_id = request.sid if hasattr(request, 'sid') else 'unknown'
        connected_clients.discard(client_id)
        logger.info(f"Client disconnected: {client_id} (Remaining: {len(connected_clients)})")
    except Exception as e:
        logger.error(f"Error in disconnect handler: {e}")

@socketio.on_error_default
def default_error_handler(e):
    """Handle SocketIO errors"""
    logger.error(f"SocketIO error: {e}")

@app.route('/')
def index():
    return render_template('dashboard.html')

@socketio.on('start_mission')
def handle_start(data):
    global mission_active, scenario_type, SCENARIOS
    logger.info(f"DEBUG: Received start_mission event with data: {data}")  # DEBUG
    scenario_type = data['scenario']
    logger.info(f"DEBUG: scenario_type set to: {scenario_type}")  # DEBUG
    custom_home = data.get('home_base')

    # Apply custom fleet configuration if provided
    if 'num_uavs' in data:
        custom_uav_count = int(data['num_uavs'])
        SCENARIOS[scenario_type]['uavs'] = custom_uav_count
        logger.info(f"Fleet configuration: {custom_uav_count} UAVs requested")

    # Apply custom Surveillance configuration if provided
    if scenario_type == 'surveillance':
        if 'patrol_pattern' in data:
            SCENARIOS['surveillance']['patrol_pattern'] = data['patrol_pattern']
            logger.info(f"Surveillance configuration: patrol_pattern={data['patrol_pattern']}")
        if 'pattern_mode' in data:
            SCENARIOS['surveillance']['pattern_mode'] = data['pattern_mode']
            logger.info(f"Surveillance configuration: pattern_mode={data['pattern_mode']}")

    # Apply custom SAR configuration if provided
    if scenario_type == 'search_rescue':
        if 'num_assets' in data:
            SCENARIOS['search_rescue']['num_assets'] = int(data['num_assets'])
            logger.info(f"SAR configuration: num_assets={data['num_assets']}")
        if 'consensus_required' in data:
            SCENARIOS['search_rescue']['consensus_required'] = int(data['consensus_required'])
            logger.info(f"SAR configuration: consensus_required={data['consensus_required']}")

    # Apply custom Delivery configuration if provided
    if scenario_type == 'delivery':
        if 'num_packages' in data:
            SCENARIOS['delivery']['num_packages'] = int(data['num_packages'])
            logger.info(f"Delivery configuration: num_packages={data['num_packages']}")
        if 'time_window' in data:
            SCENARIOS['delivery']['time_window'] = int(data['time_window'])
            logger.info(f"Delivery configuration: time_window={data['time_window']}")

    init_scenario(scenario_type, custom_home)
    mission_active = True

    # Emit OODA events for all phases to clear "Waiting for mission start..." message
    emit_ooda('observe', f'Mission started: {scenario_type.upper()} scenario with {len(uavs)} UAVs', critical=False)
    emit_ooda('orient', f'Analyzing mission parameters and fleet capabilities', critical=False)
    emit_ooda('decide', f'Assigning initial tasks to {len(uavs)} operational UAVs', critical=False)
    emit_ooda('act', f'All {len(uavs)} UAVs deployed from {home_base[:2]}', critical=False)

@socketio.on('pause_mission')
def handle_pause():
    global mission_active
    mission_active = False

@socketio.on('stop_mission')
def handle_stop():
    """Stop current mission and clean up state."""
    global mission_active, uavs, tasks, sar_assets, delivery_packages

    logger.info("Stopping mission and cleaning up state...")
    mission_active = False

    # Clear all state
    uavs.clear()
    tasks.clear()
    if sar_assets:
        sar_assets.clear()
    if delivery_packages:
        delivery_packages.clear()

    # Notify client that mission has fully stopped
    # Note: Don't use broadcast=True here, as we want to send to the requesting client
    emit('mission_stopped', {'status': 'clean'})
    logger.info("Mission stopped and state cleared")

@socketio.on('set_speed')
def handle_speed(data):
    global simulation_speed
    simulation_speed = float(data['speed'])

@socketio.on('set_pattern')
def handle_pattern(data):
    global patrol_pattern
    new_pattern = data['pattern']
    valid_patterns = ['perimeter', 'lawnmower', 'spiral', 'creeping', 'random', 'figure8', 'sector']
    
    if new_pattern not in valid_patterns:
        logger.warning(f"Invalid pattern: {new_pattern}")
        return
    
    patrol_pattern = new_pattern
    logger.info(f"Patrol pattern changed to: {patrol_pattern}")
    
    # Recompute waypoints for all operational UAVs
    for uid, uav in uavs.items():
        if uav['operational'] and uav['assigned_zones']:
            uav['contour_waypoints'] = workload_balancer.compute_zone_contour(
                uav['assigned_zones'], tasks, patrol_pattern)
            uav['waypoint_idx'] = 0

    emit_ooda('decide', f'Patrol pattern changed to {new_pattern.upper()}', critical=False)
    safe_emit('pattern_update', {'pattern': patrol_pattern})

@socketio.on('set_pattern_mode')
def handle_pattern_mode(data):
    global pattern_mode
    new_mode = data['mode']
    valid_modes = ['per_zone', 'grouped']
    
    if new_mode not in valid_modes:
        logger.warning(f"Invalid pattern mode: {new_mode}")
        return
    
    pattern_mode = new_mode
    logger.info(f"Pattern mode changed to: {pattern_mode}")
    
    # Recompute waypoints for all operational UAVs
    for uid, uav in uavs.items():
        if uav['operational'] and uav['assigned_zones']:
            uav['contour_waypoints'] = workload_balancer.compute_zone_contour(
                uav['assigned_zones'], tasks)
            uav['waypoint_idx'] = 0

    mode_label = 'GROUPED (combined area)' if new_mode == 'grouped' else 'PER ZONE (individual)'
    emit_ooda('decide', f'Pattern mode: {mode_label}', critical=False)
    safe_emit('mode_update', {'mode': pattern_mode})

@socketio.on('inject_failure')
def handle_failure(data):
    global ooda_count
    uav_id = data['uav_id']
    
    if uav_id == 'random':
        operational = [uid for uid, u in uavs.items() if u['operational'] and not u['returning'] and u['assigned_zones']]
        if not operational:
            return
        uav_id = np.random.choice(operational)
    
    if uav_id not in uavs or uavs[uav_id]['state'] == 'crashed':
        return
    
    failed_zones = uavs[uav_id]['assigned_zones'].copy()
    uavs[uav_id]['operational'] = False
    uavs[uav_id]['assigned_zones'] = []
    uavs[uav_id]['contour_waypoints'] = []
    uavs[uav_id]['state'] = 'crashed'

    emit_ooda('observe', f'{uav_id} FAILED (Injected Crash)', critical=True)

    for zone_id in failed_zones:
        if zone_id in tasks and uav_id in tasks[zone_id]['assigned_uavs']:
            tasks[zone_id]['assigned_uavs'].remove(uav_id)
    
    ooda_count += 1
    operational = [uid for uid, u in uavs.items() if u['operational'] and u['state'] not in ['returning', 'charging', 'recovered']]
    
    if operational and failed_zones:
        logger.info(f"Redistributing zones {failed_zones} from {uav_id}")
        assignments = workload_balancer.redistribute_failed_zones(failed_zones, operational, uavs, tasks)
        
        unassigned = []
        for zid in failed_zones:
            if zid in tasks and len(tasks[zid]['assigned_uavs']) == 0:
                unassigned.append(zid)
        
        if unassigned:
            logger.warning(f"Zones {unassigned} remain unassigned after redistribution")
            for zone_id in unassigned:
                best_uav = min(operational, key=lambda u: len(uavs[u]['assigned_zones']))
                uavs[best_uav]['assigned_zones'].append(zone_id)
                tasks[zone_id]['assigned_uavs'].append(best_uav)
                new_contour = workload_balancer.compute_zone_contour(uavs[best_uav]['assigned_zones'], tasks)
                uavs[best_uav]['contour_waypoints'] = new_contour
                logger.info(f"Force assigned zone {zone_id} to {best_uav}")

        safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
        emit_ooda('decide', f'OODA #{ooda_count}: Redistributed {len(failed_zones)} zones', critical=False)

@socketio.on('manual_recovery')
def handle_manual_recovery(data):
    """Manually triggers a crashed UAV to return to base for charging and re-deployment."""
    uav_id = data['uav_id']
    
    if uav_id in uavs and uavs[uav_id]['state'] == 'crashed':
        uavs[uav_id]['state'] = 'returning'
        uavs[uav_id]['returning'] = True
        uavs[uav_id]['operational'] = False
        uavs[uav_id]['battery'] = 50
        uavs[uav_id]['position'][2] = 10

        emit_ooda('act', f'{uav_id} manual recovery initiated. Returning to base.', critical=False)
        safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    else:
        logger.warning(f"Attempted recovery on non-crashed or unknown UAV: {uav_id}")


@socketio.on('charge_battery')
def handle_charge_battery(data):
    """Manually sets a UAV's battery to 100%."""
    global ooda_count
    uav_id = data['uav_id']
    
    if uav_id not in uavs:
        logger.warning(f"Attempted to charge unknown UAV: {uav_id}")
        return
    
    uav = uavs[uav_id]
    old_battery = uav['battery']
    uav['battery'] = 100
    uav['battery_warning'] = False

    logger.info(f"CHARGE_BATTERY called for {uav_id}: {old_battery:.1f}% -> 100%, state={uav['state']}, searching_asset={uav.get('searching_asset')}")

    # If UAV was returning due to low battery, it can now continue its mission
    if uav['state'] in ['returning', 'charging']:
        uav['returning'] = False
        uav['state'] = 'recovered'
        emit_ooda('observe', f'{uav_id} battery charged to 100% - ready for redeployment', critical=False)
    elif uav['state'] == 'crashed':
        # Revive crashed UAV
        uav['state'] = 'recovered'
        uav['returning'] = False
        uav['operational'] = False  # Will be set to True upon reassignment
        emit_ooda('act', f'{uav_id} revived and charged to 100%', critical=False)
    else:
        emit_ooda('observe', f'{uav_id} battery topped up: {old_battery:.0f}% -> 100%', critical=False)

    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    logger.info(f"Battery charged for {uav_id}: {old_battery:.0f}% -> 100%")


@socketio.on('charge_all_batteries')
def handle_charge_all():
    """Charge all UAVs to 100%."""
    charged_count = 0
    for uav_id, uav in uavs.items():
        if uav['battery'] < 100:
            uav['battery'] = 100
            uav['battery_warning'] = False
            charged_count += 1
            
            if uav['state'] in ['returning', 'charging']:
                uav['returning'] = False
                uav['state'] = 'recovered'
            elif uav['state'] == 'crashed':
                uav['state'] = 'recovered'
                uav['returning'] = False

    if charged_count > 0:
        emit_ooda('observe', f'All {charged_count} UAVs charged to 100%', critical=False)
        safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    logger.info(f"Charged all UAVs: {charged_count} units topped up")


@socketio.on('drain_battery')
def handle_drain_battery(data):
    """Manually sets a UAV's battery to 15%."""
    uav_id = data['uav_id']

    if uav_id not in uavs:
        logger.warning(f"Attempted to drain unknown UAV: {uav_id}")
        return

    uav = uavs[uav_id]
    old_battery = uav['battery']
    uav['battery'] = 15
    uav['battery_warning'] = True

    emit_ooda('observe', f'{uav_id} battery drained: {old_battery:.0f}% → 15%', critical=False)
    safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    logger.info(f"Battery drained for {uav_id}: {old_battery:.0f}% → 15%")


@socketio.on('drain_all_batteries')
def handle_drain_all():
    """Drain all UAVs to 15%."""
    drained_count = 0
    for uav_id, uav in uavs.items():
        if uav['battery'] != 15:
            uav['battery'] = 15
            uav['battery_warning'] = True
            drained_count += 1

    if drained_count > 0:
        emit_ooda('observe', f'All {drained_count} UAVs drained to 15%', critical=False)
        safe_emit('workload_update', {'assignments': workload_balancer.get_current_assignments(uavs, tasks, scenario_type)})
    logger.info(f"Drained all UAVs: {drained_count} units set to 15%")


@socketio.on('grant_permission')
def handle_grant_permission(data):
    """Grant permission for UAV to proceed to out-of-grid destination."""
    uav_id = data.get('uav_id')

    if not uav_id:
        logger.warning("grant_permission called without uav_id")
        return

    if uav_id not in uavs:
        logger.warning(f"Attempted to grant permission to unknown UAV: {uav_id}")
        return

    uav = uavs[uav_id]

    logger.info(f"GRANT_PERMISSION: {uav_id} at position {uav['position']}, battery {uav['battery']:.1f}%, state '{uav['state']}'")

    # Check if UAV is in awaiting_permission state
    if not uav.get('awaiting_permission', False):
        logger.warning(f"Attempted to grant permission to {uav_id} which is not awaiting permission (state: {uav['state']})")
        return

    # Grant permission - reset awaiting_permission flag and resume appropriate state
    uav['awaiting_permission'] = False

    logger.info(f"GRANT_PERMISSION: {uav_id} permission cleared, searching_asset={uav.get('searching_asset')}, assigned_task={uav.get('assigned_task')}")

    # Determine which state to resume based on mission context
    if uav.get('searching_asset') or uav.get('guardian_of_asset'):
        # SAR mission - resume searching/circling asset
        uav['state'] = 'searching'
        mission_context = "asset search"
    elif uav.get('assigned_task'):
        # Delivery mission - resume delivery
        uav['state'] = 'delivering'
        mission_context = "delivery"
    else:
        # Fallback - resume patrolling
        uav['state'] = 'patrolling'
        mission_context = "patrol"

    # Mark that permission has been granted for this specific target
    target = uav.get('out_of_grid_target')
    if target:
        uav['permission_granted_for_target'] = tuple(target[:2])  # Store as tuple for comparison
        logger.info(f"Permission granted for {uav_id} to proceed to out-of-grid destination ({target[0]:.1f}, {target[1]:.1f}) - resuming {mission_context}")
        emit_ooda('act', f'{uav_id} PERMISSION GRANTED - proceeding to out-of-grid {mission_context} ({target[0]:.0f}, {target[1]:.0f})', critical=False)
    else:
        uav['permission_granted_for_target'] = None
        logger.info(f"Permission granted for {uav_id} to proceed with delivery")
        emit_ooda('act', f'{uav_id} PERMISSION GRANTED - resuming delivery', critical=False)

    # Clear the boundary stop data (optional - kept for potential future use)
    # uav['boundary_stop_position'] = None
    # uav['out_of_grid_target'] = None

    safe_emit('telemetry', {'uavs': uavs, 'tasks': tasks})


@socketio.on('move_asset')
def handle_move_asset(data):
    """Move a SAR asset or delivery package to a new position."""
    asset_id = data['asset_id']
    new_x = data['x']
    new_y = data['y']

    # Check if it's a SAR asset
    if asset_id in tasks and tasks[asset_id].get('type') == 'asset':
        old_pos = tasks[asset_id]['position'][:2]
        tasks[asset_id]['position'] = [new_x, new_y, 0]
        emit_ooda('act', f'{asset_id} relocated: ({old_pos[0]:.0f},{old_pos[1]:.0f}) → ({new_x:.0f},{new_y:.0f})', critical=False)
        logger.info(f"SAR asset {asset_id} moved to ({new_x}, {new_y})")
    # Check if it's a delivery task
    elif asset_id in tasks and tasks[asset_id].get('type') == 'delivery':
        old_pos = tasks[asset_id]['pickup'][:2]
        tasks[asset_id]['pickup'] = [new_x, new_y, 10]
        emit_ooda('act', f'{asset_id} relocated: ({old_pos[0]:.0f},{old_pos[1]:.0f}) → ({new_x:.0f},{new_y:.0f})', critical=False)
        logger.info(f"Delivery package {asset_id} moved to ({new_x}, {new_y})")


@socketio.on('randomize_assets')
def handle_randomize_assets():
    """Randomize all SAR asset and delivery package positions within grid boundaries."""
    import random

    randomized_count = 0

    # Grid boundaries: 3x3 zones of 40m each, centered at [-40, 0, 40]
    # Safe bounds to keep assets within the grid
    GRID_MIN = -55
    GRID_MAX = 55

    # Randomize SAR assets (only unidentified ones)
    for asset_id, asset in tasks.items():
        if asset.get('type') == 'asset':
            # Skip identified or rescued assets - their positions are locked
            if asset.get('identified') or asset.get('rescued'):
                continue

            # Random position within grid bounds
            new_x = random.uniform(GRID_MIN, GRID_MAX)
            new_y = random.uniform(GRID_MIN, GRID_MAX)
            asset['position'] = [new_x, new_y, 0]
            randomized_count += 1

    # Randomize delivery packages (both pickup and dropoff locations)
    for task_id, task in tasks.items():
        if task.get('type') == 'delivery':
            # Only randomize if package hasn't been picked up yet
            if task.get('status') in ['pending', 'assigned']:
                # Randomize pickup location
                pickup_x = random.uniform(GRID_MIN, GRID_MAX)
                pickup_y = random.uniform(GRID_MIN, GRID_MAX)
                task['pickup'] = [pickup_x, pickup_y, 10]

                # Randomize dropoff location
                dropoff_x = random.uniform(GRID_MIN, GRID_MAX)
                dropoff_y = random.uniform(GRID_MIN, GRID_MAX)
                task['dropoff'] = [dropoff_x, dropoff_y, 10]

                randomized_count += 1

    if randomized_count > 0:
        emit_ooda('act', f'Randomized {randomized_count} asset positions within grid', critical=False)
        logger.info(f"Randomized {randomized_count} asset/package positions within grid boundaries")


@socketio.on('request_update')
def handle_update():
    # Only emit a single telemetry update on request (e.g., from the client's periodic check)
    if not mission_active:
        safe_emit('telemetry', {'uavs': uavs, 'tasks': tasks})

def start_dashboard(port=8085):
    threading.Thread(target=simulation_loop, daemon=True).start()
    print(f"\nDashboard: http://localhost:{port}")
    print(f"Home base centered at: {home_base}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    start_dashboard()