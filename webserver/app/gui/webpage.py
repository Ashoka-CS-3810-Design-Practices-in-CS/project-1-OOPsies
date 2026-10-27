# test_scheduling_window.py
from datetime import datetime, timedelta
from app.core.dsa import *
from app.gui.components import *
from app.core.events import *
from nicegui import ui

def dump_state(fixed_tree, wt):
    print("=" * 60)
    print("FixedTree")
    print("=" * 60)
    for iv in sorted(fixed_tree.tree):
        ev = iv.data
        print(f"  [{iv.begin:%H:%M}, {iv.end:%H:%M})  {type(ev).__name__}: {ev.title}")

    print()
    print("=" * 60)
    print("WindowTree.tree")
    print("=" * 60)
    for iv in sorted(wt.tree):
        members = ", ".join(
            f"{e.title}({e.true_start:%H:%M}-{e.true_end:%H:%M}, p={e.priority})"
            for e in iv.data.values()
        ) or "—"
        print(f"  [{iv.begin:%H:%M}, {iv.end:%H:%M})  ->  {{{members}}}")

    print()
    print("event_dict (scheduled):")
    for uid, slot in wt.event_dict.items():
        ev = slot.data[uid]
        print(f"  {ev.title:<20} -> slot [{slot.begin:%H:%M}, {slot.end:%H:%M})")

    print()
    print("unscheduled:")
    for uid, ev in wt.unscheduled.items():
        print(f"  {ev.title:<20} (p={ev.priority}, len={ev.length})")

    print()
    print(f"synced_version = {wt.synced_version}, fixed entries = {len(wt.fixed)}")
    print("=" * 60)

def seed():
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    window = Interval(day, day + timedelta(days=1))

    fixed_tree = FixedTree()

    # fixed events
    meeting = Meeting(
        title="Team Sync",
        start=day + timedelta(hours=9),
        end=day + timedelta(hours=10),
        pre_buffer=timedelta(minutes=10),
        post_buffer=timedelta(minutes=10),
        attendees=("alice", "bob"),
        recurring=False,
    )
    lecture = Lecture(
        title="Algorithms",
        start=day + timedelta(hours=14),
        end=day + timedelta(hours=15, minutes=30),
        course_code="CS341",
    )
    '''appt = Appointment(
        title="Dentist",
        start=day + timedelta(hours=17),
        end=day + timedelta(hours=17),
        attendees=("me",),
    )'''
    for ev in (meeting, lecture, ):#appt):
        fixed_tree.insert(ev)

    # window tree
    wt = WindowTree(window, fixed_tree)

    # flexible events
    tasks = [
        Task(title="Write report", start=day, end=day + timedelta(hours=2),
             priority=PriorityMatrix.URGENT_IMPORTANT),
        Task(title="Read paper", start=day, end=day + timedelta(hours=1),
             priority=PriorityMatrix.NOT_URGENT_IMPORTANT),
        Task(title="Reply emails", start=day, end=day + timedelta(minutes=45),
             priority=PriorityMatrix.URGENT_NOT_IMPORTANT),
        Task(title="Gym", start=day, end=day + timedelta(hours=1, minutes=30),
             priority=PriorityMatrix.NOT_URGENT_NOT_IMPORTANT),
    ]
    for t in tasks:
        wt.insert(t, fixed_tree)

    return fixed_tree, wt


def main():
    fixed_tree, wt = seed()
    dump_state(fixed_tree, wt) 
    
    ui.page_title("Scheduling Window Test")

    with ui.row().classes('items-start gap-8 p-6'):
        # main timeline
        with ui.column().classes('gap-2'):
            ui.label('Scheduling Window').classes('text-lg font-bold')
            SchedulingWindow(wt).render()

ui.run(main)