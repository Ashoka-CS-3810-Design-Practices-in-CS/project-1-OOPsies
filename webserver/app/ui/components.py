from datetime import datetime
from core.events import *
from core.dsa import *
from nicegui import ui


EVENT_COLORS = {
    'FixedEvent':       "#e76767",
    'FlexibleEvent':    "#66b5d5",
}

PRIORITY_COLORS = {
    PriorityMatrix.URGENT_IMPORTANT:            '#d9826b',
    PriorityMatrix.URGENT_NOT_IMPORTANT:        '#e8c07d',
    PriorityMatrix.NOT_URGENT_IMPORTANT:        '#a8c8a0',
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT:    '#9ab8d8',
}

PRIORITY_LABELS = {
    PriorityMatrix.URGENT_IMPORTANT:            'UI',
    PriorityMatrix.URGENT_NOT_IMPORTANT:        'UNI',
    PriorityMatrix.NOT_URGENT_IMPORTANT:        'NUI',
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT:    'NUNI',
}

class Event:
    def render(self):
        with ui.card().classes(f'w-80 bg-[{color}] rounded-2xl shadow-none p-4'):
            ui.label('Event').classes('text-xl font-bold')

    def hover(self):
        with ui.column().classes('w-80 gap-2'):
            
            # Buffer Before
            with ui.row().classes(f'w-full bg-[{color}] rounded-2xl py-2 justify-center'):
                ui.label(pre_buffer_min).classes('text-sm text-gray-700')

            # Main Card
            with ui.card().classes(f'w-full bg-[{color}] rounded-2xl shadow-none p-4'):
                
                # Header (Title + Edit Icon)
                with ui.row().classes('w-full justify-between items-start'):
                    ui.label('Event').classes('text-xl font-bold')
                    ui.icon('edit_rounded').classes('text-2xl cursor-pointer')
                
                # Content (Using native text bullets for minimalism)
                with ui.column().classes('gap-1 text-sm text-gray-800'):
                    ui.label(f'• xx:xx to xx:xx').classes('ml-1 mt-2')
                    ui.label(f'• Category').classes('ml-1 mt-2')
                    ui.label('○ Property X').classes('ml-6 text-gray-600')
                    ui.label('○ Property Y').classes('ml-6 text-gray-600')
                    ui.label('• Property Z').classes('ml-1 mt-1')
                
                # Footer (Delete Icon)
                with ui.row().classes('w-full justify-end mt-2'):
                    ui.icon('delete_rounded').classes('text-2xl cursor-pointer')

            # Buffer After
            with ui.row().classes(f'w-full bg-[{color}] rounded-2xl py-2 justify-center'):
                ui.label(post_buffer_min).classes('text-sm text-gray-700')

class SchedulingWindow:
    pass

class WindowSelector:
    pass

class Widget:
    pass

class PriorityChoice:
    pass

class ActionButton:
    pass

class Calendar(Widget):
    pass

class Editor(Widget):
    pass

class Feedback(Widget):
    pass

class DateSelector(WindowSelector):
    pass

class DayTimeSelector(WindowSelector):
    pass

class Add(ActionButton):
    pass

class Edit(ActionButton):
    pass

class Delete(ActionButton):
    pass

class Undo(ActionButton):
    pass