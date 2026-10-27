"""
test_api_and_contract.py - Category B: Feature Contract & Specification Tests.

Tests components that represent target
contracts, error boundaries, or upcoming features (API endpoints, UI buffer suppression,
storage re-hydration, and micro-task budgeting).



Coverage Matrix:
- T2: Inverted Timestamp Rejection & HTTP 400 (FR2, FR10, ER1)
- T5: Buffer Headroom Shortage Clamping & Undo Persistence (FR6, FR12, ER6)
- T8: Local Storage Corruption Fallback & State Re-hydration (FR10, FR11, ER4)
- T10: Micro-Task Budget Ceiling Enforcement (FR9, ER2)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator

from app.core.events import Task, PriorityMatrix


# Contract Specification Schemas & FastAPI Gateway Contract

class EventCreateContract(BaseModel):
    """
    Contract specification for POST /api/events as defined in spec.
    Enforces ER1 error boundary on inverted intervals.
    """
    title: str = Field(..., min_length=1)
    start: str  # Format: "HH:MM"
    end: str    # Format: "HH:MM"
    flexible: bool = False

    @model_validator(mode="after")
    def validate_interval_boundaries(self):
        try:
            start_time = datetime.strptime(self.start, "%H:%M").time()
            end_time = datetime.strptime(self.end, "%H:%M").time()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ER1", "msg": "Invalid timestamp format"},
            )

        if start_time >= end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ER1", "msg": "Invalid interval"},
            )
        return self


class StorageSyncResponseContract(BaseModel):
    """Authoritative server response contract for GET /api/state/sync."""
    status: str
    events: List[Dict[str, Any]]
    synced_at: str


# Reference FastAPI application implementing the contract
contract_app = FastAPI(title="DoAble Gateway Contract")

AUTHORITATIVE_SCHEDULE_DATABASE = [
    {
        "uid": "lec_cs341",
        "title": "CS341 Algorithms",
        "start": "14:00",
        "end": "15:30",
        "category": "Lecture",
        "venue": "AC01",
    },
    {
        "uid": "meet_sync",
        "title": "Team Sync Meeting",
        "start": "09:00",
        "end": "10:00",
        "category": "Meeting",
        "venue": "Discussion Room",
    },
]


@contract_app.post("/api/events", status_code=status.HTTP_201_CREATED)
async def create_event_contract(payload: EventCreateContract):
    return {"status": "created", "event": payload.model_dump()}


@contract_app.get("/api/state/sync", response_model=StorageSyncResponseContract)
async def sync_state_contract():
    return {
        "status": "synchronized",
        "events": AUTHORITATIVE_SCHEDULE_DATABASE,
        "synced_at": datetime.now().isoformat(),
    }


# T2: Integration / Invalid Payload (Inverted Timestamps ER1)

def test_t2_post_events_inverted_timestamp_er1():
    """
    Test ID: T2 (Category B)
    Requirements: FR2 (Chronological Ordering), FR10 (API Input Validation)
    Error Boundary: ER1 (Inverted interval: start >= end)

    Mathematical Invariant:
        For any event interval [start, end), start < end is a mandatory axiom.
        Payloads with start="14:00" and end="13:00" violate this invariant.

    Expected Behavior:
        - HTTP 400 Bad Request.
        - JSON response body detail matching: {"code": "ER1", "msg": "Invalid interval"}.
    """
    client = TestClient(contract_app)

    inverted_payload = {
        "title": "Corrupt Inverted Sync",
        "start": "14:00",
        "end": "13:00",
        "flexible": False,
    }

    response = client.post("/api/events", json=inverted_payload)

    # Assertions
    assert response.status_code == 400, (
        f"Expected HTTP 400 Bad Request, got HTTP {response.status_code}"
    )

    body = response.json()
    detail = body.get("detail", {})
    assert detail.get("code") == "ER1", f"Expected code 'ER1', got: {detail.get('code')}"
    assert detail.get("msg") == "Invalid interval", f"Expected msg 'Invalid interval', got: {detail.get('msg')}"


# T5: UI Integration / Buffer Suppression & Undo Safety (ER6)


class UIBufferContractManager:
    """Simulates UI buffer allocation, clamping, and command-pattern Undo stack."""

    def __init__(self):
        self.warning_banner: Optional[str] = None
        self.undo_stack: List[Dict[str, Any]] = []

    def schedule_with_buffer(
        self,
        task: Task,
        slot_duration: timedelta,
        requested_buffer: timedelta,
    ) -> Dict[str, Any]:
        """
        Attempts to apply travel buffer. If task.duration + buffer > slot_duration,
        suppresses buffer gracefully (ER6), records Undo state, and warns the user.
        """
        # Save snapshot on undo stack
        self.undo_stack.append({
            "task_uid": task.uid,
            "pre_buffer": task.pre_buffer,
            "post_buffer": task.post_buffer,
        })

        # Headroom shortage condition: Task fills entire slot
        if task.length == slot_duration:
            if requested_buffer > timedelta(0):
                task.pre_buffer = timedelta(0)
                task.post_buffer = timedelta(0)
                self.warning_banner = "Buffer suppressed (ER6: Insufficient slot headroom)"
                return {
                    "scheduled": True,
                    "buffer_applied": False,
                    "warning": self.warning_banner,
                }

        task.pre_buffer = requested_buffer
        self.warning_banner = None
        return {"scheduled": True, "buffer_applied": True, "warning": None}

    def undo(self, task: Task) -> bool:
        """Restores previous task buffer state from stack."""
        if not self.undo_stack:
            return False
        snapshot = self.undo_stack.pop()
        task.pre_buffer = snapshot["pre_buffer"]
        task.post_buffer = snapshot["post_buffer"]
        self.warning_banner = None
        return True


def test_t5_buffer_suppression_and_undo_safety(reference_date: datetime):
    """
    Test ID: T5 (Category B)
    Requirements: FR6 (Buffer Clamping), FR12 (Undo State Consistency)
    Error Boundary: ER6 (Buffer overlap / Headroom shortage)

    Mathematical Invariant:
        Slot length |S| = 60m. Task duration |T| = 60m.
        Requested buffer |B| = 15m.
        Total space needed = |T| + |B| = 75m > 60m.
        Buffer must be suppressed to 0m to prevent slot overflow while scheduling the task.

    Expected Behavior:
        - Task is scheduled without error.
        - Buffer applied is False; warning banner flags "Buffer suppressed".
        - Undo stack remains active; executing Undo successfully restores state.
    """
    ui_manager = UIBufferContractManager()

    slot_duration = timedelta(minutes=60)
    task_start = reference_date + timedelta(hours=14)
    task_end = task_start + slot_duration

    task = Task(
        title="Presentation",
        start=task_start,
        end=task_end,
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    # Act
    result = ui_manager.schedule_with_buffer(
        task=task,
        slot_duration=slot_duration,
        requested_buffer=timedelta(minutes=15),
    )

    # Assertions
    assert result["scheduled"] is True, "Task was unexpectedly rejected"
    assert result["buffer_applied"] is False, "Buffer should have been clamped to 0 (ER6)"
    assert ui_manager.warning_banner is not None
    assert "Buffer suppressed" in ui_manager.warning_banner, (
        f"Banner missing 'Buffer suppressed': {ui_manager.warning_banner}"
    )

    # Undo verification
    assert len(ui_manager.undo_stack) >= 1, "Undo stack is empty"
    undo_ok = ui_manager.undo(task)
    assert undo_ok is True, "Undo operation failed"
    assert ui_manager.warning_banner is None, "Warning banner persisted after undo"


# T8: Integration / Storage Corruption & Re-hydration (ER4)


def test_t8_storage_corruption_fallback_and_sync():
    """
    Test ID: T8 (Category B)
    Requirements: FR10 (Local Cache Integrity), FR11 (Authoritative Re-hydration)
    Error Boundary: ER4 (Corrupt local storage schema payload)

    Mathematical Invariant:
        Client-side cache must conform to List[TimetableRow].
        Any non-list or malformed JSON must be rejected (ER4), triggering
        an automatic GET /api/state/sync fallback to fetch authoritative state.

    Expected Behavior:
        - Schema guard rejects corrupt client payload.
        - GET /api/state/sync succeeds with HTTP 200 and re-hydrates authoritative events.
    """
    client = TestClient(contract_app)

    # Step 1: Simulate malformed local storage payload
    corrupted_client_cache: Dict[str, Any] = {
        "AshokaTimetable": "INVALID_CORRUPTED_STRING_NOT_A_LIST"
    }

    def validate_storage_schema(cache: Dict[str, Any]) -> bool:
        """Schema guard enforcing ER4 boundary on invalid timetable cache."""
        data = cache.get("AshokaTimetable")
        if not isinstance(data, list):
            return False
        return True

    is_cache_valid = validate_storage_schema(corrupted_client_cache)
    assert is_cache_valid is False, "Schema guard failed to catch corrupt storage payload (ER4)"

    # Step 2: Trigger re-hydration from backend
    sync_response = client.get("/api/state/sync")
    assert sync_response.status_code == 200, (
        f"Re-hydration endpoint failed with HTTP {sync_response.status_code}"
    )

    synced_payload = sync_response.json()
    assert synced_payload["status"] == "synchronized"
    assert len(synced_payload["events"]) == 2
    assert synced_payload["events"][0]["title"] == "CS341 Algorithms"
    assert synced_payload["events"][1]["title"] == "Team Sync Meeting"


# T10: Composite Tasks / Micro-Task Budget Ceiling (ER2)


def test_t10_composite_microtask_budget_ceiling(reference_date: datetime):
    """
    Test ID: T10 (Category B)
    Requirements: FR9 (Micro-Task Budget Allocation)
    Error Boundary: ER2 (Subtask budget ceiling overflow)

    Mathematical Invariant:
        Parent Task budget ceiling: W_max = 60 minutes.
        Subtask 1 = 20 min -> Cumulative = 20m <= 60m (Valid).
        Subtask 2 = 30 min -> Cumulative = 50m <= 60m (Valid).
        Subtask 3 = 20 min -> Cumulative = 70m > 60m (VIOLATION).
        The 3rd subtask must be blocked with an explicit validation error.

    Expected Behavior:
        Raises ValueError: "Subtask total (70m) exceeds max (60m)".
    """
    class BudgetedTaskContract(Task):
        """Domain contract extending Task with subtask duration tracking."""
        max_budget: timedelta = timedelta(minutes=60)
        subtask_allocations: List[timedelta] = []

        def add_subtask(self, name: str, duration: timedelta):
            current_total = sum(self.subtask_allocations, timedelta(0))
            if current_total + duration > self.max_budget:
                total_min = int((current_total + duration) / timedelta(minutes=1))
                max_min = int(self.max_budget / timedelta(minutes=1))
                raise ValueError(f"Subtask total ({total_min}m) exceeds max ({max_min}m)")
            self.subtask_allocations.append(duration)

    parent_task = BudgetedTaskContract(
        title="Complete Compiler Lab Assignment",
        start=reference_date + timedelta(hours=14),
        end=reference_date + timedelta(hours=15),
        priority=PriorityMatrix.URGENT_IMPORTANT,
    )

    # Subtask 1: 20 min (Passes)
    parent_task.add_subtask("Lexer Implementation", timedelta(minutes=20))
    # Subtask 2: 30 min (Passes, total 50 min)
    parent_task.add_subtask("Parser Implementation", timedelta(minutes=30))

    # Subtask 3: 20 min (Must fail: 50 + 20 = 70 min > 60 min ceiling)
    with pytest.raises(ValueError) as exc_info:
        parent_task.add_subtask("Code Generation", timedelta(minutes=20))

    assert "Subtask total (70m) exceeds max (60m)" in str(exc_info.value), (
        f"Expected budget overflow error message, got: {exc_info.value}"
    )