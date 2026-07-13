""" Planning agent (paper section 3.4.1).
    Turns the preplanned editing brief plus the narrative index into a
    structured storyboard for downstream narration/retrieval agents.
    Two-stage like coarse_parser: freeform reasoning memo first, then a
    transcriber call that structures the memo into PLANNING_FORMAT.
"""
from google import genai
from pathlib import Path
import json
import subprocess

import prompts_and_schema
from subsequent_alligment import normalize_event_times

client = genai.Client()

def model_json(obj):
    """Compact JSON for text sent to the model -- whitespace just burns tokens."""
    return json.dumps(obj, separators=(",", ":"))

def file_json(obj):
    """Indented JSON for files written to disk -- kept human-readable for debugging."""
    return json.dumps(obj, indent=2)

def get_video_duration(file_path):
    """Return video duration as (HH:MM:SS string, total integer seconds) using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    total_seconds = float(info["format"]["duration"])

    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}", int(total_seconds)

# Preplanned brief: the pipeline's end goal is one high-quality YouTube video.
EDITING_BRIEF = (
    "Cut this stream down into a single high-quality YouTube video. "
    "Tell the complete story of the session -- the stakes and wagers, the rivalries, "
    "and how they resolve -- while keeping the funniest and most engaging moments. "
    "Open with a hook that sells the video in the first seconds, keep the pacing tight, "
    "and end on the most satisfying payoff."
)

original_video = "../inputs/Squeex_raw.webm"
video_duration, total_seconds = get_video_duration(original_video)

# Context is the full index minus fine_events -- the planner reasons over the
# narrative scaffold; scene-level detail belongs to the retrieval agent.
with open("../outputs/index.json") as f:
    index = json.load(f)
context = {k: v for k, v in index.items() if k != "fine_events"}

planning_prompt = prompts_and_schema.PLANNING_PROMPT.format(
    video_duration=video_duration,
    editing_brief=EDITING_BRIEF,
    context=model_json(context),
)

planning_memo = client.interactions.create(
    model="gemini-3.5-flash",
    input=[{"type": "text", "text": planning_prompt}],
    generation_config={"thinking_level": "high"},
).output_text
print(planning_memo)

planning_format = prompts_and_schema.PLANNING_FORMAT
planning_skeleton = model_json(planning_format["schema"])

allignment_prompt = prompts_and_schema.PLANNING_ALLIGNMENT_PROMPT.format(
    planning_skeleton=planning_skeleton
) + planning_memo

storyboard = json.loads(
    client.interactions.create(
        model="gemini-3.5-flash",
        input=[{"type": "text", "text": allignment_prompt}],
        response_format=planning_format,
    ).output_text
)

# Timestamps are schema-forced integers, but still clamp to the video's range.
for segment in storyboard["storyboard"]:
    for time_range in segment["source_time_ranges"]:
        normalize_event_times(time_range, 0, total_seconds)

storyboard["editing_brief"] = EDITING_BRIEF
print(file_json(storyboard))

with open("../outputs/storyboard.json", "w", encoding="utf-8") as f:
    f.write(file_json(storyboard))
with open("../outputs/storyboard_memo.txt", "w", encoding="utf-8") as f:
    f.write(planning_memo)
