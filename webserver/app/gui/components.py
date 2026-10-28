from datetime import datetime, timedelta, date as date_cls, time as time_cls
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

START_TIME_ONLY_CATEGORIES = {'Appointment', 'Occasion', 'Deadline'}

EVENT_COLORS = {
    'fixed':       "#502ba5",
    'flexible':    "#56ab53",
}

PRIORITY_COLORS = {
    PriorityMatrix.URGENT_IMPORTANT:            "#ee1c4a",
    PriorityMatrix.URGENT_NOT_IMPORTANT:        "#ffb806",
    PriorityMatrix.NOT_URGENT_IMPORTANT:        "#00a8f6",
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT:    "#2643BA",
}

PRIORITY_LABELS = {
    PriorityMatrix.URGENT_IMPORTANT:            'Urgent & Important',
    PriorityMatrix.URGENT_NOT_IMPORTANT:        'Urgent',
    PriorityMatrix.NOT_URGENT_IMPORTANT:        'Important',
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT:    'Minor',
}

CATEGORY_ICONS = {
    'Meeting':      'groups',
    'Lecture':      'school',
    'Routine':      'schedule',
    'Appointment':  'meeting_room',
    'Occasion':     'celebration',
    'Deadline':     'hourglass_bottom',
    'Task':         'assignment',
}

FIELD_ICONS = {
    'attendees':    'person',
    'recurring':    'repeat',
    'micro_tasks':  'task_alt',
    'venue':        'place',
    'course_code':  'class'
}


# =====================================================================
# SHARED STATE
# =====================================================================

class SchedulerController:
    def __init__(self, fixed_tree: FixedTree):
        self.fixed_tree = fixed_tree
        self.flexibles: list[FlexibleEvent] = []

        now = datetime.now()
        self.window_start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.window_end:   datetime = self.window_start + timedelta(days=1)
        self.selected_date: date_cls = self.window_start.date()

        self.wt: WindowTree | None = None
        self.sched_view: "SchedulingWindow | None" = None
        self.window_selector: "WindowSelector | None" = None
        self.window_flow: "WindowFlowWidget | None" = None
        self.calendar: "Calendar | None" = None

        self._rebuild_wt()

    def _rebuild_wt(self):
        window = Interval(self.window_start, self.window_end)
        self.wt = WindowTree(window, self.fixed_tree)
        for ev in self.flexibles:
            try:
                self.wt.insert(ev, self.fixed_tree)
            except ValueError:
                self.wt.unscheduled[ev.uid] = ev

    def set_window(self, start: datetime, end: datetime):
        if end <= start:
            raise ValueError("Window end must be after window start.")
        self.window_start = start
        self.window_end = end
        self.selected_date = start.date()
        self._rebuild_wt()

        if self.sched_view is not None:
            self.sched_view.rerender()
        if self.window_selector is not None:
            self.window_selector.refresh_labels()
        if self.calendar is not None:
            self.calendar.refresh()

    def set_date(self, d: date_cls):
        self.selected_date = d
        start = datetime.combine(d, time_cls(0, 0))
        end   = start + timedelta(days=1)
        self.set_window(start, end)

    def add_flexible(self, ev: FlexibleEvent):
        self.flexibles.append(ev)
        self.wt.insert(ev, self.fixed_tree)
        if self.sched_view is not None:
            self.sched_view.rerender()

    def remove_flexible(self, ev: FlexibleEvent):
        if ev in self.flexibles:
            self.flexibles.remove(ev)
        self.wt.delete(ev)
        if self.sched_view is not None:
            self.sched_view.rerender()


# =====================================================================
# EVENT RENDERING
# =====================================================================

class EventUI:
    def __init__(self, event: Event):
        self.event = event

    def get_color(self) -> str:
        return EVENT_COLORS['flexible'] if self.event.flexible else EVENT_COLORS['fixed']

    def base_render(self):
        color = self.get_color()
        with ui.card().classes('w-full rounded-lg shadow-none p-4').style(f'background-color: {color}'):
            ui.label(self.event.title).classes('text-base font-bold text-white')

    @staticmethod
    def _format_value(v):
        if isinstance(v, PriorityMatrix):
            return PRIORITY_LABELS.get(v, v.name)
        if isinstance(v, bool):
            return 'Yes' if v else 'No'
        if isinstance(v, timedelta):
            total_minutes = int(v / timedelta(minutes=1))
            if total_minutes < 60:
                return f'{total_minutes}m'
            hours, mins = divmod(total_minutes, 60)
            return f'{hours}h{mins}m' if mins else f'{hours}h'
        return str(v)

    def _make_chip(self, text: str, icon: str | None = None, bg_color: str | None = None):
        chip = ui.chip(text, icon=icon, color=None)
        chip.props('dense')
        spacing = 'padding: 3px 14px; min-width: 60px; justify-content: center;'
        if bg_color:
            chip.style(
                f'background-color: {bg_color} !important; '
                f'color: #ffffff !important; '
                f'{spacing}'
            )
        else:
            chip.style(
                'background-color: #ffffff !important; '
                'color: #1f2937 !important; '
                f'{spacing}'
            )
        return chip

    def hover_render(self):
        color = self.get_color()
        current_cat = self.event.__class__.__name__

        with ui.column().classes('w-full gap-2 font-sans'):
            pre_min = int(self.event.pre_buffer / timedelta(minutes=1))
            if pre_min > 0:
                with ui.row().classes('w-full rounded-lg py-1 justify-center items-center').style(f'background-color: {color}'):
                    ui.label(f'{pre_min} min').classes('text-xs text-white')

            with ui.element('div').classes('w-full rounded-lg shadow-none flex flex-col').style(f'background-color: {color}; padding: 16px;'):
                ui.label(self.event.title).classes('text-base font-bold text-white break-words leading-tight w-full')

                if current_cat in {"Event", "FixedEvent", "FlexibleEvent", "PointEvent"}:
                    raise ValueError("Cannot choose a non-public category!")

                start_str = self.event.start.strftime('%I:%M %p')
                if current_cat in START_TIME_ONLY_CATEGORIES:
                    time_text = start_str
                else:
                    end_str = self.event.end.strftime('%I:%M %p')
                    time_text = f'{start_str} to {end_str}'
                ui.label(time_text).classes('text-xs text-white ml-1 mt-1')

                with ui.row().classes('flex-wrap gap-1 w-full mt-2 items-center'):
                    self._make_chip(current_cat, icon=CATEGORY_ICONS.get(current_cat))

                    properties = self.show_properties(current_cat)
                    for name, data in properties.items():
                        val = data["value"]
                        if val is None:
                            continue

                        if name == 'priority':
                            try:
                                p_enum = val if isinstance(val, PriorityMatrix) else PriorityMatrix(val)
                                bg = PRIORITY_COLORS.get(p_enum, '#9ca3af')
                                label = PRIORITY_LABELS.get(p_enum, str(val))
                            except (ValueError, TypeError):
                                bg = '#9ca3af'
                                label = str(val)
                            self._make_chip(label, bg_color=bg)
                            continue

                        icon = FIELD_ICONS.get(name)

                        if isinstance(val, (list, tuple, set)):
                            if not val:
                                continue
                            for item in val:
                                self._make_chip(self._format_value(item), icon=icon)
                        else:
                            self._make_chip(self._format_value(val), icon=icon)

            post_min = int(self.event.post_buffer / timedelta(minutes=1))
            if post_min > 0:
                with ui.row().classes('w-full rounded-lg py-1 justify-center items-center').style(f'background-color: {color}'):
                    ui.label(f'{post_min} min').classes('text-xs text-white')

    def show_properties(self, category_name: str) -> dict:
        cls = CATEGORIES.get(category_name)
        if not cls:
            return {}

        unused_fields = {'title', 'start', 'end', 'uid', 'series_uid',
                         'pre_buffer', 'post_buffer', 'flexible', 'missed', 'seen'}
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
        color = self.get_color()
        current_cat = self.event.__class__.__name__

        PAD        = 8
        TITLE_LINE = 15
        TIME_LINE  = 13
        THIN_LINE  = 4

        can_fit_title = height is not None and height >= PAD + TITLE_LINE
        is_thin       = height is not None and not can_fit_title
        show_title    = can_fit_title
        show_time     = height is not None and height >= PAD + TITLE_LINE + TIME_LINE

        z_class = 'z-20' if is_thin else 'z-10'
        display_height = THIN_LINE if is_thin else height

        wrapper = ui.element('div').classes(
            f'absolute left-2 right-32 rounded-lg {z_class} '
            f'transition-all duration-300 ease-in-out shadow-sm grid'
        ).style(
            f'top:{top}px; min-height:{display_height}px; max-height:{display_height}px; '
            f'background:{color}; border: 1px solid transparent; overflow: hidden;'
        )

        with wrapper:
            compact = ui.element('div').classes(
                'col-start-1 row-start-1 w-full px-2 py-1 transition-opacity duration-300 ease-in-out opacity-100 z-10'
            )
            with compact:
                if show_title:
                    ui.label(self.event.title).classes(
                        'text-xs font-bold truncate leading-tight text-white'
                    )
                if show_time:
                    if current_cat in START_TIME_ONLY_CATEGORIES:
                        time_text = f'{self.event.start:%I:%M %p}'
                    else:
                        time_text = f'{self.event.start:%I:%M %p} -- {self.event.end:%I:%M %p}'
                    ui.label(time_text).classes('text-[10px] text-white opacity-80')

            hover_container = ui.element('div').classes(
                'col-start-1 row-start-1 w-full p-2 transition-opacity duration-300 ease-in-out opacity-0 pointer-events-none z-20'
            )
            with hover_container:
                self.hover_render()

        def show_hover():
            wrapper.classes(remove='z-10 z-20')
            wrapper.classes(add='z-50 shadow-2xl')
            wrapper.style(
                f'top:{top}px; min-height:{height}px; max-height: 800px; '
                f'background: #ffffff; border: 1px solid #d1d5db; overflow: visible;'
            )
            compact.classes(remove='opacity-100').classes(add='opacity-0')
            hover_container.classes(
                remove='opacity-0 pointer-events-none'
            ).classes(add='opacity-100 pointer-events-auto')

        def show_compact():
            wrapper.classes(remove='z-50 shadow-2xl')
            wrapper.classes(add=z_class)
            wrapper.style(
                f'top:{top}px; min-height:{display_height}px; max-height:{display_height}px; '
                f'background: {color}; border: 1px solid transparent; overflow: hidden;'
            )
            compact.classes(remove='opacity-0').classes(add='opacity-100')
            hover_container.classes(
                remove='opacity-100 pointer-events-auto'
            ).classes(add='opacity-0 pointer-events-none')

        wrapper.on('mouseenter', show_hover)
        wrapper.on('mouseleave', show_compact)


# =====================================================================
# SCHEDULING WINDOW VIEW
# =====================================================================

class SchedulingWindow:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        self.outer = None
        self.now_container = None
        self._timer = None
        controller.sched_view = self

    def render(self):
        self.outer = ui.element('div').classes('w-full')
        self.rerender()
        self._timer = ui.timer(60, self._tick_now)

    def rerender(self):
        if self.outer is None:
            return
        self.outer.clear()
        with self.outer:
            self._render_body()

    def _tick_now(self):
        if self.now_container is not None:
            self.render_now(self.now_container)

    def _render_body(self):
        w = self.controller.wt
        if w is None:
            return

        max_time = w.window.end
        height = int((max_time - w.window.begin) / timedelta(minutes=1))

        with ui.element('div').classes(
            'w-full border-2 border-gray-800 rounded-2xl overflow-hidden p-2 bg-white shadow-xl'
        ).style(f'height: {height + 56}px; max-height: 53vh;'):
            with ui.scroll_area().classes('w-full h-full'):
                with ui.element('div').classes('relative w-full pr-1').style(
                    f'height:{height}px; margin-top: 20px; margin-bottom: 20px;'
                ):
                    self.hour_markers(max_time)
                    for ev in w.fixed.values():
                        self.event_box(ev)
                    for uid, slot in w.event_dict.items():
                        self.event_box(slot.data[uid])
                    self.now_container = ui.element('div').classes(
                        'absolute inset-0 pointer-events-none z-20'
                    )
                    self.render_now(self.now_container)

    def y(self, t: datetime) -> int:
        return int((t - self.controller.wt.window.begin) / timedelta(minutes=1))

    def hour_markers(self, max_time=None):
        w = self.controller.wt.window
        cur = w.begin.replace(minute=0, second=0, microsecond=0)
        if cur < w.begin:
            cur += timedelta(hours=1)

        end_time = max_time if max_time else w.end
        while cur < end_time:
            self.render_marker(cur)
            cur += timedelta(hours=1)

        next_midnight = w.begin.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if next_midnight <= end_time + timedelta(minutes=1):
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
        begin = self.controller.wt.window.begin
        end   = self.controller.wt.window.end
        ts = max(ev.true_start, begin)
        te = min(ev.true_end, end)
        top = self.y(ts)
        height = max(self.y(te) - top, 16)
        height = max(height - 2, 12)
        EventUI(ev).display(top=top, height=height)

    def render_now(self, container):
        container.clear()
        w = self.controller.wt.window
        now = datetime.now()
        if not (w.begin <= now <= w.end):
            return
        with container:
            with ui.element('div').classes('absolute left-0 right-32 flex items-center z-20').style(
                f'top:{self.y(now)}px; transform:translateY(-50%)'
            ):
                ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-pink-400')
                ui.element('div').classes('flex-1 h-0.5 bg-pink-400')


# =====================================================================
# CHOICE WIDGETS
# =====================================================================

class DateChoice:
    def __init__(self, value: date_cls):
        self.value = value
        self._picker = None

    def render(self):
        self._picker = ui.date(value=self.value.isoformat()) \
            .props('minimal flat square color=pink-400').classes('w-full') \
            .on('update:model-value', self._on_change)

    def _on_change(self, e):
        v = e.args
        if isinstance(v, list):
            v = v[0] if v else None
        if not v:
            return
        try:
            self.value = datetime.strptime(v, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass


class TimeChoice:
    def __init__(self, value: time_cls):
        self.value = value
        self._picker = None

    def render(self):
        # Added 'landscape' so the time picker takes up horizontal space rather than vertical
        self._picker = ui.time(value=self.value.strftime('%H:%M')) \
            .props('format24h landscape color=pink-400').classes('w-full max-w-sm') \
            .on('update:model-value', self._on_change)

    def _on_change(self, e):
        v = e.args
        if isinstance(v, list):
            v = v[0] if v else None
        if not v:
            return
        try:
            self.value = datetime.strptime(v, '%H:%M').time()
        except (ValueError, TypeError):
            pass


# =====================================================================
# CALENDAR
# =====================================================================

class Calendar:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        self.date = controller.selected_date
        self.date_el = None
        controller.calendar = self

    def render_content(self):
        self.date_el = ui.date(value=self.date.isoformat()) \
            .props('minimal flat square color=pink-400') \
            .classes('w-full') \
            .on('update:model-value', self._on_pick)

    def render(self):
        with ui.element('div').classes(
            'border-2 border-gray-900 rounded-2xl p-2 w-full flex-1 '
            'flex items-center justify-center min-h-[28vh] overflow-hidden'
        ):
            with ui.element('div').classes(
                'w-full h-full max-w-full max-h-full flex items-center justify-center '
                'overflow-auto'
            ):
                self.render_content()

    def _on_pick(self, e):
        value = e.args
        if isinstance(value, list):
            value = value[0] if value else None
        if not value:
            return
        try:
            new_date = datetime.strptime(value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return
        if new_date == self.controller.selected_date:
            return
        self.date = new_date
        self.controller.set_date(self.date)

    def refresh(self):
        if self.date_el is None:
            return
        self.date = self.controller.selected_date
        self.date_el.value = self.date.isoformat()


# =====================================================================
# WINDOW FLOW WIDGET
# =====================================================================

class WindowFlowWidget:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        controller.window_flow = self

        self.body = None
        self._calendar: Calendar | None = None

        self._steps: list[tuple[str, type, object]] = []
        self._widgets: list = []
        self._step = 0
        self._error = None

    def render(self):
        # Constrained to a maximum height so the time picker doesn't stretch the whole page
        with ui.element('div').classes(
            'border-2 border-gray-900 rounded-2xl p-2 w-full flex-1 min-h-[28vh] max-h-[40vh] overflow-hidden flex flex-col'
        ):
            self.body = ui.element('div').classes(
                'w-full h-full flex flex-col overflow-hidden'
            )
        self._show_calendar()

    def _show_calendar(self):
        self.controller.calendar = None
        self.body.clear()
        with self.body:
            with ui.element('div').classes('w-full h-full flex items-center justify-center'):
                self._calendar = Calendar(self.controller)
                self._calendar.render_content()

    def start_flow(self):
        c = self.controller
        self._steps = [
            ('Start date', DateChoice, c.window_start.date()),
            ('Start time', TimeChoice, c.window_start.time()),
            ('End date',   DateChoice, c.window_end.date()),
            ('End time',   TimeChoice, c.window_end.time()),
        ]
        self._widgets = [cls(value) for _, cls, value in self._steps]
        self._step = 0
        self.controller.calendar = None
        self._render_step()

    
        self.body.clear()
        with self.body:
            with ui.column().classes('w-full h-full justify-between p-2 gap-2'):

                # Header row: step title on the left, buttons on the right
                with ui.row().classes('w-full items-center justify-between shrink-0 gap-2'):
                    ui.label(self._steps[self._step][0]).classes('text-lg font-bold truncate')

                    with ui.row().classes('items-center gap-1 shrink-0'):
                        back_text = 'Cancel' if self._step == 0 else 'Back'
                        ui.button(back_text, on_click=self._go_back) \
                            .props('flat color=grey-8')

                        next_text = 'Confirm' if self._step == len(self._steps) - 1 else 'Next'
                        ui.button(next_text, on_click=self._go_next) \
                            .props('color=pink-400 text-white')

                # Picker Area
                with ui.column().classes('w-full flex-1 min-h-0 flex flex-col gap-2'):
                    widget_host = ui.element('div').classes(
                        'w-full flex-1 min-h-0 overflow-y-auto flex flex-col items-center justify-center'
                    )
                    with widget_host:
                        self._widgets[self._step].render()

                # Error message area (kept below the picker, above nothing — reserved)
                self._error = ui.label('').classes('text-xs text-red-600 shrink-0')


    def _render_step(self):
        self.body.clear()
        with self.body:
            with ui.column().classes('w-full h-full justify-between p-2 gap-2'):

                # Header row: step title on the left, buttons on the right
                with ui.row().classes('w-full items-center justify-between shrink-0'):
                    ui.label(self._steps[self._step][0]).classes('text-lg font-bold truncate pr-2')

                    with ui.row().classes('items-center gap-0 shrink-0'):
                        back_text = 'Cancel' if self._step == 0 else 'Back'
                        ui.button(back_text, on_click=self._go_back) \
                            .props('flat color=grey-8').classes('px-2 min-h-0')

                        next_text = 'Done' if self._step == len(self._steps) - 1 else 'Next'
                        ui.button(next_text, on_click=self._go_next) \
                            .props('color=pink-400 text-white').classes('px-3 min-h-0')

                # Picker Area
                with ui.column().classes('w-full flex-1 min-h-0 flex flex-col gap-2'):
                    widget_host = ui.element('div').classes(
                        'w-full flex-1 min-h-0 overflow-y-auto flex flex-col items-center justify-center'
                    )
                    with widget_host:
                        self._widgets[self._step].render()

                # Error message area
                self._error = ui.label('').classes('text-xs text-red-600 shrink-0')

    def _go_back(self):
        self._error.text = ''
        if self._step == 0:
            self._show_calendar()
        else:
            self._step -= 1
            self._render_step()

    def _go_next(self):
        self._error.text = ''
        if self._step < len(self._steps) - 1:
            self._step += 1
            self._render_step()
            return

        sd = self._widgets[0].value
        st = self._widgets[1].value
        ed = self._widgets[2].value
        et = self._widgets[3].value
        start = datetime.combine(sd, st)
        end   = datetime.combine(ed, et)
        if end <= start:
            self._error.text = 'End must be after start.'
            return

        self.controller.set_window(start, end)
        self._show_calendar()


# =====================================================================
# CONTROLS
# =====================================================================

class WindowSelector:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        controller.window_selector = self
        self.start_date_label = None
        self.start_time_label = None
        self.end_date_label = None
        self.end_time_label = None

    def render(self):
        self._build()

    def _build(self):
        with ui.row().classes(
            'h-14 flex-1 border-2 border-gray-900 rounded-full items-center justify-between px-6 gap-2 '
            'shadow-none flex-nowrap cursor-pointer hover:bg-gray-50 transition-colors'
        ).on('click', self._open_flow):
            with ui.column().classes('gap-0 items-center shrink-0'):
                self.start_date_label = ui.label().classes(
                    'text-[10px] text-gray-500 leading-none whitespace-nowrap'
                )
                self.start_time_label = ui.label().classes(
                    'text-sm font-bold text-gray-800 leading-tight whitespace-nowrap'
                )
            ui.label('-').classes('text-gray-400 font-bold text-lg shrink-0')
            with ui.column().classes('gap-0 items-center shrink-0'):
                self.end_date_label = ui.label().classes(
                    'text-[10px] text-gray-500 leading-none whitespace-nowrap'
                )
                self.end_time_label = ui.label().classes(
                    'text-sm font-bold text-gray-800 leading-tight whitespace-nowrap'
                )
        self.refresh_labels()

    def refresh_labels(self):
        if self.start_date_label is None:
            return
        c = self.controller
        self.start_date_label.text = c.window_start.strftime('%Y/%m/%d')
        self.start_time_label.text = c.window_start.strftime('%I:%M %p')
        self.end_date_label.text   = c.window_end.strftime('%Y/%m/%d')
        self.end_time_label.text   = c.window_end.strftime('%I:%M %p')

    def _open_flow(self):
        if self.controller.window_flow is not None:
            self.controller.window_flow.start_flow()


class DayTimeSelector:
    @classmethod
    def render(cls):
        with ui.row().classes(
            'h-14 shrink-0 border-2 border-gray-900 rounded-full items-center justify-center px-4 gap-4 '
            'shadow-none flex-nowrap'
        ):
            with ui.icon('wb_twilight').classes('text-2xl cursor-pointer hover:text-gray-500'):
                ui.tooltip('Morning').props('delay=1000')
            with ui.icon('sunny').classes('text-2xl cursor-pointer hover:text-gray-500'):
                ui.tooltip('Afternoon').props('delay=1000')
            with ui.icon('nights_stay').classes('text-2xl cursor-pointer hover:text-gray-500'):
                ui.tooltip('Evening').props('delay=1000')


class ActionButton:
    def __init__(self, icon: str):
        self.icon = icon
        self.btn_props = 'round outline color=grey-9'
        self.btn_classes = 'h-14 w-14 min-w-0 shrink-0 border-2 shadow-none'

    @classmethod
    def render(cls):
        inst = cls()
        inst._render()

    def _render(self):
        ui.button(icon=self.icon).props(self.btn_props).classes(self.btn_classes)


class Add(ActionButton):
    def __init__(self):
        super().__init__('add')


class Save(ActionButton):
    def __init__(self):
        super().__init__('save')


class Undo(ActionButton):
    def __init__(self):
        super().__init__('undo')


class Widget:
    def __init__(self):
        pass

    @classmethod
    def render(cls):
        inst = cls()
        inst._render()

    def _render(self):
        with ui.element('div').classes(
            'border-2 border-gray-900 rounded-2xl p-4 w-full flex-1 flex flex-col min-h-[28vh]'
        ):
            pass


class PriorityChoice:
    def __init__(self):
        self.value = None
        self.container = None
        self.dots = {}

    @classmethod
    def render(cls):
        inst = cls()
        inst._render()

    def select(self, p):
        self.value = p
        for key, (dot, color) in self.dots.items():
            selected = (p is not None and key == p)
            scale = 1 if selected else 0
            alpha = 1 if selected else 0
            dot.style(
                f'background-color: {color}; '
                f'transform: scale({scale}); '
                f'opacity: {alpha};'
            )

    def clear(self):
        self.select(None)

    def render_options(self):
        for p in PRIORITY_COLORS.keys():
            color = PRIORITY_COLORS[p]
            label = PRIORITY_LABELS[p]
            is_selected = (self.value == p)
            with ui.element('div').classes(
                'w-10 h-10 flex items-center justify-center cursor-pointer '
                'hover:bg-gray-100 rounded-full transition-colors duration-300'
            ).on('click', lambda p=p: self.select(p)):
                ui.tooltip(label).props('delay=1000')
                with ui.element('div').classes(
                    'w-6 h-6 rounded-full flex items-center justify-center transition-all duration-300'
                ).style(f'border: 2px solid {color}'):
                    inner = ui.element('div').classes(
                        'w-3 h-3 rounded-full transition-all duration-300 ease-in-out'
                    ).style(
                        f'background-color: {color}; '
                        f'transform: scale({1 if is_selected else 0}); '
                        f'opacity: {1 if is_selected else 0};'
                    )
                    self.dots[p] = (inner, color)

    def render_clear(self):
        with ui.element('div').classes(
            'w-10 h-10 flex items-center justify-center cursor-pointer '
            'hover:bg-gray-100 rounded-full transition-colors duration-300'
        ).on('click', self.clear):
            ui.icon('close').classes('text-xl text-gray-400')

    def _render(self):
        with ui.column().classes(
            'border-2 border-gray-900 rounded-full py-4 px-1 items-center '
            'w-14 shrink-0 flex-1 min-h-[20vh] justify-around'
        ) as self.container:
            self.render_options()
            self.render_clear()


# =====================================================================
# STUBS
# =====================================================================

class Editor(Widget): pass
class Feedback(Widget): pass
class Edit(ActionButton): pass
class Delete(ActionButton): pass