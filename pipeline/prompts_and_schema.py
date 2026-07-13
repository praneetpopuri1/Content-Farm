#prompts
COARSE_INITIAL_PROMPT = """
You are a narrative video comprehension agent building a reusable semantic index
for a long-form video editing system.

You will be given the first 15-minute segment of a {video_duration} (HH:MM:SS format) video.

Your goal is to establish the high-level narrative scaffold that future segment analysis will rely on.
Task:
Produce a freeform planning memo, not JSON.

You have Three objectives to reason about:
1. Think about the overarching narrative the story is telling
2. Think about the characters what their names are, descriptions of who they are, and relationships between the characters
3. Think about all of the consequential, interesting, or engaging moments that occur in the video

Analyze the video segment and extract:

1. Media format
   - cinematic film, vlog, lecture, podcast, instructional video, gameplay,
     interview, documentary, sports broadcast, etc.

2. Overall setting
   - physical setting
   - time period if inferable
   - social/contextual setting
   - visual atmosphere

3. Key named characters / speakers
   For each:
   - name if spoken or visible
   - role in the video
   - visual/personality description
   - current goal or motivation
   - uncertainty if identity is ambiguous

4. Interpersonal dynamics
   - relationships between characters
   - alliances, conflicts, authority relations, emotional tension
   - evidence from dialogue or behavior

5. Keep track of all funny moments, interesting points, and consequential events
    - Describe it in a moderate amount of detail
    - give the characters involved
    - give a start and end time as a plain integer number of seconds from the start of the video (e.g. 808). NEVER use MM:SS clock format, units like "808s", or words

6. A Narrative Timeline:
   - describe the overarching plot, by describing the overall story the Author/Creator is trying to tell, the motives and purpose of the characters in this plot, and how they are accomplishing this goal
   - describe the themes of the story
   - create a plot timeline by describing each significant event that impacts the plot and describe its relation to the overall plot
   - give a start and end time (in seconds)

Rules:
- Do not invent names. Use "unknown_person_1", etc. if needed.
- Distinguish observed facts from inferred interpretations.
- Prefer concise, stable, reusable facts over detailed moment-by-moment summary.
"""

COARSE_INTIAL_ALLIGNMENT_PROMPT = """
You convert a free-form analysis memo into JSON. You are a TRANSCRIBER, not a summarizer.

ABSOLUTE RULES:
- Transfer EVERY fact in the memo into the JSON. Do not drop, merge, shorten, or paraphrase any detail.
- If the memo lists N events, the JSON must contain N events. Never collapse multiple events into one.
- Copy descriptions essentially verbatim; only lightly reword to fit a field.
- Write every start/end timestamp as a plain integer number of seconds. Convert clock formats ("13:28" -> 808) and strip units ("1800s" -> 1800). Never put words, ranges, or explanations in a timestamp field.
- Every character mentioned in the memo must appear in key_characters.
- Every relationship described must appear in relationship_graph.
- Do NOT invent information that is not in the memo. Leave a field "" only if the memo truly has nothing for it.
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.

JSON SCHEMA TO FILL (match field names and nesting EXACTLY):
{schema_skeleton}

FREE FORM INPUT:
"""

COARSE_SUBSEQUENT_PROMPT = """You are a narrative video comprehension agent building a reusable semantic index
for a long-form video editing system.

You will a be given 15-minute segment specifcally segement_{segement_num} which starts at second {start} and ends at second {end} of a {video_duration} (HH:MM:SS format) video.

Your goal is to continue the high-level narrative scaffold that future segment analysis will rely on.
You will be given the plotline of the story along with chracter and narrative information so far. 
Task:
Produce a freeform planning memo, not JSON.

You have Three objectives to reason about:
1. Think about all of the consquential, intersting, or engaging moments that occur in the video
2. Think about the current plot and events and how it relates to the overall narrative.
3. Think about the information given to you and see if any information is wrong or misleading given the new material you have

Here is general inofrmation about the video and story and all of the previous plot points, there may be inconsistencies:
{persistent_info}

Analyze the video segment and extract:


1. Keep track of all funny moments, interesting points, and consequential events
    - Describe it in a moderate amount of detail
    - give the characters involved
    - give a start and end time as a plain integer number of seconds on the FULL video timeline: this segment runs from second {start} to second {end}, so every timestamp must be a bare number in that range. NEVER use MM:SS clock format, units like "900s", or words

2. A Narrative Timeline:
   - give a plot update, by updating the description of the overall story the Author/Creator is trying to tell, the motives and purpose of the characters in this plot, and how they are accomplishing this goal
   - create a plot timeline by describing each significant event that impacts the plot and describe its relation to the overall plot
   - give a start and end time (in seconds) remember the video starts at {start}

3. Find and correct any inconsistencies inside the story information, but do not change any previous plot developments
    - give the field where there is a mistake and write what should be their instead


Rules:
- The video file may contain roughly 30 extra seconds of footage past second {end}. Ignore everything after second {end}; it belongs to the next segment and will be analyzed there.
- Do not invent names. Use "unknown_person_1", etc. if needed.
- Distinguish observed facts from inferred interpretations.
- Prefer concise, stable, reusable facts over detailed moment-by-moment summary.""" 



COARSE_SUBSEQUENT_ALLGIMENT_PROMPT = """
You convert a free-form SEGMENT-UPDATE memo into a JSON DELTA. You are a TRANSCRIBER, not a summarizer.

The memo describes ONLY what is new or changed in this segment. It contains three kinds of content:
  (A) new significant / funny / consequential events
  (B) narrative updates: an optional revised overarching plot, new themes, and new plot threads
  (C) corrections to previously recorded facts

ABSOLUTE RULES:
- Transfer EVERY new event in the memo into significant_events. If the memo lists N events, output N events. Never merge or drop events.
- Transfer EVERY new plot thread into narrative_timeline.plotline. Never merge threads.
- Copy descriptions essentially verbatim; only lightly reword to fit a field.
- Write every start/end timestamp as a plain integer number of seconds. Convert clock formats ("13:28" -> 808) and strip units ("1800s" -> 1800). If the memo has no usable number for a timestamp, use the segment's start or end second instead. Never put words, ranges, or explanations in a timestamp field.
- For EACH correction the memo states, emit one corrections[] entry:
    target_collection : which part of the prior JSON is wrong
        (key_characters | relationship_graph | narrative_timeline | plotline | overall_setting | media_format)
    target_id : the STABLE identifier of the item being fixed
        - key_characters     -> the character_id (or name if no id)
        - relationship_graph -> "source->target"
        - plotline           -> the exact thread text of the existing thread
        - overall_setting    -> the field name being fixed (e.g. "location")
        - narrative_timeline -> "" for overarching_plot, or the theme string
        - media_format       -> ""
    field : the exact property to overwrite (e.g. "status", "description", "location")
    previous_value / corrected_value : what it was vs. what it should be
    reason : the evidence from THIS segment
- Do NOT restate unchanged characters, relationships, or prior events. Only deltas belong in this JSON.
- Do NOT rewrite history: a correction fixes a factual error, it must not erase or reinterpret a prior plot development.
- Do NOT invent information that is not in the memo. Leave a field "" or an array [] only if the memo truly has nothing for it.
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.

JSON DELTA SCHEMA TO FILL (match field names and nesting EXACTLY):
{_subsequent_skeleton}

FREE FORM SEGMENT-UPDATE MEMO:
"""

FINE_PROMPT = """
You are performing fine-grained semantic comprehension of a 5-minute video scene.

The goal is to build a high-resolution semantic trace for downstream video editing, retrieval, and QA.
To do this section the video into regular intervals of approximately 20-second  or semantic boundaries
Rules for intervals:
- Every start_sec/end_sec must be a plain number of seconds on the FULL video timeline: this scene runs from second {start} to second {end}, so every timestamp must be a number in that range. NEVER use MM:SS clock format, units, or words.
- The video file may contain roughly 30 extra seconds of footage past second {end}. Ignore everything after second {end}; it belongs to the next scene and will be analyzed there.
- Each part must satisfy start_sec < end_sec.
- Parts must be sorted by start_sec.
- Every second from {start} to {end} must be covered.
- Do not output overlapping segments.

Each interval should include:
- extract paraphrased dialogue
- extract the narrative-relevance of this scene
- extract a visual description scene
- how engaging this section as a float from 0-10
- assign timestamps at approximately 20-second intervals or semantic boundaries

Scene absolute time range:
{start} - {end}

Global context:
{context}




Rules:
- Do not invent names. Use "unknown_person_1", etc. if needed.
- Distinguish observed facts from inferred interpretations.
- Prefer concise, stable, reusable facts over detailed moment-by-moment summary.
"""
#Schemas

# ----------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH
# This schema is the only authority. The in-prompt template below is generated
# directly from it, so they can NEVER drift apart again.
# Note the ADDED fields: events and plot items now have "start"/"end" so the
# timestamps in the free-form memo actually have somewhere to go.
# ----------------------------------------------------------------------------
COARSE_INITIAL_FORMAT = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "segment_id": {"type": "string"},
            "time_range": {
                "type": "object",
                "properties": {
                    "start_sec": {"type": "integer"},
                    "end_sec": {"type": "integer"},
                },
                "required": ["start_sec", "end_sec"],
            },
            "significant_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string"},
                        "detailed_description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["introduced", "developing", "unresolved", "resolved"],
                        },
                        "characters_involved": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "start": {"type": "integer"},  # ADDED
                        "end": {"type": "integer"},     # ADDED
                    },
                    "required": [
                        "event_name",
                        "detailed_description",
                        "status",
                        "characters_involved",
                        "start",
                        "end",
                    ],
                },
            },
            "persistent_information": {
                "type": "object",
                "properties": {
                    "media_format": {"type": "string"},
                    "overall_setting": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "time_period": {"type": "string"},
                            "visual_atmosphere": {"type": "string"},
                            "social_context": {"type": "string"},
                        },
                        "required": [
                            "location",
                            "time_period",
                            "visual_atmosphere",
                            "social_context",
                        ],
                    },
                    "key_characters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "character_id": {"type": "string"},
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                                "description": {"type": "string"},
                                "personality": {"type": "string"},
                                "goals_or_motivations": {"type": "string"},
                                "evidence": {"type": "string"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                            },
                            "required": [
                                "character_id",
                                "name",
                                "role",
                                "description",
                                "personality",
                                "goals_or_motivations",
                                "evidence",
                                "confidence",
                            ],
                        },
                    },
                    "relationship_graph": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                                "relationship": {"type": "string"},
                                "evidence": {"type": "string"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                            },
                            "required": [
                                "source",
                                "target",
                                "relationship",
                                "evidence",
                                "confidence",
                            ],
                        },
                    },
                    "narrative_timeline": {
                        "type": "object",
                        "properties": {
                            "overarching_plot": {"type": "string"},
                            "themes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "plotline": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "thread": {"type": "string"},
                                        "detailed_description": {"type": "string"},
                                        "relation_to_overall_plot": {"type": "string"},
                                        "status": {
                                            "type": "string",
                                            "enum": ["introduced", "developing", "unresolved", "resolved"],
                                        },
                                        "characters_involved": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "start": {"type": "integer"},  # ADDED
                                        "end": {"type": "integer"},     # ADDED
                                    },
                                    "required": [
                                        "thread",
                                        "detailed_description",
                                        "relation_to_overall_plot",
                                        "status",
                                        "characters_involved",
                                        "start",
                                        "end",
                                    ],
                                },
                            },
                        },
                        "required": ["overarching_plot", "themes", "plotline"],
                    },
                },
                "required": [
                    "media_format",
                    "overall_setting",
                    "key_characters",
                    "relationship_graph",
                    "narrative_timeline",
                ],
            },
        },
        "required": [
            "segment_id",
            "time_range",
            "significant_events",
            "persistent_information",
        ],
    },
}

# ---------------------------------------------------------------------------
# SHARED SUB-SCHEMAS (single source of truth)
# These are the SAME item shapes used in your initial 15-min schema, extracted
# so the initial and subsequent schemas reference identical definitions and can
# never drift apart. Import these into 15_min_chunks.py and build the initial
# `json_response_format` from them too, if you want to fully de-duplicate.
# ---------------------------------------------------------------------------


# A correction targets ONE existing item by its stable identity.
CORRECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "target_collection": {
            "type": "string",
            "enum": [
                "key_characters",
                "relationship_graph",
                "narrative_timeline",  # use for overarching_plot / themes
                "plotline",            # an existing plot thread
                "overall_setting",
                "media_format",
            ],
        },
        # Stable id of the item being fixed:
        #   key_characters     -> character_id (or name)
        #   relationship_graph -> "source->target"
        #   plotline           -> the exact `thread` text of the thread
        #   overall_setting    -> the field name (e.g. "location")
        #   narrative_timeline -> "" (overarching_plot) or a theme string
        #   media_format       -> ""
        "target_id": {"type": "string"},
        # The exact property to overwrite (e.g. "status", "description", "location").
        "field": {"type": "string"},
        "previous_value": {"type": "string"},
        "corrected_value": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": [
        "target_collection",
        "target_id",
        "field",
        "previous_value",
        "corrected_value",
        "reason",
    ],
}

FINE_FORMAT = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "scene_id": {"type": "string"},
            "scene_start_sec": {"type": "integer"},
            "scene_end_sec": {"type": "integer"},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string"},
                        "start_sec": {"type": "number"},
                        "end_sec": {"type": "number"},
                        "engagment": {"type": "number"},
                        "paraphrased_dialogue": {"type": "string"},
                        "narrative_relevance": {"type": "string"},
                        "visual_description": {"type": "string"}
                    },
                    "required": [
                        "event_name",
                        "start_sec",
                        "end_sec",
                        "engagment",
                        "paraphrased_dialogue",
                        "narrative_relevance",
                        "visual_description"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["scene_id", "scene_start_sec", "scene_end_sec", "segments"],
        "additionalProperties": False
    }
}

COARSE_SUBSEQUENT_FORMAT = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "significant_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string"},
                        "detailed_description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["introduced", "developing", "unresolved", "resolved"],
                        },
                        "characters_involved": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "start": {"type": "integer"},  # ADDED
                        "end": {"type": "integer"},     # ADDED
                    },
                    "required": [
                        "event_name",
                        "detailed_description",
                        "status",
                        "characters_involved",
                        "start",
                        "end",
                    ],
                },
            },
            "narrative_timeline": {
                        "type": "object",
                        "properties": {
                            "plot_update": {"type": "string"},
                            "plotline": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "thread": {"type": "string"},
                                        "detailed_description": {"type": "string"},
                                        "relation_to_overall_plot": {"type": "string"},
                                        "status": {
                                            "type": "string",
                                            "enum": ["introduced", "developing", "unresolved", "resolved"],
                                        },
                                        "characters_involved": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "start": {"type": "integer"},  # ADDED
                                        "end": {"type": "integer"},     # ADDED
                                    },

                                    "required": [
                                        "thread",
                                        "detailed_description",
                                        "relation_to_overall_plot",
                                        "status",
                                        "characters_involved",
                                        "start",
                                        "end",
                                    ],
                                },
                            },
                            
                        },
                        "required": ["plot_update", "plotline"],
                    },
            "corrections": {
                "type": "array",
                "items": CORRECTION_SCHEMA,
            },
        },
        "required": [
            "significant_events",
            "narrative_timeline",
            "corrections",
        ],
    },
}

# ----------------------------------------------------------------------------
# PLANNING AGENT (paper section 3.4.1, "Planning and Narration")
# Two-stage like the coarse pipeline: a freeform reasoning memo first, then a
# transcriber prompt that structures the memo into a storyboard for the
# downstream narration and retrieval agents.
# ----------------------------------------------------------------------------
PLANNING_PROMPT = """You are a high-level video-edit planning agent for a long-form video editing system.
Your job is to plan a single high-quality YouTube video cut down from a {video_duration} (HH:MM:SS format) source video.

You will be given an editing brief describing the video to produce, plus the source video's
narrative index: its plot summary, narrative timeline, key characters, and significant
events with timestamps.

Task:
Produce a freeform planning memo, not JSON.

You have three objectives to reason about:
1. Interpret the brief: what tone does the video call for (comedic, dramatic, nostalgic, hype)?
   From whose perspective should the story be told? What scope of the source does it cover
   (which arcs, characters, or time ranges), and what should be left out?
2. Decide the narrative framing: the finished video must hold attention on YouTube. It should
   open with a hook that sells the video in the first seconds, build momentum with tight
   pacing, cut anything that does not earn its screen time, and land on a satisfying payoff.
   The framing may differ from the source's original telling.
3. Decompose the video into an ordered storyboard of segments (thematic or chronological)
   that together fulfill the brief.

For the interpretation, state:
- the tone, the narrative perspective, and the scope (what is included and excluded, and why)

For EACH storyboard segment, state:
- a short title and its narrative function (hook, exposition, rising_action, climax,
  resolution, montage, or transition)
- what this segment should convey, how it serves the brief, and why it keeps viewers watching
- which plot threads or events from the index it should draw from, using their exact
  names from the index
- the source time range(s) to pull footage from, as plain integer seconds on the full
  video timeline (e.g. 808). NEVER use MM:SS clock format, units like "808s", or words
- a target duration for the segment in seconds

Rules:
- Ground every segment in events that actually appear in the index. Do not invent moments.
- Copy event and thread names verbatim from the index so downstream retrieval can match them.
- Prefer fewer, stronger segments over exhaustive coverage; the storyboard must read as one
  coherent narrative, not a list of clips.
- Favor the source's highest-engagement moments, but only where they serve the story.
- Distinguish what the footage shows from what the narration will need to explain.

EDITING BRIEF:
{editing_brief}

NARRATIVE INDEX:
{context}
"""

PLANNING_FORMAT = {
    "type": "text",
    "mime_type": "application/json",
    "schema": {
        "type": "object",
        "properties": {
            "request_interpretation": {
                "type": "object",
                "properties": {
                    "tone": {"type": "string"},
                    "perspective": {"type": "string"},
                    "scope": {"type": "string"},
                    "framing": {"type": "string"},
                },
                "required": ["tone", "perspective", "scope", "framing"],
            },
            "storyboard": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_number": {"type": "integer"},
                        "title": {"type": "string"},
                        "narrative_function": {
                            "type": "string",
                            "enum": [
                                "hook", "exposition", "rising_action",
                                "climax", "resolution", "montage", "transition",
                            ],
                        },
                        "description": {"type": "string"},
                        "source_events": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "source_time_ranges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"},
                                },
                                "required": ["start", "end"],
                            },
                        },
                        "target_duration_sec": {"type": "integer"},
                    },
                    "required": [
                        "segment_number",
                        "title",
                        "narrative_function",
                        "description",
                        "source_events",
                        "source_time_ranges",
                        "target_duration_sec",
                    ],
                },
            },
        },
        "required": ["request_interpretation", "storyboard"],
    },
}

PLANNING_ALLIGNMENT_PROMPT = """
You convert a free-form edit-planning memo into a JSON storyboard. You are a TRANSCRIBER, not a summarizer.

ABSOLUTE RULES:
- Transfer EVERY storyboard segment in the memo into storyboard[]. If the memo lists N segments, output N segments, in the same order. Never merge or drop segments.
- Copy titles, descriptions, and event/thread names essentially verbatim; only lightly reword to fit a field.
- Write every start/end timestamp as a plain integer number of seconds. Convert clock formats ("13:28" -> 808) and strip units ("1800s" -> 1800). Never put words, ranges, or explanations in a timestamp field.
- narrative_function must be exactly one of: hook, exposition, rising_action, climax, resolution, montage, transition. Pick the closest match to what the memo says.
- Fill request_interpretation from the memo's interpretation of tone, perspective, scope, and framing.
- Do NOT invent information that is not in the memo. Leave a field "" or an array [] only if the memo truly has nothing for it.
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.

JSON SCHEMA TO FILL (match field names and nesting EXACTLY):
{planning_skeleton}

FREE FORM PLANNING MEMO:
"""