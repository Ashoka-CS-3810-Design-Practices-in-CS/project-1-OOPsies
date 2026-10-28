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

    fixed_tree = FixedTree()

    meeting = Meeting(
        title="Team Sync",
        start=day + timedelta(hours=9),
        end=day + timedelta(hours=10),
        pre_buffer=timedelta(minutes=10),
        post_buffer=timedelta(minutes=10),
        attendees=("Alice", "Bob"),
        venue="AC04",
        recurring=False,
    )
    lecture = Lecture(
        title="Algorithms",
        start=day + timedelta(hours=14),
        end=day + timedelta(hours=15, minutes=30),
        course_code="CS-341",
    )
    appt = Appointment(
        title="Dental Checkup",
        start=day + timedelta(hours=18),
        end=day + timedelta(hours=18),
        attendees=('Dr. Sahiba',),
    )
    for ev in (meeting, lecture, appt):
        fixed_tree.insert(ev)

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

    return fixed_tree, tasks


def main():
    fixed_tree, tasks = seed()

    controller = SchedulerController(fixed_tree)

    controller.flexibles.extend(tasks)
    controller._rebuild_wt()

    dump_state(fixed_tree, controller.wt)

    ui.page_title("UI Test")

    with ui.row().classes('w-full justify-end'):
        with ui.column().classes('w-full max-w-[30rem] flex-1 min-w-0 gap-4'):

            SchedulingWindow(controller).render()

            with ui.row().classes('w-full items-stretch'):
                with ui.column().classes('flex-1 min-w-0'):
                    with ui.row().classes('w-full justify-between items-center gap-2'):
                        WindowSelector(controller).render()
                        DayTimeSelector.render()

                    # the Calendar lives *inside* this widget; the pill
                    # swaps it out for the step-by-step flow in place
                    WindowFlowWidget(controller).render()

                with ui.column().classes('shrink-0'):
                    Add.render()
                    PriorityChoice.render()
                    Undo.render()


ui.run(main)