#!/usr/bin/env python3
"""Generate a video from a local image with the ArtWorks API.

Designed for a-Shell Mini on iPhone. Uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import getpass
import json
import os
from pathlib import Path
import random
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.artworks.ai"
TERMINAL_STATES = {"completed", "failed", "canceled", "timeout"}
# The API can genuinely report "unknown"; it is also our fallback when the
# status field is missing, so it is only treated as fatal after repeated polls.
UNKNOWN_STATUS = "unknown"
CANCELABLE_STATES = {"pending", "preparing"}
# Task IDs still worth cancelling if the run is interrupted.
TRACKED_TASKS = {}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
CREDENTIALS_FILE = SCRIPT_DIRECTORY / "artworks_credentials.txt"
SETTINGS_FILE = SCRIPT_DIRECTORY / "artworks_settings.txt"
RANDOM_PROMPTS_FILE = SCRIPT_DIRECTORY / "randomprompt.txt"
SCRIPT_BUILD = "random-prompts-v3-video-timing-probe-v2"
IPHONE_SAFARI_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.6 Mobile/15E148 Safari/604.1"
)


class TaskTerminalError(RuntimeError):
    """A remote task ended permanently without producing a video."""


def api_request(method: str, path: str, username: str, password: str, data=None):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": IPHONE_SAFARI_USER_AGENT,
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(API_ROOT + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API error {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error


PROMPT_PHOTO_SEPARATOR = "::"


def split_prompt_photo(entry: str) -> tuple:
    """Split "photo.jpg::motion text" into its two parts.

    Binding the photo to its own prompt line makes misalignment impossible,
    unlike a second parallel list of filenames.
    """
    if PROMPT_PHOTO_SEPARATOR not in entry:
        return None, entry.strip()
    head, _, tail = entry.partition(PROMPT_PHOTO_SEPARATOR)
    head = head.strip()
    # A prompt may legitimately contain "::" later on; only a leading token that
    # looks like a filename is treated as a photo reference.
    if not head or len(head.split()) > 1 or "." not in Path(head).name:
        return None, entry.strip()
    return head, tail.strip()


def image_dimensions(path: Path) -> tuple:
    """Return (width, height) for JPEG/PNG without requiring Pillow."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return (
            int.from_bytes(data[16:20], "big"),
            int.from_bytes(data[20:24], "big"),
        )
    if data[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
                offset += 2
                continue
            length = int.from_bytes(data[offset + 2:offset + 4], "big")
            # SOF0-SOF15, excluding the DHT/JPG/DAC markers in that range.
            if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
                return (
                    int.from_bytes(data[offset + 7:offset + 9], "big"),
                    int.from_bytes(data[offset + 5:offset + 7], "big"),
                )
            offset += 2 + length
    return None


def crop_photo(
    source: Path, width: int, height: int, scale_to: tuple = None
) -> Path:
    """Centre-crop a source image, optionally scaling it to a shared size.

    Reuses an existing crop when one matching the requested size is already there.
    """
    final_width, final_height = scale_to or (width, height)
    destination = source.with_name(
        f"{source.stem}_crop{final_width}x{final_height}{source.suffix}"
    )
    if destination.is_file() and image_dimensions(destination) == (final_width, final_height):
        return destination
    crop = f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2"
    if (final_width, final_height) != (width, height):
        # Identical pixel dimensions guarantee the API returns identically sized
        # videos, which is what -c copy concat actually requires.
        crop += f",scale={final_width}:{final_height}:flags=lanczos"
    arguments = ["-y", "-i", str(source), "-vf", crop]
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        # Keep the re-encode close to visually lossless; the crop is the only edit.
        arguments += ["-q:v", "2"]
    arguments += ["-frames:v", "1", str(destination)]
    run_ffmpeg(arguments, f"cropping {source.name} to {width}x{height}")
    return destination


def align_photo_geometry(
    photos: list,
    assembling: bool,
    autocrop: bool = True,
    max_difference: float = 0.2,
) -> dict:
    """Reconcile source aspect ratios before any credits are spent.

    Concat with -c copy needs identical frame sizes, so chunks generated from
    differently shaped photos cannot be joined. Slight differences are fixed by
    centre-cropping every source to a shared ratio; large ones are refused,
    because cropping across them would discard most of the frame.

    Returns a mapping of original path to cropped replacement.
    """
    shapes = {}
    for photo in photos:
        size = image_dimensions(photo)
        if size:
            shapes[photo] = size
    if len(shapes) < 2:
        return {}
    ratios = {photo: width / height for photo, (width, height) in shapes.items()}
    if len({round(value, 3) for value in ratios.values()}) <= 1:
        return {}
    listing = ", ".join(
        f"{photo.name} ({width}x{height})"
        for photo, (width, height) in sorted(shapes.items())
    )
    smallest, largest = min(ratios.values()), max(ratios.values())
    difference = (largest - smallest) / smallest

    if not assembling:
        print(f"Note: source photos differ in aspect ratio: {listing}")
        return {}
    if not autocrop:
        raise RuntimeError(
            "Source photos have different aspect ratios, so the generated chunks "
            "cannot be concatenated without re-encoding: " + listing
            + ". Enable autoCropPhotos, use photos with a matching aspect ratio, "
            "or set combineVideos=false to keep the chunks as separate files."
        )
    if difference > max_difference:
        raise RuntimeError(
            f"Source aspect ratios differ by {difference:.0%}, more than the "
            f"{max_difference:.0%} allowed by autoCropMaxDifference: " + listing
            + ". Cropping to a common ratio would discard too much of the frame. "
            "Crop the photos yourself, raise autoCropMaxDifference, or set "
            "combineVideos=false."
        )

    # The median keeps the worst-case crop small in both directions.
    ordered = sorted(ratios.values())
    target = ordered[len(ordered) // 2]

    crops = {}
    for photo, (width, height) in shapes.items():
        if ratios[photo] > target:
            new_width, new_height = int(round(height * target)), height
        else:
            new_width, new_height = width, int(round(width / target))
        # Even dimensions keep every downstream encoder happy.
        crops[photo] = (
            min(width, new_width - new_width % 2),
            min(height, new_height - new_height % 2),
        )

    # Rounding to even pixels leaves ratios fractionally apart, and the API sizes
    # its output from the input, so every source is brought to one exact size.
    common_width = min(width for width, _ in crops.values())
    common_height = min(height for _, height in crops.values())
    common = (common_width - common_width % 2, common_height - common_height % 2)
    print(
        f"Aligning {len(shapes)} source photo(s) to {common[0]}x{common[1]} "
        f"({target:.3f}:1, largest difference {difference:.1%}): {listing}"
    )
    replacements = {}
    for photo, (width, height) in sorted(shapes.items()):
        if (width, height) == common:
            continue
        cropped = crops[photo]
        lost = 1 - (cropped[0] * cropped[1]) / (width * height)
        scaled = " then scaled" if cropped != common else ""
        print(
            f"  {photo.name}: {width}x{height} -> {common[0]}x{common[1]} "
            f"({lost:.1%} cropped{scaled})"
        )
        replacements[str(photo)] = str(
            crop_photo(photo, cropped[0], cropped[1], scale_to=common)
        )
    return replacements


def track_task(task_id: str, status: str) -> None:
    """Remember live tasks so an interrupted run can cancel what is still queued."""
    if status in TERMINAL_STATES:
        TRACKED_TASKS.pop(task_id, None)
    else:
        TRACKED_TASKS[task_id] = status


def cancel_task(task_id: str, username: str, password: str) -> bool:
    try:
        api_request("POST", f"/api/v3/tasks/{task_id}/cancel", username, password)
        return True
    except RuntimeError:
        # Cancelling only works while a task is queued; anything else is not an error here.
        return False


def promote_task(task_id: str, username: str, password: str) -> bool:
    try:
        api_request("POST", f"/api/v3/tasks/{task_id}/fast", username, password)
        return True
    except RuntimeError as error:
        print(f"Could not move {task_id} to the fast queue: {error}")
        return False


def cancel_tracked_tasks(username: str, password: str) -> None:
    pending = [
        task_id for task_id, status in sorted(TRACKED_TASKS.items())
        if status in CANCELABLE_STATES
    ]
    if not pending:
        return
    print(f"Cancelling {len(pending)} queued task(s)…", file=sys.stderr)
    for task_id in pending:
        state = "cancelled" if cancel_task(task_id, username, password) else "already running"
        print(f"  {task_id}: {state}", file=sys.stderr)


def list_resources(resource_type: str, username: str, password: str, query: str = "") -> list:
    parameters = {"type": resource_type}
    if len(query) >= 3:
        # The q filter is rejected below three characters.
        parameters["q"] = query
    result = api_request("GET", "/api/v3/resources?" + urlencode(parameters), username, password)
    return result if isinstance(result, list) else []


def validate_loras(loras: list, username: str, password: str) -> None:
    """Reject unknown LoRA filenames before any generation credits are spent."""
    if not loras:
        return
    print(f"Checking {len(loras)} LoRA name(s) against the server…")
    try:
        available = list_resources("LORA", username, password)
    except RuntimeError as error:
        print(f"Could not list LoRAs ({error}); continuing without validation.")
        return
    known = set()
    for entry in available:
        for key in ("fileName", "fullFileName"):
            if entry.get(key):
                known.add(entry[key])
    if not known:
        return
    missing = [lora["modelName"] for lora in loras if lora["modelName"] not in known]
    if missing:
        lowered = {name.lower(): name for name in known}
        hints = []
        for name in missing:
            match = lowered.get(name.lower())
            hints.append(f"{name}" + (f" (did you mean {match}?)" if match else ""))
        raise RuntimeError(
            "Unknown LoRA filename(s): " + "; ".join(hints)
            + ". Names must match fileName from /api/v3/resources?type=LORA."
        )


def report_results(task: dict, label: str = "") -> None:
    """Print the metrics and warnings the API returns alongside a finished task."""
    results = task.get("results") or {}
    prefix = f"{label} " if label else ""
    metrics = results.get("metrics") or {}
    duration_secs = metrics.get("durationSecs")
    execution_secs = metrics.get("executionDurationSecs")
    parts = []
    if duration_secs is not None:
        parts.append(f"API duration {format_elapsed(float(duration_secs))}")
    if execution_secs is not None:
        parts.append(f"API execution {format_elapsed(float(execution_secs))}")
    if parts:
        print(f"{prefix}Metrics: " + " | ".join(parts))
    for warning in results.get("warnings") or []:
        print(f"{prefix}Warning from API: {warning}")


def encode_image(path: Path) -> str:
    size_mb = path.stat().st_size / 1_048_576
    print(f"Reading {path.name} ({size_mb:.1f} MB)…")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def load_credentials() -> tuple[str, str]:
    env_username = os.environ.get("ARTWORKS_USERNAME")
    env_password = os.environ.get("ARTWORKS_PASSWORD")
    if env_username and env_password:
        return env_username, env_password

    if CREDENTIALS_FILE.is_file():
        values = {}
        for line_number, raw_line in enumerate(CREDENTIALS_FILE.read_text("utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key.strip() not in {"username", "password"}:
                raise RuntimeError(
                    f"Invalid line {line_number} in {CREDENTIALS_FILE.name}. "
                    "Expected username=... or password=..."
                )
            values[key.strip()] = value.strip()

        if values.get("username") and values.get("password"):
            print(f"Using credentials from {CREDENTIALS_FILE.name}")
            return values["username"], values["password"]
        raise RuntimeError(
            f"{CREDENTIALS_FILE.name} must contain both username=... and password=..."
        )

    print(f"No {CREDENTIALS_FILE.name} found beside the script.")
    username = input("ArtWorks username: ").strip()
    password = getpass.getpass("ArtWorks password: ")
    if not username or not password:
        raise RuntimeError("Username and password are required.")

    save = input(f"Save them in {CREDENTIALS_FILE.name}? [Y/n]: ").strip().lower()
    if save in {"", "y", "yes"}:
        CREDENTIALS_FILE.write_text(
            f"username={username}\npassword={password}\n",
            encoding="utf-8",
        )
        try:
            CREDENTIALS_FILE.chmod(0o600)
        except OSError:
            pass
        print(f"Saved {CREDENTIALS_FILE.name} beside the script.")
    return username, password


def download(url: str, destination: Path, show_progress: bool = True) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    request = Request(
        url,
        headers={
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": IPHONE_SAFARI_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=300) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                received += len(chunk)
                if total and show_progress:
                    print(f"\rDownloading: {received * 100 // total}%", end="", flush=True)
        if total and show_progress:
            print()
        partial.replace(destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise


def next_available_output(path: Path) -> Path:
    """Return path, or path_1/path_2/... when the requested name already exists."""
    if not path.exists() and not path.with_suffix(path.suffix + ".part").exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        partial = candidate.with_suffix(candidate.suffix + ".part")
        if not candidate.exists() and not partial.exists():
            return candidate
        counter += 1


def run_ffmpeg(arguments: list[str], action: str) -> None:
    try:
        completed = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-nostats", "-nostdin", *arguments,
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "FFmpeg is required for video assembly/chaining but was not found in a-Shell Mini."
        ) from error
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "unknown FFmpeg error"
        raise RuntimeError(f"FFmpeg failed while {action}: {details}")


def probe_and_report_video_timing(video: Path, parameters: dict, label: str = "") -> None:
    """Decode one generated segment and compare its real timing with the request.

    This intentionally uses ffmpeg rather than ffprobe because a-Shell Mini may
    provide ffmpeg without installing a separate ffprobe executable. FFmpeg's
    machine-readable progress output gives the decoded frame count and final
    presentation timestamp. A failed diagnostic never invalidates a video that
    downloaded successfully.
    """
    requested_frames = int(parameters["numFrames"])
    requested_fps = float(parameters["fps"])
    requested_duration = requested_frames / requested_fps
    prefix = f"{label} " if label else ""

    try:
        completed = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(video), "-map", "0:v:0", "-an",
                "-progress", "pipe:1", "-nostats", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print(f"{prefix}Timing probe skipped: ffmpeg was not found.")
        return

    if completed.returncode != 0:
        details = completed.stderr.strip() or "unknown FFmpeg error"
        print(f"{prefix}Timing probe failed: {details}")
        return

    # Some a-Shell FFmpeg builds do not emit one clean key=value pair per line.
    # They may collapse the final status into a line such as:
    #   frame= 189 fps=0.0 ... time=00:00:06.30 ...
    # Parse only anchored numeric fields instead of treating everything after the
    # first equals sign as the value. Include stderr as a fallback because normal
    # FFmpeg status output is written there.
    diagnostic_text = completed.stdout + "\n" + completed.stderr

    frame_matches = re.findall(r"(?:^|[\r\n])frame\s*=\s*(\d+)", diagnostic_text)
    if not frame_matches:
        frame_matches = re.findall(r"\bframe\s*=\s*(\d+)", diagnostic_text)

    duration_matches = re.findall(
        r"(?:^|[\r\n])out_time_us\s*=\s*(\d+)", diagnostic_text
    )
    duration_scale = 1_000_000
    if not duration_matches:
        duration_matches = re.findall(
            r"(?:^|[\r\n])out_time_ms\s*=\s*(\d+)", diagnostic_text
        )
    if duration_matches:
        actual_duration = int(duration_matches[-1]) / duration_scale
    else:
        time_matches = re.findall(
            r"(?:out_time|time)\s*=\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
            diagnostic_text,
        )
        if not time_matches:
            print(f"{prefix}Timing probe returned incomplete data: no duration found")
            return
        hours, minutes, seconds = time_matches[-1]
        actual_duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    if not frame_matches:
        print(f"{prefix}Timing probe returned incomplete data: no frame count found")
        return

    actual_frames = int(frame_matches[-1])
    if actual_duration <= 0:
        print(f"{prefix}Timing probe returned incomplete data: non-positive duration")
        return
    actual_fps = actual_frames / actual_duration

    print(
        f"{prefix}Requested: {requested_frames} frames at {requested_fps:g} FPS "
        f"= {requested_duration:.2f} s"
    )
    print(
        f"{prefix}Received: {actual_frames} frames at {actual_fps:.2f} FPS "
        f"= {actual_duration:.2f} s"
    )
    frame_delta = actual_frames - requested_frames
    duration_delta = actual_duration - requested_duration
    if abs(frame_delta) <= 1 and abs(duration_delta) > 0.10:
        print(
            f"{prefix}Diagnosis: the server kept approximately the requested frame "
            "count but changed the playback frame rate/duration."
        )
    elif abs(frame_delta) > 1 and abs(actual_fps - requested_fps) <= 0.25:
        print(
            f"{prefix}Diagnosis: the server kept approximately the requested FPS "
            "but changed or capped the generated frame count."
        )
    elif abs(duration_delta) > 0.10:
        print(
            f"{prefix}Diagnosis: the returned timing differs from the request "
            "in both frame count and/or playback rate."
        )


def extract_last_frame(video: Path, image: Path) -> None:
    print(f"Extracting final frame from {video.name}…")
    run_ffmpeg(
        [
            "-y", "-i", str(video), "-map", "0:v:0", "-an",
            "-fps_mode", "passthrough", "-update", "1", str(image),
        ],
        "extracting the final frame",
    )
    if not image.is_file() or image.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg did not create the transition image: {image}")


def quote_concat_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


def combine_segments(
    segments: list[Path],
    output: Path,
    temporary_directory: Path,
    output_fps: int,
) -> None:
    concat_file = temporary_directory / "segments.txt"
    concat_file.write_text(
        "".join(f"file '{quote_concat_path(segment)}'\n" for segment in segments),
        encoding="utf-8",
    )
    temporary_output = temporary_directory / "combined.mp4"
    print(f"Combining {len(segments)} segments into {output.name}…")
    run_ffmpeg(
        [
            "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            # These are the concat-safe MP4 settings proven by the user's
            # a-Shell FFmpeg 7 scripts. No media is re-encoded.
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-video_track_timescale", str(output_fps * 1000),
            "-movflags", "+faststart",
            "-f", "mp4", str(temporary_output),
        ],
        "combining the generated segments",
    )
    temporary_output.replace(output)


def probe_frame_size(video: Path, temporary_directory: Path) -> tuple:
    """Read a generated segment's pixel dimensions via a single-frame extraction,
    since no Pillow/ffprobe dependency is available on a-Shell."""
    frame = temporary_directory / f"{video.stem}_probe.png"
    run_ffmpeg(
        ["-y", "-i", str(video), "-map", "0:v:0", "-frames:v", "1", str(frame)],
        "probing video dimensions",
    )
    if not frame.is_file() or frame.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg could not read a frame from: {video}")
    return image_dimensions(frame)


LEAD_IN_ENCODER_ATTEMPTS = [
    ("libx264", ["-c:v", "libx264"]),
    ("h264_videotoolbox", ["-c:v", "h264_videotoolbox"]),  # iOS hardware encoder
    ("mpeg4", ["-c:v", "mpeg4"]),  # always-available software fallback
]


def prepare_lead_in_clip(
    source_video: Path,
    reference_segment: Path,
    output_fps: int,
    temporary_directory: Path,
) -> Path:
    """Re-encode the user's original video to the generated segment's exact frame
    size and fps so it can be joined ahead of the AI-continued footage. Cached
    alongside the source video and regenerated only if the source changes or a
    different resolution/fps is requested. Audio is dropped: the generated
    segments carry none, so keeping the source's track would desync at the join."""
    width, height = probe_frame_size(reference_segment, temporary_directory)
    lead_in = source_video.with_name(
        f"{source_video.stem}_leadin_{width}x{height}_{output_fps}fps.mp4"
    )
    if (
        lead_in.is_file()
        and lead_in.stat().st_size > 0
        and lead_in.stat().st_mtime >= source_video.stat().st_mtime
    ):
        print(f"Reusing cached lead-in clip: {lead_in.name}")
        return lead_in
    print(
        f"Re-encoding {source_video.name} to {width}x{height}@{output_fps}fps "
        "for a seamless join…"
    )
    temporary_output = temporary_directory / "leadin.mp4"
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={output_fps},setsar=1"
    )
    # A ~0.08 bit/pixel target is a common good-quality H.264 rule of thumb.
    # -b:v is a generic per-stream option understood by every encoder below,
    # unlike -preset/-crf which are libx264-private and fail with "Unrecognized
    # option" on FFmpeg builds (common on iOS) that don't expose that encoder.
    bitrate = max(1_500_000, min(12_000_000, int(width * height * output_fps * 0.08)))
    last_error = None
    for name, codec_args in LEAD_IN_ENCODER_ATTEMPTS:
        try:
            run_ffmpeg(
                [
                    "-y", "-i", str(source_video),
                    "-map", "0:v:0", "-an",
                    "-vf", scale_filter,
                    *codec_args, "-pix_fmt", "yuv420p", "-b:v", str(bitrate),
                    "-movflags", "+faststart",
                    str(temporary_output),
                ],
                f"re-encoding the source video with {name}",
            )
            last_error = None
            break
        except RuntimeError as error:
            last_error = error
            print(f"  {name} encoder unavailable ({error}); trying the next option…")
    if last_error is not None:
        raise RuntimeError(
            f"Could not re-encode {source_video.name} with any available H.264 "
            f"encoder: {last_error}"
        )
    temporary_output.replace(lead_in)
    return lead_in
    temporary_output.replace(lead_in)
    return lead_in


def resolve_state_file(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = SCRIPT_DIRECTORY / path
    return path.resolve()


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", "utf-8")
    temporary.replace(path)


def load_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read recovery state {path}: {error}") from error
    mode = state.get("mode", "chain")
    required = {
        "version", "createdAt", "originalPhoto", "finalOutput", "segments", "parameters",
    }
    if mode == "parallel":
        required.add("jobs")
    else:
        required.update({"prompts", "currentIndex", "taskId", "combineChain"})
    missing = required.difference(state)
    if state.get("version") != 1 or missing:
        raise RuntimeError(
            f"Unsupported or incomplete recovery state {path.name}; missing: {sorted(missing)}"
        )
    if mode == "parallel":
        jobs = state.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise RuntimeError(f"Recovery state {path.name} has no parallel jobs")
        if len(state["segments"]) != len(jobs):
            raise RuntimeError(f"Recovery state {path.name} has inconsistent parallel jobs")
    else:
        state.setdefault("mode", "chain")
        if not isinstance(state["prompts"], list) or not state["prompts"]:
            raise RuntimeError(f"Recovery state {path.name} has no prompts")
        if len(state["segments"]) != len(state["prompts"]):
            raise RuntimeError(f"Recovery state {path.name} has inconsistent segment data")
        if not 0 <= int(state["currentIndex"]) <= len(state["prompts"]):
            raise RuntimeError(f"Recovery state {path.name} has an invalid chain position")
    return state


def generation_parameters(args) -> dict:
    return {
        "resolution": args.resolution,
        "performance": args.performance,
        "fps": args.fps,
        "numFrames": args.frames,
        "applyOptimizations": args.optimizations,
        "applyInterpolation": args.interpolation,
        "interpolationFps": args.interpolation_fps,
        "seed": args.seed,
        "loras": args.loras,
        "isFast": args.fast,
        "batchId": args.batch_id,
    }


def effective_output_fps(parameters: dict) -> int:
    """Return the actual generated frame rate used for MP4 timebase normalization."""
    if parameters.get("applyInterpolation"):
        return int(parameters["interpolationFps"])
    return int(parameters["fps"])


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "y", "1", "on"}:
        return True
    if normalized in {"false", "no", "n", "0", "off"}:
        return False
    raise RuntimeError(f"{key} must be true or false, not {value!r}")


def parse_int(value: str, key: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise RuntimeError(f"{key} must be an integer, not {value!r}") from error
    if not minimum <= number <= maximum:
        raise RuntimeError(f"{key} must be between {minimum} and {maximum}")
    return number


def parse_float(value: str, key: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise RuntimeError(f"{key} must be a number, not {value!r}") from error
    if not minimum <= number <= maximum:
        raise RuntimeError(f"{key} must be between {minimum} and {maximum}")
    return number


def parse_lora(value: str) -> dict:
    model_name, separator, raw_weight = value.partition("|")
    model_name = model_name.strip()
    if not model_name:
        raise RuntimeError("Each lora entry needs a model filename")
    weight = parse_float(raw_weight, "LoRA weight", -2, 2) if separator else 0.0
    return {"modelName": model_name, "weight": weight}


def load_settings(path: Path) -> dict:
    if not path.is_file():
        if path != SETTINGS_FILE:
            raise RuntimeError(f"Settings file not found: {path}")
        return {}

    allowed = {
        "photo", "prompt", "output", "resolution", "performance", "fps",
        "numFrames", "seed", "isFast", "applyOptimizations",
        "applyInterpolation", "interpolationFps", "lora", "pollIntervalSeconds",
        "overwriteExisting", "chainPrompt", "combineChain",
        "resumeInterruptedTasks", "stateFile",
        "suspensionWarningSeconds",
        "parallelChunks", "maxParallelTasks", "assembleParallelChunks",
        "incrementSeedPerChunk",
        "generationMode", "combineVideos", "incrementSeedPerTask",
        "batchId", "cancelOnInterrupt", "promoteToFastAfterSeconds",
        "unknownStatusLimit", "validateLoras",
        "autoCropPhotos", "autoCropMaxDifference",
        "includeSourceVideo",
        "experimentalLoopCount",
    }
    values = {"lora": [], "prompt": [], "chainPrompt": []}
    for line_number, raw_line in enumerate(path.read_text("utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or key not in allowed:
            raise RuntimeError(f"Invalid setting on line {line_number}: {raw_line}")
        if key in {"lora", "prompt", "chainPrompt"}:
            if value:
                values[key].append(parse_lora(value) if key == "lora" else value)
        else:
            values[key] = value

    print(f"Using settings from {path.name}")
    return values


def parse_args():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--settings", default=str(SETTINGS_FILE))
    preliminary, _ = pre_parser.parse_known_args()
    settings_path = Path(preliminary.settings).expanduser().resolve()
    settings = load_settings(settings_path)

    resolution = settings.get("resolution") or "720p"
    performance = settings.get("performance") or "quality"
    if resolution not in {"480p", "720p"}:
        raise RuntimeError("resolution must be 480p or 720p")
    if performance not in {"speed", "quality", "express"}:
        raise RuntimeError("performance must be speed, quality, or express")

    legacy_parallel_chunks = parse_int(
        settings.get("parallelChunks", "1"), "parallelChunks", 1, 20
    )
    generation_mode = settings.get("generationMode")
    if generation_mode is None:
        generation_mode = "parallel" if legacy_parallel_chunks > 1 else "chain"
    generation_mode = generation_mode.lower()
    if generation_mode not in {"chain", "parallel"}:
        raise RuntimeError("generationMode must be chain or parallel")

    if settings.get("combineVideos") is not None:
        combine_videos = parse_bool(settings["combineVideos"], "combineVideos")
    elif generation_mode == "parallel":
        combine_videos = parse_bool(
            settings.get("assembleParallelChunks", "true"), "assembleParallelChunks"
        )
    else:
        combine_videos = parse_bool(settings.get("combineChain", "true"), "combineChain")

    fps = parse_int(settings.get("fps", "16"), "fps", 8, 16)
    # The OpenAPI spec advertises numFrames up to 160, but the backend rejects
    # anything above 128. Keep both limits below in sync with reality, not the spec.
    frames = parse_int(settings.get("numFrames", "80"), "numFrames", 24, 128)
    interpolation_fps = parse_int(
        settings.get("interpolationFps", "24"), "interpolationFps", 24, 60
    )
    if interpolation_fps not in {24, 25, 30, 50, 60}:
        raise RuntimeError("interpolationFps must be 24, 25, 30, 50, or 60")

    parser = argparse.ArgumentParser(
        description="Turn a photo into a video using the ArtWorks API."
    )
    parser.add_argument(
        "--settings",
        default=str(settings_path),
        help="settings file (default: artworks_settings.txt beside the script)",
    )
    parser.add_argument(
        "photo",
        nargs="?",
        default=settings.get("photo") or None,
        help="input image or video path; if a video, its final frame becomes the "
             "starting frame and the original can be prepended to the result; "
             "if omitted, choose a file from the current folder",
    )
    parser.add_argument(
        "--prompt", action="append", default=None, metavar="PROMPT",
        help="motion prompt; repeat to create several sequential or parallel tasks",
    )
    parser.add_argument("--output", default=settings.get("output") or None, help="output MP4 path")
    parser.add_argument("--resolution", choices=("480p", "720p"), default=resolution)
    parser.add_argument("--performance", choices=("speed", "quality", "express"), default=performance)
    parser.add_argument("--fps", type=int, choices=range(8, 17), default=fps, metavar="8-16")
    # range() is exclusive at the top, so 129 permits 128. See the note above.
    parser.add_argument("--frames", type=int, choices=range(24, 129), default=frames, metavar="24-128")
    parser.add_argument(
        "--seed",
        type=int,
        default=int(settings["seed"]) if settings.get("seed") else None,
    )
    parser.add_argument(
        "--fast", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("isFast", "false"), "isFast"),
        help="use the faster, higher-cost queue",
    )
    parser.add_argument(
        "--optimizations", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("applyOptimizations", "true"), "applyOptimizations"),
    )
    parser.add_argument(
        "--interpolation", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("applyInterpolation", "false"), "applyInterpolation"),
    )
    parser.add_argument(
        "--interpolate", dest="interpolation_fps", type=int,
        choices=(24, 25, 30, 50, 60), default=interpolation_fps, metavar="FPS",
    )
    parser.add_argument(
        "--lora", action="append", default=None, metavar="MODEL|WEIGHT",
        help="LoRA filename and optional weight; repeat for multiple LoRAs",
    )
    parser.add_argument(
        "--poll-interval", type=float,
        default=parse_float(settings.get("pollIntervalSeconds", "2"), "pollIntervalSeconds", 0.5, 60),
        metavar="SECONDS",
    )
    parser.add_argument(
        "--overwrite", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("overwriteExisting", "false"), "overwriteExisting"),
        help="replace an existing output instead of adding _1, _2, ...",
    )
    parser.add_argument(
        "--chain-prompt", action="append", default=None, metavar="PROMPT",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--combine-chain", action=argparse.BooleanOptionalAction,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--mode", dest="generation_mode", choices=("chain", "parallel"),
        default=generation_mode,
        help="chain uses each preceding final frame; parallel starts every task from the original photo",
    )
    parser.add_argument(
        "--combine-videos", action=argparse.BooleanOptionalAction,
        default=combine_videos,
        help="assemble all completed task videos in prompt order",
    )
    parser.add_argument(
        "--resume-interrupted", action=argparse.BooleanOptionalAction,
        default=parse_bool(
            settings.get("resumeInterruptedTasks", "true"), "resumeInterruptedTasks"
        ),
        help="save task state and resume it after a-Shell is suspended or terminated",
    )
    parser.add_argument(
        "--state-file",
        default=settings.get("stateFile") or "artworks_tasks.json",
        help="persistent recovery file, relative to the script folder by default",
    )
    parser.add_argument(
        "--autocrop-photos", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("autoCropPhotos", "true"), "autoCropPhotos"),
        help="centre-crop source photos to a shared aspect ratio so chunks can be joined",
    )
    parser.add_argument(
        "--autocrop-max-difference",
        type=float,
        default=parse_float(
            settings.get("autoCropMaxDifference", "0.2"), "autoCropMaxDifference", 0, 1
        ),
        metavar="FRACTION",
        help="refuse to auto-crop when aspect ratios differ by more than this",
    )
    parser.add_argument(
        "--batch-id",
        default=settings.get("batchId", "auto") or "auto",
        metavar="ID",
        help="shared batch priority for every task in this run; 'auto' generates one, "
             "'off' omits it",
    )
    parser.add_argument(
        "--cancel-on-interrupt", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("cancelOnInterrupt", "true"), "cancelOnInterrupt"),
        help="cancel still-queued tasks when the script is interrupted",
    )
    parser.add_argument(
        "--promote-to-fast",
        type=float,
        default=parse_float(
            settings.get("promoteToFastAfterSeconds", "0"),
            "promoteToFastAfterSeconds", 0, 86400,
        ),
        metavar="SECONDS",
        help="move a task to the fast queue after this long pending; 0 disables it",
    )
    parser.add_argument(
        "--unknown-status-limit",
        type=int,
        default=parse_int(
            settings.get("unknownStatusLimit", "5"), "unknownStatusLimit", 0, 1000
        ),
        metavar="POLLS",
        help="fail after this many consecutive unknown statuses; 0 waits forever",
    )
    parser.add_argument(
        "--validate-loras", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("validateLoras", "true"), "validateLoras"),
        help="check LoRA filenames against /api/v3/resources before submitting",
    )
    parser.add_argument(
        "--list-loras", nargs="?", const="", default=None, metavar="SEARCH",
        help="print available LoRA filenames from /api/v3/resources and exit; "
             "optionally filter by a search term (3+ characters)",
    )
    parser.add_argument(
        "--include-source-video", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("includeSourceVideo", "true"), "includeSourceVideo"),
        help="when the input is a video, prepend it (re-encoded to match) to the "
             "combined output ahead of the AI-continued footage",
    )
    parser.add_argument(
        "--experimental-loop",
        type=lambda value: parse_int(value, "experimentalLoopCount", 0, 50),
        default=parse_int(settings.get("experimentalLoopCount", "0"), "experimentalLoopCount", 0, 50),
        metavar="N",
        help="EXPERIMENTAL: select N unique random prompts from randomprompt.txt "
             "for either chain or parallel generation",
    )
    parser.add_argument(
        "--suspension-warning",
        type=float,
        default=parse_float(
            settings.get("suspensionWarningSeconds", "15"),
            "suspensionWarningSeconds", 5, 3600,
        ),
        metavar="SECONDS",
        help="report polling gaps that suggest iOS suspension or a network stall",
    )
    parser.add_argument(
        "--parallel-chunks",
        type=int,
        choices=range(1, 21),
        default=legacy_parallel_chunks,
        metavar="1-20",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-parallel-tasks",
        type=int,
        choices=range(1, 7),
        default=parse_int(
            settings.get("maxParallelTasks", "3"), "maxParallelTasks", 1, 6
        ),
        metavar="1-6",
        help="maximum simultaneous HTTP submissions, polls, and downloads",
    )
    parser.add_argument(
        "--assemble-parallel", action=argparse.BooleanOptionalAction,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--increment-seed-per-task", dest="increment_seed_per_task",
        action=argparse.BooleanOptionalAction,
        default=parse_bool(
            settings.get(
                "incrementSeedPerTask",
                settings.get("incrementSeedPerChunk", "true"),
            ),
            "incrementSeedPerTask",
        ),
        help="in parallel mode, add each task index to a configured seed",
    )
    args = parser.parse_args()
    if any(
        value == "--interpolate" or value.startswith("--interpolate=")
        for value in sys.argv
    ):
        args.interpolation = True
    args.loras = [parse_lora(value) for value in args.lora] if args.lora else settings.get("lora", [])
    prompts = list(args.prompt if args.prompt is not None else settings.get("prompt", []))
    legacy_chain_prompts = (
        args.chain_prompt if args.chain_prompt is not None else settings.get("chainPrompt", [])
    )
    if settings.get("generationMode") is None and args.parallel_chunks > 1:
        if legacy_chain_prompts:
            raise RuntimeError(
                "Legacy parallelChunks cannot be combined with chainPrompt. Use "
                "generationMode=parallel and repeat prompt= for each independent task."
            )
        if len(prompts) == 1:
            prompts *= args.parallel_chunks
    else:
        # Old chainPrompt lines remain valid during migration. The explicit mode
        # now decides whether all prompts are sequential or independent.
        prompts.extend(legacy_chain_prompts)
    if len(prompts) > 20:
        raise RuntimeError(
            "Configure no more than 20 prompt= lines."
        )
    if args.batch_id.strip().lower() in {"off", "none", "false", ""}:
        args.batch_id = None
    elif args.batch_id.strip().lower() == "auto":
        args.batch_id = f"img2video-{uuid.uuid4().hex[:12]}" if len(prompts) > 1 else None
    prompt_photos = []
    prompt_texts = []
    for entry in prompts:
        photo_reference, text = split_prompt_photo(entry)
        prompt_photos.append(photo_reference)
        prompt_texts.append(text)
    if any(prompt_photos) and args.generation_mode != "parallel":
        ignored = ", ".join(name for name in prompt_photos if name)
        print(
            f"Warning: ignoring per-prompt photo(s) ({ignored}); chain mode always "
            "starts each step from the previous step's final frame."
        )
        prompt_photos = [None] * len(prompt_photos)
    args.prompt_photos = prompt_photos
    args.task_prompts = prompt_texts
    args.combine_chain = args.combine_videos if args.combine_chain is None else args.combine_chain
    args.assemble_parallel = (
        args.combine_videos if args.assemble_parallel is None else args.assemble_parallel
    )
    return args


def choose_photo() -> Path:
    candidates = sorted(
        path for path in Path.cwd().iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    )
    if not candidates:
        raise RuntimeError(
            "No JPG, PNG, WebP, HEIC, HEIF image or MP4, MOV, M4V, AVI, MKV video "
            "was found in the current folder."
        )

    print("Choose a photo or video:")
    for index, candidate in enumerate(candidates, 1):
        print(f"  {index}. {candidate.name}")

    while True:
        answer = input(f"Photo/video [1-{len(candidates)}]: ").strip()
        try:
            selected = int(answer)
        except ValueError:
            selected = 0
        if 1 <= selected <= len(candidates):
            return candidates[selected - 1]
        print("Enter one of the numbers shown above.")


def task_request_data(image_data: str, prompt: str, parameters: dict) -> dict:
    payload = {
        "image": image_data,
        "prompt": prompt,
        "resolution": parameters["resolution"],
        "performance": parameters["performance"],
        "fps": parameters["fps"],
        "numFrames": parameters["numFrames"],
        "applyOptimizations": parameters["applyOptimizations"],
        "applyInterpolation": parameters["applyInterpolation"],
    }
    if parameters["applyInterpolation"]:
        payload["interpolationFps"] = parameters["interpolationFps"]
    if parameters.get("seed") is not None:
        payload["seed"] = parameters["seed"]
    if parameters.get("loras"):
        payload["loras"] = parameters["loras"]
    request = {"type": "image-to-video", "isFast": parameters["isFast"], "payload": payload}
    if parameters.get("batchId"):
        # Keeps every task in this run at the priority of the first one, so a late
        # chunk cannot land behind unrelated traffic and stall the assembly.
        request["batchId"] = parameters["batchId"]
    return request


def submit_encoded_task(
    image_data: str, prompt: str, parameters: dict, username: str, password: str
) -> tuple[str, float]:
    created = api_request(
        "POST", "/api/v3/tasks", username, password,
        task_request_data(image_data, prompt, parameters),
    )
    task_id = created.get("id")
    if not task_id:
        raise RuntimeError(f"The API returned no task ID: {created}")
    return task_id, time.time()


def completed_video_url(task: dict) -> str:
    try:
        return task["results"]["data"]["video"]["url"]
    except (KeyError, TypeError) as error:
        raise RuntimeError(f"Completed task has no video URL: {task.get('results')}") from error


def generate_video(
    photo: Path,
    prompt: str,
    output: Path,
    parameters: dict,
    poll_interval: float,
    username: str,
    password: str,
    existing_task_id: str | None = None,
    existing_started_at: float | None = None,
    existing_last_active_at: float | None = None,
    existing_phase_status: str | None = None,
    existing_phase_started_at: float | None = None,
    existing_phase_durations: dict | None = None,
    suspension_warning_seconds: float = 15,
    unknown_status_limit: int = 5,
    promote_to_fast_after: float = 0,
    on_submitted=None,
    on_heartbeat=None,
) -> None:
    task_id = existing_task_id
    started_at = existing_started_at or time.time()
    if task_id:
        print(f"Resuming task: {task_id}")
    else:
        print("Submitting image-to-video task…")
        task_id, started_at = submit_encoded_task(
            encode_image(photo), prompt, parameters, username, password
        )
        print(f"Task: {task_id}")
        if on_submitted is not None:
            on_submitted(task_id, started_at)

    previous_width = 0
    unknown_polls = 0
    promoted = bool(parameters.get("isFast"))
    last_poll_at = existing_last_active_at or started_at
    phase_status = existing_phase_status
    phase_started_at = existing_phase_started_at or started_at
    phase_durations = dict(existing_phase_durations or {})
    while True:
        task = api_request("GET", f"/api/v3/tasks/{task_id}", username, password)
        now = time.time()
        polling_gap = now - last_poll_at
        if polling_gap >= suspension_warning_seconds:
            if previous_width:
                print()
            print(
                f"Execution had no polling activity for {format_elapsed(polling_gap)}; "
                "iOS may have suspended a-Shell or the network request stalled."
            )
            previous_width = 0
        last_poll_at = now
        status = task.get("status", UNKNOWN_STATUS)
        track_task(task_id, status)
        if status == UNKNOWN_STATUS:
            unknown_polls += 1
            if unknown_status_limit and unknown_polls >= unknown_status_limit:
                raise TaskTerminalError(
                    f"Task {task_id} reported an unknown status "
                    f"{unknown_polls} times in a row; giving up."
                )
        else:
            unknown_polls = 0
        position = task.get("position")
        position_text = f" | queue {position}" if status == "pending" and position is not None else ""
        if (
            promote_to_fast_after
            and not promoted
            and status == "pending"
            and now - started_at >= promote_to_fast_after
        ):
            if previous_width:
                print()
                previous_width = 0
            print(
                f"Still queued after {format_elapsed(now - started_at)}; "
                "moving the task to the fast queue."
            )
            promoted = promote_task(task_id, username, password)
        if phase_status != status:
            if phase_status and phase_status not in TERMINAL_STATES:
                phase_elapsed = max(0, now - phase_started_at)
                phase_durations[phase_status] = (
                    float(phase_durations.get(phase_status, 0)) + phase_elapsed
                )
                if previous_width:
                    print()
                print(f"Phase {phase_status}: {format_elapsed(phase_elapsed)}")
                previous_width = 0
            phase_status = None if status in TERMINAL_STATES else status
            phase_started_at = now

        if status in TERMINAL_STATES:
            if previous_width:
                print()
            print(f"Status: {status} | total elapsed {format_elapsed(now - started_at)}")
            previous_width = 0
        else:
            line = (
                f"Status: {status}{position_text} | phase {format_elapsed(now - phase_started_at)}"
                f" | total {format_elapsed(now - started_at)}"
            )
            print(f"\r{line.ljust(previous_width)}", end="", flush=True)
            previous_width = max(previous_width, len(line))
        if on_heartbeat is not None:
            on_heartbeat(
                now, status, phase_status, phase_started_at, phase_durations
            )

        if status in TERMINAL_STATES:
            break
        time.sleep(poll_interval)

    if status != "completed":
        results = task.get("results") or {}
        raise TaskTerminalError(
            f"Task ended with status {status}: {results.get('error') or results}"
        )

    report_results(task)

    video_url = completed_video_url(task)

    print("Generation completed. Downloading video…")
    download(video_url, output)
    print(f"Saved segment: {output}")
    probe_and_report_video_timing(output, parameters)


def build_plan(
    photo: Path,
    prompts: list[str],
    output: Path,
    args,
    source_video: Path | None = None,
    step_parameter_overrides: list[dict] | None = None,
) -> dict:
    if args.generation_mode == "parallel":
        segments = []
        jobs = []
        base_parameters = generation_parameters(args)
        for index, prompt in enumerate(prompts):
            segment = output.with_name(
                f"{output.stem}_chunk{index + 1}{output.suffix}"
            )
            if not args.overwrite:
                segment = next_available_output(segment)
            parameters = dict(base_parameters)
            if step_parameter_overrides and step_parameter_overrides[index]:
                parameters.update(step_parameter_overrides[index])
            elif (
                parameters.get("seed") is not None
                and args.increment_seed_per_task
            ):
                parameters["seed"] += index
            job_photo = photo
            reference = (getattr(args, "prompt_photos", None) or [None] * len(prompts))[index]
            if reference:
                job_photo = Path(reference).expanduser()
                if not job_photo.is_absolute():
                    job_photo = photo.parent / job_photo
                if not job_photo.is_file():
                    raise RuntimeError(
                        f"Prompt {index + 1} refers to a missing photo: {job_photo}"
                    )
            overrides = getattr(args, "photo_overrides", None) or {}
            job_photo = Path(overrides.get(str(job_photo), job_photo))
            segments.append(str(segment))
            jobs.append({
                "index": index,
                "prompt": prompt,
                "photo": str(job_photo),
                "output": str(segment),
                "parameters": parameters,
                "taskId": None,
                "taskStartedAt": None,
                "lastActiveAt": None,
                "lastStatus": None,
                "phaseStatus": None,
                "phaseStartedAt": None,
                "phaseDurations": {},
                "videoUrl": None,
                "downloaded": False,
                "unknownPolls": 0,
                "promoted": False,
            })
        return {
            "version": 1,
            "mode": "parallel",
            "createdAt": time.time(),
            "originalPhoto": str(photo),
            "sourceVideo": str(source_video) if source_video else None,
            "finalOutput": str(output),
            "segments": segments,
            "jobs": jobs,
            "assembleParallel": args.assemble_parallel,
            "parameters": base_parameters,
            "lastActiveAt": None,
            "lastStatus": "planned",
        }

    segments = []
    for index in range(1, len(prompts) + 1):
        if len(prompts) == 1 or (not args.combine_chain and index == 1):
            segment = output
        else:
            segment = output.with_name(f"{output.stem}_part{index}{output.suffix}")
            if not args.overwrite:
                segment = next_available_output(segment)
        segments.append(str(segment))

    return {
        "version": 1,
        "mode": "chain",
        "createdAt": time.time(),
        "originalPhoto": str(photo),
        "sourceVideo": str(source_video) if source_video else None,
        "prompts": prompts,
        "stepParameters": step_parameter_overrides or [None] * len(prompts),
        "finalOutput": str(output),
        "segments": segments,
        "currentIndex": 0,
        "taskId": None,
        "taskStartedAt": None,
        "lastActiveAt": None,
        "lastStatus": None,
        "phaseStatus": None,
        "phaseStartedAt": None,
        "phaseDurations": {},
        "combineChain": args.combine_chain,
        "parameters": generation_parameters(args),
    }


def run_parallel_plan(
    state: dict,
    args,
    username: str,
    password: str,
    state_path: Path | None,
) -> int:
    jobs = sorted(state["jobs"], key=lambda item: int(item["index"]))
    by_index = {int(job["index"]): job for job in jobs}
    original_photo = Path(state["originalPhoto"])
    final_output = Path(state["finalOutput"])
    workers = min(args.max_parallel_tasks, len(jobs))

    # Recover local completion markers first. A completed file never needs another API call.
    for job in jobs:
        output = Path(job["output"])
        if output.is_file() and output.stat().st_size > 0:
            job["downloaded"] = True

    if state.get("assembleParallel", True):
        # Fail before spending API credits rather than after every chunk is generated.
        run_ffmpeg(["-version"], "checking parallel-chunk assembly support")

    unsent = [job for job in jobs if not job.get("downloaded") and not job.get("taskId")]
    if unsent:
        batch_id = state.get("parameters", {}).get("batchId")
        if batch_id:
            print(f"Batch: {batch_id}")
        encoded_photos = {}

        def encoded_for(job: dict) -> str:
            """Base64 each distinct source photo once, however many tasks use it."""
            source = Path(job.get("photo") or original_photo)
            key = str(source)
            if key not in encoded_photos:
                if not source.is_file():
                    raise RuntimeError(f"Photo not found: {source}")
                encoded_photos[key] = encode_image(source)
            return encoded_photos[key]

        for job in unsent:
            encoded_for(job)
        if len(encoded_photos) > 1:
            print(f"Using {len(encoded_photos)} distinct source photo(s).")
        print(f"Submitting {len(unsent)} chunk task(s) with up to {workers} parallel requests…")
        failures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    submit_encoded_task,
                    encoded_for(job),
                    job["prompt"],
                    job.get("parameters") or state["parameters"],
                    username,
                    password,
                ): job
                for job in unsent
            }
            for future in concurrent.futures.as_completed(futures):
                job = futures[future]
                try:
                    task_id, started_at = future.result()
                except Exception as error:
                    failures.append((int(job["index"]) + 1, error))
                    continue
                job.update({
                    "taskId": task_id,
                    "taskStartedAt": started_at,
                    "lastActiveAt": started_at,
                    "lastStatus": "submitted",
                    "phaseStatus": None,
                    "phaseStartedAt": started_at,
                    "phaseDurations": {},
                })
                state["lastActiveAt"] = started_at
                state["lastStatus"] = "submitted"
                if state_path is not None:
                    save_state(state_path, state)
                print(f"Chunk {int(job['index']) + 1}: task {task_id}")
        if failures:
            details = "; ".join(f"chunk {number}: {error}" for number, error in failures)
            raise RuntimeError(f"Some parallel submissions failed; saved successful task IDs. {details}")

    # Downloads run in a pool of their own so each chunk lands on disk the moment
    # it completes, instead of waiting for the slowest task in the batch. Peak
    # connections are therefore up to 2x maxParallelTasks: polls plus downloads.
    download_executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    download_futures: dict = {}

    def start_ready_downloads() -> None:
        for job in jobs:
            index = int(job["index"])
            if job.get("downloaded") or not job.get("videoUrl") or index in download_futures:
                continue
            print(f"Chunk {index + 1}: downloading…")
            download_futures[index] = download_executor.submit(
                download, job["videoUrl"], Path(job["output"]), False
            )

    def reap_downloads(wait: bool) -> bool:
        """Mark finished downloads. Returns True when any job changed."""
        changed = False
        for index, future in list(download_futures.items()):
            if not wait and not future.done():
                continue
            try:
                future.result()
            except Exception as error:
                raise RuntimeError(f"Chunk {index + 1} download failed: {error}") from error
            finally:
                download_futures.pop(index, None)
            job = by_index[index]
            job["downloaded"] = True
            job["lastStatus"] = "downloaded"
            changed = True
            print(f"Saved chunk {index + 1}: {job['output']}")
            probe_and_report_video_timing(
                Path(job["output"]), job["parameters"], f"Chunk {index + 1}:"
            )
        return changed

    try:
        # A resumed run may already hold URLs for chunks that were never fetched.
        start_ready_downloads()

        active = [job for job in jobs if not job.get("downloaded") and not job.get("videoUrl")]
        last_saved_at = time.time()
        while active:
            poll_started = time.time()
            previous_poll = state.get("lastActiveAt")
            if previous_poll and poll_started - float(previous_poll) >= args.suspension_warning:
                print(
                    f"Execution had no polling activity for "
                    f"{format_elapsed(poll_started - float(previous_poll))}; iOS may have "
                    "suspended a-Shell or the network request stalled."
                )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(workers, len(active))
            ) as executor:
                futures = {
                    executor.submit(
                        api_request, "GET", f"/api/v3/tasks/{job['taskId']}",
                        username, password,
                    ): job
                    for job in active
                }
                poll_results = []
                poll_failures = []
                for future in concurrent.futures.as_completed(futures):
                    job = futures[future]
                    try:
                        poll_results.append((job, future.result()))
                    except Exception as error:
                        # One flaky poll must not abandon the other running tasks.
                        poll_failures.append((int(job["index"]) + 1, error))

            for number, error in poll_failures:
                print(f"Chunk {number}: status check failed ({error}); retrying next cycle.")

            now = time.time()
            terminal_errors = []
            counts = {}
            for job, task in poll_results:
                status = task.get("status", UNKNOWN_STATUS)
                number = int(job["index"]) + 1
                track_task(job["taskId"], status)
                counts[status] = counts.get(status, 0) + 1
                if status == UNKNOWN_STATUS:
                    job["unknownPolls"] = int(job.get("unknownPolls") or 0) + 1
                    if (
                        args.unknown_status_limit
                        and job["unknownPolls"] >= args.unknown_status_limit
                    ):
                        terminal_errors.append((
                            number, UNKNOWN_STATUS,
                            f"unknown status {job['unknownPolls']} polls in a row",
                        ))
                else:
                    job["unknownPolls"] = 0
                if (
                    args.promote_to_fast
                    and status == "pending"
                    and not job.get("promoted")
                    and not (job.get("parameters") or {}).get("isFast")
                    and now - float(job.get("taskStartedAt") or now) >= args.promote_to_fast
                ):
                    print(f"Chunk {number} still queued; moving it to the fast queue.")
                    job["promoted"] = promote_task(job["taskId"], username, password)
                old_phase = job.get("phaseStatus")
                phase_started = float(job.get("phaseStartedAt") or job.get("taskStartedAt") or now)
                if old_phase != status:
                    if old_phase and old_phase not in TERMINAL_STATES:
                        elapsed = max(0, now - phase_started)
                        durations = dict(job.get("phaseDurations") or {})
                        durations[old_phase] = float(durations.get(old_phase, 0)) + elapsed
                        job["phaseDurations"] = durations
                        print(
                            f"Chunk {int(job['index']) + 1} phase {old_phase}: "
                            f"{format_elapsed(elapsed)}"
                        )
                    job["phaseStatus"] = None if status in TERMINAL_STATES else status
                    job["phaseStartedAt"] = now
                job["lastActiveAt"] = now
                job["lastStatus"] = status

                if status == "completed":
                    job["videoUrl"] = completed_video_url(task)
                    total = now - float(job.get("taskStartedAt") or now)
                    print(f"Chunk {number} completed in {format_elapsed(total)}")
                    report_results(task, f"Chunk {number}:")
                elif status in TERMINAL_STATES:
                    results = task.get("results") or {}
                    terminal_errors.append(
                        (int(job["index"]) + 1, status, results.get("error") or results)
                    )
                    # An intentional rerun can submit only this failed chunk again.
                    job["taskId"] = None
                    job["taskStartedAt"] = None
                    job["phaseStatus"] = None

            # Fetch newly completed chunks now; do not wait for the whole batch.
            start_ready_downloads()
            saved_any = reap_downloads(False)

            state["lastActiveAt"] = now
            state["lastStatus"] = ", ".join(
                f"{name}:{count}" for name, count in sorted(counts.items())
            )
            if state_path is not None and (
                terminal_errors or saved_any or now - last_saved_at >= 15 or any(
                    job.get("videoUrl") for job, _ in poll_results
                )
            ):
                save_state(state_path, state)
                last_saved_at = now
            summary = " | ".join(f"{name} {count}" for name, count in sorted(counts.items()))
            downloading = len(download_futures)
            downloading_text = f" | downloading {downloading}" if downloading else ""
            print(
                f"Parallel status: {summary}{downloading_text} | "
                f"elapsed {format_elapsed(now - state.get('createdAt', now))}"
            )
            if terminal_errors:
                number, status, details = terminal_errors[0]
                raise TaskTerminalError(f"Chunk {number} ended with status {status}: {details}")
            active = [
                job for job in jobs
                if not job.get("downloaded") and not job.get("videoUrl")
            ]
            if active:
                elapsed_poll = time.time() - poll_started
                time.sleep(max(0, args.poll_interval - elapsed_poll))

        if download_futures:
            print(f"Waiting for {len(download_futures)} remaining download(s)…")
        if reap_downloads(True) and state_path is not None:
            state["lastActiveAt"] = time.time()
            save_state(state_path, state)
    finally:
        download_executor.shutdown(wait=False, cancel_futures=True)

    segments = [Path(job["output"]) for job in jobs]
    if state.get("assembleParallel", True):
        with tempfile.TemporaryDirectory(
            prefix=".img2video_parallel_", dir=final_output.parent
        ) as temp_name:
            temporary_directory = Path(temp_name)
            combine_targets = list(segments)
            source_video = state.get("sourceVideo")
            if source_video and args.include_source_video:
                lead_in = prepare_lead_in_clip(
                    Path(source_video), segments[0],
                    effective_output_fps(state["parameters"]), temporary_directory,
                )
                combine_targets = [lead_in] + combine_targets
            combine_segments(
                combine_targets,
                final_output,
                temporary_directory,
                effective_output_fps(state["parameters"]),
            )
        print(f"Saved assembled video: {final_output}")
    else:
        print("Saved parallel chunks without assembly.")

    if state_path is not None and state_path.exists():
        state_path.unlink()
        print(f"Recovery state cleared: {state_path.name}")
    return 0


def run_plan(
    state: dict,
    args,
    username: str,
    password: str,
    state_path: Path | None,
) -> int:
    if state.get("mode", "chain") == "parallel":
        return run_parallel_plan(state, args, username, password, state_path)

    prompts = state["prompts"]
    segments = [Path(value) for value in state["segments"]]
    final_output = Path(state["finalOutput"])
    original_photo = Path(state["originalPhoto"])
    parameters = state["parameters"]
    step_overrides = state.get("stepParameters") or [None] * len(prompts)

    if len(prompts) > 1:
        # Fail before spending more API credits if FFmpeg cannot run.
        run_ffmpeg(["-version"], "checking chained-prompt support")

    with tempfile.TemporaryDirectory(
        prefix=".img2video_chain_", dir=final_output.parent
    ) as temp_name:
        temporary_directory = Path(temp_name)

        while int(state["currentIndex"]) < len(prompts):
            index = int(state["currentIndex"])
            task_id = state.get("taskId")
            step_prompt = prompts[index]
            segment = segments[index]

            print(f"\nChain step {index + 1}/{len(prompts)}" if len(prompts) > 1 else "")
            if len(prompts) > 1:
                print(f"Prompt: {step_prompt}")

            if task_id:
                # The image is no longer needed once the remote task exists.
                current_photo = original_photo
            elif index == 0:
                current_photo = original_photo
                if not current_photo.is_file():
                    raise RuntimeError(f"Original photo not found: {current_photo}")
            else:
                previous_segment = segments[index - 1]
                if not previous_segment.is_file():
                    raise RuntimeError(
                        f"Cannot resume chain; previous segment is missing: {previous_segment}"
                    )
                current_photo = temporary_directory / f"last_frame_{index}.png"
                extract_last_frame(previous_segment, current_photo)

            def remember_submission(new_task_id: str, started_at: float) -> None:
                state["taskId"] = new_task_id
                state["taskStartedAt"] = started_at
                state["lastActiveAt"] = started_at
                state["lastStatus"] = "submitted"
                state["phaseStatus"] = None
                state["phaseStartedAt"] = started_at
                state["phaseDurations"] = {}
                if state_path is not None:
                    save_state(state_path, state)

            last_persisted_heartbeat = [float(state.get("lastActiveAt") or 0)]

            def remember_heartbeat(
                active_at: float,
                status: str,
                phase_status: str | None,
                phase_started_at: float,
                phase_durations: dict,
            ) -> None:
                state["lastActiveAt"] = active_at
                state["lastStatus"] = status
                state["phaseStatus"] = phase_status
                state["phaseStartedAt"] = phase_started_at
                state["phaseDurations"] = phase_durations
                if (
                    state_path is not None
                    and (
                        active_at - last_persisted_heartbeat[0] >= 15
                        or status in TERMINAL_STATES
                    )
                ):
                    save_state(state_path, state)
                    last_persisted_heartbeat[0] = active_at

            step_parameters = parameters
            if step_overrides[index]:
                step_parameters = {**parameters, **step_overrides[index]}

            try:
                generate_video(
                    current_photo,
                    step_prompt,
                    segment,
                    step_parameters,
                    args.poll_interval,
                    username,
                    password,
                    existing_task_id=task_id,
                    existing_started_at=state.get("taskStartedAt"),
                    existing_last_active_at=state.get("lastActiveAt"),
                    existing_phase_status=state.get("phaseStatus"),
                    existing_phase_started_at=state.get("phaseStartedAt"),
                    existing_phase_durations=state.get("phaseDurations"),
                    suspension_warning_seconds=args.suspension_warning,
                    unknown_status_limit=args.unknown_status_limit,
                    promote_to_fast_after=args.promote_to_fast,
                    on_submitted=remember_submission,
                    on_heartbeat=remember_heartbeat,
                )
            except TaskTerminalError:
                # A retry should create a fresh task rather than polling a permanently failed one.
                state["taskId"] = None
                state["taskStartedAt"] = None
                if state_path is not None:
                    save_state(state_path, state)
                raise

            state["currentIndex"] = index + 1
            state["taskId"] = None
            state["taskStartedAt"] = None
            state["lastActiveAt"] = time.time()
            state["lastStatus"] = "segment_downloaded"
            state["phaseStatus"] = None
            state["phaseStartedAt"] = None
            state["phaseDurations"] = {}
            if state_path is not None:
                save_state(state_path, state)

        source_video = state.get("sourceVideo")
        combine_targets = list(segments)
        if state["combineChain"] and source_video and args.include_source_video:
            lead_in = prepare_lead_in_clip(
                Path(source_video), segments[0],
                effective_output_fps(parameters), temporary_directory,
            )
            combine_targets = [lead_in] + combine_targets

        if state["combineChain"] and len(combine_targets) > 1:
            combine_segments(
                combine_targets,
                final_output,
                temporary_directory,
                effective_output_fps(parameters),
            )
            print(f"Saved combined video: {final_output}")
        elif len(segments) == 1:
            print(f"Saved: {segments[0]}")
        else:
            print("Saved chained segments:")
            for segment in segments:
                print(f"  {segment}")

    if state_path is not None and state_path.exists():
        state_path.unlink()
        print(f"Recovery state cleared: {state_path.name}")
    return 0


def main() -> int:
    print(f"Script: {Path(__file__).resolve()} | build: {SCRIPT_BUILD}")
    args = parse_args()

    if args.list_loras is not None:
        username, password = load_credentials()
        available = list_resources("LORA", username, password, args.list_loras)
        if not available:
            print("No LoRAs found." + (f" (filter: {args.list_loras})" if args.list_loras else ""))
            return 0
        print(f"Available LoRAs ({len(available)}):")
        for entry in available:
            name = entry.get("fileName") or entry.get("fullFileName") or "?"
            print(f"  {name}")
        return 0

    state_path = resolve_state_file(args.state_file) if args.resume_interrupted else None

    if state_path is not None and state_path.is_file():
        state = load_state(state_path)

        # A saved but untouched experimental plan must not silently replay an old
        # prompt order. Discard it and build a fresh random plan. Once any task has
        # started, preserve it so interrupted work can still resume safely.
        if args.experimental_loop:
            if state.get("mode") == "parallel":
                experimental_started = any(
                    job.get("taskId") or job.get("downloaded")
                    for job in state.get("jobs", [])
                )
            else:
                experimental_started = bool(
                    int(state.get("currentIndex", 0))
                    or state.get("taskId")
                )
            if not experimental_started:
                state_path.unlink()
                print(
                    f"Discarded untouched experimental recovery plan: "
                    f"{state_path.name}; generating a fresh random order."
                )
                state = None

        if state is not None:
            if state.get("mode") == "parallel":
                finished = sum(bool(job.get("downloaded")) for job in state["jobs"])
                submitted = sum(bool(job.get("taskId")) for job in state["jobs"])
                print(
                    f"Resuming interrupted parallel generation from {state_path.name}: "
                    f"{finished}/{len(state['jobs'])} downloaded, {submitted} task ID(s) saved"
                )
            else:
                completed = int(state["currentIndex"])
                task_note = f", task {state['taskId']}" if state.get("taskId") else ""
                print(
                    f"Resuming interrupted generation from {state_path.name}: "
                    f"step {min(completed + 1, len(state['prompts']))}/{len(state['prompts'])}{task_note}"
                )
            last_active_at = state.get("lastActiveAt") or state.get("taskStartedAt")
            if last_active_at:
                inactive_for = time.time() - float(last_active_at)
                if inactive_for >= args.suspension_warning:
                    print(
                        f"Previous execution stopped updating for approximately "
                        f"{format_elapsed(inactive_for)} (last status: {state.get('lastStatus') or 'unknown'})."
                    )
            username, password = load_credentials()
            try:
                return run_plan(state, args, username, password, state_path)
            except KeyboardInterrupt:
                if args.cancel_on_interrupt:
                    cancel_tracked_tasks(username, password)
                raise

    photo = Path(args.photo).expanduser().resolve() if args.photo else choose_photo().resolve()
    if not photo.is_file():
        print(f"Photo not found: {photo}", file=sys.stderr)
        return 2

    source_video = None
    if photo.suffix.lower() in VIDEO_EXTENSIONS:
        source_video = photo
        frame = source_video.with_name(source_video.stem + "_lastframe.jpg")
        if not frame.is_file() or frame.stat().st_mtime < source_video.stat().st_mtime:
            extract_last_frame(source_video, frame)
        else:
            print(f"Reusing cached final frame: {frame.name}")
        photo = frame

    prompts = list(args.task_prompts)
    step_parameter_overrides = None
    if args.experimental_loop:
        if not RANDOM_PROMPTS_FILE.is_file():
            raise RuntimeError(
                f"experimentalLoopCount requires {RANDOM_PROMPTS_FILE.name} "
                f"next to the script: {RANDOM_PROMPTS_FILE}"
            )
        available_prompts = list(dict.fromkeys(
            line.strip()
            for line in RANDOM_PROMPTS_FILE.read_text("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ))
        if args.experimental_loop > len(available_prompts):
            raise RuntimeError(
                f"experimentalLoopCount={args.experimental_loop}, but "
                f"{RANDOM_PROMPTS_FILE.name} contains only "
                f"{len(available_prompts)} usable unique prompt(s)."
            )
        # Experimental prompt order and task seeds must not depend on seed=.
        # SystemRandom uses OS entropy and therefore produces a fresh order per run.
        # Shuffle the complete pool using OS entropy, then take the requested
        # number. This order is preserved unchanged in build_plan/run_plan.
        prompt_rng = secrets.SystemRandom()
        shuffled_prompts = list(available_prompts)
        prompt_rng.shuffle(shuffled_prompts)
        prompts = shuffled_prompts[:args.experimental_loop]

        # A fresh independent seed is generated for every experimental task.
        used_seeds = set()
        step_parameter_overrides = []
        for _ in prompts:
            task_seed = secrets.randbelow(2**31)
            while task_seed in used_seeds:
                task_seed = secrets.randbelow(2**31)
            used_seeds.add(task_seed)
            step_parameter_overrides.append({"seed": task_seed})
        args.prompt_photos = [None] * len(prompts)
        print(
            f"Experimental loop: selected {len(prompts)} unique random prompt(s) "
            f"from {RANDOM_PROMPTS_FILE.name} in {args.generation_mode} mode."
        )
        print("Random experimental task order:")
        for index, (prompt, override) in enumerate(
            zip(prompts, step_parameter_overrides), start=1
        ):
            print(f"  {index}. seed={override['seed']} | {prompt}")
    elif not prompts:
        interactive_prompt = input("Describe the motion: ").strip()
        if interactive_prompt:
            prompts.append(interactive_prompt)
    if not prompts:
        print("A motion prompt is required.", file=sys.stderr)
        return 2

    username, password = load_credentials()
    if args.validate_loras:
        validate_loras(args.loras, username, password)
    output = (
        Path(args.output).expanduser() if args.output
        else (source_video or photo).with_name((source_video or photo).stem + "_video.mp4")
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not args.overwrite:
        available_output = next_available_output(output)
        if available_output != output:
            print(f"Output already exists; using {available_output.name}")
        output = available_output

    print(
        f"Generation mode: {args.generation_mode} | "
        f"{len(prompts)} prompt task(s)"
    )
    if args.generation_mode == "parallel" and any(getattr(args, "prompt_photos", []) or []):
        job_photos = []
        for reference in args.prompt_photos:
            if not reference:
                job_photos.append(photo)
                continue
            candidate = Path(reference).expanduser()
            job_photos.append(candidate if candidate.is_absolute() else photo.parent / candidate)
        missing = [str(item) for item in job_photos if not item.is_file()]
        if missing:
            print("Photo not found: " + ", ".join(sorted(set(missing))), file=sys.stderr)
            return 1
        distinct = sorted({str(item) for item in job_photos})
        print(f"Source photos: {len(distinct)} distinct image(s) across {len(job_photos)} task(s)")
        args.photo_overrides = align_photo_geometry(
            [Path(item) for item in distinct],
            args.assemble_parallel,
            args.autocrop_photos,
            args.autocrop_max_difference,
        )
        photo = Path(args.photo_overrides.get(str(photo), photo))
    state = build_plan(
        photo, prompts, output, args,
        source_video=source_video,
        step_parameter_overrides=step_parameter_overrides,
    )
    if state_path is not None:
        save_state(state_path, state)
        print(f"Recovery enabled: {state_path.name}")
    try:
        return run_plan(state, args, username, password, state_path)
    except KeyboardInterrupt:
        if args.cancel_on_interrupt:
            cancel_tracked_tasks(username, password)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped. The remote task may still be running.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
