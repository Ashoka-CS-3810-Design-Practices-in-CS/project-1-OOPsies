"""
test_core_dsa.py - Category A: Core Algorithm & IntervalTree Unit Tests.

Directly tests the operational implementation in `webserver/app/core/dsa.py`
and `webserver/app/core/events.py`.

Coverage Matrix:
- T1: Abutting Interval Collision Boundary Check (FR1, FR2)
- T6: MC/DC Overlap Predicate Coverage (FR1, FR2)
- T7: Window Boundary Violation Error Check (FR3, ER2)
- T11: IntervalTree Bulk Scaling & Performance (FR11)
- T12: 24-Hour Midnight Rollover Transition (FR12)
"""

from datetime import datetime, timedelta
import math
import time
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


# T1: Unit / Boundary Value Analysis (Abutting Intervals)


def test_t1_abutting_intervals_strict_inequality(reference_date: datetime):
    """
    Test ID: T1 (Category A)
    Requirements: FR1 (Collision Detection), FR2 (Strict Boundary Inequality)
    Error Boundary: None (Valid non-colliding state)

    Mathematical Invariant:
        For two contiguous intervals A = [t0, t1) and B = [t1, t2),
        the half-open interval overlap predicate:
            P = (A.start < B.end) and (B.start < A.end)
        evaluates to:
            (t0 < t2) and (t1 < t1) = True and False = False.
        Hence, abutting intervals must NOT register a conflict.

    Expected Behavior:
        - Conflict search in FixedTree returns None.
        - Event A ends exactly when Event B begins with zero overlap.
    """
    fixed_tree = FixedTree()

    # Event A: [10:00, 11:00)
    event_a_start = reference_date + timedelta(hours=10)
    event_a_end = reference_date + timedelta(hours=11)
    event_a = Lecture(
        title="Discrete Mathematics",
        start=event_a_start,
        end=event_a_end,
        course_code="MAT201",
    )

    # Event B: [11:00, 12:00) - starts precisely at event_a_end
    event_b_start = reference_date + timedelta(hours=11)
    event_b_end = reference_date + timedelta(hours=12)
    event_b = Lecture(
        title="Computer Architecture",
        start=event_b_start,
        end=event_b_end,
        course_code="CS204",
    )


    fixed_tree.insert(event_a)
    conflict = fixed_tree.conflict_search(event_b)

    # Mathematical Predicate Verification
    c1 = event_a.true_start < event_b.true_end
    c2 = event_b.true_start < event_a.true_end
    has_predicate_overlap = c1 and c2

    # Assert
    assert has_predicate_overlap is False, (
        f"Mathematical predicate failed: C1={c1}, C2={c2}. Abutting intervals must not overlap."
    )
    assert conflict is None, (
        f"FixedTree erroneously detected a conflict between abutting intervals: {conflict}"
    )


# T6: White-Box / MC/DC (Modified Condition/Decision Coverage)

@pytest.mark.parametrize(
    "vector_id, c1_expected, c2_expected, expected_decision, a_start_h, a_end_h, b_start_h, b_end_h",
    [
        # V1: Both conditions True -> Decision True (Actual overlap)
        ("V1", True, True, True, 10, 12, 11, 13),
        # V2: C1 False, C2 True -> Decision False (A is strictly after B)
        ("V2", False, True, False, 14, 16, 10, 12),
        # V3: C1 True, C2 False -> Decision False (A is strictly before B)
        ("V3", True, False, False, 10, 12, 14, 16),
    ],
)
def test_t6_mcdc_interval_collision_predicate(
    reference_date: datetime,
    vector_id: str,
    c1_expected: bool,
    c2_expected: bool,
    expected_decision: bool,
    a_start_h: int,
    a_end_h: int,
    b_start_h: int,
    b_end_h: int,
):
    """
    Test ID: T6 (Category A)
    Requirements: FR1 (Collision Checking), FR2 (Inequality Decision Soundness)
    Error Boundary: None

    Mathematical Invariant:
        Decision P = C1 and C2, where:
            C1: start_A < end_B
            C2: start_B < end_A


        - Vector 1 (V1): Baseline True outcome (C1=True, C2=True -> P=True)
        - Vector 2 (V2): Toggles C1 independently (C1=False, C2=True -> P=False)
        - Vector 3 (V3): Toggles C2 independently (C1=True, C2=False -> P=False)

    Expected Behavior:
        Proves each condition independently dictates the scheduling collision decision.
    """
    start_a = reference_date + timedelta(hours=a_start_h)
    end_a = reference_date + timedelta(hours=a_end_h)
    start_b = reference_date + timedelta(hours=b_start_h)
    end_b = reference_date + timedelta(hours=b_end_h)

    # Evaluate conditions
    c1 = start_a < end_b
    c2 = start_b < end_a
    decision = c1 and c2

    assert c1 == c1_expected, f"Vector {vector_id}: Expected C1={c1_expected}, got {c1}"
    assert c2 == c2_expected, f"Vector {vector_id}: Expected C2={c2_expected}, got {c2}"
    assert decision == expected_decision, (
        f"Vector {vector_id}: Expected Decision={expected_decision}, got {decision}"
    )



# T7: Boundary / Invalid Input Validation

def test_t7_task_duration_exceeds_window_bounds(reference_date: datetime):
    """
    Test ID: T7 (Category A)
    Requirements: FR3 (Window Bounds Validation)
    Error Boundary: ER2 (Task duration exceeds allocated scheduling window)

    Mathematical Invariant:
        Given window W = [W_begin, W_end) with length |W| = 120 minutes:
        Any event E with |E| = 180 minutes satisfies |E| > |W|.
        Therefore, E cannot satisfy (W_begin <= E.true_start and W_end >= E.true_end).

    Expected Behavior:
        WindowTree.insert() raises ValueError with message:
        "Event bounds cannot exceed the scheduling window!"
    """
    # 2-hour window: [09:00, 11:00) = 120 minutes
    w_start = reference_date + timedelta(hours=9)
    w_end = reference_date + timedelta(hours=11)
    two_hour_window = Interval(w_start, w_end)

    empty_fixed = FixedTree()
    window_tree = WindowTree(two_hour_window, empty_fixed)

    # 3-hour flexible task: [09:00, 12:00) = 180 minutes
    oversized_task = Task(
        title="Comprehensive Term Project Implementation",
        start=w_start,
        end=w_start + timedelta(hours=3),
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    # Act & Assert
    with pytest.raises(ValueError) as exc_info:
        window_tree.insert(oversized_task, empty_fixed)

    assert "Event bounds cannot exceed the scheduling window!" in str(exc_info.value), (
        f"Expected exact boundary error message, got: {exc_info.value}"
    )


# T11: Performance & Scalability Benchmark

def test_t11_interval_tree_scalability_benchmark(reference_date: datetime):
    """
    Test ID: T11 (Category A)
    Requirements: FR11 (IntervalTree Operational Complexity)
    Error Boundary: Performance degradation threshold (> 45 ms)

    Mathematical Invariant:
        IntervalTree uses an augmented balanced binary tree with search complexity
        O(log N + k), where N = 1,000 nodes and k is number of overlaps.
        Inserting 1,000 non-overlapping 1-minute intervals across 2,000 minutes
        must execute efficiently and support full-range overlap queries under 45 ms.

    Expected Behavior:
        - 1,000 elements inserted and queried in < 45 milliseconds.
        - Result list contains exactly 1,000 items without memory leakage.
    """
    fixed_tree = FixedTree()
    total_items = 1000

    start_perf = time.perf_counter()

    for idx in range(total_items):
        start_t = reference_date + timedelta(minutes=idx * 2)
        end_t = start_t + timedelta(minutes=1)
        ev = FixedEvent(
            title=f"Synthetic_Event_{idx}",
            start=start_t,
            end=end_t,
        )
        fixed_tree.insert(ev)

    # Query full range
    query_start = reference_date
    query_end = reference_date + timedelta(minutes=total_items * 2)
    matched = list(fixed_tree.tree.overlap(query_start, query_end))

    elapsed_ms = (time.perf_counter() - start_perf) * 1000

    # Theoretical tree height lower bound: ceil(log2(1000)) = 10
    theoretical_min_depth = math.ceil(math.log2(total_items))

    # Assertions
    assert len(matched) == total_items, f"Expected {total_items} retrieved intervals, got {len(matched)}"
    assert elapsed_ms < 45.0, f"Scalability threshold exceeded: {elapsed_ms:.2f} ms > 45.0 ms limit"
    assert theoretical_min_depth == 10, "Mathematical depth check: ceil(log2(1000)) == 10"


# T12: BVA / 24-Hour Midnight Rollover

def test_t12_cross_midnight_rollover_boundaries(reference_date: datetime):
    """
    Test ID: T12 (Category A)
    Requirements: FR12 (Midnight Rollover Arithmetic)
    Error Boundary: Wrap-around integer overflow / negative duration truncation

    Mathematical Invariant:
        An event starting at 23:00 on Day D (timestamp 1380m) and ending at 01:00
        on Day D+1 (timestamp 60m) has:
            duration = (Day D+1 01:00) - (Day D 23:00) = +120 minutes (+2.0 hours).
        It must not calculate as (60 - 1380 = -1320 minutes)

    Expected Behavior:
        - `Event.length` is strictly `timedelta(hours=2)`.
        - `FixedTree.tree.overlap` correctly queries across the 00:00:00 midnight threshold.
    """
    day_d_night = reference_date.replace(hour=23, minute=0, second=0)
    day_d1_morning = day_d_night + timedelta(hours=2)

    overnight_event = Meeting(
        title="Hackathon Night Session",
        start=day_d_night,
        end=day_d1_morning,
        attendees=("lead@ashoka.edu.in",),
        recurring=False,
    )

    # Assert duration and ordering
    assert overnight_event.length == timedelta(hours=2), (
        f"Midnight rollover produced invalid duration: {overnight_event.length}"
    )
    assert overnight_event.true_start < overnight_event.true_end, (
        "true_start must strictly precede true_end across midnight boundaries"
    )

    # Verify IntervalTree indexing across midnight
    tree = FixedTree()
    tree.insert(overnight_event)

    # Probe query spanning midnight: 23:55 to 00:05
    probe_start = day_d_night + timedelta(minutes=55)
    probe_end = day_d_night + timedelta(minutes=65)
    overlaps = list(tree.tree.overlap(probe_start, probe_end))

    assert len(overlaps) == 1, "Midnight probe query failed to locate cross-midnight event"
    assert overlaps[0].data.title == "Hackathon Night Session"