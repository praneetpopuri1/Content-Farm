"""
subsequent_alignment.py
------------------------
Delta-based alignment for segments AFTER the first one.

The subsequent free-form memo only ever contains:
  (A) new significant events
  (B) narrative updates (revised overarching plot, new themes, new plot threads)
  (C) corrections to previously recorded facts

So instead of re-emitting the whole `persistent_information` block every segment
(which is where flash-lite drops/hallucinates fields), the alignment model emits
a DELTA. `apply_segment_delta` then folds that delta into the carried-forward
scaffold: events and plot threads are append-only (history is never rewritten),
and corrections are applied by stable identity, not array index.
"""

import copy
import json
import re


def normalize_timestamp(value, seg_start=None, seg_end=None, fallback=None):
    """Coerce a model-emitted timestamp into absolute integer seconds.

    Handles the failure modes seen in real runs: plain numbers, numeric
    strings, unit suffixes ("1800s", "14400+"), clock strings ("13:28",
    "1:02:05"), and prose with a number buried in it ("after 12600s").
    Prose with no number at all resolves to `fallback` (usually the segment
    bound). When segment bounds are given, values that look like
    segment-local offsets are shifted to absolute time and the result is
    clamped into [seg_start, seg_end]. Returns None only if nothing works.
    """
    seconds = None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        clock = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if clock:
            a, b, c = clock.groups()
            if c is None:
                seconds = int(a) * 60 + int(b)          # MM:SS
            else:
                seconds = int(a) * 3600 + int(b) * 60 + int(c)  # HH:MM:SS
        else:
            num = re.search(r"\d+(?:\.\d+)?", text)
            if num:
                seconds = float(num.group())
    if seconds is None:
        seconds = fallback
    if seconds is None:
        return None
    if seg_start is not None and seg_end is not None:
        if seconds < seg_start and seg_start + seconds <= seg_end:
            seconds += seg_start  # looked like a segment-local offset
        seconds = min(max(seconds, seg_start), seg_end)
    return int(round(seconds))


def normalize_event_times(item, seg_start=None, seg_end=None):
    """Normalize the start/end fields of one event or plot thread in place."""
    if "start" in item:
        item["start"] = normalize_timestamp(
            item["start"], seg_start, seg_end, fallback=seg_start
        )
    if "end" in item:
        item["end"] = normalize_timestamp(
            item["end"], seg_start, seg_end, fallback=seg_end
        )
    start, end = item.get("start"), item.get("end")
    if isinstance(start, int) and isinstance(end, int) and end < start:
        item["end"] = start
    return item


def _apply_correction(persistent_info, c):
    """Apply one correction in place, locating the target by identity."""
    coll = c.get("target_collection")
    tid = c.get("target_id", "") or ""
    field = c.get("field", "") or ""
    new_val = c.get("corrected_value", "")
    if not field and coll not in ("media_format",):
        return

    if coll == "media_format":
        persistent_info["media_format"] = new_val

    elif coll == "overall_setting":
        persistent_info.setdefault("overall_setting", {})[field] = new_val

    elif coll == "key_characters":
        for ch in persistent_info.get("key_characters", []):
            if ch.get("character_id") == tid or ch.get("name") == tid:
                ch[field] = new_val
                break

    elif coll == "relationship_graph":
        src, _, tgt = tid.partition("->")
        src, tgt = src.strip(), tgt.strip()
        for rel in persistent_info.get("relationship_graph", []):
            if rel.get("source") == src and rel.get("target") == tgt:
                rel[field] = new_val
                break

    elif coll == "narrative_timeline":
        nt = persistent_info.setdefault("narrative_timeline", {})
        if field == "overarching_plot" or tid == "":
            nt["overarching_plot"] = new_val
        else:
            # correcting a specific theme string
            themes = nt.setdefault("themes", [])
            if tid in themes:
                themes[themes.index(tid)] = new_val

    elif coll == "plotline":
        nt = persistent_info.setdefault("narrative_timeline", {})
        for thread in nt.get("plotline", []):
            if thread.get("thread") == tid:
                thread[field] = new_val
                break


def apply_segment_delta(persistent_info, running_events, delta, seg_num,
                        seg_start=None, seg_end=None):
    """
    persistent_info : dict  -> carried-forward persistent_information block
    running_events  : list  -> significant_events accumulated across all segments
    delta           : dict  -> parsed subsequent-alignment JSON
    seg_start/end   : absolute second bounds of this segment; when given, new
                      event/thread timestamps are normalized and clamped

    Returns (new_persistent_info, new_running_events, events_added_this_segment).
    Events and new plot threads are append-only; only explicitly listed fields
    are corrected, so prior plot developments are preserved.
    """
    persistent_info = copy.deepcopy(persistent_info)
    running_events = list(running_events)

    nt = persistent_info.setdefault("narrative_timeline", {})
    nt.setdefault("overarching_plot", "")
    nt.setdefault("themes", [])
    nt.setdefault("plotline", [])

    # (A) new events
    new_events = delta.get("significant_events", []) or []
    for ev in new_events:
        normalize_event_times(ev, seg_start, seg_end)
    running_events.extend(new_events)

    # (B) narrative updates
    upd = delta.get("narrative_timeline", {}) or {}
    plot_update = upd.get("plot_update", "")
    if plot_update:
        nt.setdefault("plot_update", []).append(
            {"update_number": seg_num, "update": plot_update}
        )

    new_threads = upd.get("plotline", []) or []
    for th in new_threads:
        normalize_event_times(th, seg_start, seg_end)
    nt["plotline"].extend(new_threads)  # append-only

    # (C) corrections
    for c in delta.get("corrections", []) or []:
        _apply_correction(persistent_info, c)

    return persistent_info, running_events, new_events
