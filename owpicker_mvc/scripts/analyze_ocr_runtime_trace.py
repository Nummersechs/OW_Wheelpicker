#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
from statistics import mean
from typing import Any


def _parse_line(line: str) -> dict[str, Any] | None:
    raw = str(line or "").strip()
    if not raw or raw.startswith("==="):
        return None
    if " | " not in raw:
        return None
    data: dict[str, str] = {}
    for part in raw.split(" | "):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not key:
            continue
        data[key] = value.strip()
    event = str(data.get("event", "")).strip()
    if not event:
        return None
    pid_raw = str(data.get("pid", "")).strip()
    mono_raw = str(data.get("mono", "")).strip()
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        pid = -1
    try:
        mono = float(mono_raw)
    except (TypeError, ValueError):
        mono = -1.0
    if pid <= 0 or mono < 0.0:
        return None
    return {"pid": pid, "mono": mono, "event": event, "fields": data}


def _first_event(events: list[dict[str, Any]], name: str, *, start_idx: int = 0) -> tuple[int, dict[str, Any]] | None:
    for idx in range(max(0, int(start_idx)), len(events)):
        if str(events[idx].get("event", "")) == name:
            return idx, events[idx]
    return None


def _first_event_any(
    events: list[dict[str, Any]],
    names: set[str],
    *,
    start_idx: int = 0,
) -> tuple[int, dict[str, Any]] | None:
    for idx in range(max(0, int(start_idx)), len(events)):
        if str(events[idx].get("event", "")) in names:
            return idx, events[idx]
    return None


def _event_ms_from_field(entry: dict[str, Any], key: str) -> int | None:
    fields = entry.get("fields", {})
    if not isinstance(fields, dict):
        return None
    raw = str(fields.get(key, "")).strip()
    if not raw:
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return max(0, value)


def _delta_ms(left: dict[str, Any] | None, right: dict[str, Any] | None) -> int | None:
    if not left or not right:
        return None
    try:
        return max(0, int(round((float(right.get("mono", 0.0)) - float(left.get("mono", 0.0))) * 1000.0)))
    except (TypeError, ValueError):
        return None


def _format_ms(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value} ms"


def _summary(values: list[int]) -> str:
    if not values:
        return "-"
    return f"min={min(values)} ms | avg={int(round(mean(values)))} ms | max={max(values)} ms"


def analyze_trace(path: Path, *, include_empty_runs: bool = False) -> int:
    if not path.exists():
        print(f"Trace file not found: {path}")
        return 1

    runs: "OrderedDict[int, list[dict[str, Any]]]" = OrderedDict()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parsed = _parse_line(line)
            if not parsed:
                continue
            pid = int(parsed["pid"])
            runs.setdefault(pid, []).append(parsed)

    if not runs:
        print(f"No parseable OCR runtime events found in: {path}")
        return 1

    print(f"OCR runtime metrics from: {path}")
    print(f"Runs (by PID): {len(runs)}")
    print("")

    preload_totals: list[int] = []
    preload_inprocess: list[int] = []
    first_click_totals: list[int] = []
    first_request_totals: list[int] = []
    first_worker_totals: list[int] = []

    terminal_events = {
        "ocr_async_import:worker_result",
        "ocr_async_import:worker_error",
        "ocr_async_import:exception",
        "ocr_async_import:image_prepare_failed",
        "ocr_availability_probe:not_ready",
    }

    for pid, events in runs.items():
        preload_start = _first_event(events, "ocr_preload_worker:start")
        preload_done = _first_event(events, "ocr_preload_worker:done")
        inprocess_done = _first_event(events, "ocr_preload_worker:inprocess_warmup_done")
        warmup_start = _first_event(events, "easyocr_warmup:start")

        preload_total_ms = None
        if preload_done:
            preload_total_ms = _event_ms_from_field(preload_done[1], "runtime_ms")
        if preload_total_ms is None and preload_start and preload_done:
            preload_total_ms = _delta_ms(preload_start[1], preload_done[1])

        inprocess_ms = None
        if inprocess_done:
            inprocess_ms = _event_ms_from_field(inprocess_done[1], "runtime_ms")

        first_click = _first_event(events, "ocr_button_clicked")
        first_async_start = _first_event(events, "ocr_async_import:start")
        first_terminal = None
        if first_async_start:
            first_terminal = _first_event_any(events, terminal_events, start_idx=int(first_async_start[0]) + 1)
        elif first_click:
            first_terminal = _first_event_any(events, terminal_events, start_idx=int(first_click[0]) + 1)

        request_total_ms = None
        worker_total_ms = None
        click_total_ms = None
        request_to_worker_start_ms = None

        if first_terminal:
            request_total_ms = _event_ms_from_field(first_terminal[1], "request_latency_ms")
            worker_total_ms = _event_ms_from_field(first_terminal[1], "worker_latency_ms")
        if request_total_ms is None and first_async_start and first_terminal:
            request_total_ms = _delta_ms(first_async_start[1], first_terminal[1])
        if first_click and first_terminal:
            click_total_ms = _delta_ms(first_click[1], first_terminal[1])

        first_worker_started = None
        if first_async_start:
            first_worker_started = _first_event(events, "ocr_async_import:worker_thread_started", start_idx=first_async_start[0])
        if first_worker_started:
            request_to_worker_start_ms = _event_ms_from_field(first_worker_started[1], "request_to_worker_start_ms")
        if request_to_worker_start_ms is None and first_async_start and first_worker_started:
            request_to_worker_start_ms = _delta_ms(first_async_start[1], first_worker_started[1])

        if preload_total_ms is not None:
            preload_totals.append(preload_total_ms)
        if inprocess_ms is not None:
            preload_inprocess.append(inprocess_ms)
        if click_total_ms is not None:
            first_click_totals.append(click_total_ms)
        if request_total_ms is not None:
            first_request_totals.append(request_total_ms)
        if worker_total_ms is not None:
            first_worker_totals.append(worker_total_ms)

        group_done_ms = None
        if warmup_start:
            group_done = _first_event_any(events, {"easyocr_warmup:group_done", "easyocr_warmup:group_error"}, start_idx=warmup_start[0])
            group_done_ms = _delta_ms(warmup_start[1], group_done[1]) if group_done else None

        has_metrics = any(
            value is not None
            for value in (
                preload_total_ms,
                inprocess_ms,
                request_to_worker_start_ms,
                request_total_ms,
                worker_total_ms,
                click_total_ms,
                group_done_ms,
            )
        ) or bool(warmup_start)
        if not include_empty_runs and not has_metrics:
            continue

        print(f"PID {pid}")
        print(f"  preload total: {_format_ms(preload_total_ms)}")
        print(f"  preload in-process warmup: {_format_ms(inprocess_ms)}")
        print(f"  first inference warmup start: {'yes' if warmup_start else 'no'}")
        print(f"  first inference warmup first-group-done: {_format_ms(group_done_ms)}")
        print(f"  first OCR request -> worker start: {_format_ms(request_to_worker_start_ms)}")
        print(f"  first OCR request total: {_format_ms(request_total_ms)}")
        print(f"  first OCR worker phase: {_format_ms(worker_total_ms)}")
        print(f"  first click -> terminal OCR result: {_format_ms(click_total_ms)}")
        print("")

    print("Summary")
    print(f"  preload total: {_summary(preload_totals)}")
    print(f"  preload in-process warmup: {_summary(preload_inprocess)}")
    print(f"  first click -> terminal OCR result: {_summary(first_click_totals)}")
    print(f"  first OCR request total: {_summary(first_request_totals)}")
    print(f"  first OCR worker phase: {_summary(first_worker_totals)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze OCR warmup + first-click latency from ocr_runtime_trace.log")
    parser.add_argument(
        "trace_file",
        nargs="?",
        default="logs/ocr_runtime_trace.log",
        help="Path to OCR runtime trace file (default: logs/ocr_runtime_trace.log)",
    )
    parser.add_argument(
        "--all-runs",
        action="store_true",
        help="Include runs without measurable OCR warmup/click metrics.",
    )
    args = parser.parse_args()
    return analyze_trace(
        Path(str(args.trace_file)).expanduser(),
        include_empty_runs=bool(args.all_runs),
    )


if __name__ == "__main__":
    raise SystemExit(main())
