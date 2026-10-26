"""
conftest.py - Shared Pytest Fixtures for DoAble Smart Scheduler.

Provides deterministic fixtures matching the domain models in
`webserver/app/core/events.py` and `webserver/app/core/dsa.py`.
"""


from datetime import datetime, timedelta
import os
import sys
import pytest
from intervaltree import Interval

# Add both `webserver` and `.` to sys.path so app is always found
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEBSERVER_DIR = os.path.join(ROOT_DIR, "webserver")

for p in (WEBSERVER_DIR, ROOT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Handle both Events.py (capitalized) and events.py (lowercase)
try:
    from app.core.events import (
        FixedEvent,
        FlexibleEvent,
        Lecture,
        Meeting,
        Task,
        PriorityMatrix,
    )
except ImportError:
    from app.core.Events import (
        FixedEvent,
        FlexibleEvent,
        Lecture,
        Meeting,
        Task,
        PriorityMatrix,
    )

from app.core.dsa import FixedTree, WindowTree


@pytest.fixture
def reference_date() -> datetime:
    """Returns a deterministic reference day (Monday, 2026-10-26 at midnight 00:00:00)."""
    return datetime(2026, 10, 26, 0, 0, 0)


@pytest.fixture
def full_day_window(reference_date: datetime) -> Interval:
    """Returns a standard 24-hour interval window [00:00, 24:00)."""
    return Interval(reference_date, reference_date + timedelta(days=1))


@pytest.fixture
def active_hours_window(reference_date: datetime) -> Interval:
    """Returns an active daytime working window: [08:00, 20:00) (12 hours)."""
    start = reference_date + timedelta(hours=8)
    end = reference_date + timedelta(hours=20)
    return Interval(start, end)


@pytest.fixture
def empty_fixed_tree() -> FixedTree:
    """Returns a freshly initialized FixedTree with zero registered events."""
    return FixedTree()


@pytest.fixture
def sample_lecture(reference_date: datetime) -> Lecture:
    return Lecture(
        title="CS341 Algorithms",
        start=reference_date + timedelta(hours=14),
        end=reference_date + timedelta(hours=15, minutes=30),
        course_code="CS341",
        venue="AC01-LectureHall",
        recurring=True,
    )


@pytest.fixture
def sample_meeting(reference_date: datetime) -> Meeting:
    return Meeting(
        title="Project OOPsies Team Sync",
        start=reference_date + timedelta(hours=10),
        end=reference_date + timedelta(hours=11),
        pre_buffer=timedelta(minutes=10),
        post_buffer=timedelta(minutes=10),
        attendees=("sampurna", "rupsha"),
        recurring=False,
        venue="Library Discussion Room 2",
    )


@pytest.fixture
def standard_window_tree(active_hours_window: Interval, empty_fixed_tree: FixedTree) -> WindowTree:
    return WindowTree(active_hours_window, empty_fixed_tree)
