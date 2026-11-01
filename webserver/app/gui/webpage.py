from app.core.dsa import *
from app.core.events import *
from app.gui.components import *
from nicegui import ui

def main():
    ui.page_title("Scheduler")
    ui.add_css('''
    @import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@500;700&display=swap');

    html, body {
        font-family: "Quicksand", sans-serif;
        margin: 0;
        padding: 0;
        width: 100vw;
        height: 100vh;
        overflow: hidden; /* Prevent scrolling */
    }

    /* Force NiceGUI's default wrapper to not add padding/margins */
    .nicegui-content {
        padding: 0 !important;
        margin: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
    }

    .scale-wrapper {
        position: absolute;
        top: 50%;
        right: 0.5rem; /* <--- CHANGED THIS (was 2rem) */
        transform: translateY(-50%) scale(0.75); /* Vertically center and scale */
        transform-origin: right center; /* Anchor scaling to the right edge */
        width: 133.3333%;
        max-width: 30rem;
    }
    ''')

    fixed_tree = FixedTree()
    controller = SchedulerController(fixed_tree)

    # Use a relative container to establish the positioning context
    with ui.element('div').classes('relative w-full h-screen'):
        
        with ui.column().classes('gap-5 scale-wrapper'):
            SchedulingWindow(controller).render()

            PendingBar(controller).render()

            with ui.row().classes('w-full items-stretch'):
                with ui.column().classes('flex-1 min-w-0'):
                    with ui.row().classes('w-full justify-between items-center gap-2'):
                        WindowSelector(controller).render()
                        DayTimeSelector.render(controller)

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

ui.run(main)