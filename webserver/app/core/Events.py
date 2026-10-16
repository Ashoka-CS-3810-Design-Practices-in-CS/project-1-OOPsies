class Event:
    pass

class FixedEvent(Event):
    pass

class FlexibleEvent(Event):
    pass

class Meeting(FixedEvent):
    pass

class Lecture(FixedEvent):
    pass

class Routine(FixedEvent):
    pass

class PointEvent(FixedEvent):
    pass

class Appointment(PointEvent):
    pass

class Deadline(PointEvent):
    pass

class Occasion(PointEvent):
    pass

class Task(FlexibleEvent):
    pass

class Session(FlexibleEvent):
    pass