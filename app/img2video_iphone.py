# VERSION$00052$ | Edited: 07/08 | TIME: 08:21
"""Generate a video from a local image with the ArtWorks API.

Designed for a-Shell Mini on iPhone. Uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import base64
import builtins
import concurrent.futures
import getpass
import hashlib
from fractions import Fraction
import json
import os
from pathlib import Path
import random
import secrets
import shutil
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
# --- Terminal presentation -------------------------------------------------
# a-Shell Mini renders standard ANSI SGR sequences, but output is also piped to
# files and read by other tools, so colour is opt-out and auto-disabled when the
# stream is not a terminal. Only the basic 8 colours are used so the user's own
# terminal theme keeps control of the actual shades.
COLOR_MODE = "auto"
COLOR_ENABLED = False
ANSI = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
}
# iPhone terminals are narrow; keep separators short enough for portrait use.
MIN_RULE_WIDTH = 20
MAX_RULE_WIDTH = 60


def color_supported() -> bool:
    """Honour NO_COLOR, dumb terminals, and redirected output."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def configure_color(mode: str) -> None:
    global COLOR_MODE, COLOR_ENABLED
    COLOR_MODE = mode
    COLOR_ENABLED = mode == "always" or (mode == "auto" and color_supported())


def completed_output_video(state: dict) -> Path | None:
    """Return the single completed video that best represents this run."""
    final_output_value = state.get("finalOutput")
    if final_output_value:
        final_output = Path(final_output_value)
        if final_output.is_file() and final_output.stat().st_size > 0:
            return final_output

    segments = [Path(value) for value in state.get("segments", [])]
    completed_segments = [
        segment
        for segment in segments
        if segment.is_file() and segment.stat().st_size > 0
    ]
    if state.get("mode") == "chain" and completed_segments:
        # Without chain assembly, the last segment is the final chronological result.
        return completed_segments[-1]
    if len(completed_segments) == 1:
        return completed_segments[0]
    return None


def play_output_video(video_path: Path) -> None:
    """Open the completed video in a-Shell's player without failing the run."""
    try:
        result = subprocess.run(
            ["play", str(video_path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        print(f"Warning: could not play {video_path}: {error}", file=sys.stderr)
        return
    if result.returncode != 0:
        print(
            f"Warning: play exited with status {result.returncode} for {video_path}.",
            file=sys.stderr,
        )


def finish_run(result: int, play_video: bool, state: dict) -> int:
    """Optionally play the final output video after a successful generation run."""
    if result != 0 or not play_video:
        return result
    video_path = completed_output_video(state)
    if video_path is None:
        print(
            "Warning: no single completed output video is available to play.",
            file=sys.stderr,
        )
        return result
    play_output_video(video_path)
    return result


def preferred_color_mode(argv=None) -> str:
    """Resolve --color before full parsing so the start banner is styled too.

    parse_args reconfigures colour afterwards, which is when a color= entry in
    the settings file takes effect.
    """
    values = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(values):
        if value.startswith("--color="):
            candidate = value.split("=", 1)[1]
        elif value == "--color" and index + 1 < len(values):
            candidate = values[index + 1]
        else:
            continue
        if candidate in ("auto", "always", "never"):
            return candidate
    return "auto"


def erase_to_end() -> str:
    """ANSI erase-to-end-of-line for in-place updates.

    A carriage return only moves the cursor; anything already on that row to the
    right of a shorter replacement line would otherwise remain visible. Padding
    covers only text this program printed, so the escape is used whenever the
    stream is a terminal, independently of whether colour is enabled.
    """
    try:
        return "\033[K" if sys.stdout.isatty() else ""
    except (AttributeError, ValueError):
        return ""


def paint(text: str, *styles: str) -> str:
    """Wrap text in SGR codes, or return it unchanged when colour is off."""
    if not COLOR_ENABLED or not styles:
        return text
    prefix = "".join(ANSI[style] for style in styles if style in ANSI)
    return f"{prefix}{text}{ANSI['reset']}" if prefix else text


def console_width() -> int:
    """Actual terminal width, used to keep single-line updates from wrapping."""
    try:
        return max(MIN_RULE_WIDTH, shutil.get_terminal_size(fallback=(40, 24)).columns)
    except OSError:
        return 40


def terminal_width() -> int:
    return min(MAX_RULE_WIDTH, console_width())


def rule(title: str = "") -> str:
    """A separator line, optionally carrying a short title."""
    width = terminal_width()
    try:
        "\u2500".encode(sys.stdout.encoding or "utf-8")
        dash = "\u2500"
    except (UnicodeEncodeError, LookupError):
        dash = "-"
    if not title:
        return paint(dash * width, "dim")
    label = f" {title} "
    remaining = max(2, width - len(label))
    left = remaining // 2
    body = f"{dash * left}{label}{dash * (remaining - left)}"
    return paint(body, "bold", "cyan")


# Prefixes recognised by the module-level print wrapper below.
LINE_STYLES = (
    ("Error:", ("bold", "red")),
    ("Warning:", ("yellow",)),
    ("Note:", ("dim",)),
    ("Saved", ("green",)),
    ("Generation completed", ("green",)),
)


def print(*values, **kwargs):  # noqa: A001 - deliberate module-level wrapper
    """Colourise well-known line prefixes without touching every call site.

    Module globals shadow builtins, so every print in this file routes here
    while builtins.print stays available for the actual write.
    """
    separator = kwargs.pop("sep", " ")
    text = separator.join(str(value) for value in values)
    if COLOR_ENABLED and text:
        for prefix, styles in LINE_STYLES:
            if text.startswith(prefix):
                text = paint(text, *styles)
                break
    builtins.print(text, **kwargs)


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
CREDENTIALS_FILE = SCRIPT_DIRECTORY / "artworks_credentials.txt"
SETTINGS_FILE = SCRIPT_DIRECTORY / "artworks_settings.txt"
RANDOM_PROMPTS_FILE = SCRIPT_DIRECTORY / "randomprompt.txt"
DEFAULT_PROMPTS_FILE_NAME = "prompts.txt"
SCRIPT_BUILD = "api-contract-v10-final-video-playback"
SUPPORTED_MODELS = ("wan-2.2", "ltx-2.3")
SUPPORTED_RESOLUTIONS = ("480p", "720p", "1080p")
SUPPORTED_PERFORMANCE_MODES = ("speed", "quality", "express")
MODEL_LIMITS = {
    "wan-2.2": {"fps": (8, 16), "frames": (24, 160)},
    "ltx-2.3": {"fps": (8, 24), "frames": (24, 361)},
}
# Encoded-rate evidence: LTX ~24 FPS is confirmed; Wan 16 FPS is user-reported.
# These values are fallbacks only when ffprobe is unavailable, for media-duration
# and output estimation. They have no role in interpolation validation or
# defaults: interpolationFps is a separate target, not the native/output rate.
MODEL_OUTPUT_FPS_FALLBACK = {"wan-2.2": 16.0, "ltx-2.3": 24.0}
# Authenticated OpenAPI interpolationFps enum, default 24 (see devdocs/api.md).
# This is model-independent: Wan and LTX share the same documented target set.
# A historical interpolationFps=30 task failed late in one executor path with an
# internal body.fps error ("None, 16 or 24"), while the user has separately
# observed Wan interpolation at 30 working. That is conflicting, path-specific
# runtime evidence, not proof that the public enum is {16, 24}, so it must not
# be used to silently rewrite a requested target.
SUPPORTED_INTERPOLATION_FPS = (24, 25, 30, 50, 60)
DEFAULT_INTERPOLATION_FPS = 24
# Confirmed normalization measurements start at 200 requested frames for LTX. A
# 30-frame request produced 57 encoded frames on LTX and 65 on Wan, i.e. more
# than requested, so the downward 8n+1 rule cannot be extrapolated to small
# requests. Both models land on the same 8n+1 lattice.
ESTIMATE_MINIMUM_FRAMES = 64
FFPROBE_WARNING_SHOWN = False
IPHONE_SAFARI_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.6 Mobile/15E148 Safari/604.1"
)


class TaskTerminalError(RuntimeError):
    """A remote task ended permanently without producing a video."""


class TaskStillRunningError(TaskTerminalError):
    """Local monitoring stopped, but the remote task may still be active."""


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


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a bounded-memory SHA-256 digest for local provenance checks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(path: Path) -> dict:
    """Identify a source file strongly enough to invalidate derived caches."""
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
        "sha256": file_sha256(path),
    }


def crop_cache_metadata_path(destination: Path) -> Path:
    return destination.with_suffix(destination.suffix + ".source.json")


def crop_cache_is_current(source: Path, destination: Path, dimensions: tuple) -> bool:
    """Return True only when a crop was derived from this exact source file."""
    metadata_path = crop_cache_metadata_path(destination)
    if not destination.is_file() or image_dimensions(destination) != dimensions:
        return False
    try:
        saved = json.loads(metadata_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return saved == source_fingerprint(source)


def save_crop_cache_metadata(source: Path, destination: Path) -> None:
    metadata_path = crop_cache_metadata_path(destination)
    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(source_fingerprint(source), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(metadata_path)


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

    A cached crop is reused only when its dimensions and saved source fingerprint
    match the current input. Replacing a photo under the same filename therefore
    cannot silently reuse pixels from an older image.
    """
    final_width, final_height = scale_to or (width, height)
    destination = source.with_name(
        f"{source.stem}_crop{final_width}x{final_height}{source.suffix}"
    )
    if crop_cache_is_current(source, destination, (final_width, final_height)):
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
    if image_dimensions(destination) != (final_width, final_height):
        raise RuntimeError(
            f"The cached crop has unexpected dimensions: {destination.name}"
        )
    save_crop_cache_metadata(source, destination)
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


def set_task_priority(
    task_id: str, priority: int, username: str, password: str
) -> bool:
    """Change a queued task's priority using the current v3 endpoint."""
    try:
        api_request(
            "POST", f"/api/v3/tasks/{task_id}/priority", username, password,
            {"priority": priority},
        )
        return True
    except RuntimeError as error:
        print(f"Could not change {task_id} to priority {priority}: {error}")
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


def display_path(path) -> str:
    """Show only the file name; iOS container paths wrap over several lines."""
    return Path(path).name


def shorten_path(path, keep: int = 2) -> str:
    """Collapse a long absolute path to its last few components.

    The iOS app-group container prefix is both unreadable and constant, so it
    carries no information worth three wrapped lines on a phone.
    """
    parts = Path(path).parts
    if len(parts) <= keep + 1:
        return str(path)
    return "…/" + "/".join(parts[-keep:])


def display_dir(path) -> str:
    """Express a directory relative to the script directory when possible."""
    try:
        resolved = Path(path).resolve()
    except OSError:
        return str(path)
    if resolved == SCRIPT_DIRECTORY:
        return "."
    try:
        return "./" + str(resolved.relative_to(SCRIPT_DIRECTORY))
    except ValueError:
        return shorten_path(resolved)


def metrics_parts(task: dict) -> list:
    """Labelled API timing metrics, API duration first, execution second."""
    metrics = (task.get("results") or {}).get("metrics") or {}
    parts = []
    if metrics.get("durationSecs") is not None:
        parts.append(f"API {format_elapsed(float(metrics['durationSecs']))}")
    if metrics.get("executionDurationSecs") is not None:
        parts.append(f"exec {format_elapsed(float(metrics['executionDurationSecs']))}")
    return parts


def print_completion(head: str, task: dict, *styles: str) -> None:
    """Print a completion line with its API metrics, preferring full labels.

    Three tiers, in order of preference: labelled and inline; labelled on its own
    line; abbreviated. Labels are only dropped when even a dedicated line cannot
    hold them, since an unlabelled pair of durations is ambiguous.
    """
    parts = metrics_parts(task)
    if not parts:
        print(paint(head, *styles))
        return
    limit = console_width() - 1
    suffix = f" ({', '.join(parts)})"
    if len(head) + len(suffix) <= limit:
        print(paint(head + suffix, *styles))
        return
    print(paint(head, *styles))
    labelled = " | ".join(parts)
    if len(labelled) <= limit:
        print(labelled)
        return
    # Last resort: drop the labels too, keeping API duration then execution.
    print("/".join(part.split()[-1] for part in parts))


def report_results(task: dict, label: str = "") -> None:
    """Surface API warnings for a finished task.

    Timing metrics are folded into the completion status line by
    print_completion, so they are no longer repeated here.
    """
    results = task.get("results") or {}
    prefix = f"{label} " if label else ""
    for warning in results.get("warnings") or []:
        print(f"{prefix}Warning from API: {warning}")


def encode_image(path: Path) -> str:
    size_mb = path.stat().st_size / 1_048_576
    print(f"Encoding {path.name} ({size_mb:.1f} MB)…")
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


def download(url: str, destination: Path, show_progress: bool = True) -> dict:
    """Download, verify, and atomically install one completed video."""
    partial = destination.with_suffix(destination.suffix + ".part")
    request = Request(
        url,
        headers={
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": IPHONE_SAFARI_USER_AGENT,
        },
    )
    received = 0
    total = 0
    content_type = None
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=300) as response:
            raw_length = response.headers.get("Content-Length")
            if raw_length:
                try:
                    total = int(raw_length)
                except (TypeError, ValueError):
                    total = 0
            raw_content_type = response.headers.get("Content-Type")
            if raw_content_type:
                content_type = raw_content_type.split(";", 1)[0].strip().lower()
            if content_type and (
                content_type.startswith("text/")
                or content_type in {"application/json", "application/xml"}
            ):
                raise RuntimeError(
                    f"Download returned non-video content type {content_type}."
                )
            with partial.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if total and show_progress:
                        percentage = min(100, received * 100 // total)
                        print(
                            f"\r{paint(f'Downloading: {percentage}%', 'cyan')}"
                            f"{erase_to_end()}",
                            end="", flush=True,
                        )
        if total and show_progress:
            print(f"\r{' ' * 20}{erase_to_end()}\r", end="", flush=True)
        if received <= 0:
            raise RuntimeError("Download produced an empty file.")
        if total and received != total:
            raise RuntimeError(
                f"Download is incomplete: received {received} of {total} bytes."
            )
        media = validate_video_file(partial)
        partial.replace(destination)
        return {
            "media": media,
            "sha256": digest.hexdigest(),
            "fileSizeBytes": received,
            "contentLength": total or None,
            "contentType": content_type,
        }
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


def extract_last_frame(video: Path, image: Path) -> None:
    print("Extracting final frame…")
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


H264_ENCODER_ATTEMPTS = [
    ("libx264", ["-c:v", "libx264"]),
    ("h264_videotoolbox", ["-c:v", "h264_videotoolbox"]),
]


def require_h264_encoder() -> None:
    """Fail before API submission when codec-safe source assembly is impossible."""
    try:
        completed = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "FFmpeg is required to include the source video in the final output."
        ) from error
    available = completed.stdout + completed.stderr
    names = [name for name, _ in H264_ENCODER_ATTEMPTS if name in available]
    if completed.returncode != 0 or not names:
        raise RuntimeError(
            "Including the source video requires libx264 or h264_videotoolbox. "
            "Neither H.264 encoder is available, so generation was stopped before "
            "submitting billable API tasks."
        )


def probe_frame_size(video: Path, temporary_directory: Path) -> tuple:
    """Read a video's pixel dimensions by decoding one frame with FFmpeg."""
    frame = temporary_directory / f"{video.stem}_probe.png"
    run_ffmpeg(
        ["-y", "-i", str(video), "-map", "0:v:0", "-frames:v", "1", str(frame)],
        "probing video dimensions",
    )
    if not frame.is_file() or frame.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg could not read a frame from: {video}")
    size = image_dimensions(frame)
    if not size:
        raise RuntimeError(f"Could not determine video dimensions from: {video}")
    return size


def combine_segments(
    segments: list[Path],
    output: Path,
    temporary_directory: Path,
    output_fps: float,
    *,
    reencode: bool = False,
    reference_segment: Path | None = None,
) -> None:
    """Combine segments safely, re-encoding when a source video is included.

    Generated API chunks use stream-copy concat for speed. A user-provided source
    video may have different codec parameters, so that path decodes, normalizes,
    concatenates, and encodes the complete result as H.264 instead of relying on
    unsafe codec compatibility assumptions.
    """
    temporary_output = temporary_directory / "combined.mp4"
    print(f"Combining {len(segments)} segments into {output.name}…")
    if not reencode:
        concat_file = temporary_directory / "segments.txt"
        concat_file.write_text(
            "".join(f"file '{quote_concat_path(segment)}'\n" for segment in segments),
            encoding="utf-8",
        )
        run_ffmpeg(
            [
                "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-video_track_timescale",
                str(max(1000, int(round(float(output_fps) * 1000)))),
                "-movflags", "+faststart",
                "-f", "mp4", str(temporary_output),
            ],
            "combining the generated segments",
        )
    else:
        reference = reference_segment or segments[-1]
        width, height = probe_frame_size(reference, temporary_directory)
        fps_text = f"{float(output_fps):.8g}"
        input_arguments = []
        filters = []
        labels = []
        for index, segment in enumerate(segments):
            input_arguments += ["-i", str(segment)]
            label = f"v{index}"
            filters.append(
                f"[{index}:v:0]"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps_text},setsar=1,"
                f"format=yuv420p,setpts=PTS-STARTPTS[{label}]"
            )
            labels.append(f"[{label}]")
        filters.append(
            f"{''.join(labels)}concat=n={len(segments)}:v=1:a=0[outv]"
        )
        filter_graph = ";".join(filters)
        bitrate = max(
            1_500_000,
            min(12_000_000, int(width * height * float(output_fps) * 0.08)),
        )
        last_error = None
        for encoder_name, codec_arguments in H264_ENCODER_ATTEMPTS:
            if temporary_output.exists():
                temporary_output.unlink()
            try:
                run_ffmpeg(
                    [
                        "-y", *input_arguments,
                        "-filter_complex", filter_graph,
                        "-map", "[outv]", "-an",
                        *codec_arguments, "-pix_fmt", "yuv420p",
                        "-b:v", str(bitrate),
                        "-video_track_timescale",
                        str(max(1000, int(round(float(output_fps) * 1000)))),
                        "-movflags", "+faststart",
                        str(temporary_output),
                    ],
                    f"combining and re-encoding with {encoder_name}",
                )
                last_error = None
                break
            except RuntimeError as error:
                last_error = error
                print(
                    f"  {encoder_name} encoder unavailable ({error}); "
                    "trying the next H.264 encoder…"
                )
        if last_error is not None:
            raise RuntimeError(
                "Could not create a codec-safe H.264 assembly with any available "
                f"encoder: {last_error}"
            )
    validate_video_file(temporary_output)
    temporary_output.replace(output)


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


def validate_interpolation_fps(value, source: str = "interpolationFps") -> int:
    """Validate a requested interpolation target against the documented enum.

    This is validation, not normalization: the exact requested value is returned
    unchanged, or rejected outright. interpolationFps is model-independent, so
    unlike the old implementation this never derives a fallback from the
    selected model, and it never silently substitutes a nearby accepted value
    (e.g. 30 -> 16 or 30 -> 24). Runtime support within the documented enum has
    conflicting, path-specific evidence (see AGENTS.md and devdocs/api.md); that
    evidence is not a reason to reject or rewrite a documented value here.
    """
    accepted = ", ".join(str(rate) for rate in SUPPORTED_INTERPOLATION_FPS)
    try:
        requested = int(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"{source} must be an integer, not {value!r}. Documented values are {accepted}.")
    # int(30.8) silently truncates to 30, which would contradict "the exact
    # requested value is returned unchanged" above for a non-whole float, e.g.
    # a malformed recovery-state JSON number.
    if isinstance(value, float) and not value.is_integer():
        raise RuntimeError(f"{source} must be an integer, not {value!r}. Documented values are {accepted}.")
    if requested not in SUPPORTED_INTERPOLATION_FPS:
        raise RuntimeError(f"{source} must be one of {accepted}, not {requested}.")
    return requested


def generation_parameters(args) -> dict:
    return {
        "model": args.model,
        "resolution": args.resolution,
        "performance": args.performance,
        "fps": args.fps,
        "numFrames": args.frames,
        "applyOptimizations": args.optimizations,
        "applyInterpolation": args.interpolation,
        "interpolationFps": args.interpolation_fps,
        "seed": args.seed,
        "loras": args.loras,
        "priority": args.priority,
        "tags": args.tags,
        "batchId": args.batch_id,
    }


def parse_rate(value) -> float | None:
    """Parse an ffprobe rational rate such as ``24000/1001``."""
    if value in (None, "", "0/0", "N/A"):
        return None
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None


def probe_video_metadata(video: Path) -> dict | None:
    """Read encoded media properties with ffprobe when it is available."""
    global FFPROBE_WARNING_SHOWN
    try:
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_frames",
                "-show_entries",
                "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,"
                "nb_frames,nb_read_frames:format=duration,size",
                "-of", "json", str(video),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        if not FFPROBE_WARNING_SHOWN:
            print(
                "Note: ffprobe is unavailable; encoded FPS, frame count, duration, "
                "and codec cannot be measured exactly."
            )
            FFPROBE_WARNING_SHOWN = True
        return None
    if completed.returncode != 0:
        print(
            f"Warning: ffprobe could not inspect {video.name}: "
            f"{completed.stderr.strip() or 'unknown error'}"
        )
        return None
    try:
        document = json.loads(completed.stdout)
        stream = (document.get("streams") or [])[0]
        container = document.get("format") or {}
    except (json.JSONDecodeError, IndexError, TypeError):
        print(f"Warning: ffprobe returned incomplete metadata for {video.name}.")
        return None

    frame_count = stream.get("nb_read_frames") or stream.get("nb_frames")
    try:
        frame_count = int(frame_count) if frame_count not in (None, "N/A") else None
    except (TypeError, ValueError):
        frame_count = None
    try:
        duration = float(container["duration"]) if container.get("duration") else None
    except (TypeError, ValueError):
        duration = None
    try:
        file_size = int(container["size"]) if container.get("size") else video.stat().st_size
    except (TypeError, ValueError, OSError):
        file_size = None

    avg_fps = parse_rate(stream.get("avg_frame_rate"))
    nominal_fps = parse_rate(stream.get("r_frame_rate"))
    measured_fps = avg_fps or nominal_fps
    if frame_count and duration and duration > 0:
        derived_fps = frame_count / duration
        # Prefer the derived value when the declared rate is absent or clearly wrong.
        if measured_fps is None or abs(derived_fps - measured_fps) > 0.5:
            measured_fps = derived_fps

    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "rFrameRate": stream.get("r_frame_rate"),
        "avgFrameRate": stream.get("avg_frame_rate"),
        "encodedFps": measured_fps,
        "frameCount": frame_count,
        "durationSeconds": duration,
        "fileSizeBytes": file_size,
    }


def print_video_metadata(metadata: dict | None, label: str = "") -> None:
    if metadata is None:
        return
    prefix = f"{label} " if label else ""
    # Kept short enough to survive a ~40-column phone terminal without wrapping
    # mid-number. Full precision stays available in the returned metadata.
    parts = []
    if metadata.get("codec"):
        parts.append(str(metadata["codec"]))
    if metadata.get("width") and metadata.get("height"):
        parts.append(f"{metadata['width']}x{metadata['height']}")
    frames_and_rate = ""
    if metadata.get("frameCount") is not None:
        frames_and_rate = f"{metadata['frameCount']}f"
    if metadata.get("encodedFps") is not None:
        frames_and_rate += f"@{metadata['encodedFps']:.4g}"
    if frames_and_rate:
        parts.append(frames_and_rate)
    if metadata.get("durationSeconds") is not None:
        parts.append(f"{metadata['durationSeconds']:.3f}s")
    if metadata.get("fileSizeBytes") is not None:
        parts.append(f"{metadata['fileSizeBytes'] / 1_048_576:.1f}MB")
    if parts:
        print(f"{prefix}Media: " + " ".join(parts))


def report_video_metadata(video: Path, label: str = "") -> dict | None:
    metadata = probe_video_metadata(video)
    print_video_metadata(metadata, label)
    return metadata


def validate_video_file(video: Path) -> dict | None:
    """Require a non-empty file containing at least one decodable video stream."""
    if not video.is_file() or video.stat().st_size <= 0:
        raise RuntimeError(f"Video file is empty or missing: {video}")
    metadata = probe_video_metadata(video)
    if metadata is not None:
        if not metadata.get("codec") or not metadata.get("width") or not metadata.get("height"):
            raise RuntimeError(f"No usable video stream was found in {video.name}.")
        return metadata
    # ffprobe may be absent on a minimal a-Shell installation. FFmpeg is already
    # required by assembly and cropping, and decoding one frame is sufficient to
    # reject HTML/error bodies and truncated media without scanning the full file.
    run_ffmpeg(
        [
            "-v", "error", "-i", str(video), "-map", "0:v:0",
            "-frames:v", "1", "-f", "null", "-",
        ],
        f"validating downloaded video {video.name}",
    )
    return None


def effective_output_fps(parameters: dict, reference_video: Path | None = None) -> float:
    """Return measured encoded FPS, never the request FPS when avoidable."""
    if reference_video is not None:
        metadata = probe_video_metadata(reference_video)
        if metadata and metadata.get("encodedFps"):
            return float(metadata["encodedFps"])
    # Interpolation is explicitly unverified, so its requested target is not a
    # trustworthy fallback. Use the model's observed/native rate instead.
    model = parameters.get("model")
    return float(MODEL_OUTPUT_FPS_FALLBACK.get(model, 24.0))


def estimated_output_description(parameters: dict) -> str:
    """Describe evidence-based output timing without presenting it as measured."""
    model = parameters["model"]
    requested = int(parameters["numFrames"])
    if parameters.get("applyInterpolation"):
        return "interpolation unverified"
    rate = MODEL_OUTPUT_FPS_FALLBACK.get(model)
    if rate is None:
        return "unknown model; measured after download"
    # Below the lowest verified request size the estimate is withheld rather
    # than printed as a confident number that measurement contradicts.
    if requested < ESTIMATE_MINIMUM_FRAMES:
        return f"no estimate under {ESTIMATE_MINIMUM_FRAMES} frames"
    normalized = 8 * ((requested - 1) // 8) + 1
    return f"~{normalized}f @{rate:g} = {normalized / rate:.2f}s (inferred)"

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



def load_prompt_file(path: Path) -> list[str]:
    """Load one prompt per non-empty, non-comment UTF-8 line.

    Prompt order is task and assembly order. In parallel mode, a line may use
    ``photo.jpg::prompt text`` to bind that task to a different source image.
    """
    if not path.is_file():
        raise RuntimeError(
            f"Prompt file not found: {path}. Create it, change promptFile=, "
            "or leave promptFile empty to use inline/interactive prompts."
        )
    prompts = [
        line.strip()
        for line in path.read_text("utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    print(f"Using {len(prompts)} prompt(s) from {path.name}")
    return prompts


def load_settings(path: Path) -> dict:
    """Load the line-oriented ``key=value`` settings file.

    ``promptFile=`` points to a file containing one prompt per line. Repeat
    ``prompt=``, ``tag=``, and ``lora=`` for additional list-valued settings.
    Empty scalar values are retained as empty strings so optional paths and
    seeds can be intentionally left unset in a complete template.
    """
    if not path.is_file():
        if path == SETTINGS_FILE:
            return {}
        raise RuntimeError(f"Settings file not found: {path}")

    allowed = {
        "photo", "prompt", "promptFile", "output", "model", "resolution", "performance",
        "fps", "numFrames", "seed", "priority", "tag", "isFast",
        "applyOptimizations", "applyInterpolation", "interpolationFps", "lora",
        "pollIntervalSeconds", "taskTimeoutSeconds", "pollRequestRetryLimit",
        "pollRequestRetryBackoffSeconds", "overwriteExisting", "chainPrompt",
        "combineChain", "resumeInterruptedTasks", "stateFile",
        "suspensionWarningSeconds", "parallelChunks", "maxParallelTasks",
        "assembleParallelChunks", "incrementSeedPerChunk", "generationMode",
        "combineVideos", "incrementSeedPerTask", "batchId", "cancelOnInterrupt",
        "promotePriorityAfterSeconds", "promotePriorityTo",
        "promoteToFastAfterSeconds", "unknownStatusLimit", "validateLoras",
        "autoCropPhotos", "autoCropMaxDifference", "includeSourceVideo",
        "experimentalLoopCount", "showPrompts", "color",
    }
    values = {"lora": [], "prompt": [], "chainPrompt": [], "tag": []}
    for line_number, raw_line in enumerate(path.read_text("utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or key not in allowed:
            raise RuntimeError(f"Invalid setting on line {line_number}: {raw_line}")
        if key in {"lora", "prompt", "chainPrompt", "tag"}:
            if value:
                values[key].append(parse_lora(value) if key == "lora" else value)
        else:
            values[key] = value

    print(f"Using settings from {path.name}")
    return values


def parse_args():
    pre_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre_parser.add_argument("--settings", default=str(SETTINGS_FILE))
    preliminary, _ = pre_parser.parse_known_args()
    settings_path = Path(preliminary.settings).expanduser().resolve()
    settings = load_settings(settings_path)

    model = (settings.get("model") or "ltx-2.3").lower()
    if model not in SUPPORTED_MODELS:
        raise RuntimeError("model must be wan-2.2 or ltx-2.3")

    resolution = settings.get("resolution") or "480p"
    performance = settings.get("performance") or "speed"
    if resolution not in SUPPORTED_RESOLUTIONS:
        raise RuntimeError("resolution must be 480p, 720p, or 1080p")
    if performance not in SUPPORTED_PERFORMANCE_MODES:
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

    model_limits = MODEL_LIMITS[model]
    default_fps = "16" if model == "wan-2.2" else "24"
    default_frames = "160" if model == "wan-2.2" else "360"
    fps = parse_int(settings.get("fps", default_fps), "fps", 8, 24)
    frames = parse_int(settings.get("numFrames", default_frames), "numFrames", 24, 361)
    # Deliberately not validated yet: interpolationFps is a stored preference
    # that only matters once interpolation is actually requested (enabled, or
    # --interpolate given explicitly on the command line). Whether that is the
    # case is only known after full argument parsing below, so an inactive
    # preference here is not validated and cannot abort a run that would never
    # transmit it.
    interpolation_fps_configured = settings.get("interpolationFps", str(DEFAULT_INTERPOLATION_FPS))

    if settings.get("priority"):
        priority = parse_int(settings["priority"], "priority", 1, 5)
        if settings.get("isFast") is not None:
            print("Warning: isFast is deprecated and ignored because priority is set.")
    elif settings.get("isFast") is not None:
        legacy_fast = parse_bool(settings["isFast"], "isFast")
        priority = 1 if legacy_fast else 5
        print(
            f"Warning: isFast is deprecated; translated to priority={priority}. "
            "Update the settings file to use priority."
        )
    else:
        priority = 5

    legacy_promote_after = settings.get("promoteToFastAfterSeconds")
    promote_after_value = settings.get("promotePriorityAfterSeconds")
    if promote_after_value is None and legacy_promote_after is not None:
        promote_after_value = legacy_promote_after
        print(
            "Warning: promoteToFastAfterSeconds is deprecated; use "
            "promotePriorityAfterSeconds and promotePriorityTo."
        )

    parser = argparse.ArgumentParser(
        description="Turn a photo into a video using the ArtWorks image-to-video API."
    )
    parser.add_argument(
        "--settings",
        default=str(settings_path),
        help="key=value settings file (default: artworks_settings.txt beside the script)",
    )
    parser.add_argument(
        "photo",
        nargs="?",
        default=settings.get("photo") or None,
        help="input image or video path; a video's final frame becomes the starting "
             "image and the source video can be prepended to the result",
    )
    parser.add_argument(
        "--prompt", action="append", default=None, metavar="PROMPT",
        help="motion prompt; repeat for several tasks; overrides configured prompt sources",
    )
    parser.add_argument(
        "--prompt-file",
        default=settings.get("promptFile") or None,
        metavar="FILE",
        help="UTF-8 text file with one prompt per non-comment line",
    )
    parser.add_argument("--output", default=settings.get("output") or None, help="output MP4 path")
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=model)
    parser.add_argument("--resolution", choices=SUPPORTED_RESOLUTIONS, default=resolution)
    parser.add_argument("--performance", choices=SUPPORTED_PERFORMANCE_MODES, default=performance)
    parser.add_argument("--fps", type=int, choices=range(8, 25), default=fps, metavar="8-24")
    parser.add_argument("--frames", type=int, choices=range(24, 362), default=frames, metavar="24-361")
    parser.add_argument(
        "--seed", type=int,
        default=int(settings["seed"]) if settings.get("seed") else None,
        help="signed 64-bit generation seed; reproducibility is not yet guaranteed",
    )
    parser.add_argument(
        "--priority", type=int, choices=range(1, 6), default=priority, metavar="1-5",
        help="queue priority; 1 is highest and 5 is the default/lowest",
    )
    parser.add_argument(
        "--tag", action="append", default=None, metavar="TAG",
        help="task tag; repeat for multiple tags",
    )
    parser.add_argument(
        "--fast", dest="legacy_fast", action=argparse.BooleanOptionalAction,
        default=None, help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--optimizations", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("applyOptimizations", "false"), "applyOptimizations"),
        help="send applyOptimizations explicitly; runtime effect remains unverified",
    )
    parser.add_argument(
        "--interpolation", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("applyInterpolation", "false"), "applyInterpolation"),
        help="enable interpolation (applyInterpolation); runtime effect remains unverified",
    )
    parser.add_argument(
        # Deliberately type=str with no choices: the settings-sourced default
        # must not be forced through int()/choices at parse time (argparse
        # applies both to a string default), because an inactive interpolation
        # preference must not abort argument parsing. validate_interpolation_fps
        # runs explicitly below once whether interpolation is active is known.
        "--interpolate", dest="interpolation_fps", type=str,
        default=interpolation_fps_configured, metavar="FPS",
        help=(
            "interpolation target FPS; documented enum 24, 25, 30, 50, 60 (default "
            "24). Also enables interpolation when supplied, even together with "
            "--no-interpolation. Runtime support within this enum has conflicting "
            "path-specific evidence (see AGENTS.md)."
        ),
    )
    parser.add_argument(
        "--lora", action="append", default=None, metavar="MODEL|WEIGHT",
        help="LoRA filename and optional weight (-2 to 2); repeat for multiple LoRAs",
    )
    parser.add_argument(
        "--poll-interval", type=float,
        default=parse_float(settings.get("pollIntervalSeconds", "2"), "pollIntervalSeconds", 0.5, 60),
        metavar="SECONDS",
    )
    parser.add_argument(
        "--task-timeout", type=float,
        default=parse_float(settings.get("taskTimeoutSeconds", "7200"), "taskTimeoutSeconds", 0, 604800),
        metavar="SECONDS",
        help="overall timeout per remote task; 0 disables it",
    )
    parser.add_argument(
        "--poll-retries", type=int,
        default=parse_int(settings.get("pollRequestRetryLimit", "3"), "pollRequestRetryLimit", 0, 20),
        metavar="COUNT",
        help="retries for a transient task-status request failure",
    )
    parser.add_argument(
        "--poll-retry-backoff", type=float,
        default=parse_float(
            settings.get("pollRequestRetryBackoffSeconds", "2"),
            "pollRequestRetryBackoffSeconds", 0.1, 60,
        ),
        metavar="SECONDS",
    )
    parser.add_argument(
        "--overwrite", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("overwriteExisting", "false"), "overwriteExisting"),
        help="replace existing output instead of adding _1, _2, ...",
    )
    parser.add_argument(
        "--color", choices=("auto", "always", "never"),
        default=(settings.get("color") or "auto"),
        help="colourise output: auto (only when attached to a terminal), always, never",
    )
    parser.add_argument(
        "-s", "--s", "--sound", dest="play_completed_video", action="store_true",
        help="play the final output video after a successful generation run",
    )
    parser.add_argument(
        "--show-prompts", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("showPrompts", "false"), "showPrompts"),
        help="echo full prompt text to the console; hidden by default",
    )
    parser.add_argument(
        "--chain-prompt", action="append", default=None, metavar="PROMPT",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--combine-chain", action=argparse.BooleanOptionalAction,
        default=None, help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--mode", dest="generation_mode", choices=("chain", "parallel"),
        default=generation_mode,
        help="chain continues from the preceding final frame; parallel starts independently",
    )
    parser.add_argument(
        "--combine-videos", action=argparse.BooleanOptionalAction,
        default=combine_videos,
        help="assemble all completed task videos in prompt order",
    )
    parser.add_argument(
        "--resume-interrupted", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("resumeInterruptedTasks", "true"), "resumeInterruptedTasks"),
        help="persist task IDs and resume after a-Shell suspension or termination",
    )
    parser.add_argument(
        "--state-file", default=settings.get("stateFile") or "artworks_tasks.json",
        help="persistent recovery file, relative to the script folder by default",
    )
    parser.add_argument(
        "--autocrop-photos", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("autoCropPhotos", "true"), "autoCropPhotos"),
        help="centre-crop sources to a shared aspect ratio before parallel assembly",
    )
    parser.add_argument(
        "--autocrop-max-difference", type=float,
        default=parse_float(settings.get("autoCropMaxDifference", "0.2"), "autoCropMaxDifference", 0, 1),
        metavar="FRACTION",
        help="refuse automatic cropping above this aspect-ratio difference",
    )
    parser.add_argument(
        "--batch-id", default=settings.get("batchId", "auto") or "auto", metavar="ID",
        help="shared batch ID; 'auto' creates one for multi-task runs and 'off' omits it",
    )
    parser.add_argument(
        "--cancel-on-interrupt", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("cancelOnInterrupt", "true"), "cancelOnInterrupt"),
        help="attempt to cancel tasks that are still queued when interrupted",
    )
    parser.add_argument(
        "--promote-priority-after", "--promote-to-fast",
        dest="promote_priority_after", type=float,
        default=parse_float(promote_after_value or "0", "promotePriorityAfterSeconds", 0, 86400),
        metavar="SECONDS",
        help="while pending, change to promotePriorityTo after this delay; 0 disables it",
    )
    parser.add_argument(
        "--promote-priority-to", type=int, choices=range(1, 6),
        default=parse_int(settings.get("promotePriorityTo", "1"), "promotePriorityTo", 1, 5),
        metavar="1-5",
        help="target queue priority for delayed promotion; lower is faster",
    )
    parser.add_argument(
        "--unknown-status-limit", type=int,
        default=parse_int(settings.get("unknownStatusLimit", "5"), "unknownStatusLimit", 0, 1000),
        metavar="POLLS",
        help="fail after this many consecutive unknown statuses; 0 waits indefinitely",
    )
    parser.add_argument(
        "--validate-loras", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("validateLoras", "true"), "validateLoras"),
        help="check LoRA filenames against /api/v3/resources before submission",
    )
    parser.add_argument(
        "--list-loras", nargs="?", const="", default=None, metavar="SEARCH",
        help="print available LoRA filenames and exit; optional filter needs 3+ characters",
    )
    parser.add_argument(
        "--include-source-video", action=argparse.BooleanOptionalAction,
        default=parse_bool(settings.get("includeSourceVideo", "true"), "includeSourceVideo"),
        help="prepend a video input, re-encoded to match the generated footage",
    )
    parser.add_argument(
        "--experimental-loop",
        type=lambda value: parse_int(value, "experimentalLoopCount", 0, 50),
        default=parse_int(settings.get("experimentalLoopCount", "0"), "experimentalLoopCount", 0, 50),
        metavar="N",
        help="EXPERIMENTAL: select N unique prompts from randomprompt.txt",
    )
    parser.add_argument(
        "--suspension-warning", type=float,
        default=parse_float(settings.get("suspensionWarningSeconds", "15"), "suspensionWarningSeconds", 5, 3600),
        metavar="SECONDS",
        help="report polling gaps suggesting iOS suspension or a network stall",
    )
    parser.add_argument(
        "--parallel-chunks", type=int, choices=range(1, 21),
        default=legacy_parallel_chunks, metavar="1-20", help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-parallel-tasks", type=int, choices=range(1, 7),
        default=parse_int(settings.get("maxParallelTasks", "3"), "maxParallelTasks", 1, 6),
        metavar="1-6",
        help="maximum simultaneous submissions, status requests, and downloads",
    )
    parser.add_argument(
        "--assemble-parallel", action=argparse.BooleanOptionalAction,
        default=None, help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--increment-seed-per-task", dest="increment_seed_per_task",
        action=argparse.BooleanOptionalAction,
        default=parse_bool(
            settings.get("incrementSeedPerTask", settings.get("incrementSeedPerChunk", "true")),
            "incrementSeedPerTask",
        ),
        help="in parallel mode, add each task index to a configured seed",
    )
    args = parser.parse_args()
    configure_color(args.color)

    if any(value == "--interpolate" or value.startswith("--interpolate=") for value in sys.argv):
        args.interpolation = True

    priority_was_explicit = any(
        value == "--priority" or value.startswith("--priority=") for value in sys.argv
    )
    if args.legacy_fast is not None:
        if priority_was_explicit:
            raise RuntimeError("Do not combine deprecated --fast with --priority")
        args.priority = 1 if args.legacy_fast else 5
        print(f"Warning: --fast is deprecated; translated to --priority {args.priority}.")

    limits = MODEL_LIMITS[args.model]
    if not limits["fps"][0] <= args.fps <= limits["fps"][1]:
        raise RuntimeError(
            f"{args.model} accepts fps from {limits['fps'][0]} to {limits['fps'][1]}, "
            f"not {args.fps}"
        )
    if not limits["frames"][0] <= args.frames <= limits["frames"][1]:
        raise RuntimeError(
            f"{args.model} accepts numFrames from {limits['frames'][0]} to "
            f"{limits['frames'][1]}, not {args.frames}"
        )
    if args.seed is not None and not -(2**63) <= args.seed <= 2**63 - 1:
        raise RuntimeError("seed must fit a signed 64-bit integer")
    if args.promote_priority_after and args.promote_priority_to >= args.priority:
        raise RuntimeError(
            "promotePriorityTo must be numerically lower (higher priority) than priority"
        )
    if args.interpolation:
        # args.interpolation is already True here whenever --interpolate was
        # given explicitly (forced above), so this covers both "interpolation
        # enabled" and "an explicit target was requested". Only now is the
        # value actually going to reach the API, so only now is it validated.
        args.interpolation_fps = validate_interpolation_fps(args.interpolation_fps)
        # args.fps is the generation request FPS, not the native/output FPS that
        # interpolation would actually act on, so it cannot be used to predict
        # whether this target adds or discards frames.
        print(
            "Warning: interpolation runtime support within the documented "
            f"{', '.join(str(rate) for rate in SUPPORTED_INTERPOLATION_FPS)} enum has "
            "conflicting path-specific evidence; the downloaded MP4 will be measured."
        )
    else:
        # Interpolation is inactive, so this stored preference will never reach
        # the API. Keep it as a best-effort integer for generation_parameters()
        # and recovery state without aborting the run over a value it will
        # never transmit; an unusable value only becomes an error once
        # interpolation is actually turned on.
        try:
            args.interpolation_fps = int(args.interpolation_fps)
        except (TypeError, ValueError):
            args.interpolation_fps = DEFAULT_INTERPOLATION_FPS

    args.tags = list(args.tag if args.tag is not None else settings.get("tag", []))
    args.loras = [parse_lora(value) for value in args.lora] if args.lora else settings.get("lora", [])

    # Explicit CLI prompts are a complete override. Otherwise load the separate
    # prompt file first, then append any legacy/inline prompt= entries. A relative
    # promptFile from settings is resolved beside that settings file, which keeps
    # the iPhone bundle portable regardless of the current shell directory.
    if args.prompt is not None:
        prompts = list(args.prompt)
    else:
        prompts = []
        prompt_file_value = args.prompt_file
        if prompt_file_value is None and "promptFile" not in settings:
            implicit_prompt_file = settings_path.parent / DEFAULT_PROMPTS_FILE_NAME
            if implicit_prompt_file.is_file():
                prompt_file_value = DEFAULT_PROMPTS_FILE_NAME
        if prompt_file_value:
            prompt_file_explicit = any(
                value == "--prompt-file" or value.startswith("--prompt-file=")
                for value in sys.argv
            )
            prompt_file = Path(prompt_file_value).expanduser()
            if not prompt_file.is_absolute():
                prompt_file = (Path.cwd() if prompt_file_explicit else settings_path.parent) / prompt_file
            args.prompt_file = str(prompt_file.resolve())
            prompts.extend(load_prompt_file(prompt_file.resolve()))
        prompts.extend(settings.get("prompt", []))

    legacy_chain_prompts = args.chain_prompt if args.chain_prompt is not None else settings.get("chainPrompt", [])
    if settings.get("generationMode") is None and args.parallel_chunks > 1:
        if legacy_chain_prompts:
            raise RuntimeError(
                "Legacy parallelChunks cannot be combined with chainPrompt. Use "
                "generationMode=parallel and repeat prompt= for each independent task."
            )
        if len(prompts) == 1:
            prompts *= args.parallel_chunks
    else:
        prompts.extend(legacy_chain_prompts)
    if len(prompts) > 20:
        raise RuntimeError("Configure no more than 20 prompts across promptFile and prompt= entries.")

    if args.batch_id.strip().lower() in {"off", "none", "false", ""}:
        args.batch_id = None
    elif args.batch_id.strip().lower() == "auto":
        args.batch_id = f"img2video-{uuid.uuid4().hex[:12]}" if len(prompts) > 1 else None

    prompt_photos = []
    prompt_texts = []
    for entry in prompts:
        photo_reference, prompt_text = split_prompt_photo(entry)
        prompt_photos.append(photo_reference)
        prompt_texts.append(prompt_text)
    if any(prompt_photos) and args.generation_mode != "parallel":
        ignored = ", ".join(name for name in prompt_photos if name)
        print(
            f"Warning: ignoring per-prompt photo(s) ({ignored}); chain mode always "
            "continues from the previous step's final frame."
        )
        prompt_photos = [None] * len(prompt_photos)

    args.prompt_photos = prompt_photos
    args.task_prompts = prompt_texts
    args.combine_chain = args.combine_videos if args.combine_chain is None else args.combine_chain
    args.assemble_parallel = args.combine_videos if args.assemble_parallel is None else args.assemble_parallel
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
    """Build the current documented v3 request without deprecated fields."""
    payload = {
        "image": image_data,
        "prompt": prompt,
        "model": parameters["model"],
        "resolution": parameters["resolution"],
        "performance": parameters["performance"],
        "fps": parameters["fps"],
        "numFrames": parameters["numFrames"],
        "applyOptimizations": parameters["applyOptimizations"],
        "applyInterpolation": parameters["applyInterpolation"],
        "loras": parameters.get("loras") or [],
    }
    # The executor accepts None for this field, so omitting it when interpolation
    # is off keeps a stale or unsupported rate from failing an otherwise valid task.
    if parameters.get("applyInterpolation"):
        payload["interpolationFps"] = parameters["interpolationFps"]
    if parameters.get("seed") is not None:
        payload["seed"] = parameters["seed"]
    request = {
        "type": "image-to-video",
        "priority": int(parameters["priority"]),
        "payload": payload,
    }
    if parameters.get("tags"):
        request["tags"] = list(parameters["tags"])
    if parameters.get("batchId"):
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


def completed_video_url(task: dict, task_id: str | None = None) -> str:
    try:
        return task["results"]["data"]["video"]["url"]
    except (KeyError, TypeError) as error:
        identity = f"Task {task_id}" if task_id else "Completed task"
        raise RuntimeError(
            f"{identity} has no video URL at results.data.video.url: "
            f"{task.get('results')}"
        ) from error



def poll_task_status(
    task_id: str,
    username: str,
    password: str,
    retry_limit: int,
    retry_backoff: float,
) -> dict:
    """Poll safely without retrying billable POST submissions."""
    for attempt in range(retry_limit + 1):
        try:
            return api_request("GET", f"/api/v3/tasks/{task_id}", username, password)
        except RuntimeError as error:
            if attempt >= retry_limit:
                raise RuntimeError(
                    f"Task {task_id} status request failed after {attempt + 1} "
                    f"attempt(s): {error}"
                ) from error
            delay = retry_backoff * (attempt + 1)
            print(
                f"Task {task_id}: transient status request failure ({error}); "
                f"retrying in {delay:.1f}s."
            )
            time.sleep(delay)
    raise AssertionError("unreachable")



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
    task_timeout_seconds: float = 7200,
    poll_retry_limit: int = 3,
    poll_retry_backoff: float = 2,
    promote_priority_after: float = 0,
    promote_priority_to: int = 1,
    on_submitted=None,
    on_heartbeat=None,
) -> dict | None:
    task_id = existing_task_id
    started_at = existing_started_at or time.time()
    if task_id:
        print("Resuming task: " + paint(task_id, "dim"))
    else:
        task_id, started_at = submit_encoded_task(
            encode_image(photo), prompt, parameters, username, password
        )
        print("Task: " + paint(task_id, "dim"))
        if on_submitted is not None:
            on_submitted(task_id, started_at)

    previous_width = 0
    unknown_polls = 0
    promoted = int(parameters.get("priority", 5)) <= promote_priority_to
    last_poll_at = existing_last_active_at or started_at
    phase_status = existing_phase_status
    phase_started_at = existing_phase_started_at or started_at
    phase_durations = dict(existing_phase_durations or {})
    task = {}
    status = UNKNOWN_STATUS

    while True:
        task = poll_task_status(
            task_id, username, password, poll_retry_limit, poll_retry_backoff
        )
        now = time.time()
        polling_gap = now - last_poll_at
        if polling_gap >= suspension_warning_seconds:
            if previous_width:
                print()
            print(
                f"Warning: no polling activity for {format_elapsed(polling_gap)}; "
                "iOS may have suspended a-Shell or the network stalled."
            )
            previous_width = 0
        last_poll_at = now
        status = task.get("status", UNKNOWN_STATUS)
        track_task(task_id, status)
        if status == UNKNOWN_STATUS:
            unknown_polls += 1
            if unknown_status_limit and unknown_polls >= unknown_status_limit:
                raise TaskStillRunningError(
                    f"Task {task_id} reported an unknown status {unknown_polls} times in a row. "
                    "The task may still be running and remains in the recovery state."
                )
        else:
            unknown_polls = 0

        position = task.get("position")
        position_text = f" | queue {position}" if status == "pending" and position is not None else ""
        if (
            promote_priority_after
            and not promoted
            and status == "pending"
            and now - started_at >= promote_priority_after
        ):
            if previous_width:
                print()
                previous_width = 0
            print(
                f"Still queued after {format_elapsed(now - started_at)}; changing "
                f"priority from {parameters.get('priority', 5)} to {promote_priority_to}."
            )
            promoted = set_task_priority(task_id, promote_priority_to, username, password)

        if phase_status != status:
            if phase_status and phase_status not in TERMINAL_STATES:
                phase_elapsed = max(0, now - phase_started_at)
                phase_durations[phase_status] = float(phase_durations.get(phase_status, 0)) + phase_elapsed
                if previous_width:
                    print()
                # Phase lines get their own colour so they read as timing
                # markers rather than status updates. Processing is bolded
                # because it is the phase that actually consumes generation time.
                phase_styles = ("magenta", "bold") if phase_status == "processing" else ("magenta",)
                print(paint(f"Phase {phase_status}: {format_elapsed(phase_elapsed)}", *phase_styles))
                previous_width = 0
            phase_status = None if status in TERMINAL_STATES else status
            phase_started_at = now

        if status in TERMINAL_STATES:
            if previous_width:
                print()
            terminal_styles = ("green",) if status == "completed" else ("bold", "red")
            head = f"Status: {status} | {format_elapsed(now - started_at)}"
            print_completion(head, task if status == "completed" else {}, *terminal_styles)
            previous_width = 0
        else:
            phase_elapsed_text = format_elapsed(now - phase_started_at)
            total_elapsed_text = format_elapsed(now - started_at)
            line = f"Status: {status}{position_text} | phase {phase_elapsed_text}"
            # One column stays free so the cursor itself cannot force a wrap.
            width_limit = console_width() - 1
            # During the first phase the two clocks are identical, so the total
            # is pure noise. On a narrow terminal it is dropped rather than
            # truncated: a carriage return only rewinds to the start of the last
            # wrapped row, so an over-long line would leave fragments behind.
            total_suffix = f" | total {total_elapsed_text}"
            if total_elapsed_text != phase_elapsed_text and len(line) + len(total_suffix) <= width_limit:
                line += total_suffix
            line = line[:width_limit]
            # Padding is computed on the plain string so escape codes never
            # affect the width used to erase the previous line.
            print(
                f"\r{paint(line.ljust(previous_width), 'cyan')}{erase_to_end()}",
                end="", flush=True,
            )
            previous_width = max(previous_width, len(line))

        if on_heartbeat is not None:
            on_heartbeat(now, status, phase_status, phase_started_at, phase_durations)
        if status in TERMINAL_STATES:
            break
        if task_timeout_seconds and now - started_at >= task_timeout_seconds:
            if previous_width:
                print()
            raise TaskStillRunningError(
                f"Task {task_id} exceeded the configured timeout of "
                f"{format_elapsed(task_timeout_seconds)} after a fresh status poll. "
                "The remote task may still be running; its ID remains in the recovery state."
            )
        time.sleep(poll_interval)

    if status != "completed":
        results = task.get("results") or {}
        raise TaskTerminalError(
            f"Task {task_id} ended with status {status}: {results.get('error') or results}"
        )

    report_results(task)
    video_url = completed_video_url(task, task_id)
    download_result = download(video_url, output)
    print(f"Saved: {display_path(output)}")
    print_video_metadata(download_result.get("media"))
    return download_result.get("media")

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
                if not -(2**63) <= parameters["seed"] <= 2**63 - 1:
                    raise RuntimeError(
                        f"Incremented seed for task {index + 1} exceeds signed 64-bit range"
                    )
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
                "videoReadyAt": None,
                "downloaded": False,
                "downloadProof": None,
                "unknownPolls": 0,
                "pollFailures": 0,
                "promoted": False,
                "media": None,
                "lastFailedTaskId": None,
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


def download_proof_for(job: dict, download_result: dict) -> dict:
    """Bind a validated local file to the exact remote task that produced it."""
    return {
        "taskId": job.get("taskId"),
        "videoUrl": job.get("videoUrl"),
        "fileSizeBytes": download_result.get("fileSizeBytes"),
        "sha256": download_result.get("sha256"),
        "verifiedAt": time.time(),
    }


def recover_parallel_output(job: dict) -> tuple[bool, bool]:
    """Trust a local chunk only when recovery metadata proves its provenance.

    Returns ``(trusted, changed)``. A legacy state can be upgraded after an
    interrupted post-download state save only when the output is newer than the
    saved task submission and the remote task ID/video URL are still present.
    """
    output = Path(job["output"])
    before = json.dumps(
        {
            "downloaded": job.get("downloaded"),
            "downloadProof": job.get("downloadProof"),
            "media": job.get("media"),
        },
        sort_keys=True,
        default=str,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        job["downloaded"] = False
        job["downloadProof"] = None
        job["media"] = None
        after = json.dumps(
            {
                "downloaded": job.get("downloaded"),
                "downloadProof": job.get("downloadProof"),
                "media": job.get("media"),
            },
            sort_keys=True,
            default=str,
        )
        return False, before != after

    proof = job.get("downloadProof")
    task_id = job.get("taskId")
    if isinstance(proof, dict):
        expected_url = proof.get("videoUrl")
        expected_size = proof.get("fileSizeBytes")
        expected_hash = proof.get("sha256")
        if (
            task_id
            and proof.get("taskId") == task_id
            and (not expected_url or expected_url == job.get("videoUrl"))
            and expected_size == output.stat().st_size
            and expected_hash
            and expected_hash == file_sha256(output)
        ):
            job["downloaded"] = True
            return True, before != json.dumps(
                {
                    "downloaded": job.get("downloaded"),
                    "downloadProof": job.get("downloadProof"),
                    "media": job.get("media"),
                },
                sort_keys=True,
                default=str,
            )
        # A proof mismatch means the validated file was changed or replaced. Never
        # reinterpret it through the weaker legacy recovery path.
        job["downloaded"] = False
        job["downloadProof"] = None
        job["media"] = None
        print(
            f"Ignoring changed chunk {int(job['index']) + 1}: {output.name}. "
            "Its size/hash no longer matches the saved validated download."
        )
        return False, True

    # Upgrade an older state that explicitly recorded a completed download, or
    # recover the small crash window after videoReadyAt was saved and the atomic
    # file replacement finished but before its proof was persisted.
    started_at = job.get("taskStartedAt")
    ready_at = job.get("videoReadyAt")
    legacy_downloaded = bool(job.get("downloaded"))
    recovery_boundary = ready_at or (started_at if legacy_downloaded else None)
    if task_id and job.get("videoUrl") and recovery_boundary:
        if output.stat().st_mtime + 2 >= float(recovery_boundary):
            media = validate_video_file(output)
            result = {
                "media": media,
                "fileSizeBytes": output.stat().st_size,
                "sha256": file_sha256(output),
            }
            job["media"] = media or job.get("media")
            job["downloadProof"] = download_proof_for(job, result)
            job["downloaded"] = True
            print(
                f"Recovered verified chunk {int(job['index']) + 1} from its saved task metadata."
            )
            return True, True

    job["downloaded"] = False
    job["downloadProof"] = None
    job["media"] = None
    print(
        f"Ignoring untrusted existing chunk {int(job['index']) + 1}: "
        f"{output.name}. It is not bound to a saved task and will be replaced only "
        "after a validated download."
    )
    after = json.dumps(
        {
            "downloaded": job.get("downloaded"),
            "downloadProof": job.get("downloadProof"),
            "media": job.get("media"),
        },
        sort_keys=True,
        default=str,
    )
    return False, before != after


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

    # Recover only outputs whose saved task metadata proves their provenance.
    recovery_changed = False
    for job in jobs:
        _, changed = recover_parallel_output(job)
        recovery_changed = recovery_changed or changed
    if recovery_changed and state_path is not None:
        save_state(state_path, state)

    if state.get("assembleParallel", True):
        # Fail before spending API credits rather than after every chunk is generated.
        run_ffmpeg(["-version"], "checking parallel-chunk assembly support")
        if state.get("sourceVideo") and args.include_source_video:
            require_h264_encoder()

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
                    "videoUrl": None,
                    "videoReadyAt": None,
                    "downloaded": False,
                    "downloadProof": None,
                    "media": None,
                    "pollFailures": 0,
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
                download_result = future.result()
            except Exception as error:
                raise RuntimeError(f"Chunk {index + 1} download failed: {error}") from error
            finally:
                download_futures.pop(index, None)
            job = by_index[index]
            job["media"] = download_result.get("media")
            job["downloadProof"] = download_proof_for(job, download_result)
            job["downloaded"] = True
            job["lastStatus"] = "downloaded"
            changed = True
            print(f"Saved chunk {index + 1}: {display_path(job['output'])}")
            print_video_metadata(job["media"], f"Chunk {index + 1}:")
            if state_path is not None:
                state["lastActiveAt"] = time.time()
                save_state(state_path, state)
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
                    f"Warning: no polling activity for "
                    f"{format_elapsed(poll_started - float(previous_poll))}; iOS may "
                    "have suspended a-Shell or the network stalled."
                )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(workers, len(active))
            ) as executor:
                futures = {
                    executor.submit(
                        poll_task_status, job["taskId"], username, password,
                        args.poll_retries, args.poll_retry_backoff,
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
                        poll_failures.append((job, error))

            now = time.time()
            terminal_errors = []
            uncertain_errors = []
            counts = {}
            poll_failure_limit = max(1, int(args.unknown_status_limit or 5))
            for job, error in poll_failures:
                number = int(job["index"]) + 1
                failures = int(job.get("pollFailures") or 0) + 1
                job["pollFailures"] = failures
                job["lastStatus"] = "poll-error"
                job["lastActiveAt"] = now
                counts["poll-error"] = counts.get("poll-error", 0) + 1
                print(
                    f"Chunk {number}: status unavailable after bounded retries "
                    f"({failures} consecutive polling cycle(s)): {error}"
                )
                if failures >= poll_failure_limit:
                    uncertain_errors.append((
                        number,
                        "poll-error",
                        f"task {job['taskId']} remains status-unknown after "
                        f"{failures} consecutive polling cycles",
                    ))
            for job, task in poll_results:
                status = task.get("status", UNKNOWN_STATUS)
                number = int(job["index"]) + 1
                track_task(job["taskId"], status)
                counts[status] = counts.get(status, 0) + 1
                job["pollFailures"] = 0
                if status == UNKNOWN_STATUS:
                    job["unknownPolls"] = int(job.get("unknownPolls") or 0) + 1
                    if (
                        args.unknown_status_limit
                        and job["unknownPolls"] >= args.unknown_status_limit
                    ):
                        uncertain_errors.append((
                            number, UNKNOWN_STATUS,
                            f"task {job['taskId']} reported unknown status "
                            f"{job['unknownPolls']} polls in a row",
                        ))
                else:
                    job["unknownPolls"] = 0
                job_parameters = job.get("parameters") or state["parameters"]
                if (
                    args.promote_priority_after
                    and status == "pending"
                    and not job.get("promoted")
                    and int(job_parameters.get("priority", 5)) > args.promote_priority_to
                    and now - float(job.get("taskStartedAt") or now) >= args.promote_priority_after
                ):
                    print(
                        f"Chunk {number} still queued; changing priority to "
                        f"{args.promote_priority_to}."
                    )
                    job["promoted"] = set_task_priority(
                        job["taskId"], args.promote_priority_to, username, password
                    )
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
                    job["videoUrl"] = completed_video_url(task, job["taskId"])
                    job["videoReadyAt"] = now
                    total = now - float(job.get("taskStartedAt") or now)
                    print_completion(
                        f"Chunk {number} completed in {format_elapsed(total)}", task
                    )
                    report_results(task, f"Chunk {number}:")
                elif status in TERMINAL_STATES:
                    results = task.get("results") or {}
                    failed_task_id = job.get("taskId")
                    terminal_errors.append((
                        int(job["index"]) + 1,
                        status,
                        f"task {failed_task_id}: {results.get('error') or results}",
                    ))
                    # Preserve evidence while allowing an intentional rerun of this chunk.
                    job["lastFailedTaskId"] = failed_task_id
                    job["taskId"] = None
                    job["taskStartedAt"] = None
                    job["videoReadyAt"] = None
                    job["phaseStatus"] = None

            if args.task_timeout:
                for job, task in poll_results:
                    status = task.get("status", UNKNOWN_STATUS)
                    started = float(job.get("taskStartedAt") or now)
                    if status not in TERMINAL_STATES and now - started >= args.task_timeout:
                        uncertain_errors.append((
                            int(job["index"]) + 1,
                            "local-timeout",
                            f"task {job['taskId']} is still {status} after a fresh poll "
                            f"and exceeded {format_elapsed(args.task_timeout)}",
                        ))

            # Fetch newly completed chunks now; do not wait for the whole batch.
            start_ready_downloads()
            saved_any = reap_downloads(False)

            state["lastActiveAt"] = now
            state["lastStatus"] = ", ".join(
                f"{name}:{count}" for name, count in sorted(counts.items())
            )
            if state_path is not None and (
                terminal_errors or uncertain_errors or poll_failures or saved_any
                or now - last_saved_at >= 15 or any(
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
            if uncertain_errors:
                number, status, details = uncertain_errors[0]
                raise TaskStillRunningError(
                    f"Chunk {number} monitoring stopped with {status}: {details}. "
                    "The remote task ID remains in recovery state; do not resubmit it."
                )
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
            reencode_source_timeline = bool(source_video and args.include_source_video)
            if reencode_source_timeline:
                combine_targets = [Path(source_video)] + combine_targets
            combine_segments(
                combine_targets,
                final_output,
                temporary_directory,
                effective_output_fps(state["parameters"], segments[0]),
                reencode=reencode_source_timeline,
                reference_segment=segments[0],
            )
        print(f"Saved assembled video: {display_path(final_output)}")
        report_video_metadata(final_output, "Combined:")
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
    if state["combineChain"] and state.get("sourceVideo") and args.include_source_video:
        require_h264_encoder()

    with tempfile.TemporaryDirectory(
        prefix=".img2video_chain_", dir=final_output.parent
    ) as temp_name:
        temporary_directory = Path(temp_name)

        while int(state["currentIndex"]) < len(prompts):
            index = int(state["currentIndex"])
            task_id = state.get("taskId")
            step_prompt = prompts[index]
            segment = segments[index]

            if len(prompts) > 1:
                print("")
                print(rule(f"Chain step {index + 1}/{len(prompts)}"))
            else:
                print("")
            if len(prompts) > 1 and args.show_prompts:
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
                    task_timeout_seconds=args.task_timeout,
                    poll_retry_limit=args.poll_retries,
                    poll_retry_backoff=args.poll_retry_backoff,
                    promote_priority_after=args.promote_priority_after,
                    promote_priority_to=args.promote_priority_to,
                    on_submitted=remember_submission,
                    on_heartbeat=remember_heartbeat,
                )
            except TaskStillRunningError:
                # Preserve the task ID: a local timeout/unknown response is not proof
                # that the remote task stopped, and resubmitting could spend twice.
                if state_path is not None:
                    save_state(state_path, state)
                raise
            except TaskTerminalError:
                # A confirmed remote terminal failure can be intentionally resubmitted.
                state["lastFailedTaskId"] = state.get("taskId")
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
        reencode_source_timeline = bool(
            state["combineChain"] and source_video and args.include_source_video
        )
        if reencode_source_timeline:
            combine_targets = [Path(source_video)] + combine_targets

        if state["combineChain"] and len(combine_targets) > 1:
            combine_segments(
                combine_targets,
                final_output,
                temporary_directory,
                effective_output_fps(parameters, segments[0]),
                reencode=reencode_source_timeline,
                reference_segment=segments[0],
            )
            print(f"Saved combined video: {display_path(final_output)}")
            report_video_metadata(final_output, "Combined:")
        elif len(segments) == 1:
            print(f"Saved: {display_path(segments[0])}")
        else:
            print("Saved chained segments:")
            for segment in segments:
                print(f"  {segment}")

    if state_path is not None and state_path.exists():
        state_path.unlink()
        print(f"Recovery state cleared: {state_path.name}")
    return 0



def normalize_recovery_parameters(state: dict, args) -> None:
    """Upgrade old local recovery metadata without changing an existing remote task."""
    parameter_sets = [state.get("parameters")]
    if state.get("mode") == "parallel":
        parameter_sets.extend(job.get("parameters") for job in state.get("jobs", []))
    warned_model = False
    warned_priority = False
    for parameters in parameter_sets:
        if not isinstance(parameters, dict):
            continue
        if not parameters.get("model"):
            parameters["model"] = args.model
            warned_model = True
        if parameters.get("priority") is None:
            parameters["priority"] = 1 if parameters.get("isFast") else args.priority
            warned_priority = True
        parameters.setdefault("tags", [])
        parameters.setdefault("interpolationFps", DEFAULT_INTERPOLATION_FPS)
        # A resumed run reuses these stored parameters verbatim instead of the
        # freshly parsed CLI values. interpolationFps is validated against the
        # current documented enum, not silently rewritten to a model-derived
        # value -- but only when applyInterpolation is actually true, so an
        # inactive stored preference that will never reach the API cannot block
        # resuming an otherwise-valid recovery state.
        if parameters.get("applyInterpolation"):
            parameters["interpolationFps"] = validate_interpolation_fps(
                parameters["interpolationFps"], source="recovery-state interpolationFps"
            )
        else:
            try:
                parameters["interpolationFps"] = int(parameters["interpolationFps"])
            except (TypeError, ValueError):
                parameters["interpolationFps"] = DEFAULT_INTERPOLATION_FPS
        parameters.setdefault("loras", [])
        parameters.pop("isFast", None)
    if warned_model:
        print(
            f"Warning: recovery state predates explicit model support; using {args.model}. "
            "Existing submitted task IDs are not resubmitted."
        )
    if warned_priority:
        print("Warning: recovery state priority was upgraded from deprecated isFast metadata.")


def main() -> int:
    configure_color(preferred_color_mode())
    print(rule(Path(__file__).name))
    print(f"  build       {SCRIPT_BUILD}")
    print("  folder      " + paint(shorten_path(SCRIPT_DIRECTORY, keep=1), "dim"))
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
        normalize_recovery_parameters(state, args)

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
                result = run_plan(state, args, username, password, state_path)
                return finish_run(result, args.play_completed_video, state)
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
            print(
                f"  {index}. seed={override['seed']}"
                + (f" | {prompt}" if args.show_prompts else "")
            )
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

    print(rule("Run plan"))
    print(f"  mode        {args.generation_mode} | {len(prompts)} prompt task(s)")
    print(f"  model       {args.model} | performance={args.performance}")
    print(f"  request     {args.frames} frames @ {args.fps} FPS | {args.resolution}")
    print(f"  queue       priority={args.priority}")
    output_folder = display_dir(output.parent)
    if output_folder != ".":
        print("  folder      " + paint(output_folder, "dim"))
    print("  timing      " + estimated_output_description(generation_parameters(args)))
    print(rule())
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
        result = run_plan(state, args, username, password, state_path)
        return finish_run(result, args.play_completed_video, state)
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
