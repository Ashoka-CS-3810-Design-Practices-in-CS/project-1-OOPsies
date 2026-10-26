from intervaltree import Interval, IntervalTree
from bisect import bisect_right
from collections import deque
from events import *
# this library manages to do the majority of the tasks we needed from our custom 
# imagination of the data structure.

class FixedTree:
    def __init__(self):
        self.tree = IntervalTree()
        self.change_count = 0

    def insert(self, event:FixedEvent):
        self.tree.addi(event.true_start, event.true_end, event)
        self.change_count += 1

    def conflict_search(self, event:Event):
        found = list(self.tree.overlap(event.true_start, event.true_end))
        if found == []:
            return None
        else:
            return found[0].data

    def delete(self, event:FixedEvent):
        self.tree.removei(event.true_start, event.true_end, event)
        self.change_count += 1

    def edit(self, old_event:FixedEvent, new_event:FixedEvent):
        self.delete(old_event)
        self.insert(new_event)
        

class WindowTree:
    def __init__(self, window:Interval, event_tree:FixedTree):
        self.tree = IntervalTree([Interval(window.begin, window.end, {})])
        self.event_dict = dict[str,Interval]()
        self.unscheduled = dict[str, FlexibleEvent]()
        self.window = window
        self.fixed = dict[str, FixedEvent]()
        self.synced_version = event_tree.change_count

        fixed_intervals = event_tree.tree.overlap(window.begin, window.end)
        for interval in fixed_intervals:
            self.fixed[interval.data.uid] = interval.data
            self.tree.chop(interval.begin, interval.end, lambda *_ : dict[str,FlexibleEvent]())

    def subset_search(self, event:Event)->Interval|None:
            found = list(self.tree.overlap(event.true_start, event.true_end))
            if found == []:
                return None
            slot = found[0]

            if slot.begin <= event.true_start and slot.end >= event.true_end:
                return slot
            else:
                return None


    def insert_helper(self, event:FlexibleEvent):
        slot = self.subset_search(event)
        if slot is not None:
            slot.data[event.uid] = event

            schedule_data, leftovers = max_scheduling(list(slot.data.values()))

            slot.data.clear()
            slot.data.update(schedule_data)

            if event.uid in slot.data:
                self.event_dict[event.uid] = slot
                self.unscheduled.pop(event.uid, None)

            if len(leftovers) > 0:
                for leftover in leftovers:
                    leftover.seen.add(slot)
                    self.event_dict.pop(leftover.uid, None)
                    self.unscheduled[leftover.uid] = leftover 
                self.cascade(leftovers)
        else:
            self.unscheduled[event.uid] = event

    def validate(self, event:FlexibleEvent, event_tree:FixedTree):
        if not (self.window.begin <= event.true_start and self.window.end >= event.true_end):
            raise ValueError("Event bounds cannot exceed the scheduling window!")

        conflict = event_tree.conflict_search(event)
        if conflict is not None:
            raise ValueError(f"Conflict with fixed event: {conflict.title}")
                
                
    def insert(self, event:FlexibleEvent, event_tree:FixedTree):
        self.validate(event, event_tree)
        event.seen.clear() 
        self.insert_helper(event)

    def cascade(self, leftovers:list[FlexibleEvent]):
        queue: deque[FlexibleEvent] = deque(leftovers)
        all_slots = self.tree.items()
        while queue:
            event = queue.popleft()
            unseen = all_slots - event.seen
            candidates = {slot for slot in unseen if slot.length >= event.length}

            for slot in candidates:
                event.seen.add(slot)

                trial = dict(slot.data)
                trial[event.uid] = event
                new_schedule, new_leftovers = max_scheduling(list(trial.values()))

                if event.uid not in new_schedule:
                    continue

                slot.data.clear()
                slot.data.update(new_schedule)
                self.event_dict[event.uid] = slot
                self.unscheduled.pop(event.uid, None) 

                for leftover in new_leftovers:
                    leftover.seen.add(slot)
                    self.event_dict.pop(leftover.uid, None)
                    self.unscheduled[leftover.uid] = leftover
                    queue.append(leftover)
                    
                break

            else:
                self.unscheduled[event.uid] = event

    def delete_helper(self, event: FlexibleEvent):
        if event.uid in self.unscheduled:
            return self.unscheduled.pop(event.uid), []

        slot = self.event_dict.pop(event.uid, None)
        if slot is None:
            raise KeyError(f"Could not find event!")

        removed = slot.data.pop(event.uid)

        retry = [leftover for leftover in self.unscheduled.values() if slot in leftover.seen]
        for leftover in retry:
            leftover.seen.discard(slot)

        return removed, retry

    def delete(self, event:FlexibleEvent):
        removed, retry = self.delete_helper(event)
        if retry:
            self.cascade(retry)
        return removed

    def edit(self, event: FlexibleEvent, event_tree: FixedTree):
        self.validate(event, event_tree)
        removed, retry = self.delete_helper(event)
        event.seen.clear()
        self.insert_helper(event)
        if retry:
            self.cascade(retry)
        return removed

    def forget(self, slot: Interval):
        for s in self.tree:
            for e in s.data.values():
                e.seen.discard(slot)
        for e in self.unscheduled.values():
            e.seen.discard(slot)

    def split(self, fixed_event:FixedEvent):
        start, end = fixed_event.true_start, fixed_event.true_end
        orphans = list[FlexibleEvent]()

        for slot in list(self.tree.overlap(start, end)):
            left_end = max(slot.begin, start)
            right_start = min(slot.end, end)

            left  = Interval(slot.begin, left_end, {}) if left_end > slot.begin else None
            right = Interval(right_start, slot.end,{}) if right_start < slot.end else None

            for uid, e in slot.data.items():
                if left is not None and left.begin <= e.true_start and e.true_end <= left.end:
                    left.data[uid] = e;  self.event_dict[uid] = left
                elif right is not None and right.begin <= e.true_start and e.true_end <= right.end:
                    right.data[uid] = e; self.event_dict[uid] = right
                else:
                    orphans.append(e)
                    self.event_dict.pop(uid, None)
                    self.unscheduled[uid] = e

            self.forget(slot)
            self.tree.remove(slot)
            if left  is not None: self.tree.add(left)
            if right is not None: self.tree.add(right)

        if orphans:
            self.cascade(orphans)

    def merge(self, fixed_event:FixedEvent):
        if fixed_event.true_start == fixed_event.true_end:
            return

        start = max(fixed_event.true_start, self.window.begin)
        end = min(fixed_event.true_end, self.window.end)
        if start >= end:
            return

        left = next((s for s in self.tree if s.end == start), None)
        right = next((s for s in self.tree if s.begin == end), None)

        merged_slot = Interval(left.begin if left is not None else start,
                          right.end if right is not None else end, {})
        
        for slot in (left, right):
            if slot is None: continue
            self.forget(slot)
            self.tree.remove(slot)
            for uid, e in slot.data.items():
                merged_slot.data[uid] = e
                self.event_dict[uid] = merged_slot
        self.tree.add(merged_slot)

        retry = [e for e in self.unscheduled.values()
                 if merged_slot.begin <= e.true_start and e.true_end <= merged_slot.end]
        
        self.cascade(retry)

    def sync(self, event_tree: FixedTree):
            if self.synced_version == event_tree.change_count:
                return
    
            current = {iv.data.uid: iv.data 
                       for iv in event_tree.tree.overlap(self.window.begin, self.window.end)}
    
            for uid, ev in self.fixed.items():
                if uid not in current:
                    self.merge(ev)
            for uid, ev in current.items():
                if uid not in self.fixed:
                    self.split(ev)
    
            self.fixed = current
            self.synced_version = event_tree.change_count

# based on Kleinberg, Jon; Tardos, Eva (2006). Algorithm Design (1st ed.). Pearson. p. 254 
# and wikipedia: https://en.wikipedia.org/wiki/Interval_scheduling#Weighted
def max_scheduling_setup(data:list[FlexibleEvent]):
    v = sorted(data, key=lambda e: e.true_end)
    # O(nlogn) - sorted in increasing end times

    ends = [event.true_end for event in v]
    n = len(v)

    w = [event.priority for event in v] 
    # weight for each event
    # O(n)

    p = [0]*n
    # "we define p(j), for an interval j, to be the largest index i < j such that intervals 
    # i and j are disjoint. In other words, i is the leftmost interval that ends before j 
    # begins. We define p(j)=0 if no request i <j is disjoint from j"

    # "p[j] is the # of vectors that end before v[j] begins."
    for j in range(n):
        p[j] = bisect_right(ends, v[j].true_start, 0, j)
        # bisect_right: finds the largest index in ends (say, val)
        # such that val <= v[j].true_start. We want <= because 
        # our intervals are half open: [a,b). This ensures
        # that [a,b) and [b,c) can be scheduled togeter.
        # If we made the equality strict, b) and [b would be 
        # considered as a conflict even though they are not.
        
        #O(logn)

    # O(nlogn)
    
    v.insert(0,0)
    w.insert(0,0)
    p.insert(0,0)

    M = [0]
    for i in range(1,n+1): # O(n)
        M.append(max(w[i] + M[p[i]], M[i-1]))

    return n, v, w, p, M

def max_scheduling_recursive(i:int, v:list[FlexibleEvent|int], w:list[PriorityMatrix|int], p:list[int], M:list[int], 
                             schedule:deque[FlexibleEvent], chosen:deque[FlexibleEvent]): # O(n)
    if i == 0:
        schedule_data = dict[str,FlexibleEvent]()
        for event in schedule:
            schedule_data[event.uid] = event
        return schedule_data, set(chosen)
    
    elif w[i] + M[p[i]] >= M[i - 1]:
        schedule.appendleft(v[i])
        chosen.appendleft(i)
        return max_scheduling_recursive(p[i], v, w, p, M, schedule, chosen)
    
    else:
        return max_scheduling_recursive(i-1, v, w, p, M, schedule, chosen)

def max_scheduling(data:list[FlexibleEvent]): 
    # O(nlogn)

    n, v, w, p, M = max_scheduling_setup(data) # O(nlogn)
    schedule, chosen = max_scheduling_recursive(n, v, w, p, M, deque(), deque()) # O(n)

    leftovers = [v[i] for i in range(1, n+1) if i not in chosen]
    
    return schedule, leftovers