from datetime import datetime, timedelta, date as date_cls, time as time_cls
from dataclasses import dataclass, fields, MISSING
from dateutil.relativedelta import relativedelta
from typing import get_origin, get_args
from app.core.events import *
from app.core.dsa import *
from nicegui import ui

PX_PER_HOUR = 60

RECURRENCE_UNIT = {'Daily': 'days', 'Weekly': 'weeks', 'Monthly': 'months', 'Yearly': 'years'}

CATEGORIES = {
    'Meeting': Meeting, 'Lecture': Lecture, 'Routine': Routine,
    'Appointment': Appointment, 'Occasion': Occasion,
    'Deadline': Deadline, 'Task': Task,
}
START_TIME_ONLY = {'Appointment', 'Occasion', 'Deadline'}
EVENT_COLORS = {'fixed': "#502ba5", 'flexible': "#56ab53"}

PRIORITY_COLORS = {
    PriorityMatrix.URGENT_IMPORTANT: "#d23e5e",
    PriorityMatrix.URGENT_NOT_IMPORTANT: "#ffb806",
    PriorityMatrix.NOT_URGENT_IMPORTANT: "#45c4ff",
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT: "#2643BA",
}
PRIORITY_LABELS = {
    PriorityMatrix.URGENT_IMPORTANT: 'Urgent & Important',
    PriorityMatrix.URGENT_NOT_IMPORTANT: 'Urgent',
    PriorityMatrix.NOT_URGENT_IMPORTANT: 'Important',
    PriorityMatrix.NOT_URGENT_NOT_IMPORTANT: 'Minor',
}
CATEGORY_ICONS = {
    'Meeting': 'groups', 'Lecture': 'school', 'Routine': 'schedule',
    'Appointment': 'meeting_room', 'Occasion': 'celebration',
    'Deadline': 'hourglass_bottom', 'Task': 'assignment',
}
FIELD_ICONS = {'attendees': 'person', 'recurring': 'repeat',
               'micro_tasks': 'task_alt', 'venue': 'place', 'course_code': 'class'}
TIME_BUCKETS = {
    'morning': (time_cls(4, 0), time_cls(12, 0)),
    'afternoon': (time_cls(12, 0), time_cls(18, 0)),
    'evening': (time_cls(18, 0), time_cls(23, 0)),
}
PROP_SKIP = {'title', 'start', 'end', 'uid', 'series_uid', 'pre_buffer',
             'post_buffer', 'flexible', 'missed', 'seen'}

class SchedulerController:
    def __init__(self, fixed_tree: FixedTree):
        self.fixed_tree = fixed_tree
        self.windows: dict[date_cls, WindowTree] = {}
        self.current_wt: WindowTree | None = None
        self.selected_date = datetime.now().date()
        self.time_filter: set[str] = set()
        self.priority_filter: PriorityMatrix | None = None
        self.sched_view = self.calendar = self.pill = None
        self.editor = None
        self.priority_filter_widget = None
        self.series: dict[str, Event] = {}
        self.pending_fixed: dict[str, FixedEvent] = {}
        self.pending_bar = None 
        self.in_editor = False
        self.draft_priority: PriorityMatrix | None = None
        self.undo_btn = self.add_btn = None
        self._load_day(self.selected_date)

    @property
    def unscheduled(self) -> dict[str, tuple[WindowTree, Event]]:
        return {uid: (wt, e)
                for wt in self.windows.values()
                for uid, e in wt.unscheduled.items()}

    # ------------------------------------------------------------------ windows

    def _ensure_window(self, d: date_cls) -> WindowTree:
        if d not in self.windows:
            start = datetime.combine(d, time_cls(0, 0))
            self.windows[d] = WindowTree(
                Interval(start, start + timedelta(days=1)), self.fixed_tree
            )
        return self.windows[d]

    def _load_day(self, d: date_cls):
        wt = self._ensure_window(d)
        for s in list(self.series.values()):
            self._materialize_for_day(s, d)
        for w in self.windows.values():
            w.sync(self.fixed_tree)
        self.current_wt = wt
        self.selected_date = d

    # ------------------------------------------------------ recurrence indexing

    def _occurrence_index(self, proto: Event, target: date_cls) -> int | None:
        """Return the positive integer k such that target == anchor + k*unit,
        or None if target is not an occurrence. O(1); preserves relativedelta
        clamping semantics for Monthly/Yearly."""
        rule = getattr(proto, 'recurring', 'Never')
        if rule not in RECURRENCE_UNIT:
            return None
        anchor = proto.start.date()
        if rule == 'Daily':
            k = (target - anchor).days
        elif rule == 'Weekly':
            days = (target - anchor).days
            if days % 7:
                return None
            k = days // 7
        elif rule == 'Monthly':
            k = (target.year - anchor.year) * 12 + (target.month - anchor.month)
        elif rule == 'Yearly':
            k = target.year - anchor.year
        else:
            return None
        if k <= 0:
            return None
        if anchor + relativedelta(**{RECURRENCE_UNIT[rule]: k}) != target:
            return None
        return k

    # ------------------------------------------------------ materialisation

    def _materialize_for_day(self, s: Event, target: date_cls):
        k = self._occurrence_index(s, target)
        if k is None:
            return
        if self._already_materialised(s, target):
            return
        self._materialize(s, target, k)

    def _already_materialised(self, proto: Event, nd: date_cls) -> bool:
        """Idempotency guard: (series_uid, start.date()) uniquely identifies an
        occurrence, regardless of how it was placed."""
        series_uid = proto.series_uid
        day_begin = datetime.combine(nd, time_cls(0, 0))
        day_end = day_begin + timedelta(days=1)

        if isinstance(proto, FixedEvent):
            for iv in self.fixed_tree.tree.overlap(day_begin, day_end):
                e = iv.data
                if e.series_uid == series_uid and e.start.date() == nd:
                    return True
            for e in self.pending_fixed.values():
                if e.series_uid == series_uid and e.start.date() == nd:
                    return True
            return False

        wt = self.windows.get(nd)
        if wt is None:
            return False
        for slot in wt.tree:
            for e in slot.data.values():
                if e.series_uid == series_uid and e.start.date() == nd:
                    return True
        for e in wt.unscheduled.values():
            if e.series_uid == series_uid and e.start.date() == nd:
                return True
        return False

    def _materialize(self, proto: Event, nd: date_cls, k: int):
        shift = datetime.combine(nd, proto.start.time()) - proto.start
        kw = {f.name: getattr(proto, f.name) for f in fields(type(proto))
              if f.init and f.name not in {'series_uid', 'start', 'end'}}
        occ = type(proto)(**kw,
                          start=proto.start + shift,
                          end=proto.end + shift,
                          series_uid=proto.series_uid)

        if isinstance(occ, FixedEvent):
            if self.fixed_tree.conflict_search(occ) is None:
                self.fixed_tree.insert(occ)
            else:
                self.pending_fixed[occ.uid] = occ
        else:
            wt = self._ensure_window(nd)
            try:
                wt.insert(occ, self.fixed_tree)
            except ValueError:
                wt.unscheduled[occ.uid] = occ

    def register_series(self, event: Event):
        self.series[event.series_uid] = event

    # ---------------------------------------------------------------- public

    def set_date(self, d: date_cls):
        if d == self.selected_date:
            return
        old = self.windows.get(self.selected_date)
        if old is not None and not old.event_dict and not old.unscheduled:
            del self.windows[self.selected_date]
        self._load_day(d)
        self._refresh()

    def toggle_time_bucket(self, bucket: str):
        self.time_filter = {bucket} if bucket not in self.time_filter else set()
        self._refresh_visibility()

    def set_priority_filter(self, p: PriorityMatrix | None):
        self.priority_filter = p
        self._refresh_visibility()

    def event_visible(self, ev: Event) -> bool:
        if self.time_filter:
            ev_s, ev_e = ev.true_start.time(), ev.true_end.time()
            bs, be = TIME_BUCKETS[next(iter(self.time_filter))]
            if ev_e <= bs or ev_s >= be:
                return False
        if self.priority_filter is not None:
            return getattr(ev, 'priority', None) == self.priority_filter
        return True

    def _refresh(self):
        ui.timer(0.01, self._do_refresh, once=True)

    def _do_refresh(self):
        if self.sched_view: self.sched_view.rerender()
        if self.calendar:   self.calendar.refresh()
        if self.pill:       self.pill.refresh()
        if self.pending_bar: self.pending_bar.refresh()

    def _refresh_visibility(self):
        ui.timer(0.01, self._do_refresh_visibility, once=True)

    def _do_refresh_visibility(self):
        if self.sched_view:
            self.sched_view.apply_visibility()

    def open_editor(self):
        if self.editor:
            self.editor.open()


class EventUI:
    _active_hover = None
    _is_animating = False

    def __init__(self, event: Event, controller: SchedulerController):
        self.event = event
        self.controller = controller
        self.color = EVENT_COLORS['flexible' if event.flexible else 'fixed']
        self._collapse_timer = None
        self.collapse_now = None

    @staticmethod
    def _fmt(v):
        if isinstance(v, PriorityMatrix): return PRIORITY_LABELS.get(v, v.name)
        if isinstance(v, bool): return 'Yes' if v else 'No'
        if isinstance(v, timedelta):
            m = int(v / timedelta(minutes=1))
            return f'{m}m' if m < 60 else f'{m // 60}h{m % 60}m'.replace('h0m', 'h')
        return str(v)

    def _chip(self, text, icon=None, bg=None):
        chip = ui.chip(text, icon=icon, color=None).props('dense')
        chip.style(
            f'background-color:{bg or "#fff"} !important; '
            f'color:{"#fff" if bg else "#1f2937"} !important; '
            'padding: 3px 14px; min-width: 60px; justify-content: center;'
        )

    def _props(self) -> dict:
        cls = CATEGORIES.get(self.event.__class__.__name__)
        if not cls:
            return {}
        out = {}
        for f in fields(cls):
            if f.name in PROP_SKIP:
                continue
            val = getattr(self.event, f.name, None)
            if val is None and f.default is not MISSING:
                val = f.default
            if val is None and f.default_factory is not MISSING:
                val = f.default_factory()
            out[f.name] = val
        return out

    def _noop(self):
        pass

    def hover_render(self):
        pre = int(self.event.pre_buffer / timedelta(minutes=1))
        post = int(self.event.post_buffer / timedelta(minutes=1))

        rows = []

        with ui.column().classes('w-full flex-1 gap-2 p-2 bg-white rounded-lg shadow-2xl'):
            if pre > 0:
                pre_row = ui.row().classes(
                    'w-full rounded-md py-1.5 justify-center items-center shrink-0 reveal-row'
                ).style(f'background-color:{self.color}')
                with pre_row:
                    ui.label(f'{pre} min').classes('text-xs text-white')
                rows.append(pre_row)

            body = ui.column().classes(
                'w-full flex-1 rounded-lg p-4 gap-2 reveal-row relative'
            ).style(f'background-color:{self.color}')
            with body:
                actions = ui.column().classes('absolute top-2 bottom-2 right-2 gap-1 z-10 justify-between')
                with actions:
                    ui.button(icon='delete', on_click=self._noop) \
                        .props('flat dense round color=white') \
                        .classes('text-white') \
                        .on('click', lambda e: None, ['stop'])
                    ui.button(icon='edit', on_click=self._noop) \
                        .props('flat dense round color=white') \
                        .classes('text-white') \
                        .on('click', lambda e: None, ['stop'])

                ui.label(self.event.title).classes(
                    'text-base font-bold text-white break-words leading-tight w-5/6'
                )
                cat = self.event.__class__.__name__
                start = self.event.start.strftime('%I:%M %p')
                tt = start if cat in START_TIME_ONLY else f'{start} to {self.event.end:%I:%M %p}'
                ui.label(tt).classes('text-xs text-white ml-1 mt-1')

                chips_row = ui.row().classes('flex-wrap gap-1 w-5/6 mt-2 items-start reveal-row')
                with chips_row:
                    self._chip(cat, icon=CATEGORY_ICONS.get(cat))
                    for name, val in self._props().items():
                        if val is None:
                            continue
                        if name == 'priority':
                            try:
                                p = val if isinstance(val, PriorityMatrix) else PriorityMatrix(val)
                                self._chip(PRIORITY_LABELS.get(p, str(val)), bg=PRIORITY_COLORS.get(p, '#9ca3af'))
                            except (ValueError, TypeError):
                                self._chip(str(val), bg='#9ca3af')
                            continue
                        icon = FIELD_ICONS.get(name)
                        if isinstance(val, (list, tuple, set)):
                            for item in val:
                                self._chip(self._fmt(item), icon=icon)
                        else:
                            self._chip(self._fmt(val), icon=icon)

            rows.append(body)
            rows.append(chips_row)

            if post > 0:
                post_row = ui.row().classes(
                    'w-full rounded-md py-1.5 justify-center items-center shrink-0 reveal-row'
                ).style(f'background-color:{self.color}')
                with post_row:
                    ui.label(f'{post} min').classes('text-xs text-white')
                rows.append(post_row)

        for i, row in enumerate(rows):
            row.style(
                f'transition: opacity 220ms ease-out, transform 220ms ease-out; '
                f'transition-delay: {i * 45}ms;'
            )
        self._reveal_rows = rows

    def display(self, top: int, height: int):
        cat = self.event.__class__.__name__
        can_title = height >= 23
        show_time = height >= 36

        dh = 8 if not can_title else height
        z = 'z-20' if not can_title else 'z-10'
        visible = self.controller.event_visible(self.event)
        opacity = '1' if visible else '0.25'
        pe = 'auto' if visible else 'none'

        wrapper = ui.element('div').classes(
            f'absolute left-2 right-32 rounded-lg transition-[top,height,opacity] duration-500 ease-in-out {z}'
        ).style(
            f'top:{top}px; height:{dh}px; background:transparent; '
            f'overflow:visible; opacity:{opacity}; pointer-events:{pe};'
        )

        with wrapper:
            compact = ui.element('div').classes(
                'absolute top-0 bottom-0 left-1 right-1 rounded-lg shadow-sm overflow-hidden transition-opacity duration-500'
            ).style(f'background:{self.color};')

            with compact:
                if can_title:
                    with ui.element('div').classes('w-full h-full px-2 py-1'):
                        ui.label(self.event.title).classes(
                            'text-xs font-bold truncate leading-tight text-white'
                        )
                        if show_time:
                            tt = (self.event.start.strftime('%I:%M %p')
                                  if cat in START_TIME_ONLY
                                  else f'{self.event.start:%I:%M %p} -- {self.event.end:%I:%M %p}')
                            ui.label(tt).classes('text-[10px] text-white opacity-80')

            hover_classes = (
                'absolute top-0 left-0 right-0 flex flex-col transition-all duration-300 ease-out '
                'opacity-0 pointer-events-none scale-95 origin-top overflow-hidden'
            )
            hover = ui.element('div').classes(hover_classes).style(
                f'z-index: 30; min-height: {dh}px; transform-origin: top center; '
                'border: 2px solid rgba(255,255,255,0.75); border-radius: 0.5rem; '
                'box-shadow: 0 8px 30px rgba(0,0,0,0.18); '
                'border-color: transparent;'
            )
            with hover:
                self.hover_render()
                rows = self._reveal_rows

            for row in rows:
                row.classes(add='opacity-0 -translate-y-1')

        def do_expand():
            wrapper.classes(remove='z-10 z-20').classes(add='z-50')
            hover.classes(remove='opacity-0 pointer-events-none scale-95 origin-top overflow-hidden') \
                 .classes(add='opacity-100 pointer-events-auto scale-100 origin-top overflow-visible')
            hover.style('border-color: rgba(0,0,0,1);')
            for i, row in enumerate(rows):
                row.style(f'transition-delay: {i * 45}ms;')
                row.classes(remove='opacity-0 -translate-y-1') \
                   .classes(add='opacity-100 translate-y-0')

        def do_collapse():
            wrapper.classes(remove='z-50').classes(add=f'{z}')
            n = len(rows)
            for i, row in enumerate(rows):
                row.style(f'transition-delay: {(n - 1 - i) * 35}ms;')
                row.classes(remove='opacity-100 translate-y-0') \
                   .classes(add='opacity-0 -translate-y-1')
            hover.classes(remove='opacity-100 pointer-events-auto scale-100 origin-top overflow-visible') \
                 .classes(add='opacity-0 pointer-events-none scale-95 origin-top overflow-hidden')
            hover.style('border-color: transparent;')

        def expand():
            if not self.controller.event_visible(self.event):
                return
            if self._collapse_timer:
                self._collapse_timer.cancel()
                self._collapse_timer = None
            EventUI._active_hover = self
            if EventUI._is_animating:
                return
            do_expand()

        def collapse():
            if EventUI._active_hover is self:
                EventUI._active_hover = None
            if EventUI._active_hover is not None:
                wrapper.classes(remove='z-50').classes(add=f'{z}')
                hover.classes(remove='overflow-visible').classes(
                    add='opacity-0 pointer-events-none scale-95 origin-top overflow-hidden')
                hover.style('border-color: transparent;')
                for row in rows:
                    row.style('transition-delay: 0ms;')
                    row.classes(add='opacity-0 -translate-y-1')
                return
            EventUI._is_animating = True
            do_collapse()
            n = len(rows)
            total_delay = (n - 1) * 35 + 300

            def finish_collapse():
                EventUI._is_animating = False
                if EventUI._active_hover is not None and EventUI._active_hover is not self:
                    EventUI._active_hover.do_expand_now()

            self._collapse_timer = ui.timer(total_delay / 1000.0, finish_collapse, once=True)

        def do_expand_now():
            do_expand()

        self.do_expand_now = do_expand_now

        wrapper.on('mouseenter', expand)
        wrapper.on('mouseleave', collapse)

        self.collapse_now = collapse
        return wrapper


class SchedulingWindow:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        self.outer = self.wrapper = self.scroll_area = self.content = self.now_container = None
        self._event_boxes: dict = {}
        controller.sched_view = self

    def render(self):
        self.outer = ui.element('div').classes('w-full')
        with self.outer:
            self.wrapper = ui.element('div').classes('w-full border-2 border-gray-800 rounded-2xl overflow-hidden p-2 bg-white shadow-xl')
            with self.wrapper:
                self.scroll_area = ui.scroll_area().classes('w-full h-full')
                with self.scroll_area:
                    self.content = ui.element('div').classes('relative w-full pr-1')
        self.rerender()
        ui.timer(60, lambda: self.now_container and self.render_now(self.now_container))

    def rerender(self):
        if self.content is None:
            return
        w = self.controller.current_wt
        if w is None:
            return

        self._event_boxes.clear()
        height = int((w.window.end - w.window.begin) / timedelta(minutes=1))
        self.wrapper.style(f'height:{height + 56}px; max-height:55vh;')

        self.content.clear()
        with self.content:
            self.content.style(f'height:{height}px; margin-top:20px; margin-bottom:20px;')
            self.hour_markers()
            for ev in w.fixed.values():
                self.event_box(ev)
            for uid, slot in w.event_dict.items():
                self.event_box(slot.data[uid])
            self.now_container = ui.element('div').classes('absolute inset-0 pointer-events-none z-20 transition-opacity duration-200')
            self.render_now(self.now_container)

    def apply_visibility(self):
        active = EventUI._active_hover
        for info in self._event_boxes.values():
            ev = info['event']
            wrapper = info['wrapper']
            ui_obj = info['ui']
            visible = self.controller.event_visible(ev)

            opacity = 1.0 if visible else 0.25
            pe = 'auto' if visible else 'none'
            dh = 8 if info['height'] < 23 else info['height']
            wrapper.style(
                f'top:{info["top"]}px; height:{dh}px; background:transparent; '
                f'overflow:visible; opacity:{opacity}; pointer-events:{pe};'
            )

            if not visible and active is ui_obj:
                ui_obj.collapse_now()

    def y(self, t: datetime) -> int:
        return int((t - self.controller.current_wt.window.begin) / timedelta(minutes=1))

    def hour_markers(self):
        w = self.controller.current_wt.window
        cur = w.begin
        while cur <= w.end:
            self._marker(cur)
            cur += timedelta(hours=1)

    def _marker(self, t: datetime):
        with ui.element('div').classes('absolute left-2 right-2 flex items-center gap-2 z-0').style(f'top:{self.y(t)}px; transform:translateY(-50%)'):
            ui.element('div').classes('flex-1 border-t-2 border-dashed border-gray-300')
            with ui.column().classes('gap-0 text-right w-20 shrink-0'):
                ui.label(t.strftime('%Y/%m/%d')).classes('text-[10px] text-gray-400 tabular-nums leading-tight')
                ui.label(t.strftime('%I:%M %p')).classes('text-xs text-gray-500 tabular-nums leading-tight font-semibold')

    def event_box(self, ev: Event):
        w = self.controller.current_wt.window
        ts = max(ev.true_start, w.begin)
        te = min(ev.true_end, w.end)
        top = self.y(ts)
        height = max(self.y(te) - top - 2, 12)
        ui_obj = EventUI(ev, self.controller)
        wrapper = ui_obj.display(top=top, height=height)
        self._event_boxes[ev.uid] = {
            'wrapper': wrapper, 'ui': ui_obj, 'event': ev,
            'top': top, 'height': height,
        }

    def render_now(self, container):
        container.clear()
        w = self.controller.current_wt.window
        now = datetime.now()
        if not (w.begin <= now <= w.end):
            return
        with container:
            with ui.element('div').classes('absolute left-0 right-32 flex items-center z-20').style(f'top:{self.y(now)}px; transform:translateY(-50%)'):
                ui.element('div').classes('w-2.5 h-2.5 rounded-full bg-pink-400')
                ui.element('div').classes('flex-1 h-0.5 bg-pink-400')


class WindowSelector:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        controller.pill = self
        self.start_date = self.start_time = self.end_date = self.end_time = None
        self.start_tri = self.end_tri = self.start_col = self.end_col = None
        self.start_content = self.end_content = None
        self.editor_mode = False
        self._draft_start = self._draft_end = None
        self._on_change = None
        self.start_only = False

    def render(self):
        with ui.row().classes(
            'h-14 flex-1 border-2 border-gray-900 rounded-full items-center '
            'justify-between px-6 gap-2 shadow-none flex-nowrap'
        ):
            self.start_date, self.start_time, self.start_tri, self.start_col, self.start_content = self._side('start')
            ui.label('–').classes('text-lg font-bold text-gray-400')
            self.end_date, self.end_time, self.end_tri, self.end_col, self.end_content = self._side('end')
        self.refresh()

    def _side(self, which):
        c = ui.column().classes('gap-0 items-center justify-center select-none transition-all duration-300 rounded-lg px-2 h-full relative')
        with c:
            content = ui.column().classes('gap-0 items-center transition-transform duration-300')
            with content:
                t = ui.label().classes('text-sm font-bold text-gray-800 leading-tight whitespace-nowrap')
                d = ui.label().classes('text-[10px] text-gray-500 leading-none whitespace-nowrap')
            tri = ui.icon('arrow_drop_down').classes('text-gray-500 text-2xl opacity-0 transition-all duration-300 absolute bottom-0')
        c.on('click', lambda: self._pick_time(which))
        return d, t, tri, c, content

    def _pick_time(self, which):
        if not self.editor_mode:
            return
        cur = self._draft_start if which == 'start' else self._draft_end
        # For the end side, default the picker to 23:59 (11:59 PM) instead of the current end time
        display_time = cur.strftime('%H:%M') if which == 'start' else '23:59'
        with ui.dialog() as dialog, ui.card().classes('items-center p-0 border-2 border-gray-300 shadow-none overflow-hidden rounded-2xl'):
            tp = ui.time(value=display_time).props('color=pink-400 flat')
            with ui.row().classes('w-full justify-end p-5 bg-white'):
                ui.button('OK', on_click=lambda: self._apply_time(which, tp.value, dialog)).props('flat color=pink-400')
        dialog.open()

    def _apply_time(self, which, val, dialog):
        dialog.close()
        if not val:
            return
        try:
            h, m = int(str(val).split(':')[0]), int(str(val).split(':')[1])
        except (ValueError, IndexError):
            return
        if which == 'start':
            self._draft_start = self._draft_start.replace(hour=h, minute=m, second=0, microsecond=0)
            if self.start_only:
                self._draft_end = self._draft_start
            elif self._draft_end <= self._draft_start:
                self._draft_end = self._draft_start + timedelta(hours=1)
        else:
            # Keep the end on the same day as the start (no next-day rollover)
            self._draft_end = self._draft_start.replace(hour=h, minute=m, second=0, microsecond=0)
            if self.start_only:
                self._draft_end = self._draft_start
            elif self._draft_end <= self._draft_start:
                # If the chosen end time is before/equal to start, clamp to 23:59 same day
                self._draft_end = self._draft_start.replace(hour=23, minute=59, second=0, microsecond=0)
        self.refresh()
        if self._on_change:
            self._on_change(self._draft_start, self._draft_end)

    def enter_editor_mode(self, start, end, on_change=None):
        self.editor_mode = True
        self._draft_start, self._draft_end, self._on_change = start, end, on_change
        self.start_col.classes(add='cursor-pointer hover:bg-gray-50')
        self.end_col.classes(add='cursor-pointer hover:bg-gray-50')
        self.start_content.classes(add='-translate-y-1.5')
        self.end_content.classes(add='-translate-y-1.5')
        self.start_tri.classes(remove='opacity-0').classes(add='opacity-100')
        self.end_tri.classes(remove='opacity-0').classes(add='opacity-100')
        self.refresh()

    def exit_editor_mode(self):
        self.editor_mode = False
        self.start_only = False
        self._draft_start = self._draft_end = self._on_change = None
        self.start_col.classes(remove='cursor-pointer hover:bg-gray-50')
        self.end_col.classes(remove='cursor-pointer hover:bg-gray-50')
        self.start_content.classes(remove='-translate-y-1.5')
        self.end_content.classes(remove='-translate-y-1.5')
        self.start_tri.classes(remove='opacity-100').classes(add='opacity-0')
        self.end_tri.classes(remove='opacity-100').classes(add='opacity-0')
        self.refresh()

    def refresh(self):
        if self.start_date is None:
            return
        if self.editor_mode:
            self.start_date.text = self._draft_start.strftime('%Y/%m/%d')
            self.start_time.text = self._draft_start.strftime('%I:%M %p')
            self.end_date.text = self._draft_end.strftime('%Y/%m/%d')
            self.end_time.text = self._draft_end.strftime('%I:%M %p')
            return
        w = self.controller.current_wt.window
        self.start_date.text = w.begin.strftime('%Y/%m/%d')
        self.start_time.text = w.begin.strftime('%I:%M %p')
        self.end_date.text = w.end.strftime('%Y/%m/%d')
        self.end_time.text = w.end.strftime('%I:%M %p')


class DayTimeSelector:
    BUCKETS = [
        ('morning', 'wb_twilight', 'Morning'),
        ('afternoon', 'sunny', 'Afternoon'),
        ('evening', 'nights_stay', 'Evening'),
    ]

    def __init__(self, controller: SchedulerController):
        self.controller = controller
        self.icons = {}
        self.active_bucket = None
        self._render()

    @classmethod
    def render(cls, controller):
        sel = cls(controller)
        controller.day_time_selector = sel
        return sel

    def _render(self):
        with ui.row().classes('h-14 shrink-0 border-2 border-gray-900 rounded-full items-center justify-center px-4 gap-4 shadow-none flex-nowrap'):
            for key, icon_name, tip in self.BUCKETS:
                icon = ui.icon(icon_name).classes('text-2xl cursor-pointer transition-all duration-300 ease-in-out text-gray-800')
                icon.on('click', lambda k=key: self._toggle(k))
                with icon:
                    ui.tooltip(tip).props('delay=2000')
                self.icons[key] = icon

    def _toggle(self, key):
        if self.controller.in_editor:
            # In editor mode: always apply the bucket, flash the icon, then clear visuals.
            self.active_bucket = key
            d = self.controller.selected_date
            bs, be = TIME_BUCKETS[key]
            start = datetime.combine(d, bs)
            end = datetime.combine(d, be)
            self.controller.pill.enter_editor_mode(start, end)

            # Flash the selected icon pink
            for k, icon in self.icons.items():
                if k == key:
                    icon.classes(add='text-pink-400 scale-110', remove='text-gray-800 scale-100')
                else:
                    icon.classes(add='text-gray-800 scale-100', remove='text-pink-400 scale-110')

            # After a moment, revert the visual highlight (but don't touch the clock)
            def _reset_visuals():
                self.active_bucket = None
                for icon in self.icons.values():
                    icon.classes(add='text-gray-800 scale-100', remove='text-pink-400 scale-110')

            ui.timer(0.35, _reset_visuals, once=True)
            return

        # Normal filter mode — unchanged
        self.controller.toggle_time_bucket(key)
        for k, icon in self.icons.items():
            if k in self.controller.time_filter:
                icon.classes(add='text-pink-400 scale-110', remove='text-gray-800 scale-100')
            else:
                icon.classes(add='text-gray-800 scale-100', remove='text-pink-400 scale-110')



class PriorityChoice:
    def __init__(self, on_change=None, show_clear=True, initial=None):
        self.value = None
        self.dots = {}
        self.on_change = on_change
        self.show_clear = show_clear
        self.container = None
        self._render()
        if initial is not None:
            self._visual(initial)
            self.value = initial

    @classmethod
    def render(cls, on_change=None, show_clear=True, initial=None):
        return cls(on_change, show_clear, initial)

    def set_enabled(self, enabled: bool):
        if self.container is None:
            return
        if enabled:
            self.container.classes(remove='pointer-events-none opacity-40')
        else:
            self.container.classes(add='pointer-events-none opacity-40')

    def _visual(self, p):
        for key, (dot, color) in self.dots.items():
            sel = p is not None and key == p
            dot.style(f'background-color:{color}; transform:scale({1 if sel else 0}); opacity:{1 if sel else 0};')

    def select(self, p):
        self.value = p
        self._visual(p)
        if self.on_change:
            self.on_change(self.value)

    def _render(self):
        self.container = ui.column().classes(
            'border-2 border-gray-900 rounded-full py-4 px-1 items-center w-14 shrink-0 '
            'flex-1 min-h-[20vh] justify-around'
        )
        with self.container:
            for p, color in PRIORITY_COLORS.items():
                with ui.element('div').classes('w-10 h-10 flex items-center justify-center cursor-pointer hover:bg-gray-100 rounded-full transition-colors duration-300').on('click', lambda p=p: self.select(p)):
                    ui.tooltip(PRIORITY_LABELS[p]).props('delay=2000')
                    with ui.element('div').classes('w-6 h-6 rounded-full flex items-center justify-center transition-all duration-300').style(f'border:2px solid {color}'):
                        inner = ui.element('div').classes('w-3 h-3 rounded-full transition-all duration-300 ease-in-out').style(f'background-color:{color}; transform:scale(0); opacity:0;')
                        self.dots[p] = (inner, color)
            if self.show_clear:
                with ui.element('div').classes('w-10 h-10 flex items-center justify-center cursor-pointer hover:bg-gray-100 rounded-full transition-colors duration-300').on('click', lambda: self.select(None)):
                    ui.icon('close').classes('text-xl text-gray-400')


class Calendar:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        self.date_el = None
        self.outer = None
        controller.calendar = self

    def render(self):
        self.outer = ui.element('div').classes(
            'border-2 border-gray-900 rounded-2xl p-2 w-full flex-1 flex items-center '
            'justify-center min-h-[28vh] overflow-hidden'
        )
        with self.outer:
            with ui.element('div').classes('w-full h-full max-w-full max-h-full flex items-center justify-center overflow-auto'):
                self.date_el = ui.date(value=self.controller.selected_date.isoformat()).props('minimal flat square color=pink-400').classes('w-full').on('update:model-value', self._pick)

    def _pick(self, e):
        v = e.args[0] if isinstance(e.args, list) else e.args
        if not v:
            return
        try:
            self.controller.set_date(datetime.strptime(v, '%Y-%m-%d').date())
        except (ValueError, TypeError):
            pass

    def refresh(self):
        if self.date_el:
            self.date_el.value = self.controller.selected_date.isoformat()


def render_undo(controller):
    controller.undo_btn = btn = ui.button(icon='undo').props('round outline color=grey-9') \
        .classes('h-14 w-14 min-w-0 shrink-0 border-2 shadow-none')
    btn.on('click', lambda: controller.editor.close() if controller.in_editor else None)
    return btn

def render_add(controller):
    controller.add_btn = btn = ui.button(icon='add').props('round outline color=grey-9') \
        .classes('h-14 w-14 min-w-0 shrink-0 border-2 shadow-none')
    btn.on('click', lambda: controller.editor.save() if controller.in_editor else controller.open_editor())
    return btn


class Undo: render = staticmethod(render_undo)
class Add:  render = staticmethod(render_add)


class EventEditor:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        controller.editor = self
        self.outer = self.title_input = self.category_select = self.fields_area = None
        self.draft: dict = {}
        self.active = False

    def render(self):
        self.outer = ui.element('div').classes(
            'justify-center items-center border-2 border-gray-900 rounded-2xl p-2 w-full flex-1 min-h-[28vh] overflow-hidden'
        )
        self.outer.set_visibility(False)
        with self.outer:
            with ui.column().classes('justify-center items-center w-full h-full p-3 gap-3 overflow-hidden flex flex-col'):
                with ui.row().classes('w-full items-center justify-center gap-3 mt-auto pt-2'):
                    self.title_input = ui.input('Title').classes('w-1/3 text-sm').props('color=pink-400')
                    self.category_select = ui.select(
                        list(CATEGORIES.keys()), label='Category', on_change=self._on_category, with_input=True
                    ).props('popup-content-class=text-center color=pink-400').classes('w-1/2 text-sm')
                    
                self.fields_area = ui.column().classes('w-full justify-center items-center gap-2 flex-1 overflow-auto ')

    def open(self):
        if self.active:
            return
        self.active = True
        self.controller.in_editor = True
        self.controller.draft_priority = None
        self.title_input.value = ''
        self.category_select.value = None
        self.fields_area.clear()
        self.draft = {}

        # Reset DayTimeSelector visual state
        if hasattr(self.controller, 'day_time_selector'):
            self.controller.day_time_selector.active_bucket = None
            for icon in self.controller.day_time_selector.icons.values():
                icon.classes(add='text-gray-800 scale-100', remove='text-pink-400 scale-110')

        d = self.controller.selected_date
        bucket = next(iter(self.controller.time_filter), None)
        if bucket in TIME_BUCKETS:
            bs, be = TIME_BUCKETS[bucket]
            start, end = datetime.combine(d, bs), datetime.combine(d, be)
        else:
            start = self.controller.current_wt.window.begin
            end = self.controller.current_wt.window.end

        self.controller.pill.enter_editor_mode(start, end)
        if self.controller.calendar and self.controller.calendar.outer:
            self.controller.calendar.outer.set_visibility(False)
        self.outer.set_visibility(True)
        
        if self.controller.priority_filter_widget:
            self.controller.priority_filter_widget.select(None)
            self.controller.priority_filter_widget.set_enabled(False)

        self.controller.undo_btn.props('icon=close')
        self.controller.add_btn.props('icon=save')

    def close(self):
        if not self.active:
            return
        self.active = False
        self.controller.in_editor = False
        self.outer.set_visibility(False)
        if self.controller.calendar and self.controller.calendar.outer:
            self.controller.calendar.outer.set_visibility(True)
        self.controller.pill.exit_editor_mode()
        self.fields_area.clear()
        self.draft = {}
        
        if self.controller.priority_filter_widget:
            self.controller.priority_filter_widget.set_enabled(True)
            self.controller.priority_filter_widget.select(self.controller.priority_filter)

        self.controller.undo_btn.props('icon=undo')
        self.controller.add_btn.props('icon=add')

    def _on_category(self, e):
        self.fields_area.clear()
        self.draft = {}
        self.controller.draft_priority = None
        cat = e.value
        if not cat:
            if self.controller.priority_filter_widget:
                self.controller.priority_filter_widget.set_enabled(False)
            return

        pill = self.controller.pill
        pill.start_only = (cat in START_TIME_ONLY)
        if pill.start_only:
            pill._draft_end = pill._draft_start
        elif pill._draft_end <= pill._draft_start:
            pill._draft_end = pill._draft_start + timedelta(hours=1)
        pill.refresh()
        
        cls = CATEGORIES[cat]
        supports_priority = issubclass(cls, FlexibleEvent)
        if self.controller.priority_filter_widget:
            self.controller.priority_filter_widget.set_enabled(supports_priority)
            if not supports_priority:
                self.controller.priority_filter_widget.select(None)

        with self.fields_area:
            f_recurring = None
            for f in fields(cls):
                if f.name in PROP_SKIP or f.name == 'priority':
                    continue
                if f.name == 'recurring':
                    f_recurring = f
                    continue
                self._render_field(f)
            self._render_field(f_recurring)

    def _render_field(self, f):
        if f is None: return
        t = f.type
        optional = type(None) in get_args(t)
        inner = t
        if optional:
            nn = [a for a in get_args(t) if a is not type(None)]
            inner = nn[0] if len(nn) == 1 else t
        origin = get_origin(inner)
        label = f.name.replace('_', ' ').title()

        default = f.default if f.default is not MISSING else (
            f.default_factory() if f.default_factory is not MISSING else None
        )

        if origin in (tuple, list, set):
            with ui.row().classes('justify-center w-5/6'):
                chips = ui.input_chips(label, value=list(default) if default else []).classes('w-full').props('color=pink-400')
            chips.on('update:model-value',
                     lambda e, n=f.name, opt=optional: self.draft.__setitem__(
                         n, tuple(e.args or []) if (e.args or []) else (None if opt else ())))

        elif inner is str:
            with ui.row().classes('justify-center w-5/6'):
                ui.input(label,
                     value='' if default is None else default,
                     on_change=lambda e, n=f.name, opt=optional: self.draft.__setitem__(
                         n, (e.value or '').strip() or (None if opt else ''))
                     ).classes('w-full').props('color=pink-400')

        elif origin is Literal:
            params = list(get_args(inner))
            with ui.row().classes('justify-center w-2/5'):
                ui.select(
                    params,
                    label=label,
                    value=default,
                    with_input=True,
                    on_change=lambda e, n=f.name: self.draft.__setitem__(n, e.value),
                ).props('popup-content-class=text-center color=pink-400').classes('w-full text-sm')

    def save(self):
        cat = self.category_select.value
        if not cat:
            ui.notify('Choose a category', color='negative'); return
        title = (self.title_input.value or '').strip()
        if not title:
            ui.notify('Title is required', color='negative'); return

        start = self.controller.pill._draft_start
        end = self.controller.pill._draft_end
        if start is None or end is None or (cat in START_TIME_ONLY and start!=end) or (cat not in START_TIME_ONLY and end<=start):
            ui.notify('Set valid start and end times', color='negative'); return

        cls = CATEGORIES[cat]
        kwargs = {'title': title, 'start': start, 'end': end}

        for f in fields(cls):
            if f.name in PROP_SKIP or f.name in ('uid', 'series_uid'):
                continue
            if f.name == 'priority':
                if issubclass(cls, FlexibleEvent):
                    if self.controller.draft_priority is None:
                        ui.notify('Pick a priority', color='negative'); return
                    kwargs['priority'] = self.controller.draft_priority
                continue
            if f.name in self.draft and self.draft[f.name] not in (None, ''):
                kwargs[f.name] = self.draft[f.name]
            elif f.default is not MISSING:
                kwargs[f.name] = f.default
            elif f.default_factory is not MISSING:
                kwargs[f.name] = f.default_factory()
            else:
                ui.notify(f'{f.name} is required', color='negative'); return

        try:
            event = cls(**kwargs)
        except Exception as ex:
            ui.notify(f'Error: {ex}', color='negative'); return

        if isinstance(event, FixedEvent):
            if self.controller.fixed_tree.conflict_search(event) is not None:
                ui.notify('Conflicts with a fixed event', color='negative'); return
            self.controller.fixed_tree.insert(event)
            for wt in self.controller.windows.values():
                wt.sync(self.controller.fixed_tree)
        else:
            try:
                self.controller.current_wt.insert(event, self.controller.fixed_tree)
            except ValueError as ex:
                ui.notify(str(ex), color='negative'); return

        if getattr(event, 'recurring', 'Never') != 'Never':
            self.controller.register_series(event)
        self.close()
        self.controller._refresh()

class PendingBar:
    def __init__(self, controller: SchedulerController):
        self.controller = controller
        controller.pending_bar = self
        self.row = None

    def render(self):
        with ui.element('div').classes('w-full h-16 shrink-0 flex items-center'):
            ui.label('Pending:').classes(
                'text-xs font-semibold text-gray-600 px-2 pt-1 shrink-0 leading-none'
            )
            with ui.element('div').classes('w-full h-20 shrink-0 overflow-x-auto overflow-y-hidden'):
                self.row = ui.row(wrap=False).classes('h-full flex-nowrap items-center gap-2 p-1')
        self.refresh()

    def refresh(self):
        if self.row is None:
            return
        self.row.clear()
        with self.row:
            entries = (
                [(ev, EVENT_COLORS['fixed'], 'Recurrence Conflict')
                 for ev in self.controller.pending_fixed.values()] +
                [(ev, EVENT_COLORS['flexible'], 'Unable to Fit')
                 for _, ev in self.controller.unscheduled.values()]
            )
            for ev, color, kind in entries:
                self._card(ev, color, kind)
            if not entries:
                ui.label('NA').classes(
                    'text-xs text-gray-400 px-3 h-14 flex items-center'
                )

    def _card(self, ev, color, kind):
        card = ui.element('div').classes(
            'h-14 w-40 shrink-0 rounded-lg px-2 py-1 cursor-pointer '
            'shadow-sm transition-transform duration-200 hover:scale-105'
        ).style(f'background:{color};')
        day = ev.start.date()
        card.on('click', lambda: lambda: None if self.controller.in_editor else re_edit())
        with card:
            ui.label(ev.title).classes('text-xs font-bold text-white truncate leading-tight')
            ui.label(f'{kind} \n on {ev.start:%Y/%m/%d}').classes('whitespace-pre-line text-[10px] text-white opacity-80 truncate')

def re_edit():
    pass