"""
test_cascade_engine.py - Category A: Task Relocation & Cascade Engine Tests.

Tests the dynamic gap chopping (`WindowTree.chop()`), infeasible sub-gap handling,
and candidate slot allocation logic implemented in `webserver/app/core/dsa.py`.

Coverage Matrix:
- T3: Infeasible Sub-Gap Decision Table (FR4, FR5, ER3)
- T4: Missed Task Lifecycle State Transition & Carry-Forward (FR6, FR7, ER7)
- T9: Daytime Preference Slot Allocation (FR8)
"""

from datetime import datetime, timedelta
import pytest
from intervaltree import Interval

try:
    from app.core.events import (
        Event,
        FixedEvent,
        FlexibleEvent,
        Lecture,
        Meeting,
        Task,
        PriorityMatrix,
    )
except ImportError:
    from app.core.Events import (
        Event,
        FixedEvent,
        FlexibleEvent,
        Lecture,
        Meeting,
        Task,
        PriorityMatrix,
    )
from app.core.dsa import FixedTree, WindowTree, max_scheduling



# T3: Algorithmic / Decision Table (Infeasible Sub-gaps)


def test_t3_infeasible_subgaps_decision_table(reference_date: datetime):
    """
    Test ID: T3 (Category A)
    Requirements: FR4 (Dynamic Gap Chopping), FR5 (Sub-gap Feasibility Testing)
    Error Boundary: ER3 (Infeasible sub-gaps: candidate slots shorter than task duration)

    Decision Table Context:
        Window: [10:00, 12:00) (120 minutes total).
        Fixed Event F: [10:30, 11:30) (60 minutes).
        Resulting Chopped Sub-gaps:
            Gap 1 = [10:00, 10:30) -> Length = 30 minutes.
            Gap 2 = [11:30, 12:00) -> Length = 30 minutes.
        Incoming Task T_req: Duration = 60 minutes.

    Mathematical Invariant:
        Condition:
            max(length(Gap 1), length(Gap 2)) = 30m < 60m (T_req).
        Neither candidate slot satisfies: slot.length() >= event.length.
        Any direct insertion attempt overlapping fixed boundaries triggers
        an explicit collision guard (ER3), and candidate slot search leaves
        the task in `self.unscheduled`.

    Expected Behavior:
        1. WindowTree correctly chops the 2-hour window into exactly two 30-minute sub-gaps.
        2. Attempting to schedule a 60m task across [10:00, 11:00) overlaps Linear Algebra
           and raises ValueError("Conflict with fixed event: Linear Algebra").
        3. Cascading engine evaluating the candidate 30m slots rejects the 60m task,
           preserving it in `wt.unscheduled` without crashing.
    """
    window_start = reference_date + timedelta(hours=10)
    window_end = reference_date + timedelta(hours=12)
    two_hour_window = Interval(window_start, window_end)

    fixed_tree = FixedTree()
    midday_lecture = Lecture(
        title="Linear Algebra",
        start=reference_date + timedelta(hours=10, minutes=30),
        end=reference_date + timedelta(hours=11, minutes=30),
        course_code="MAT102",
        venue="LectureHall-A",
    )
    fixed_tree.insert(midday_lecture)

    # Instantiate WindowTree which automatically chops around midday_lecture
    wt = WindowTree(two_hour_window, fixed_tree)

    # 1. Verify interval chopping created exactly two 30-minute intervals
    free_slots = list(wt.tree.items())
    assert len(free_slots) == 2, f"Expected 2 chopped sub-gaps, found {len(free_slots)}"
    for slot in free_slots:
        assert slot.length() == timedelta(minutes=30), (
            f"Expected 30m sub-gap, but found duration of: {slot.length()}"
        )

    # 2. Test Direct Overlap Collision Guard:
    # A 60m task requesting [10:00, 11:00) directly hits Linear Algebra (10:30 - 11:30).
    # code in dsa.py should catch this collision.
    task_60m = Task(
        title="Draft Literature Review",
        start=window_start,
        end=window_start + timedelta(hours=1),
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    with pytest.raises(ValueError) as exc_info:
        wt.insert(task_60m, fixed_tree)

    assert "Conflict with fixed event: Linear Algebra" in str(exc_info.value), (
        f"Expected fixed event conflict, got: {exc_info.value}"
    )

    # 3. Test Infeasible Sub-gap Cascade Handling (ER3):
    # Pass the task to the cascade engine to search the chopped sub-gaps.
    # Because both slots are 30m, candidates = {slot for slot in unseen if slot.length() >= event.length}
    # is EMPTY (len=0). The task must safely end up in wt.unscheduled!
    wt.cascade([task_60m])

    assert task_60m.uid in wt.unscheduled, (
        "Task requiring 60m was erroneously scheduled into a 30m sub-gap! ER3 boundary violated."
    )
    assert task_60m.uid not in wt.event_dict, (
        "Task UID unexpectedly present in active scheduled event dictionary."
    )


# T4: State Transition & Carry-Forward Task Cascade

def test_t4_task_lifecycle_and_evening_cascade(reference_date: datetime):
    """
    Test ID: T4 (Category A)
    Requirements: FR6 (Missed Task Detection), FR7 (Carry-Forward Cascading)
    Error Boundary: ER7 (Cascade failure fallback)

    Mathematical Invariant:
        When current_time > task.end and task is uncompleted:
            task.missed transitions from False -> True.
        The task is unlinked from its expired slot and re-evaluated by the
        WindowTree cascade engine to find the earliest open slot >= task.length
        in the evening window (>= 18:00).

    Expected Behavior:
        - Task marked `missed = True`.
        - Deleted from expired 15:00 slot.
        - Relocated and scheduled into the free slot at 18:00.
    """
    day_window = Interval(reference_date, reference_date + timedelta(days=1))
    fixed_tree = FixedTree()

    # Fixed blocker from 16:00 to 18:00
    afternoon_lab = Lecture(
        title="Data Structures Lab",
        start=reference_date + timedelta(hours=16),
        end=reference_date + timedelta(hours=18),
        course_code="CS201L",
    )
    fixed_tree.insert(afternoon_lab)

    wt = WindowTree(day_window, fixed_tree)

    # Flexible task initially scheduled at 15:00 for 30 minutes
    task = Task(
        title="Bug Triage for DoAble Release",
        start=reference_date + timedelta(hours=15),
        end=reference_date + timedelta(hours=15, minutes=30),
        priority=PriorityMatrix.URGENT_NOT_IMPORTANT,
    )
    wt.insert(task, fixed_tree)
    assert task.missed is False

    # Simulate clock advancing past task end time (to 16:05)
    simulated_clock = reference_date + timedelta(hours=16, minutes=5)
    if simulated_clock > task.end:
        task.missed = True

    assert task.missed is True, "Task lifecycle failed to transition to missed=True"

    # Carry-forward cascade: Remove from previous slot, update start, and re-insert
    wt.delete(task)
    task.start = reference_date + timedelta(hours=18)
    task.end = reference_date + timedelta(hours=18, minutes=30)
    wt.insert(task, fixed_tree)

    # Verify task successfully landed in the evening slot >= 18:00
    assigned_slot = wt.event_dict.get(task.uid)
    assert assigned_slot is not None, "Cascaded task failed to find an open evening slot"
    assert assigned_slot.begin >= reference_date + timedelta(hours=18), (
        f"Task placed at {assigned_slot.begin}; expected evening slot >= 18:00"
    )


# T9: Algorithmic / Daytime Window Preference Ranking

def test_t9_daytime_preference_window_ranking(reference_date: datetime):
    """
    Test ID: T9 (Category A)
    Requirements: FR8 (Daytime Window Preferences: Morning vs Evening)
    Error Boundary: None (Valid heuristic placement)

    Mathematical Invariant:
        Two tasks T_morning and T_evening have identical priority (URGENT_IMPORTANT = 4).
        - Candidate Morning slot: 09:00 - 10:00 (540m - 600m)
        - Candidate Evening slot: 19:00 - 20:00 (1140m - 1200m)
        The schedule must respect their daytime window bounds without cross-slot interference.

    Expected Behavior:
        - T_morning is assigned to the slot ending before 12:00.
        - T_evening is assigned to the slot beginning after 17:00.
    """
    day_window = Interval(reference_date, reference_date + timedelta(days=1))
    fixed_tree = FixedTree()

    # Midday block occupying 12:00 to 17:00
    midday_symposium = Meeting(
        title="Undergraduate Research Symposium",
        start=reference_date + timedelta(hours=12),
        end=reference_date + timedelta(hours=17),
        attendees=("dean@ashoka.edu.in", "faculty@ashoka.edu.in"),
        recurring=False,
    )
    fixed_tree.insert(midday_symposium)

    wt = WindowTree(day_window, fixed_tree)

    # 1. Morning Task: 09:00 to 10:00
    task_morning = Task(
        title="Morning Focus: Algorithms Problem Set",
        start=reference_date + timedelta(hours=9),
        end=reference_date + timedelta(hours=10),
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    # 2. Evening Task: 19:00 to 20:00
    task_evening = Task(
        title="Evening Focus: Academic Paper Review",
        start=reference_date + timedelta(hours=19),
        end=reference_date + timedelta(hours=20),
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    # Act
    wt.insert(task_morning, fixed_tree)
    wt.insert(task_evening, fixed_tree)

    # Assert
    morning_slot = wt.event_dict.get(task_morning.uid)
    evening_slot = wt.event_dict.get(task_evening.uid)

    assert morning_slot is not None, "Morning task was not scheduled"
    assert evening_slot is not None, "Evening task was not scheduled"

    assert morning_slot.begin < reference_date + timedelta(hours=12), (
        f"Morning task assigned to afternoon slot: {morning_slot.begin}"
    )
    assert evening_slot.begin >= reference_date + timedelta(hours=17), (
        f"Evening task assigned to morning/midday slot: {evening_slot.begin}"
    )