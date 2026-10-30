from app.core.dsa import *
from app.core.events import *
from app.gui.components import *
from nicegui import ui


def main():
    ui.page_title("Scheduler")
    ui.add_css('''
    @import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@500;700&display=swap');
    body { font-family: "Quicksand", sans-serif; }
    ''')

    fixed_tree = FixedTree()
    controller = SchedulerController(fixed_tree)

    with ui.row().classes('w-full justify-end'):
        with ui.column().classes('w-full max-w-[30rem] flex-1 min-w-0 gap-4'):
            SchedulingWindow(controller).render()

            with ui.row().classes('w-full items-stretch'):
                with ui.column().classes('flex-1 min-w-0'):
                    with ui.row().classes('w-full justify-between items-center gap-2'):
                        WindowSelector(controller).render()
                        DayTimeSelector.render(controller)

                    # Calendar and editor occupy the same slot.
                    calendar = Calendar(controller)
                    calendar.render()

                    event_editor = EventEditor(controller)
                    event_editor.render()

                with ui.column().classes('shrink-0'):
                    Add.render(controller)
                    priority_filter = PriorityChoice(
                        on_change=lambda p: setattr(controller, 'draft_priority', p)
                        if controller.in_editor else controller.set_priority_filter(p)
                    )
                    controller.priority_filter_widget = priority_filter
                    Undo.render(controller)

            PendingBar(controller).render()


ui.run(main)