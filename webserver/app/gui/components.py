from datetime import datetime, timedelta
from dataclasses import fields, MISSING
from app.core.events import *
from app.core.dsa import *
from nicegui import ui

PX_PERhour = 60

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
        with ui.card().classes('w-full rounded-lg shadow-none p-4').style(f'background-color: {color}'):
            ui.label(self.event.title).classes('text-base font-bold text-white')

    def hover_render(self):
        color = self.get_color()
        
        with ui.column().classes('w-full gap-2 font-sans'):
            # pre_buffer (only if > 0)
            pre_min = int(self.event.pre_buffer / timedelta(minutes=1))
            if pre_min > 0:
                with ui.row().classes('w-full rounded-lg py-1 justify-center items-center').style(f'background-color: {color}'):
                    ui.label(f'{pre_min} min').classes('text-xs text-white')

            # Main event card (Colored Box)
            with ui.element('div').classes('w-full rounded-lg shadow-none flex flex-col').style(f'background-color: {color}; padding: 16px;'):
                
                # Title
                ui.label(self.event.title).classes('text-base font-bold text-white break-words leading-tight w-full')
                
                # Details
                with ui.column().classes('gap-1 text-xs text-white w-full mt-2'):
                    start_str = self.event.start.strftime('%I:%M %p')
                    end_str = self.event.end.strftime('%I:%M %p')
                    
                    current_cat = self.event.__class__.__name__
                    if current_cat in {"Event", "FixedEvent", "FlexibleEvent", "PointEvent"}:
                        raise ValueError("Cannot choose a non-public category!")
                    
                    properties = self.show_properties(current_cat)

                    ui.label(f'{start_str} to {end_str}').classes('ml-1 mt-1')
                    ui.label(f'{current_cat}').classes('w-full mt-2 text-white font-bold')
                    for name, data in properties.items():
                        ui.label(f'{data["label"]}: {data["value"]}').classes('w-full')

            # post-buffer (only if > 0)
            post_min = int(self.event.post_buffer / timedelta(minutes=1))
            if post_min > 0:
                with ui.row().classes('w-full rounded-lg py-1 justify-center items-center').style(f'background-color: {color}'):
                    ui.label(f'{post_min} min').classes('text-xs text-white')
    
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

    def display(self, top: int = None, height: int = None):
        """Render the event as an absolutely-positioned block inside a SchedulingWindow."""
        color = self.get_color()

        wrapper = ui.element('div').classes(
            'absolute left-2 right-32 rounded-lg z-10 transition-all duration-300 ease-in-out shadow-sm grid'
        ).style(f'top:{top}px; min-height:{height}px; max-height:{height}px; background:{color}; border: 1px solid transparent; overflow: hidden;')
        
        with wrapper:
            # COMPACT VIEW (Fades out on hover)
            compact = ui.element('div').classes(
                'col-start-1 row-start-1 w-full px-2 py-1 transition-opacity duration-300 ease-in-out opacity-100 z-10'
            )
            with compact:
                ui.label(self.event.title).classes('text-xs font-bold truncate leading-tight text-white')
                ui.label(f'{self.event.start:%I:%M %p} – {self.event.end:%I:%M %p}').classes('text-[10px] text-white opacity-80')

            # EXPANDED VIEW (Fades in on hover)
            hover_container = ui.element('div').classes(
                'col-start-1 row-start-1 w-full p-2 transition-opacity duration-300 ease-in-out opacity-0 pointer-events-none z-20'
            )
            with hover_container:
                self.hover_render()

        def show_hover():
            # 1. Expand max-height, change bg to white, add border/shadow
            # 2. Remove z-10, add z-50 to ensure it paints OVER the next event
            wrapper.classes(remove='z-10')
            wrapper.classes(add='z-50 shadow-2xl')
            wrapper.style(f'top:{top}px; min-height:{height}px; max-height: 800px; background: #ffffff; border: 1px solid #d1d5db; overflow: visible;')
            
            # Cross-fade contents
            compact.classes(remove='opacity-100').classes(add='opacity-0')
            hover_container.classes(remove='opacity-0 pointer-events-none').classes(add='opacity-100 pointer-events-auto')

        def show_compact():
            # 1. Restore max-height, original color, remove border/shadow
            # 2. Remove z-50, restore z-10
            wrapper.classes(remove='z-50 shadow-2xl')
            wrapper.classes(add='z-10')
            wrapper.style(f'top:{top}px; min-height:{height}px; max-height:{height}px; background: {color}; border: 1px solid transparent; overflow: hidden;')
            
            # Cross-fade back
            compact.classes(remove='opacity-0').classes(add='opacity-100')
            hover_container.classes(remove='opacity-100 pointer-events-auto').classes(add='opacity-0 pointer-events-none')

        wrapper.on('mouseenter', show_hover)
        wrapper.on('mouseleave', show_compact)


class SchedulingWindow:
    def __init__(self, window_tree: WindowTree):
        self.window_tree = window_tree

    def render(self):
        w = self.window_tree
        height = int((w.window.end - w.window.begin) / timedelta(minutes=1))

        # Outer bounding box with medium black outline and round corners
        with ui.element('div').classes('w-96 h-[620px] border-2 border-gray-800 rounded-2xl overflow-hidden p-2 bg-white shadow-xl'):
            with ui.scroll_area().classes('w-full h-full'):
                with ui.element('div').classes('relative w-full pr-1').style(f'height:{height}px'):
                    self.hour_markers()
                    for ev in w.fixed.values():
                        self.event_box(ev)
                    for uid, slot in w.event_dict.items():
                        self.event_box(slot.data[uid])
                    now_container = ui.element('div').classes('absolute inset-0 pointer-events-none z-20')

        self.render_now(now_container)
        ui.timer(60, lambda: self.render_now(now_container))

    def y(self, t: datetime) -> int:
        return int((t - self.window_tree.window.begin) / timedelta(minutes=1))

    def hour_markers(self):
        w = self.window_tree.window
        cur = w.begin.replace(minute=0, second=0, microsecond=0)
        if cur < w.begin:
            cur += timedelta(hours=1)

        while cur < w.end:
            self.render_marker(cur)
            cur += timedelta(hours=1)

        # Draw the next day's midnight (12:00 AM) at the very end
        next_midnight = w.begin.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if next_midnight <= w.end + timedelta(minutes=1):
            self.render_marker(next_midnight)

    def render_marker(self, t: datetime):
        with ui.element('div').classes('absolute left-2 right-2 flex items-center gap-2 z-0').style(
            f'top:{self.y(t)}px; transform:translateY(-50%)'
        ):
            ui.element('div').classes('flex-1 border-t-2 border-dashed border-gray-300')
            
            with ui.column().classes('gap-0 text-right w-20 shrink-0'):
                ui.label(t.strftime('%Y/%m/%d')).classes('text-[10px] text-gray-400 tabular-nums leading-tight')
                ui.label(t.strftime('%I:%M %p')).classes('text-xs text-gray-500 tabular-nums leading-tight font-semibold')

    def event_box(self, ev: Event):
        top = self.y(ev.true_start)
        height = max(self.y(ev.true_end) - top, 16)
        height = max(height - 2, 12)
        EventUI(ev).display(top=top, height=height)

    def render_now(self, container):
        container.clear()
        w = self.window_tree.window
        now = datetime.now()
        if not (w.begin <= now <= w.end):
            return
        with container:
            with ui.element('div').classes('absolute left-0 right-32 flex items-center z-20').style(
                f'top:{self.y(now)}px; transform:translateY(-50%)'
            ):
                ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-pink-400')
                ui.element('div').classes('flex-1 h-0.5 bg-pink-400')

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