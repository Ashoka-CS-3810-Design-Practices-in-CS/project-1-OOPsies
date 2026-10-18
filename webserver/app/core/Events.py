from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

@dataclass(kw_only=True)
class Event:
    title:str
    start:datetime 
    end:datetime
    pre_buffer:timedelta = timedelta(0)
    post_buffer:timedelta = timedelta(0)

    @property
    def interval(self) -> tuple[datetime,datetime]:
        return (self.start + self.pre_buffer, self.end+self.post_buffer)

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Event cannot end before it begins!")

@dataclass(kw_only=True)
class FixedEvent(Event):
    flexible:bool = False

class PriorityMatrix(IntEnum):
    UI = 4
    UNI = 3
    NUI = 2
    NUNI = 1

@dataclass(kw_only=True)
class FlexibleEvent(Event):
    priority:PriorityMatrix
    flexible:bool = True
    
@dataclass(kw_only=True)
class Meeting(FixedEvent):
    attendees:tuple[str, ...]
    recurring:bool
    venue:str|None

@dataclass(kw_only=True)
class Lecture(FixedEvent):
    course_code:str
    recurring:bool = True
    venue:str|None = None

@dataclass(kw_only=True)
class Routine(FixedEvent):
    recurring:bool = True

@dataclass(kw_only=True)
class PointEvent(FixedEvent):

    pre_buffer:  timedelta = field(default=timedelta(0), init=False)
    post_buffer: timedelta = field(default=timedelta(0), init=False)
    
    @property
    def datepoint(self):
        if self.start == self.end:
            return self.start
        else:
            raise ValueError("Start and end of point events cannot differ.")
    
@dataclass(kw_only=True)
class Appointment(PointEvent):
    attendees:tuple[str, ...]

@dataclass(kw_only=True)
class Occasion(PointEvent):
    recurring:bool

@dataclass(kw_only=True)
class Deadline(PointEvent):
    course_code:str

@dataclass(kw_only=True)
class Task(FlexibleEvent):
    missed:bool = False
    micro_tasks:tuple[str, ...]|None = None