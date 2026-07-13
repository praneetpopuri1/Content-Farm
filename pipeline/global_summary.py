"""Takes information from Coarse understanding and feeds selectively to Fine Parser"""
from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json
import math

import subprocess
import prompts_and_schema
from subsequent_alligment import normalize_timestamp
client = genai.Client()

# ----------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH for the global summary packet.
# Same shape convention as the coarse-parser schemas: a "general_plot_summary"
# string plus a "major_plot_events" array of timestamped beats.
# ----------------------------------------------------------------------------
GLOBAL_SUMMARY_FORMAT = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "general_plot_summary": {"type": "string"},
            "major_plot_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "detailed_description": {"type": "string"},
                        "start": {"type": "string"},  # MM:SS
                        "end": {"type": "string"},     # MM:SS
                    },
                    "required": [
                        "title",
                        "detailed_description",
                        "start",
                        "end",
                    ],
                },
            },
        },
        "required": ["general_plot_summary", "major_plot_events"],
    },
}

#create a general summary and a local plot summary
with open("../outputs/plot_2.json") as f:
    plot = json.load(f)
summary_prompt = f"""
You are an agent that converts plot details into a compact context packet for fine-grained
5-minute scene analysis.
You will be given all of the plot details

Reason through what the plot is 
And how it should be condensed into major plot points and a plot summary

This packet will be inserted into every scene-level prompt, so it must be:
- compact
- stable
- globally useful

Ouput two things:
1. A general plot summary
2. Each major plot event

INFORMATION:
""" + json.dumps(plot)

first_out = client.interactions.create(
    model="gemini-3.5-flash",
    input=[
        {"type": "text", "text": summary_prompt}
    ],
    response_format=GLOBAL_SUMMARY_FORMAT,
).output_text
print(first_out)
def get_video_duration(file_path):
    """Return video duration formatted seconds diff then one in coarse parser."""
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
    return total_seconds
num_seconds = get_video_duration("../inputs/Squeex_raw.webm")
SEG_DURATION = 5*60
directory = Path("../inputs/chunks_5min")

file_paths = [str(p) for p in directory.iterdir() if p.is_file()]
num_fine_segs = len(file_paths)
coarse_json_location = "../outputs/coarse_events_2.json"

with open(coarse_json_location) as f:
    coarse_events = json.load(f)

for i in range(num_fine_segs):
    seg_info = json.loads(first_out)
    start = int(i/3) * 900
    end = int(i/3+1) * 900
    local_coarse_events = []
    for event in coarse_events["coarse_events"]:
        end_sec = normalize_timestamp(event["end"])
        if end_sec is not None and end_sec <= end and end_sec > start:
            local_coarse_events.append(event)
    seg_info["local_coarse_events"] = local_coarse_events
    seg_info["characters"] = plot["key_characters"]
    seg_info["media_format"] = plot["media_format"]
    seg_info["overall_setting"] = plot["overall_setting"]
    seg_info["relationship_graph"] = plot["relationship_graph"]
    fine_out_location = f"../inputs/fine_seg_info/seg_{i}_info.json"
    with open(fine_out_location,'w',encoding='utf-8') as f:
        json.dump(seg_info,f,indent=2)