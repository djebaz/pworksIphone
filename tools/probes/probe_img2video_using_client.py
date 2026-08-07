#!/usr/bin/env python3
"""Focused ArtWorks image-to-video API probe.

This script imports the networking and payload functions from the existing
img2video client, so requests have exactly the same authentication, headers,
User-Agent, encoding, and error handling as the working generator.

Tests only:
- model = wan-2.2
- model = ltx-2.3
- fps = 8
- fps = 24
- numFrames = 160
- numFrames = 360
- resolution = 1080p

Each accepted task is cancelled immediately after a short configurable delay.
Results are written to a timestamped JSONL log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def find_default_client() -> Path | None:
    candidates = (
        "img2video_iphone.py",
        "img2video_iphone(5).py",
        "img2video_iphone_timing_probe_v2.py",
        "img2video_iphone_timing_probe.py",
    )
    for name in candidates:
        path = SCRIPT_DIR / name
        if path.is_file():
            return path
    return None


def load_client(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("artworks_img2video_client", path)
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

    # Make credential lookup deterministic: credentials beside the imported client.
    if hasattr(module, "CREDENTIALS_FILE"):
        module.CREDENTIALS_FILE = path.parent / "artworks_credentials.txt"

    return module


def baseline_parameters() -> dict[str, Any]:
    """Parameters required by the existing task_request_data() function."""
    return {
        "resolution": "480p",
        "performance": "speed",
        "fps": 16,
        "numFrames": 24,
        "applyOptimizations": False,
        "applyInterpolation": False,
        "interpolationFps": 24,
        "seed": None,
        "loras": [],
        "isFast": False,
        "batchId": None,
    }


def build_cases() -> list[tuple[str, dict[str, Any]]]:
    return [
        ("model_wan-2.2", {"model": "wan-2.2"}),
        ("model_ltx-2.3", {"model": "ltx-2.3"}),
        ("fps_8", {"fps": 8}),
        ("fps_24", {"fps": 24}),
        ("frames_160", {"numFrames": 160}),
        ("frames_360", {"numFrames": 360}),
        ("resolution_1080p", {"resolution": "1080p"}),
    ]


def redact_request(request: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(request))
    image = safe.get("payload", {}).get("image")
    if isinstance(image, str):
        safe["payload"]["image"] = f"<redacted image: {len(image)} base64 chars>"
    return safe


def write_record(handle, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def main() -> int:
    default_client = find_default_client()

    parser = argparse.ArgumentParser(
        description="Probe selected image-to-video schema values using the working client."
    )
    parser.add_argument("image", type=Path, help="input image")
    parser.add_argument(
        "--client",
        type=Path,
        default=default_client,
        help="working img2video Python file",
    )
    parser.add_argument(
        "--prompt",
        default="Static camera, subtle natural movement.",
    )
    parser.add_argument(
        "--cancel-delay",
        type=float,
        default=0.5,
        help="seconds to wait before cancelling an accepted task",
    )
    parser.add_argument(
        "--between-tests",
        type=float,
        default=0.2,
        help="seconds between test cases",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL output path",
    )
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if args.client is None:
        raise FileNotFoundError(
            "No img2video client found beside this probe. "
            "Pass it with --client img2video_iphone.py"
        )

    client_path = args.client.expanduser().resolve()
    if not client_path.is_file():
        raise FileNotFoundError(f"Client not found: {client_path}")

    client = load_client(client_path)
    username, password = client.load_credentials()
    image_data = client.encode_image(image_path)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = (
        args.log.expanduser().resolve()
        if args.log
        else SCRIPT_DIR / f"img2video_probe_{timestamp}.jsonl"
    )

    cases = build_cases()
    accepted = 0
    rejected = 0
    cancelled = 0
    cancel_failed = 0

    print(f"Client: {client_path.name}")
    print(f"Cases: {len(cases)}")
    print(f"Log: {log_path}")

    with log_path.open("w", encoding="utf-8") as log:
        for index, (name, overrides) in enumerate(cases, 1):
            parameters = baseline_parameters()

            # task_request_data() only knows existing fields. Apply known overrides
            # to parameters first, then add new schema fields such as model.
            model_value = overrides.get("model")
            for key, value in overrides.items():
                if key != "model":
                    parameters[key] = value

            request = client.task_request_data(
                image_data,
                args.prompt,
                parameters,
            )
            if model_value is not None:
                request["payload"]["model"] = model_value

            started = time.time()
            created: Any = None
            create_error: str | None = None
            task_id: str | None = None
            cancel_response: Any = None
            cancel_error: str | None = None

            print(f"[{index}/{len(cases)}] {name}")

            try:
                created = client.api_request(
                    "POST",
                    "/api/v3/tasks",
                    username,
                    password,
                    request,
                )
                if isinstance(created, dict):
                    raw_id = created.get("id")
                    if raw_id:
                        task_id = str(raw_id)
            except Exception as exc:
                create_error = f"{type(exc).__name__}: {exc}"

            if task_id:
                accepted += 1
                time.sleep(max(0.0, args.cancel_delay))
                try:
                    cancel_response = client.api_request(
                        "POST",
                        f"/api/v3/tasks/{task_id}/cancel",
                        username,
                        password,
                    )
                    cancelled += 1
                except Exception as exc:
                    cancel_error = f"{type(exc).__name__}: {exc}"
                    cancel_failed += 1
            else:
                rejected += 1

            record = {
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "test": name,
                "overrides": overrides,
                "request": redact_request(request),
                "createResponse": created,
                "createError": create_error,
                "taskId": task_id,
                "cancelResponse": cancel_response,
                "cancelError": cancel_error,
                "elapsedSeconds": round(time.time() - started, 3),
            }
            write_record(log, record)

            if task_id:
                cancel_state = "cancelled" if cancel_error is None else "cancel failed"
                print(f"  accepted: {task_id} — {cancel_state}")
            else:
                print(f"  rejected: {create_error or created}")

            time.sleep(max(0.0, args.between_tests))

    print()
    print(f"Accepted: {accepted}")
    print(f"Rejected: {rejected}")
    print(f"Cancelled: {cancelled}")
    print(f"Cancel failed: {cancel_failed}")
    print(f"Results: {log_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
