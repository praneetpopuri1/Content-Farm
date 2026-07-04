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


def apply_segment_delta(persistent_info, running_events, delta, seg_num):
    """
    persistent_info : dict  -> carried-forward persistent_information block
    running_events  : list  -> significant_events accumulated across all segments
    delta           : dict  -> parsed subsequent-alignment JSON

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
    running_events.extend(new_events)

    # (B) narrative updates
    upd = delta.get("narrative_timeline", {}) or {}
    plot_update = upd.get("plot_update", "")
    if plot_update:
        nt.setdefault("plot_update", []).append(
            {"update_number": seg_num, "update": plot_update}
        )

    nt["plotline"].extend(upd.get("plotline", []) or [])  # append-only

    # (C) corrections
    for c in delta.get("corrections", []) or []:
        _apply_correction(persistent_info, c)

    return persistent_info, running_events, new_events
