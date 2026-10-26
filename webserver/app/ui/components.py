from datetime import datetime, timedelta
from dataclasses import fields, MISSING
from core.events import *
from nicegui import ui

CATEGORIES = {
    'Meeting': Meeting,
    'Lecture': Lecture,
    'Routine': Routine,
    'Appointment': Appointment,
    'Occasion': Occasion,
    'Deadline': Deadline,
    'Task': Task
}

EVENT_COLORS = {
    'fixed':       "#e76767",
    'flexible':    "#66b5d5",
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


class EventUI:
    def __init__(self, event: Event):
        self.event = event

    def get_color(self) -> str:
        return EVENT_COLORS['flexible'] if self.event.flexible else EVENT_COLORS['fixed']

    def base_render(self):
        color = self.get_color()
        with ui.card().classes('w-full rounded-2xl shadow-none p-4').style(f'background-color: {color}'):
            ui.label(self.event.title).classes('text-xl font-bold text-white')

    def hover_render(self):
        color = self.get_color()
        
        with ui.column().classes('w-full gap-2 font-sans'):

            # pre_buffer
            pre_min = int(self.event.pre_buffer / timedelta(minutes=1))
            with ui.row().classes('w-full rounded-2xl py-2 justify-center items-center').style(f'background-color: {color}90'):
                ui.label(f'{pre_min} min').classes('text-sm text-white')

            # event card
            with ui.card().classes('w-full rounded-2xl shadow-none p-4').style(f'background-color: {color}'):
                
                with ui.row().classes('w-full justify-between items-start'):
                    ui.label(self.event.title).classes('text-xl font-bold text-white')
                    ui.icon('edit_rounded').classes('text-2xl text-white cursor-pointer hover:text-gray-200').on('click', self.on_edit)
                
                with ui.column().classes('gap-1 text-sm text-white w-full'):
                    start_str = self.event.start.strftime('%H:%M')
                    end_str = self.event.end.strftime('%H:%M')
                    
                    current_cat = self.event.__class__.__name__
                    if current_cat in {"Event", "FixedEvent", "FlexibleEvent", "PointEvent"}:
                        raise ValueError("Cannot choose a non-public category!")
                    
                    properties = self.show_properties(current_cat)

                    ui.label(f'{start_str} to {end_str}').classes('ml-1 mt-2 mb-1')
                    ui.label(f'{current_cat}').classes('w-full mt-2 text-white font-bold')
                    for name, data in properties.items():
                        ui.label(f'{data["label"]}: {data["value"]}').classes('w-full')

                with ui.row().classes('w-full justify-end mt-2'):
                    ui.icon('delete_rounded').classes('text-2xl text-white cursor-pointer hover:text-red-200').on('click', self.on_delete)

            # post-buffer
            post_min = int(self.event.post_buffer / timedelta(minutes=1))
            with ui.row().classes('w-full rounded-2xl py-2 justify-center items-center').style(f'background-color: {color}90'):
                ui.label(f'{post_min} min').classes('text-sm text-white')

    
    def show_properties(self, category_name: str) -> dict:
        cls = CATEGORIES.get(category_name)
        if not cls:
            return {}
            
        unused_fields = {'title', 'start', 'end', 'uid', 'series_uid', 'pre_buffer', 'post_buffer'}
        valid_fields = [f for f in fields(cls) if f.name not in unused_fields]
        
        properties = {}
        for f in valid_fields:
            is_fixed = not f.init 
            label_text = f.name.replace('_', ' ').title()
            
            if isinstance(self.event, cls) and hasattr(self.event, f.name):
                val = getattr(self.event, f.name)
            elif f.default is not MISSING:
                val = f.default
            elif f.default_factory is not MISSING:
                val = f.default_factory()
            else:
                val = None
                
            properties[f.name] = {
                'value': val,
                'is_fixed': is_fixed,
                'label': label_text,
                'type': f.type
            }
            
        return properties

    def on_edit(self):
        ui.notify(f'Editing {self.event.title}')

    def on_delete(self):
        ui.notify(f'Deleting {self.event.title}')

    def display(self):
        with ui.element('div').classes('w-80') as wrapper:
            container = ui.element('div').classes('w-full')
            
            def show_base():
                container.clear()
                with container:
                    self.base_render()

            def show_hover():
                container.clear()
                with container:
                    self.hover_render()

            show_base()

            wrapper.on('mouseenter', show_hover)
            wrapper.on('mouseleave', show_base)


class SchedulingWindow: pass

class WindowSelector: pass

class Widget: pass

class PriorityChoice: pass

class ActionButton: pass

class Calendar(Widget): pass

class Editor(Widget): pass

class Feedback(Widget): pass

class DateSelector(WindowSelector): pass

class DayTimeSelector(WindowSelector): pass

class Add(ActionButton): pass

class Edit(ActionButton): pass

class Delete(ActionButton): pass

class Undo(ActionButton): pass