from dataclasses import dataclass, field
from datetime import datetime, timedelta
from intervaltree import Interval
from typing import Literal
from enum import IntEnum
from uuid import uuid4

@dataclass(kw_only=True)
class Event:
    title:str
    start:datetime 
    end:datetime
    pre_buffer:timedelta = timedelta(0)
    post_buffer:timedelta = timedelta(0)
    flexible:bool

    uid: str = field(default_factory=lambda: uuid4().hex, init=False)
    series_uid: str | None = None

    @property
    def true_start(self) -> datetime:
        return self.start - self.pre_buffer

    @property
    def true_end(self) -> datetime:
        return self.end + self.post_buffer

    @property
    def length(self) -> timedelta:
        return self.true_end - self.true_start

    def __post_init__(self):
        if self.series_uid is None:
            self.series_uid = self.uid
        if self.start > self.end:
            raise ValueError("Event cannot end before it begins!")

@dataclass(kw_only=True)
class FixedEvent(Event):
    flexible:bool = field(default=False, init=False)

class PriorityMatrix(IntEnum):
    URGENT_IMPORTANT = 4
    URGENT_NOT_IMPORTANT = 3
    NOT_URGENT_IMPORTANT = 2
    NOT_URGENT_NOT_IMPORTANT = 1

@dataclass(kw_only=True)
class FlexibleEvent(Event):
    priority:PriorityMatrix
    flexible: bool = field(default=True, init=False)
    seen: set[Interval] = field(default_factory=set, init=False)

    def __post_init__(self):
        super().__post_init__()
        if self.length <= timedelta(0):
            raise ValueError("Flexible event cannot have non-positive length!")
    
@dataclass(kw_only=True)
class Meeting(FixedEvent):
    attendees:tuple[str, ...]
    recurring:Literal['Never', 'Daily', 'Weekly', 'Monthly', 'Yearly'] = 'Weekly'
    venue:str|None = None

@dataclass(kw_only=True)
class Lecture(FixedEvent):
    course_code:str
    recurring:Literal['Never','Daily', 'Weekly', 'Monthly', 'Yearly'] = 'Weekly'
    venue:str|None = None

@dataclass(kw_only=True)
class PointEvent(FixedEvent):

    pre_buffer:  timedelta = field(default=timedelta(0), init=False)
    post_buffer: timedelta = field(default=timedelta(0), init=False)

    @property
    def true_start(self) -> datetime:
        return self.start

    @property
    def true_end(self) -> datetime:
        return self.end + timedelta(microseconds=1)

    @property
    def length(self) -> timedelta:
        return self.true_end - self.true_start
    
    def __post_init__(self):
        super().__post_init__()
        if self.start != self.end:
            raise ValueError("Point event is defined by start date!")
    
@dataclass(kw_only=True)
class Appointment(PointEvent):
    attendees:tuple[str, ...]

@dataclass(kw_only=True)
class Occasion(PointEvent):
    recurring:Literal['Never', 'Daily', 'Weekly', 'Monthly', 'Yearly'] = 'Yearly'

@dataclass(kw_only=True)
class Deadline(PointEvent):
    course_code:str

@dataclass(kw_only=True)
class Task(FlexibleEvent):
    missed:bool = False
    micro_tasks:tuple[str, ...]|None = None

@dataclass(kw_only=True)
class Routine(FlexibleEvent):
    recurring:Literal['Never','Daily', 'Weekly', 'Monthly', 'Yearly'] = 'Daily'
