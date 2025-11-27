"""
Mission Manager - Task database and assignment management.

Author: Vítor Eulálio Reis <vitor.reis@proton.me>
Copyright (c) 2025

This module provides the authoritative task database for mission management.
It tracks all tasks, their assignments to UAVs, and their execution status.

Key Classes:
    MissionDatabase: Central repository for tasks and assignments
    Task: Data structure for individual mission tasks
    TaskType: Enumeration of mission types (surveillance, search_rescue, delivery)
    TaskStatus: Enumeration of task states (pending, assigned, completed, failed)

Task Lifecycle:
    1. PENDING: Task created but not assigned
    2. ASSIGNED: Task allocated to a UAV
    3. IN_PROGRESS: UAV is executing the task
    4. COMPLETED: Task successfully finished
    5. FAILED: Task could not be completed

Usage:
    >>> db = MissionDatabase()
    >>> task_id = db.add_task(
    ...     task_type=TaskType.SURVEILLANCE,
    ...     position=np.array([100, 200, 25]),
    ...     priority=75
    ... )
    >>> db.assign_task(task_id, uav_id=1)
    >>> db.mark_completed(task_id)

OODA Integration:
    The MissionDatabase is used by the OODA engine during the DECIDE phase
    to commit reallocation decisions atomically via `commit_reallocation()`.
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# Import MissionContext for type hints (avoid circular import)
# The actual MissionContext class is in objective_function.py
try:
    from .objective_function import MissionContext, MissionType
except ImportError:
    MissionContext = None
    MissionType = None


class TaskType(Enum):
    SURVEILLANCE = "surveillance"
    SEARCH_RESCUE = "search_rescue"
    DELIVERY = "delivery"


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Mission task definition"""

    id: int
    type: TaskType
    position: np.ndarray  # [x, y, z]
    priority: float  # 0-100
    status: TaskStatus = TaskStatus.PENDING
    assigned_uav: Optional[int] = None

    # Optional attributes
    deadline: Optional[float] = None
    duration_sec: float = 60.0
    payload_kg: Optional[float] = None
    zone_id: Optional[int] = None


class MissionDatabase:
    """
    Authoritative mission database managing tasks and assignments
    """

    def __init__(self, mission_context: Optional["MissionContext"] = None):
        self.tasks: Dict[int, Task] = {}
        self.uav_assignments: Dict[int, List[int]] = {}  # UAV ID -> Task IDs
        self.next_task_id = 1

        # Mission context for objective function optimization
        self._mission_context = mission_context
        self._mission_type: Optional[TaskType] = None
        self._mission_start_time: Optional[float] = None

    @property
    def mission_context(self) -> Optional["MissionContext"]:
        """Get current mission context"""
        return self._mission_context

    @mission_context.setter
    def mission_context(self, context: "MissionContext"):
        """Set mission context"""
        self._mission_context = context
        if context and hasattr(context, "mission_type"):
            # Map MissionType to TaskType
            type_map = {
                "surveillance": TaskType.SURVEILLANCE,
                "search_rescue": TaskType.SEARCH_RESCUE,
                "delivery": TaskType.DELIVERY,
            }
            mission_type_str = (
                context.mission_type.value
                if hasattr(context.mission_type, "value")
                else str(context.mission_type)
            )
            self._mission_type = type_map.get(mission_type_str, TaskType.SURVEILLANCE)
        logger.info(f"Mission context set: {self._mission_type}")

    def get_mission_type(self) -> Optional[TaskType]:
        """Get inferred mission type from tasks or context"""
        if self._mission_type:
            return self._mission_type

        # Infer from majority task type
        if self.tasks:
            type_counts: Dict[TaskType, int] = {}
            for task in self.tasks.values():
                type_counts[task.type] = type_counts.get(task.type, 0) + 1
            return max(type_counts, key=type_counts.get)

        return None

    def add_task(
        self, task_type: TaskType, position: np.ndarray, priority: float, **kwargs
    ) -> int:
        """Add new task to database"""
        task_id = self.next_task_id
        self.next_task_id += 1

        task = Task(
            id=task_id, type=task_type, position=position, priority=priority, **kwargs
        )

        self.tasks[task_id] = task
        logger.info(f"Added task {task_id}: {task_type.value} at {position}")
        return task_id

    def assign_task(self, task_id: int, uav_id: int):
        """Assign task to UAV"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.tasks[task_id]

        # Remove from previous assignment if exists
        if task.assigned_uav is not None:
            self.uav_assignments[task.assigned_uav].remove(task_id)

        # Assign to new UAV
        task.assigned_uav = uav_id
        task.status = TaskStatus.ASSIGNED

        if uav_id not in self.uav_assignments:
            self.uav_assignments[uav_id] = []
        self.uav_assignments[uav_id].append(task_id)

        logger.debug(f"Assigned task {task_id} to UAV {uav_id}")

    def get_task(self, task_id: int) -> Optional[Task]:
        """Retrieve task by ID"""
        return self.tasks.get(task_id)

    def get_uav_tasks(self, uav_id: int) -> List[int]:
        """Get all tasks assigned to UAV"""
        return self.uav_assignments.get(uav_id, [])

    def get_affected_zones(self, task_ids: List[int]) -> List[int]:
        """Get zones affected by given tasks"""
        zones = set()
        for task_id in task_ids:
            task = self.get_task(task_id)
            if task and task.zone_id is not None:
                zones.add(task.zone_id)
        return list(zones)

    def commit_reallocation(self, reallocation_plan: Dict[int, List[int]]):
        """
        Commit OODA reallocation decision to database
        Updates task assignments atomically
        """
        # Verify all tasks exist
        all_tasks = [tid for tasks in reallocation_plan.values() for tid in tasks]
        for task_id in all_tasks:
            if task_id not in self.tasks:
                raise ValueError(f"Cannot reallocate non-existent task {task_id}")

        # Apply reallocation
        for uav_id, task_ids in reallocation_plan.items():
            for task_id in task_ids:
                self.assign_task(task_id, uav_id)

        logger.info(
            f"Committed reallocation: {len(all_tasks)} tasks across "
            f"{len(reallocation_plan)} UAVs"
        )

    def mark_completed(self, task_id: int):
        """Mark task as completed"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.COMPLETED
            logger.info(f"Task {task_id} completed")

    def mark_failed(self, task_id: int):
        """Mark task as failed"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.FAILED
            logger.error(f"Task {task_id} failed")

    def get_lost_tasks(self, uav_id: int) -> List[int]:
        """Get all tasks from failed UAV"""
        return self.get_uav_tasks(uav_id)

    def get_mission_stats(self) -> Dict:
        """Get mission statistics"""
        total = len(self.tasks)
        by_status = {}

        for status in TaskStatus:
            count = sum(1 for t in self.tasks.values() if t.status == status)
            by_status[status.value] = count

        completion = (by_status.get("completed", 0) / total * 100) if total > 0 else 0

        return {
            "total_tasks": total,
            "by_status": by_status,
            "completion_percent": completion,
        }

    def load_mission_scenario(self, scenario: dict):
        """Load predefined mission scenario"""
        for task_def in scenario.get("tasks", []):
            self.add_task(
                task_type=TaskType(task_def["type"]),
                position=np.array(task_def["position"]),
                priority=task_def["priority"],
                deadline=task_def.get("deadline"),
                duration_sec=task_def.get("duration_sec", 60.0),
                payload_kg=task_def.get("payload_kg"),
                zone_id=task_def.get("zone_id"),
            )

        logger.info(f"Loaded mission scenario: {len(self.tasks)} tasks")
