""" Coarse Video understanding + Narrative understanding.
    This script takes long form videos and ouputs coarse semantic understanding of the video
    Also creates a narrative timeline of the given video.
    Both are used to create the sematic index, where narrative understanding is used for story planning
    and coarse understanding is used for retreival and other downstream tasks

 """
from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json

import subprocess
import prompts_and_schema
from subsequent_alligment import apply_segment_delta
client = genai.Client()
#TODO need to change the output timestamps so there are (hh:mm:ss)
def model_json(obj):
    """Compact JSON for text sent to the model -- whitespace just burns tokens."""
    return json.dumps(obj, separators=(",", ":"))

def file_json(obj):
    """Indented JSON for files written to disk -- kept human-readable for debugging."""
    return json.dumps(obj, indent=2)

def get_video_duration(file_path):
    """Return video duration formatted as HH:MM:SS using ffprobe."""
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
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

original_video = "../inputs/Squeex_raw.webm"
video_duration = get_video_duration(original_video)

# Cache uploaded Gemini files locally (path -> file name) so re-running the
# script while iterating on prompts doesn't re-upload the same video.
file_cache_path = Path(".gemini_file_cache.json")
file_cache = json.loads(file_cache_path.read_text()) if file_cache_path.exists() else {}

#uploading files takes time for 15 min video 20 seconds
initial_video_path = "../inputs/chunks_15min/chunk_0000_start_0.mp4"
initial_cache_key = str(Path(initial_video_path).resolve())
intial_file = None
if initial_cache_key in file_cache:
    try:
        intial_file = client.files.get(name=file_cache[initial_cache_key])
        if not intial_file.state or intial_file.state.name != "ACTIVE":
            intial_file = None
        else:
            print(f"Using cached upload for {initial_video_path}")
    except Exception:
        intial_file = None
if intial_file is None:
    intial_file = client.files.upload(file=initial_video_path)
    while not intial_file.state or intial_file.state.name != "ACTIVE":
        print("Processing video...")
        time.sleep(5)
        intial_file = client.files.get(name=intial_file.name)
    file_cache[initial_cache_key] = intial_file.name
    file_cache_path.write_text(file_json(file_cache))

#prompts are loaded from prompts_and_schema.py 
initial_prompt = prompts_and_schema.COARSE_INITIAL_PROMPT.format(
    video_duration = video_duration
)
# 3.5 flash on high thinking is very strong and prompts should go before video since this is video extraction
initial_free_form = client.interactions.create(
    model="gemini-3.5-flash",
    input=[
        {"type": "text", "text": initial_prompt},
        {"type": "video", "uri": intial_file.uri, "mime_type": intial_file.mime_type},
    ],
    generation_config={"thinking_level": "high"},
).output_text
print(initial_free_form)

# ----------------------------------------------------------------------------
# The in-prompt template is now PRINTED FROM THE SCHEMA so it can't drift.
# We hand the model the exact JSON skeleton it must fill, plus strict
# lossless-transfer rules so it copies instead of summarizing.
# ----------------------------------------------------------------------------
initial_format = prompts_and_schema.COARSE_INITIAL_FORMAT
schema_skeleton = model_json(initial_format["schema"])

allignment_schema = prompts_and_schema.COARSE_INTIAL_ALLIGNMENT_PROMPT.format(
    schema_skeleton = schema_skeleton
)

allignment_prompt =  allignment_schema + initial_free_form

inital_allignment = client.interactions.create(
    # Use a stronger model than flash-lite for faithful copying; add thinking.
    model="gemini-3.1-flash-lite",
    input=[{"type": "text", "text": allignment_prompt}],
    response_format=initial_format,
).output_text
print(inital_allignment)
output_json = json.loads(inital_allignment)

persistent_info = output_json["persistent_information"]
coarse_events = list(output_json["significant_events"])
plotline = persistent_info["narrative_timeline"]["plotline"]

directory = Path("../inputs/chunks_15min")

file_paths = [str(p) for p in directory.iterdir() if p.is_file()]
#intial and subsequent video chunks have different prompts
for i in range(1,2):
    subsequent_cache_key = str(Path(file_paths[i]).resolve())
    subsequent_file = None
    if subsequent_cache_key in file_cache:
        try:
            subsequent_file = client.files.get(name=file_cache[subsequent_cache_key])
            if not subsequent_file.state or subsequent_file.state.name != "ACTIVE":
                subsequent_file = None
            else:
                print(f"Using cached upload for {file_paths[i]}")
        except Exception:
            subsequent_file = None
    if subsequent_file is None:
        subsequent_file = client.files.upload(file=file_paths[i])
        while not subsequent_file.state or subsequent_file.state.name != "ACTIVE":
            print("Processing video...")
            time.sleep(5)
            subsequent_file = client.files.get(name=subsequent_file.name)
        file_cache[subsequent_cache_key] = subsequent_file.name
        file_cache_path.write_text(file_json(file_cache))

    start = 900 * (i)
    end = 900 * (i+1)

    subsequent_prompt = prompts_and_schema.COARSE_SUBSEQUENT_PROMPT.format(
    segement_num=(i+1),
    video_duration = video_duration,
    start=start,
    end=end,
    persistent_info=model_json(persistent_info)
    )
    print(f"subsequent prompt {subsequent_prompt}")
    subsequent_prompt = subsequent_prompt
    memo = client.interactions.create(
        model="gemini-3.5-flash",
        input=[
            {"type": "text", "text": subsequent_prompt},
            {"type": "video", "uri": subsequent_file.uri, "mime_type": subsequent_file.mime_type}
        ],
        generation_config={"thinking_level": "high"},
    ).output_text
    
    print(memo)
    delta_format = prompts_and_schema.COARSE_SUBSEQUENT_FORMAT
    subsequent_skeleton = model_json(delta_format["schema"])
    sub_allignment_schema = prompts_and_schema.COARSE_SUBSEQUENT_ALLGIMENT_PROMPT.format(
        _subsequent_skeleton = subsequent_skeleton
    )
    
    delta_prompt = sub_allignment_schema + memo
    delta = json.loads(
        client.interactions.create(
            model="gemini-3.5-flash",
            input=[{"type": "text", "text": delta_prompt}],
            response_format=delta_format,
        ).output_text
    )
    print(delta)
    persistent_info, coarse_events, new_events = apply_segment_delta(
        persistent_info, coarse_events, delta
    )
    chunk_record = {
        "segment_id": f"coarse_{i:03d}",          # Python-authoritative
        "time_range": {"start_sec": start, "end_sec": end},
        "significant_events": new_events,          # events from THIS segment
        "persistent_information": persistent_info, # full carried-forward scaffold
        "delta": delta,                            # raw delta, kept for auditing
    }
    with open(f"../ouputs/chunk_record_c/chunk_{i}.json",
              "w", encoding="utf-8") as f:
        f.write(file_json(chunk_record))

with open(f"../outputs/coarse_events.json",
              "w", encoding="utf-8") as f:
        f.write(file_json(coarse_events))
with open(f"../outputs/plot.json",
              "w", encoding="utf-8") as f:
        f.write(file_json(persistent_info))