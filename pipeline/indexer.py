from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json

import subprocess
import prompts_and_schema
client = genai.Client()
# wanted output
# gen info :
#  
# Events: where there will be a coarse event and then all of the fine events inside of it
#
# plotline :
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

original_video = "../inputs/Squeex_raw.webm"
video_duration = get_video_duration(original_video)

with open("../outputs/plot_2.json") as f:
    plotline = json.load(f) 
with open("../outputs/fine_events.json") as f:
    fine_events = json.load(f) 
with open("../outputs/coarse_events_2.json") as f:
    coarse_events = json.load(f)
index = {}

fields_to_copy = ["media_format", "overall_setting", "key_characters","relationship_graph"]
gen_info = {k: plotline[k] for k in fields_to_copy if k in plotline}
index["gen_info"] = gen_info

index["coarse_events"] = coarse_events["coarse_events"]
index["fine_events"] = fine_events["segments"]

for i in range(len(index["coarse_events"])):
    event = index["coarse_events"][i]
    id = i
    event["event_id"] = f"event-{id:04d}"
    event["start"] = int(event["start"])
    event["end"] = int(event["end"])

for i in range(len(index["fine_events"])):
    event = index["fine_events"][i]
    id = i + len(index["coarse_events"])
    event["event_id"] = f"event-{id:04d}"
    event["start"] = event.pop("start_sec")
    event["end"] = event.pop("end_sec")
index["narrative_timeline"] = plotline["narrative_timeline"]
for i in range(len(index["narrative_timeline"]["plotline"])):
    event = index["narrative_timeline"]["plotline"][i]
    event["start"] = int(event["start"])
    event["end"] = int(event["end"])
# for i in range(len(coarse_events["coarse_events"])):
#     coarse_event = coarse_events["coarse_events"][i]
#     if i == (len(coarse_events["coarse_events"]) -1):
#         end = video_duration
#     else:
#         end = int(coarse_events["coarse_events"][i+1]["start"])
#     start = int(coarse_event["start"])
#     coarse_event["coarse_event_name"] = coarse_event.pop("event_name")
#     events.append(coarse_event)
#     for fine_event in fine_events["segments"]:
#         fine_start = int(fine_event["start_sec"])
#         if fine_start >= start and fine_start < end:
#             events.append(fine_event)



with open("../outputs/index.json", 'w',encoding='utf-8') as f:
    json.dump(index,f,indent=2)
