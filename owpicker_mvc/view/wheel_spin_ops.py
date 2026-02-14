from __future__ import annotations

import random
from typing import Sequence

from PySide6 import QtCore

from logic.spin_engine import plan_spin


def spin_to_label(
    owner,
    names: Sequence[str],
    enabled_indices: Sequence[int],
    *,
    duration_ms: int,
    target_label: str | None = None,
) -> bool:
    if not names or not enabled_indices:
        return False

    enabled_set = set(enabled_indices)
    if target_label and target_label in names:
        idx = names.index(target_label)
        if idx not in enabled_set:
            idx = random.choice(list(enabled_indices))
    else:
        idx = random.choice(list(enabled_indices))
    resolved_label = names[idx]

    step = 360.0 / len(names)
    slice_center = (idx + 0.5) * step

    owner.hard_stop()
    current = float(owner.wheel.rotation()) % 360.0
    owner.wheel.setRotation(current)
    plan = plan_spin(current_deg=current, slice_center_deg=slice_center, duration_ms=max(1, int(duration_ms)))

    owner.anim = QtCore.QPropertyAnimation(owner.wheel, b"rotation", owner)
    owner.anim.setDuration(plan.duration_ms)
    owner.anim.setStartValue(plan.start_deg)
    owner.anim.setEndValue(plan.end_deg)
    owner.anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
    owner._pending_result = resolved_label
    owner._is_spinning = True
    def _force_repaint(*_args):
        try:
            owner.wheel.update()
        except Exception:
            pass
        try:
            owner.view.viewport().update()
        except Exception:
            pass
    owner.anim.valueChanged.connect(_force_repaint)
    owner.anim.finished.connect(owner._emit_result)
    owner.anim.start()
    try:
        duration = int(owner.anim.duration())
        if duration > 1 and owner.anim.state() == QtCore.QAbstractAnimation.Running:
            owner.anim.setCurrentTime(min(16, duration - 1))
    except Exception:
        pass
    _force_repaint()
    return True
