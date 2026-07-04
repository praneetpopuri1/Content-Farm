from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json
from prompts_and_schema import FINE_PROMPT, FINE_FORMAT

client = genai.Client()

directory = Path("../inputs/chunks_5min")
segs_path = Path("../inputs/fine_seg_info")


file_paths = sorted(
    [str(p) for p in directory.iterdir() if p.is_file()],
    key=lambda path: int(Path(path).stem.split("_start_")[1])
)
file_segs = sorted(
    [str(p) for p in segs_path.iterdir() if p.is_file()],
    key=lambda path: int(Path(path).stem.split("_")[1])
)
segments = []
for i in range(6):
    file = client.files.upload(file=file_paths[i])
    while not file.state or file.state.name != "ACTIVE":
        print("Processing video...")
        time.sleep(5)
        file = client.files.get(name=file.name)
    
    start = i* 300
    end = (i+1) * 300
    with open(file_segs[i]) as f:
        context = json.dumps(json.load(f))
    prompt = FINE_PROMPT.format(start=start, end=end, context=context)

    first_interaction = client.interactions.create(
    model="gemini-3.5-flash",
    input=[
        {"type": "text", "text": prompt},
        {"type": "video", "uri": file.uri, "mime_type": file.mime_type}

    ],
    response_format=FINE_FORMAT,
    ).output_text
    first_interaction_json = json.loads(first_interaction)
    segments.extend(first_interaction_json["segments"])
    print(json.dumps(first_interaction_json, indent=2))

with open("../outputs/fine_events.json", 'w', encoding="utf-8") as f:
    json.dump({"segments": segments}, f, indent=2)