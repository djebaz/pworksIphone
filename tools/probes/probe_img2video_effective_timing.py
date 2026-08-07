#!/usr/bin/env python3
"""Measure the effective FPS and duration of an ArtWorks image-to-video result.

Default experiment:
    model      = ltx-2.3
    fps        = 10
    numFrames  = 200
    resolution = 480p

Unlike the validation probes, this script lets the task complete, downloads the
video, then measures the actual encoded frame rate, frame count, dimensions,
and duration.

It imports the networking and download functions from the existing working
img2video client, preserving its credentials, headers, user agent, and API
behavior.

Primary analysis uses ffprobe. If ffprobe is unavailable, it falls back to
ffmpeg and parses its output.

Example:

    python3 probe_img2video_effective_timing.py input.jpg \
        --client "img2video_iphone(5).py"

Optional Wan comparison:

    python3 probe_img2video_effective_timing.py input.jpg \
        --client "img2video_iphone(5).py" \
        --compare-wan
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TERMINAL_STATES = {"completed", "failed", "canceled", "timeout"}
MODELS = ("wan-2.2", "ltx-2.3")


def find_default_client() -> Path | None:
    for name in (
        "img2video_iphone.py",
        "img2video_iphone(5).py",
        "img2video_iphone_timing_probe_v2.py",
        "img2video_iphone_timing_probe.py",
    ):
        path = SCRIPT_DIR / name
        if path.is_file():
            return path
    return None


def load_client(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "artworks_img2video_client",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import client: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    required = (
        "api_request",
        "task_request_data",
        "encode_image",
        "load_credentials",
    )
    missing = [name for name in required if not callable(getattr(module, name, None))]
    if missing:
        raise RuntimeError(
            f"{path.name} is missing required function(s): {', '.join(missing)}"
        )

    if hasattr(module, "CREDENTIALS_FILE"):
        module.CREDENTIALS_FILE = path.parent / "artworks_credentials.txt"

    return module


def task_video_url(task: dict[str, Any]) -> str:
    helper = task.get("results") or {}
    try:
        return str(helper["data"]["video"]["url"])
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Completed task has no results.data.video.url: {helper}"
        ) from exc


def safe_download(client: ModuleType, url: str, destination: Path) -> None:
    download_fn = getattr(client, "download", None)
    if callable(download_fn):
        download_fn(url, destination)
        return

    # This path is only a fallback for clients without download().
    from urllib.request import Request, urlopen

    request = Request(
        url,
        headers={
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
            "User-Agent": getattr(
                client,
                "IPHONE_SAFARI_USER_AGENT",
                "Mozilla/5.0",
            ),
        },
    )
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urlopen(request, timeout=300) as response, partial.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def parse_fraction(value: Any) -> float | None:
    if value in (None, "", "N/A", "0/0"):
        return None
    try:
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            result = float(Fraction(str(value)))
        return result if math.isfinite(result) else None
    except (ValueError, ZeroDivisionError):
        return None


def parse_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_ffprobe(video: Path) -> dict[str, Any] | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None

    command = [
        executable,
        "-v", "error",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries",
        (
            "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,"
            "nb_frames,nb_read_frames,duration,time_base:"
            "format=duration,size,bit_rate"
        ),
        "-of", "json",
        str(video),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed ({completed.returncode}): {completed.stderr.strip()}"
        )

    raw = json.loads(completed.stdout)
    streams = raw.get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe found no video stream")

    stream = streams[0]
    fmt = raw.get("format") or {}

    frame_count = (
        parse_int(stream.get("nb_read_frames"))
        or parse_int(stream.get("nb_frames"))
    )
    duration = (
        parse_float(stream.get("duration"))
        or parse_float(fmt.get("duration"))
    )
    measured_fps = (
        frame_count / duration
        if frame_count is not None and duration and duration > 0
        else None
    )

    return {
        "tool": "ffprobe",
        "codec": stream.get("codec_name"),
        "width": parse_int(stream.get("width")),
        "height": parse_int(stream.get("height")),
        "rFrameRate": parse_fraction(stream.get("r_frame_rate")),
        "avgFrameRate": parse_fraction(stream.get("avg_frame_rate")),
        "frameCount": frame_count,
        "durationSeconds": duration,
        "measuredFpsFromFramesAndDuration": measured_fps,
        "timeBase": stream.get("time_base"),
        "fileSizeBytes": parse_int(fmt.get("size")) or video.stat().st_size,
        "bitRate": parse_int(fmt.get("bit_rate")),
        "raw": raw,
    }


def hms_to_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def run_ffmpeg_fallback(video: Path) -> dict[str, Any] | None:
    executable = shutil.which("ffmpeg")
    if not executable:
        return None

    # Decode the stream to count actual frames. ffmpeg writes progress to stderr.
    command = [
        executable,
        "-hide_banner",
        "-i", str(video),
        "-map", "0:v:0",
        "-an",
        "-f", "null",
        "-",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = completed.stderr

    duration_matches = re.findall(
        r"Duration:\s*(\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
        stderr,
    )
    encoded_fps_matches = re.findall(
        r"Video:.*?(\d+(?:\.\d+)?)\s+fps\b",
        stderr,
    )
    frame_matches = re.findall(r"\bframe=\s*(\d+)", stderr)
    time_matches = re.findall(
        r"\btime=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
        stderr,
    )
    dimension_match = re.search(
        r"Video:.*?(\d{2,5})x(\d{2,5})",
        stderr,
    )

    frame_count = int(frame_matches[-1]) if frame_matches else None
    decoded_time = hms_to_seconds(time_matches[-1]) if time_matches else None
    container_duration = (
        hms_to_seconds(duration_matches[-1])
        if duration_matches
        else None
    )
    duration = decoded_time or container_duration
    measured_fps = (
        frame_count / duration
        if frame_count is not None and duration and duration > 0
        else None
    )

    return {
        "tool": "ffmpeg",
        "codec": None,
        "width": int(dimension_match.group(1)) if dimension_match else None,
        "height": int(dimension_match.group(2)) if dimension_match else None,
        "rFrameRate": (
            float(encoded_fps_matches[-1])
            if encoded_fps_matches
            else None
        ),
        "avgFrameRate": None,
        "frameCount": frame_count,
        "durationSeconds": duration,
        "containerDurationSeconds": container_duration,
        "decodedTimelineSeconds": decoded_time,
        "measuredFpsFromFramesAndDuration": measured_fps,
        "fileSizeBytes": video.stat().st_size,
        "rawStderr": stderr,
        "returnCode": completed.returncode,
    }


def analyze_video(video: Path) -> dict[str, Any]:
    analysis = run_ffprobe(video)
    if analysis is not None:
        return analysis

    analysis = run_ffmpeg_fallback(video)
    if analysis is not None:
        return analysis

    return {
        "tool": None,
        "error": (
            "Neither ffprobe nor ffmpeg was found. The video was downloaded, "
            "but its timing metadata could not be measured."
        ),
        "fileSizeBytes": video.stat().st_size,
    }


def classify_timing(
    requested_fps: int,
    requested_frames: int,
    media: dict[str, Any],
) -> dict[str, Any]:
    requested_duration = requested_frames / requested_fps
    forced_16_duration = requested_frames / 16
    actual_duration = parse_float(media.get("durationSeconds"))
    actual_fps = (
        parse_float(media.get("measuredFpsFromFramesAndDuration"))
        or parse_float(media.get("avgFrameRate"))
        or parse_float(media.get("rFrameRate"))
    )
    actual_frames = parse_int(media.get("frameCount"))

    def delta(actual: float | None, expected: float) -> float | None:
        return None if actual is None else actual - expected

    conclusion = "undetermined"
    if actual_fps is not None:
        if abs(actual_fps - requested_fps) <= 0.25:
            conclusion = "encoded close to requested FPS"
        elif abs(actual_fps - 16) <= 0.25:
            conclusion = "encoded close to 16 FPS"
        else:
            conclusion = "encoded at another FPS"

    return {
        "requestedDurationSeconds": requested_duration,
        "durationIfForcedTo16Fps": forced_16_duration,
        "actualDurationSeconds": actual_duration,
        "actualFrameCount": actual_frames,
        "actualFps": actual_fps,
        "durationDeltaFromRequestedSeconds": delta(
            actual_duration,
            requested_duration,
        ),
        "durationDeltaFromForced16Seconds": delta(
            actual_duration,
            forced_16_duration,
        ),
        "conclusion": conclusion,
    }


def poll_task(
    client: ModuleType,
    task_id: str,
    username: str,
    password: str,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    started = time.time()
    previous_status: str | None = None

    while True:
        task = client.api_request(
            "GET",
            f"/api/v3/tasks/{task_id}",
            username,
            password,
        )
        status = str(task.get("status", "unknown"))
        elapsed = time.time() - started

        if status != previous_status:
            print(f"  status={status} elapsed={elapsed:.1f}s")
            previous_status = status
        elif status == "pending":
            position = task.get("position")
            suffix = f" position={position}" if position is not None else ""
            print(
                f"\r  status=pending elapsed={elapsed:.1f}s{suffix}",
                end="",
                flush=True,
            )

        if status in TERMINAL_STATES:
            if status == "pending":
                print()
            return task

        if timeout > 0 and elapsed >= timeout:
            raise TimeoutError(
                f"Task {task_id} did not finish within {timeout:.0f} seconds"
            )

        time.sleep(max(0.1, poll_interval))


def make_request(
    client: ModuleType,
    image_data: str,
    prompt: str,
    model: str,
    fps: int,
    num_frames: int,
    resolution: str,
    performance: str,
    priority: int,
) -> dict[str, Any]:
    parameters = {
        "resolution": resolution,
        "performance": performance,
        "fps": fps,
        "numFrames": num_frames,
        "applyOptimizations": False,
        "applyInterpolation": False,
        "interpolationFps": 24,
        "seed": None,
        "loras": [],
        "isFast": False,
        "batchId": None,
    }
    request = client.task_request_data(image_data, prompt, parameters)
    request["payload"]["model"] = model

    # Authenticated Swagger exposes priority and deprecates isFast.
    request["priority"] = priority
    request.pop("isFast", None)
    return request


def run_experiment(
    client: ModuleType,
    username: str,
    password: str,
    image_data: str,
    image_path: Path,
    prompt: str,
    model: str,
    fps: int,
    num_frames: int,
    resolution: str,
    performance: str,
    priority: int,
    poll_interval: float,
    timeout: float,
    output_directory: Path,
) -> dict[str, Any]:
    request = make_request(
        client,
        image_data,
        prompt,
        model,
        fps,
        num_frames,
        resolution,
        performance,
        priority,
    )

    print()
    print(
        f"Submitting {model}: fps={fps}, frames={num_frames}, "
        f"resolution={resolution}"
    )
    created = client.api_request(
        "POST",
        "/api/v3/tasks",
        username,
        password,
        request,
    )
    task_id = created.get("id") if isinstance(created, dict) else None
    if not task_id:
        raise RuntimeError(f"API returned no task ID: {created}")
    task_id = str(task_id)
    print(f"  task={task_id}")

    task = poll_task(
        client,
        task_id,
        username,
        password,
        poll_interval,
        timeout,
    )
    status = str(task.get("status", "unknown"))
    if status != "completed":
        results = task.get("results") or {}
        raise RuntimeError(
            f"Task {task_id} ended with status {status}: "
            f"{results.get('error') or results}"
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / (
        f"{image_path.stem}_{model}_requested-{fps}fps-"
        f"{num_frames}frames-{resolution}.mp4"
    )

    url = task_video_url(task)
    print(f"  downloading={output.name}")
    safe_download(client, url, output)

    print("  measuring video timing")
    media = analyze_video(output)
    timing = classify_timing(fps, num_frames, media)

    print(
        "  result: "
        f"duration={timing['actualDurationSeconds']}s, "
        f"frames={timing['actualFrameCount']}, "
        f"fps={timing['actualFps']}"
    )
    print(f"  conclusion: {timing['conclusion']}")

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "taskId": task_id,
        "request": {
            **request,
            "payload": {
                **request["payload"],
                "image": f"<redacted image: {len(image_data)} chars>",
            },
        },
        "task": task,
        "videoPath": str(output),
        "videoUrl": url,
        "media": media,
        "timing": timing,
    }


def main() -> int:
    default_client = find_default_client()

    parser = argparse.ArgumentParser(
        description=(
            "Generate an image-to-video task and measure the actual encoded "
            "FPS, frame count, and duration."
        )
    )
    parser.add_argument("image", type=Path, help="input image")
    parser.add_argument(
        "--client",
        type=Path,
        default=default_client,
        help="working img2video Python client",
    )
    parser.add_argument(
        "--model",
        choices=MODELS,
        default="ltx-2.3",
    )
    parser.add_argument(
        "--compare-wan",
        action="store_true",
        help="also generate the same experiment with wan-2.2",
    )
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument(
        "--resolution",
        choices=("480p", "720p", "1080p"),
        default="480p",
    )
    parser.add_argument(
        "--performance",
        choices=("speed", "quality", "express"),
        default="speed",
    )
    parser.add_argument(
        "--priority",
        type=int,
        choices=range(1, 6),
        default=5,
    )
    parser.add_argument(
        "--prompt",
        default="Static camera, subtle natural movement.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600.0,
        help="per-task timeout in seconds; 0 disables the timeout",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=SCRIPT_DIR / "timing_probe_output",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON report path",
    )
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if args.client is None:
        raise FileNotFoundError(
            "No working img2video client found beside this script. "
            "Pass --client 'img2video_iphone(5).py'"
        )

    client_path = args.client.expanduser().resolve()
    if not client_path.is_file():
        raise FileNotFoundError(f"Client not found: {client_path}")

    client = load_client(client_path)
    username, password = client.load_credentials()
    image_data = client.encode_image(image_path)

    models = [args.model]
    if args.compare_wan and "wan-2.2" not in models:
        models.append("wan-2.2")

    experiments: list[dict[str, Any]] = []
    for model in models:
        experiments.append(
            run_experiment(
                client=client,
                username=username,
                password=password,
                image_data=image_data,
                image_path=image_path,
                prompt=args.prompt,
                model=model,
                fps=args.fps,
                num_frames=args.frames,
                resolution=args.resolution,
                performance=args.performance,
                priority=args.priority,
                poll_interval=args.poll_interval,
                timeout=args.timeout,
                output_directory=args.output_directory.expanduser().resolve(),
            )
        )

    report = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "client": str(client_path),
        "requested": {
            "fps": args.fps,
            "numFrames": args.frames,
            "resolution": args.resolution,
            "performance": args.performance,
        },
        "expectedRequestedDurationSeconds": args.frames / args.fps,
        "expectedDurationAt16FpsSeconds": args.frames / 16,
        "experiments": experiments,
    }

    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else SCRIPT_DIR
        / f"img2video_effective_timing_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print()
    print("Timing comparison")
    print("=================")
    print(f"Requested duration: {args.frames / args.fps:.6f}s")
    print(f"Duration at forced 16 FPS: {args.frames / 16:.6f}s")
    for experiment in experiments:
        timing = experiment["timing"]
        model = experiment["request"]["payload"]["model"]
        print(
            f"{model}: duration={timing['actualDurationSeconds']}s, "
            f"frames={timing['actualFrameCount']}, "
            f"fps={timing['actualFps']} — {timing['conclusion']}"
        )
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. The remote task may still be running.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
