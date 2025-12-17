import random
from dataclasses import dataclass

@dataclass
class SpinPlan:
    start_deg: float
    end_deg: float
    duration_ms: int

def _turns_for_duration(duration_ms: int) -> int:
    """
    Wähle die Zahl der vollen Umdrehungen abhängig von der Dauer, damit
    der Spin am Anfang subjektiv gleich schnell startet. Mehr Dauer ⇒ mehr Weg.
    """
    # Basis: mindestens 3 Umdrehungen.
    # Alle ~900 ms fügen wir ca. 1 zusätzliche Umdrehung hinzu.
    turns = 3 + max(0, int(duration_ms / 900))
    # etwas Varianz, damit es nicht immer exakt gleich ist
    turns += random.choice([0, 0, 1])  # zu ~33% +1 turn
    # Begrenzen, damit es nicht ausufert
    return max(3, min(turns, 12))

def plan_spin(current_deg: float, slice_center_deg: float, duration_ms: int) -> SpinPlan:
    """
    current_deg: aktuelle Rotationslage des Rades (Grad, 0° = nach rechts, mathematische Richtung)
    slice_center_deg: Mittelpunkt des Zielsegments in Grad (selbe Konvention)
    duration_ms: gewünschte Dauer

    Zeiger ist bei 12 Uhr. Damit der Ziel-Segmentmittelpunkt unter dem Zeiger landet, gilt:
    Rot_end ≡ slice_center_deg - 90° (mod 360)
    """
    current = current_deg % 360.0

    # Korrekte Ziel-Orientierung: Segment-Mitte unter 12-Uhr-Zeiger
    rot_end_mod = (slice_center_deg - 90.0) % 360.0

    # kleinste positive Differenz von current zu rot_end_mod
    delta = (rot_end_mod - current) % 360.0

    # Anzahl der vollen Umdrehungen passend zur Dauer (für "schnell starten")
    turns = _turns_for_duration(int(duration_ms))

    end = current + delta + 360.0 * turns
    return SpinPlan(start_deg=current, end_deg=end, duration_ms=int(duration_ms))
