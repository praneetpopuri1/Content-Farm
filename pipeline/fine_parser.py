from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json
import subprocess
from prompts_and_schema import FINE_PROMPT, FINE_FORMAT
from subsequent_alligment import normalize_timestamp

client = genai.Client()

# Chunks are 300s of footage cut every CHUNK_STRIDE seconds, so consecutive
# chunks overlap by 30s; the labeled ranges tile the video with no gaps.
CHUNK_STRIDE = 270

def get_video_duration_seconds(file_path):
    """Return video duration in seconds using ffprobe."""
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
    return float(info["format"]["duration"])

# Cache uploaded Gemini files locally (path -> file name) so re-running the
# script while iterating on prompts doesn't re-upload the same video.
file_cache_path = Path(".gemini_file_cache.json")
file_cache = json.loads(file_cache_path.read_text()) if file_cache_path.exists() else {}

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
for i in range(len(file_paths)):
    cache_key = str(Path(file_paths[i]).resolve())
    file = None
    if cache_key in file_cache:
        try:
            file = client.files.get(name=file_cache[cache_key])
            if not file.state or file.state.name != "ACTIVE":
                file = None
            else:
                print(f"Using cached upload for {file_paths[i]}")
        except Exception:
            file = None
    if file is None:
        file = client.files.upload(file=file_paths[i])
        while not file.state or file.state.name != "ACTIVE":
            print("Processing video...")
            time.sleep(5)
            file = client.files.get(name=file.name)
        file_cache[cache_key] = file.name
        file_cache_path.write_text(json.dumps(file_cache, indent=2))

    start = int(Path(file_paths[i]).stem.split("_start_")[1])
    end = start + CHUNK_STRIDE
    if i == len(file_paths) - 1:
        end = start + int(get_video_duration_seconds(file_paths[i]))
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
    # Force timestamps onto the absolute video timeline (shifts segment-local
    # offsets, clamps to this chunk's labeled range).
    for seg in first_interaction_json["segments"]:
        seg["start_sec"] = normalize_timestamp(seg["start_sec"], start, end, fallback=start)
        seg["end_sec"] = normalize_timestamp(seg["end_sec"], start, end, fallback=end)
        if seg["end_sec"] < seg["start_sec"]:
            seg["end_sec"] = seg["start_sec"]
    segments.extend(first_interaction_json["segments"])
    print(json.dumps(first_interaction_json, indent=2))

with open("../outputs/fine_events.json", 'w', encoding="utf-8") as f:
    json.dump({"segments": segments}, f, indent=2)