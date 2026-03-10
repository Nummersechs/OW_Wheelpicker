from __future__ import annotations

from dataclasses import dataclass


def snap_to_step(value: int, *, step: int) -> int:
    step_i = max(1, int(step))
    if step_i <= 1:
        return int(value)
    return int(round(float(value) / float(step_i)) * step_i)


def compute_map_list_names_target_height(
    *,
    row_height: int,
    row_count: int,
    min_rows: int,
    max_rows: int,
    frame_width: int,
    extra_padding: int,
    min_height: int = 40,
) -> int:
    safe_row_height = max(1, int(row_height))
    safe_row_count = max(1, int(row_count))
    safe_min_rows = max(1, int(min_rows))
    safe_max_rows = max(safe_min_rows, int(max_rows))
    visible_rows = max(safe_min_rows, min(safe_row_count, safe_max_rows))
    frame_px = max(0, int(frame_width)) * 2
    padding_px = max(0, int(extra_padding))
    target = int((visible_rows * safe_row_height) + frame_px + padding_px)
    return max(int(min_height), target)


@dataclass(frozen=True)
class MapPanelMetrics:
    soft_canvas: int
    panel_min_width: int
    panel_min_height: int
    frame_min_height: int


def compute_map_panel_metrics(ref_height: int) -> MapPanelMetrics:
    ref_h = max(200, int(ref_height))
    soft_canvas = max(160, min(320, snap_to_step(int(ref_h * 0.40), step=10)))
    panel_min_width = max(210, min(360, snap_to_step(int(soft_canvas * 1.15), step=10)))
    panel_min_height = max(220, snap_to_step(soft_canvas + 70, step=10))
    frame_min_height = max(150, min(420, snap_to_step(ref_h - 30, step=12)))
    return MapPanelMetrics(
        soft_canvas=int(soft_canvas),
        panel_min_width=int(panel_min_width),
        panel_min_height=int(panel_min_height),
        frame_min_height=int(frame_min_height),
    )
