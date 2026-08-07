#!/usr/bin/env python3
"""Discover ArtWorks image-to-video parameter constraints from API errors.

Instead of brute-forcing every valid combination, this script deliberately sends
invalid values. The API validation messages are parsed to discover:

- enum options, such as model, resolution, performance, and interpolationFps
- model-specific numeric minimums and maximums for fps and numFrames
- basic expected types for boolean/integer/array fields

The script imports the networking functions from an existing working img2video
client, so it reuses its credentials, image encoding, headers, user agent,
authentication, and API error handling.

Typical usage:

    python3 probe_img2video_discover_values.py input.jpg \
        --client "img2video_iphone(5).py"

Outputs:

    img2video_discovery_<timestamp>.jsonl
    img2video_discovery_<timestamp>.json
    img2video_discovery_<timestamp>.csv

Most requests should be rejected by design. If an invalid probe is unexpectedly
accepted, the resulting task is cancelled immediately.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent

MODELS = ("wan-2.2", "ltx-2.3")
INVALID_ENUM = "__ARTWORKS_DISCOVERY_INVALID_OPTION__"
VERY_LOW = -999_999_999
VERY_HIGH = 999_999_999


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


def baseline_parameters() -> dict[str, Any]:
    """Safe parameters expected by task_request_data()."""
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


def make_base_request(
    client: ModuleType,
    image_data: str,
    prompt: str,
    model: str,
) -> dict[str, Any]:
    request = client.task_request_data(
        image_data,
        prompt,
        baseline_parameters(),
    )
    payload = request.setdefault("payload", {})
    payload.update({
        "model": model,
        "fps": 16,
        "numFrames": 24,
        "resolution": "480p",
        "performance": "speed",
        "applyInterpolation": False,
        "applyOptimizations": False,
    })
    return request


def build_probes(
    models: list[str],
    include_type_probes: bool,
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = [
        {
            "name": "model enum",
            "model_context": None,
            "field": "model",
            "kind": "enum",
            "value": INVALID_ENUM,
            "changes": {"model": INVALID_ENUM},
        },
    ]

    for model in models:
        probes.extend([
            {
                "name": f"{model} resolution enum",
                "model_context": model,
                "field": "resolution",
                "kind": "enum",
                "value": INVALID_ENUM,
                "changes": {"resolution": INVALID_ENUM},
            },
            {
                "name": f"{model} performance enum",
                "model_context": model,
                "field": "performance",
                "kind": "enum",
                "value": INVALID_ENUM,
                "changes": {"performance": INVALID_ENUM},
            },
            {
                "name": f"{model} interpolationFps enum",
                "model_context": model,
                "field": "interpolationFps",
                "kind": "enum",
                "value": VERY_HIGH,
                "changes": {
                    "applyInterpolation": True,
                    "interpolationFps": VERY_HIGH,
                },
            },
            {
                "name": f"{model} fps minimum",
                "model_context": model,
                "field": "fps",
                "kind": "minimum",
                "value": VERY_LOW,
                "changes": {"fps": VERY_LOW},
            },
            {
                "name": f"{model} fps maximum",
                "model_context": model,
                "field": "fps",
                "kind": "maximum",
                "value": VERY_HIGH,
                "changes": {"fps": VERY_HIGH},
            },
            {
                "name": f"{model} numFrames minimum",
                "model_context": model,
                "field": "numFrames",
                "kind": "minimum",
                "value": VERY_LOW,
                "changes": {"numFrames": VERY_LOW},
            },
            {
                "name": f"{model} numFrames maximum",
                "model_context": model,
                "field": "numFrames",
                "kind": "maximum",
                "value": VERY_HIGH,
                "changes": {"numFrames": VERY_HIGH},
            },
        ])

        if include_type_probes:
            probes.extend([
                {
                    "name": f"{model} applyInterpolation type",
                    "model_context": model,
                    "field": "applyInterpolation",
                    "kind": "type",
                    "value": INVALID_ENUM,
                    "changes": {"applyInterpolation": INVALID_ENUM},
                },
                {
                    "name": f"{model} applyOptimizations type",
                    "model_context": model,
                    "field": "applyOptimizations",
                    "kind": "type",
                    "value": INVALID_ENUM,
                    "changes": {"applyOptimizations": INVALID_ENUM},
                },
                {
                    "name": f"{model} seed type",
                    "model_context": model,
                    "field": "seed",
                    "kind": "type",
                    "value": INVALID_ENUM,
                    "changes": {"seed": INVALID_ENUM},
                },
                {
                    "name": f"{model} loras type",
                    "model_context": model,
                    "field": "loras",
                    "kind": "type",
                    "value": INVALID_ENUM,
                    "changes": {"loras": INVALID_ENUM},
                },
            ])

    return probes


def redact_request(request: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(request))
    image = safe.get("payload", {}).get("image")
    if isinstance(image, str):
        safe["payload"]["image"] = f"<redacted image: {len(image)} chars>"
    return safe


def get_task_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    value = response.get("id") or response.get("taskId")
    return str(value) if value else None


def compact_text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value.replace("\r", " ").replace("\n", " ")).strip()


def exception_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def extract_api_messages(error_text: str | None) -> list[str]:
    """Extract the API's errors array from the client's RuntimeError text."""
    if not error_text:
        return []

    # The working client commonly raises:
    # RuntimeError: API error 400: {"errors":["..."]}
    match = re.search(r"API error\s+\d+\s*:\s*(\{.*\})\s*$", error_text, re.DOTALL)
    if match:
        try:
            body = json.loads(match.group(1))
            errors = body.get("errors")
            if isinstance(errors, list):
                return [str(item) for item in errors]
            if errors is not None:
                return [str(errors)]
        except json.JSONDecodeError:
            pass

    return [compact_text(error_text) or error_text]


def parse_scalar(value: str) -> Any:
    value = value.strip().strip("'\"")
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", value):
        try:
            return float(value)
        except ValueError:
            return value
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none"}:
        return None
    return value


def parse_discovery(messages: list[str]) -> dict[str, Any]:
    discovered: dict[str, Any] = {}

    for message in messages:
        # Example:
        # unsupported option '2160p'. Available options: 480p, 720p, 1080p
        option_match = re.search(
            r"Available options:\s*(.+?)(?:[\"'}\]]\s*$|$)",
            message,
            re.IGNORECASE,
        )
        if option_match:
            raw = option_match.group(1).strip().rstrip(".")
            options = [
                item.strip().strip("'\"")
                for item in raw.split(",")
                if item.strip()
            ]
            if options:
                discovered["availableOptions"] = options

        # Example:
        # condition: max { 16 } for wan-2.2, actual: 24
        for condition, raw_value, raw_model in re.findall(
            r"condition:\s*(min|max)\s*\{\s*([^}]+?)\s*\}"
            r"(?:\s*for\s*([^,]+?))?\s*,",
            message,
            re.IGNORECASE,
        ):
            key = "minimum" if condition.lower() == "min" else "maximum"
            discovered[key] = parse_scalar(raw_value)
            if raw_model:
                discovered["constraintModel"] = raw_model.strip()

        # Alternate forms such as "minimum: 8" or "maximum 24".
        minimum_match = re.search(
            r"\bminimum(?:\s+value)?\s*(?:is|:|=)?\s*(-?\d+(?:\.\d+)?)",
            message,
            re.IGNORECASE,
        )
        if minimum_match and "minimum" not in discovered:
            discovered["minimum"] = parse_scalar(minimum_match.group(1))

        maximum_match = re.search(
            r"\bmaximum(?:\s+value)?\s*(?:is|:|=)?\s*(-?\d+(?:\.\d+)?)",
            message,
            re.IGNORECASE,
        )
        if maximum_match and "maximum" not in discovered:
            discovered["maximum"] = parse_scalar(maximum_match.group(1))

        # Common JSON decoder/unmarshal type messages.
        type_patterns = (
            r"cannot unmarshal \w+ into Go struct field .* of type ([\w\[\].*]+)",
            r"expected\s+(?:type\s+)?([A-Za-z0-9_\[\].*]+)",
            r"must be (?:an? )?([A-Za-z0-9_\[\].*]+)",
            r"parse \w+:\s+.*?(?:expected|want)\s+([A-Za-z0-9_\[\].*]+)",
        )
        for pattern in type_patterns:
            type_match = re.search(pattern, message, re.IGNORECASE)
            if type_match:
                discovered.setdefault("expectedType", type_match.group(1))
                break

    return discovered


def merge_discovery(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key == "availableOptions":
            existing = target.setdefault(key, [])
            for option in value:
                if option not in existing:
                    existing.append(option)
        else:
            target[key] = value


def build_summary(records: list[dict[str, Any]], models: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "deliberately invalid values parsed from API validation errors",
        "totals": {
            "probes": len(records),
            "rejectedAsExpected": sum(not record["accepted"] for record in records),
            "unexpectedlyAccepted": sum(record["accepted"] for record in records),
        },
        "global": {},
        "models": {model: {} for model in models},
        "records": [],
    }

    for record in records:
        model = record["modelContext"]
        field = record["field"]
        destination = (
            summary["global"]
            if model is None
            else summary["models"].setdefault(model, {})
        )
        field_summary = destination.setdefault(field, {})
        merge_discovery(field_summary, record["discovered"])

        field_summary.setdefault("probeResults", []).append({
            "kind": record["kind"],
            "sentValue": record["sentValue"],
            "accepted": record["accepted"],
            "messages": record["apiMessages"],
        })

        summary["records"].append({
            "name": record["name"],
            "modelContext": model,
            "field": field,
            "kind": record["kind"],
            "accepted": record["accepted"],
            "discovered": record["discovered"],
        })

    return summary


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    columns = [
        "name",
        "modelContext",
        "field",
        "kind",
        "sentValue",
        "accepted",
        "availableOptions",
        "minimum",
        "maximum",
        "constraintModel",
        "expectedType",
        "error",
        "taskId",
        "cancelError",
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        for record in records:
            discovered = record["discovered"]
            writer.writerow({
                "name": record["name"],
                "modelContext": record["modelContext"] or "",
                "field": record["field"],
                "kind": record["kind"],
                "sentValue": json.dumps(record["sentValue"], ensure_ascii=False),
                "accepted": record["accepted"],
                "availableOptions": ", ".join(
                    str(value) for value in discovered.get("availableOptions", [])
                ),
                "minimum": discovered.get("minimum", ""),
                "maximum": discovered.get("maximum", ""),
                "constraintModel": discovered.get("constraintModel", ""),
                "expectedType": discovered.get("expectedType", ""),
                "error": compact_text(record.get("createError")) or "",
                "taskId": record.get("taskId") or "",
                "cancelError": compact_text(record.get("cancelError")) or "",
            })


def print_summary(summary: dict[str, Any]) -> None:
    print()
    print("Discovered constraints")
    print("======================")

    global_fields = summary.get("global", {})
    if global_fields:
        print("Global:")
        for field, values in global_fields.items():
            clean = {k: v for k, v in values.items() if k != "probeResults"}
            print(f"  {field}: {json.dumps(clean, ensure_ascii=False)}")

    for model, fields in summary.get("models", {}).items():
        print(f"{model}:")
        for field, values in fields.items():
            clean = {k: v for k, v in values.items() if k != "probeResults"}
            print(f"  {field}: {json.dumps(clean, ensure_ascii=False)}")


def main() -> int:
    default_client = find_default_client()

    parser = argparse.ArgumentParser(
        description=(
            "Discover image-to-video enum options and model-specific numeric "
            "limits by sending deliberately invalid values."
        )
    )
    parser.add_argument("image", type=Path, help="input image")
    parser.add_argument(
        "--client",
        type=Path,
        default=default_client,
        help="working img2video Python file",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=MODELS,
        default=list(MODELS),
        help="models for model-dependent probes",
    )
    parser.add_argument(
        "--prompt",
        default="Static camera, subtle natural movement.",
    )
    parser.add_argument(
        "--include-type-probes",
        action="store_true",
        help="also send wrong JSON types for boolean, seed, and loras fields",
    )
    parser.add_argument(
        "--between-tests",
        type=float,
        default=0.15,
        help="seconds between requests",
    )
    parser.add_argument(
        "--cancel-delay",
        type=float,
        default=0.0,
        help="delay before cancelling any unexpectedly accepted probe",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="output prefix without extension",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print probes without calling the API",
    )
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if args.client is None:
        raise FileNotFoundError(
            "No working img2video client found beside this script. "
            "Pass it with --client 'img2video_iphone(5).py'"
        )

    client_path = args.client.expanduser().resolve()
    if not client_path.is_file():
        raise FileNotFoundError(f"Client not found: {client_path}")

    probes = build_probes(list(args.models), args.include_type_probes)

    if args.plan:
        print(f"Probes: {len(probes)}")
        for index, probe in enumerate(probes, 1):
            print(
                f"{index:>2}. {probe['name']}: "
                f"{json.dumps(probe['changes'], ensure_ascii=False)}"
            )
        return 0

    client = load_client(client_path)
    username, password = client.load_credentials()
    image_data = client.encode_image(image_path)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = (
        args.output_prefix.expanduser().resolve()
        if args.output_prefix
        else SCRIPT_DIR / f"img2video_discovery_{timestamp}"
    )
    jsonl_path = prefix.with_suffix(".jsonl")
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")

    records: list[dict[str, Any]] = []

    print(f"Client: {client_path.name}")
    print(f"Probes: {len(probes)}")
    print(f"JSONL: {jsonl_path}")
    print(f"Summary: {json_path}")
    print(f"CSV: {csv_path}")

    with jsonl_path.open("w", encoding="utf-8") as log:
        for index, probe in enumerate(probes, 1):
            model_context = probe["model_context"]
            request_model = model_context or "wan-2.2"
            request = make_base_request(
                client,
                image_data,
                args.prompt,
                request_model,
            )
            request["payload"].update(probe["changes"])

            created: Any = None
            create_error: str | None = None
            cancel_response: Any = None
            cancel_error: str | None = None
            task_id: str | None = None
            started = time.time()

            print(f"[{index}/{len(probes)}] {probe['name']}")

            try:
                created = client.api_request(
                    "POST",
                    "/api/v3/tasks",
                    username,
                    password,
                    request,
                )
                task_id = get_task_id(created)
            except Exception as exc:
                create_error = exception_text(exc)

            if task_id:
                time.sleep(max(0.0, args.cancel_delay))
                try:
                    cancel_response = client.api_request(
                        "POST",
                        f"/api/v3/tasks/{task_id}/cancel",
                        username,
                        password,
                    )
                except Exception as exc:
                    cancel_error = exception_text(exc)

            api_messages = extract_api_messages(create_error)
            discovered = parse_discovery(api_messages)

            record = {
                "index": index,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "name": probe["name"],
                "modelContext": model_context,
                "field": probe["field"],
                "kind": probe["kind"],
                "sentValue": probe["value"],
                "changes": probe["changes"],
                "request": redact_request(request),
                "accepted": task_id is not None,
                "createResponse": created,
                "createError": create_error,
                "apiMessages": api_messages,
                "discovered": discovered,
                "taskId": task_id,
                "cancelResponse": cancel_response,
                "cancelError": cancel_error,
                "elapsedSeconds": round(time.time() - started, 3),
            }
            records.append(record)

            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()

            if task_id:
                print(f"  unexpectedly accepted: {task_id}")
                print(f"  cancel: {'ok' if cancel_error is None else compact_text(cancel_error)}")
            else:
                print(f"  rejected as expected")
                for message in api_messages:
                    print(f"    {message}")
                if discovered:
                    print(f"  discovered: {json.dumps(discovered, ensure_ascii=False)}")

            time.sleep(max(0.0, args.between_tests))

    summary = build_summary(records, list(args.models))
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(csv_path, records)
    print_summary(summary)

    print()
    print(f"Rejected as expected: {summary['totals']['rejectedAsExpected']}")
    print(f"Unexpectedly accepted: {summary['totals']['unexpectedlyAccepted']}")
    print(f"Raw log: {jsonl_path}")
    print(f"Summary: {json_path}")
    print(f"CSV: {csv_path}")
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
