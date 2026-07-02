from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json


def make_windows(start: int, end: int, step: int = 20):
    windows = []
    t = start
    idx = 1
    while t < end:
        windows.append({
            "event_id": f"E{idx:02d}",
            "window_start_sec": t,
            "window_end_sec": min(t + step, end)
        })
        t += step
        idx += 1
    return windows

def validate_event_count(output, expected_event_count):
    events = output.get("semantic_events", [])
    if len(events) != expected_event_count:
        raise ValueError(
            f"Expected {expected_event_count} events, got {len(events)}"
        )


client = genai.Client()
json_response_format = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "additionalProperties": True
    }
}
directory = Path("../outputs/chunks_5min")
with open("../outputs/coarse_summary.txt", 'r', encoding='utf-8') as f:
    global_context = f.read()

file_paths = sorted(
    [str(p) for p in directory.iterdir() if p.is_file()],
    key=lambda path: int(Path(path).stem.split("_start_")[1])
)
for i in range(1):
    file = client.files.upload(file=file_paths[i])
    while not file.state or file.state.name != "ACTIVE":
        print("Processing video...")
        time.sleep(5)
        file = client.files.get(name=file.name)
    start = i* 300
    end = (i+1) * 300
    canonical_windows = make_windows(start, end, step=20)
    expected_event_count = len(canonical_windows)  # 15 for a 300-second chunk
    windows_json = json.dumps(canonical_windows, indent=2)
    first_prompt = f"""
You are performing fine-grained semantic comprehension of a 5-minute video scene.

The goal is to build a high-resolution semantic trace for downstream video editing, retrieval, and QA.

This pass should match the paper's fine-grained scene comprehension stage:
- extract paraphrased dialogue
- extract narrative-relevant speech acts
- extract cinematographic descriptors
- extract affective signals
- assign timestamps at approximately 20-second intervals or semantic boundaries

Scene absolute time range:
{start} - {end}

Global context:
{global_context}

CANONICAL TIME WINDOWS:
{windows_json}

HARD OUTPUT CONTRACT:
1. Return exactly {expected_event_count} semantic_events.
2. There must be exactly one event for each canonical time window above.
3. Do not skip quiet, repetitive, low-action, or transitional windows.
4. If little happens in a window, still create an event and mark it as "low_activity" or "continuity".
5. Each event must preserve its assigned canonical window.
6. Do not merge neighboring windows.
7. If a semantic boundary occurs inside a window, mention it in boundary_notes, but still keep the event tied to the canonical window.
8. The output must cover the full scene from {start} to {end}; no missing tail section is allowed.
9. Use only known characters from the provided global context / character registry. Do not invent names.
10. Paraphrase dialogue; do not produce full transcript.

Return JSON only.
"""
    event_schema = {
    "type": "object",
    "properties": {
        "event_id": {"type": "string"},
        "window_start_sec": {"type": "integer"},
        "window_end_sec": {"type": "integer"},
        "actual_start_sec": {"type": "number"},
        "actual_end_sec": {"type": "number"},
        "duration_sec": {"type": "number"},

        "summary": {"type": "string"},
        "characters": {"type": "array", "items": {"type": "string"}},
        "speakers": {"type": "array", "items": {"type": "string"}},
        "paraphrased_dialogue": {"type": "string"},

        "speech_acts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "act_type": {
                        "type": "string",
                        "enum": [
                            "question", "accusation", "explanation", "joke",
                            "instruction", "reaction", "agreement",
                            "disagreement", "other"
                        ]
                    },
                    "content": {"type": "string"},
                    "target": {"type": "string"},
                    "narrative_function": {"type": "string"}
                },
                "required": ["speaker", "act_type", "content", "target", "narrative_function"],
                "additionalProperties": False
            }
        },

        "visual_description": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}},

        "cinematography": {
            "type": "object",
            "properties": {
                "shot_type": {"type": "string"},
                "camera_movement": {"type": "string"},
                "composition": {"type": "string"},
                "lighting": {"type": "string"},
                "setting": {"type": "string"}
            },
            "required": ["shot_type", "camera_movement", "composition", "lighting", "setting"],
            "additionalProperties": False
        },

        "affective_signals": {
            "type": "object",
            "properties": {
                "emotion": {"type": "string"},
                "body_language": {"type": "string"},
                "tone": {"type": "string"},
                "confidence": {"type": "string"}
            },
            "required": ["emotion", "body_language", "tone", "confidence"],
            "additionalProperties": False
        },

        "narrative_relevance": {"type": "string"},
        "retrieval_tags": {"type": "array", "items": {"type": "string"}},
        "boundary_notes": {"type": "string"},
        "activity_level": {
            "type": "string",
            "enum": ["high", "medium", "low", "continuity"]
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}}
    },
    "required": [
        "event_id",
        "window_start_sec",
        "window_end_sec",
        "actual_start_sec",
        "actual_end_sec",
        "duration_sec",
        "summary",
        "characters",
        "speakers",
        "paraphrased_dialogue",
        "speech_acts",
        "visual_description",
        "actions",
        "cinematography",
        "affective_signals",
        "narrative_relevance",
        "retrieval_tags",
        "boundary_notes",
        "activity_level",
        "uncertainties"
    ],
    "additionalProperties": False
}

    first_response_schema = {
    "type": "object",
    "properties": {
        "scene_id": {"type": "string"},
        "scene_start_sec": {"type": "integer"},
        "scene_end_sec": {"type": "integer"},
        "expected_event_count": {"type": "integer"},
        "scene_summary": {"type": "string"},
        "semantic_events": {
            "type": "array",
            "minItems": expected_event_count,
            "maxItems": expected_event_count,
            "items": event_schema
        }
    },
    "required": [
        "scene_id",
        "scene_start_sec",
        "scene_end_sec",
        "expected_event_count",
        "scene_summary",
        "semantic_events"
    ],
    "additionalProperties": False
    }

    json_response_format = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "scene_id": {"type": "string"},
            "scene_start_sec": {"type": "integer"},
            "scene_end_sec": {"type": "integer"},
            "expected_event_count": {"type": "integer"},
            "scene_summary": {"type": "string"},
            "semantic_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True
                }
            }
        },
        "required": [
            "scene_id",
            "scene_start_sec",
            "scene_end_sec",
            "expected_event_count",
            "scene_summary",
            "semantic_events"
        ],
        "additionalProperties": True
    }
}
    SCENE_ID = f"scene_{i}"

    first_schema_string = json.dumps(first_response_schema, indent=2)

    first_prompt = first_prompt + first_schema_string

    first_interaction = client.interactions.create(
    model="gemini-3.1-flash-lite",
    input=[
        {"type": "video", "uri": file.uri, "mime_type": file.mime_type},
        {"type": "text", "text": first_prompt}
    ],
        response_format=json_response_format

    )
    first_repsonse = json.loads(first_interaction.output_text)
    first_repsonse = json.loads(first_interaction.output_text)
    
    first_repsonse_text = json.dumps(first_repsonse, indent= 2)
    print(first_repsonse_text)
    validate_event_count(first_repsonse, expected_event_count)

    second_prompt = f"""
You are a timestamp alignment and citation agent.

You are given:
1. A 5-minute video scene.
2. A draft semantic trace with exactly {expected_event_count} canonical 20-second events.
3. The canonical time windows.
4. The global context.

Scene absolute time range:
{start} - {end}

Canonical windows:
{windows_json}

Draft semantic trace:
{first_repsonse_text}

TASK:
Verify, correct, and align each event to the best-supported timestamp range.

HARD RULES:
1. Preserve exactly {expected_event_count} events.
2. Preserve one aligned event per canonical window.
3. Do not merge canonical windows.
4. Do not delete events unless they are completely unsupported; if unsupported, keep the event but set confidence to "low" and explain why.
5. Correct hallucinated speakers, characters, visual details, or timestamps.
6. If the draft missed activity inside a canonical window, add the missing detail to that window.
7. The aligned trace must cover the entire scene from {start} to {end}.
8. Each citation must point to a timestamp range inside or near the event window.
9. Separate audio evidence, visual evidence, and inferred evidence.

Return JSON only.
"""
    aligner_response_format = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "scene_id": {"type": "string"},
            "aligned_semantic_trace": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "removed_or_corrected_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True
                }
            }
        },
        "required": ["scene_id", "aligned_semantic_trace"],
        "additionalProperties": True
    }
}
    second_interaction = client.interactions.create(
    model="gemini-3.1-flash-lite",
    input=[
        {"type": "video", "uri": file.uri, "mime_type": file.mime_type},
        {"type": "text", "text": second_prompt}
    ],
        response_format=aligner_response_format

    )
    second_interaction_json = json.loads(second_interaction.output_text)
    with open(f"../outputs/5_chunk_output/chunk_{i}.json",'w',encoding='utf-8') as f:
        json.dump(second_interaction_json,f, indent=2)
    print(json.dumps(second_interaction_json, indent=2))
    print(f"chunk {i} processed")