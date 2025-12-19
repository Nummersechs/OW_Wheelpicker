import random
from dataclasses import dataclass

@dataclass
class SpinPlan:
    start_deg: float
    end_deg: float
    duration_ms: int

def _turns_for_duration(duration_ms: int) -> int:
    """Choose turn count based on duration for a consistent start speed."""
    # Base: at least 3 turns; every ~900 ms adds ~1 turn.
    turns = 3 + max(0, int(duration_ms / 900))
    # Slight variance so results are not identical every time
    turns += random.choice([0, 0, 1])  # ~33% chance to add 1 turn
    # Clamp to avoid excessive spins
    return max(3, min(turns, 12))

def plan_spin(current_deg: float, slice_center_deg: float, duration_ms: int) -> SpinPlan:
    """
    current_deg: current rotation of the wheel (deg, 0° = right, math direction)
    slice_center_deg: midpoint of target segment in degrees (same convention)
    duration_ms: desired duration

    Pointer is at 12 o'clock. To land the segment midpoint under the pointer:
    rot_end ≡ slice_center_deg - 90° (mod 360)
    """
    current = current_deg % 360.0

    # Correct orientation: segment midpoint under 12 o'clock pointer
    rot_end_mod = (slice_center_deg - 90.0) % 360.0

    # Smallest positive diff from current to rot_end_mod
    delta = (rot_end_mod - current) % 360.0

    # Turns based on duration for “fast start” feel
    turns = _turns_for_duration(int(duration_ms))

    end = current + delta + 360.0 * turns
    return SpinPlan(start_deg=current, end_deg=end, duration_ms=int(duration_ms))
