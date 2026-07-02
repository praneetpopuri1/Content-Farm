# goal of this file is to turn a live stream into collections of 15 and 5 minute segemnts with the output video being 480 with 1 fps
import os
import subprocess
from pathlib import Path


def downsample(input,ouput):
    input_path = Path(input)
    output_path = Path(ouput)

    subprocess.run([
        "ffmpeg",
        "-i", str(input_path),
        "-vf", "fps=1,scale=-2:480",
        "-c:v", "libx264",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "32k",
        "-ac", "1",
        str(output_path),
    ], check=True)


import subprocess
from pathlib import Path


def get_duration_sec(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def make_overlapping_chunks(
    input_path: str,
    output_dir: str,
    chunk_len_sec: int,
    overlap_sec: int = 30,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = get_duration_sec(input_path)
    step = chunk_len_sec - overlap_sec

    start = 0
    chunk_idx = 0

    while start < duration:
        output_path = output_dir / f"chunk_{chunk_idx:04d}_start_{int(start)}.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(chunk_len_sec),
            "-vf", "fps=1,scale=-2:480",
            "-c:v", "libx264",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "32k",
            "-ac", "1",
            str(output_path),
        ]

        subprocess.run(cmd, check=True)

        start += step
        chunk_idx += 1

input_video = "../inputs/Squeex_raw.webm"
output_video = "../outputs/Squeex_processed.mp4"
downsample(input_video, output_video)
# 15-minute chunks with 30-second overlap
make_overlapping_chunks(
    input_path=output_video,
    output_dir="../outputs/chunks_15min",
    chunk_len_sec=15 * 60,
    overlap_sec=30,
)

# 5-minute chunks with 30-second overlap
make_overlapping_chunks(
    input_path=output_video,
    output_dir="../outputs/chunks_5min",
    chunk_len_sec=5 * 60,
    overlap_sec=30,
)

