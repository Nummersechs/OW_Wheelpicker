import math
from typing import List
from PySide6 import QtCore, QtGui, QtWidgets
import config


def make_colors(n: int) -> List[QtGui.QColor]:
    return [] if n <= 0 else [
        QtGui.QColor.fromHsl(int(360 * i / n), 180, 140) for i in range(n)
    ]


class WheelDisc(QtWidgets.QGraphicsObject):
    segmentToggled = QtCore.Signal(int, bool, str)
    def __init__(self, names: List[str], radius: int = None, parent=None):
        super().__init__(parent)
        self.radius = radius if radius is not None else config.WHEEL_RADIUS
        self.names = [n.strip() for n in names if n.strip()]
        self.disabled_indices: set[int] = set()
        # Flag, ob die Namens-Labels gezeichnet werden sollen
        self.show_labels = True
        self._cache_key = (tuple(self.names), self.radius, tuple(sorted(self.disabled_indices)))
        self._cached = None
        self.setTransformOriginPoint(0, 0)


    def set_radius(self, radius: int):
        """Radius des Rads ändern und Cache neu aufbauen."""
        if radius == self.radius:
            return
        self.prepareGeometryChange()
        self.radius = int(radius)
        self._cached = None
        self._cache_key = (tuple(self.names), self.radius, tuple(sorted(self.disabled_indices)))
        self.update()

    def boundingRect(self) -> QtCore.QRectF:
        r = self.radius
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def _ensure_cache(self):
        key = (tuple(self.names), self.radius, tuple(sorted(self.disabled_indices)))
        if self._cached is not None and key == self._cache_key:
            return
        self._cache_key = key

        # Pixmap aufsetzen
        s = int(2 * self.radius) + 4
        pm = QtGui.QPixmap(s, s)
        pm.fill(QtCore.Qt.transparent)

        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        center = QtCore.QPointF(s / 2.0, s / 2.0)
        r = float(self.radius)

        # ----- Leerzustand -----
        if not self.names:
            p.setBrush(QtGui.QColor(230, 230, 230))
            p.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200), 2))
            p.drawEllipse(center, r, r)
            p.end()
            self._cached = pm
            return

        # ----- Segmente -----
        n = len(self.names)
        cols = make_colors(n)
        angle_step = 360.0 / float(n)

        pie_rect = QtCore.QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r)
        start_deg = 0.0
        for i in range(n):
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
            color = cols[i]
            # Visuelle Markierung gespiegelt zur X-Achse? -> Index spiegeln für Darstellung
            disabled_for_draw = False
            if self.disabled_indices:
                mirror_idx = (n - 1 - i) % n
                disabled_for_draw = mirror_idx in self.disabled_indices
            if disabled_for_draw:
                # Deutlich ausgegraut/dunkler
                color = QtGui.QColor(color)
                color.setHsl(color.hslHue(), 25, 120)
                color.setAlpha(90)
            p.setBrush(color)
            # QPainter: 0° = 3 Uhr, positive Winkel CCW.
            # Wir wollen CW drehen → negativer Sweep:
            p.drawPie(pie_rect, int(-start_deg * 16), int(-angle_step * 16))
            start_deg += angle_step

        # ----- Außenring -----
        p.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 3))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(center, r, r)

        # ================= LABELS =================
        if not getattr(self, "show_labels", True):
            p.end()
            self._cached = pm
            return
        base_font = QtGui.QFont()
        base_size = float(getattr(config, 'LABEL_FONT_SIZE', 10))
        # Skalierung der Schrift relativ zum Basisradius
        # Für kleine Räder darf die Schrift bis auf 50% schrumpfen,
        # für große Räder wächst sie maximal auf 130% der Basisgröße.
        scale = float(self.radius) / float(getattr(config, 'WHEEL_RADIUS', self.radius or 1))
        eff_scale = max(0.5, min(1.3, scale))
        scaled_size = max(6.0, min(64.0, base_size * eff_scale))
        base_font.setPointSizeF(scaled_size)
        base_font.setBold(bool(getattr(config, 'LABEL_FONT_BOLD', True)))
        p.setFont(base_font)

        def fmt(raw: str) -> str:
            """Paare auf 3 Zeilen, LÄNGERER Name oben, kürzerer unten."""
            if " + " in raw:
                a, b = [part.strip() for part in raw.split(" + ", 1)]

                fm_tmp = QtGui.QFontMetrics(base_font)
                # a soll der längere (oder gleich lange) sein
                if fm_tmp.horizontalAdvance(a) < fm_tmp.horizontalAdvance(b):
                    a, b = b, a

                return f"{a}\n+\n{b}"
            return raw

        def initials_label(raw: str) -> str:
            """Nur Anfangsbuchstaben (mit + dazwischen)."""
            if " + " in raw:
                a, b = [part.strip() for part in raw.split(" + ", 1)]

                fm_tmp = QtGui.QFontMetrics(base_font)
                # längerer Name weiterhin oben
                if fm_tmp.horizontalAdvance(a) < fm_tmp.horizontalAdvance(b):
                    a, b = b, a

                top = a[0] if a else ""
                bottom = b[0] if b else ""
                return f"{top}\n+\n{bottom}"
            else:
                raw = raw.strip()
                return raw[0] if raw else ""

        # Radius etwas Richtung Rand, aber noch im Segment
        radius_txt = r * 0.65  # kannst du auf 0.6–0.72 anpassen

        for i, raw in enumerate(self.names):
            theta_deg = (i + 0.5) * angle_step     # Mitte des Segments
            theta = math.radians(theta_deg)

            # Mittelpunkt des Textes auf dem Kreis
            tx = center.x() + radius_txt * math.cos(theta)
            ty = center.y() - radius_txt * math.sin(theta)

            # verfügbare Bogenlänge entlang des Kreisbogens
            arc_len = 2.0 * math.pi * radius_txt * (angle_step / 360.0)

            # nutze z.B. 80% davon für den Text
            max_w = arc_len * 0.8

            # nach oben begrenzen, aber NICHT nach unten
            max_w = min(130.0, max_w)

            # 1) Wenn es *extrem* schmal ist → gar kein Label
            if max_w < 12.0:
                continue

            # 2) Wenn es recht schmal ist → nur Initialen
            use_initials_only = max_w < 25.0

            # Höhe für max. 3 Zeilen (dynamisch aus der aktuellen Schrift abgeleitet)
            fm_base = QtGui.QFontMetrics(base_font)
            line_h = fm_base.height()
            rect_h = float(line_h * 3.2)  # 3 Zeilen + etwas Luft
            # rect: Mittelpunkt = (0,0) nach Transformation
            rect = QtCore.QRectF(-max_w / 2.0, -rect_h / 2.0, max_w, rect_h)

            # Textwahl je nach Platz
            if use_initials_only:
                text = initials_label(raw)
            else:
                text = fmt(raw)

            # FontMetrics für aktuelle Schrift
            fm = QtGui.QFontMetrics(base_font)

            # Zeilenweise eliden
            if "\n" in text:
                parts = text.split("\n")
                elided_parts = []
                for line in parts:
                    if line == "+":
                        elided_parts.append(line)
                    else:
                        elided_parts.append(
                            fm.elidedText(line, QtCore.Qt.ElideRight, int(max_w))
                        )
                safe_text = "\n".join(elided_parts)
            else:
                safe_text = fm.elidedText(text, QtCore.Qt.ElideRight, int(max_w))

            # Regel: Wenn der Text so stark gekürzt wurde, dass er nur noch
            # als "…" oder "A…" dargestellt würde, dann nur Initialen anzeigen.
            # Wir erlauben aber z.B. "AB..." (mind. 2 Buchstaben vor den Punkten).
            if safe_text != text and "\n" not in safe_text:
                trimmed = safe_text.strip()
                # reine Ellipse "..." oder "…"
                is_just_ellipsis = trimmed in ("...", "…")
                # genau ein Buchstabe + "..."
                is_one_letter_three_dots = (
                    len(trimmed) == 4
                    and trimmed[0].isalpha()
                    and trimmed[1:] == "..."
                )
                # genau ein Buchstabe + "…"
                is_one_letter_ellipsis = (
                    len(trimmed) == 2
                    and trimmed[0].isalpha()
                    and trimmed[1] == "…"
                )
                if is_just_ellipsis or is_one_letter_three_dots or is_one_letter_ellipsis:
                    # Für Single-Namen → erster Buchstabe,
                    # für Paare → beide Initialen mit "+"
                    text = initials_label(raw)
                    safe_text = text

            # Schrift ggf. verkleinern, falls sie in der Höhe nicht mehr passt.
            # Dabei wird bei Bedarf mehrmals verkleinert, bis sie in die Box passt
            # oder eine Untergrenze erreicht ist.
            def fits_height(font_to_test: QtGui.QFont, txt: str) -> (bool, QtGui.QFontMetrics, str):
                fm_local = QtGui.QFontMetrics(font_to_test)
                if "\n" in txt:
                    parts = txt.split("\n")
                    elided_parts2 = []
                    for line in parts:
                        if line == "+":
                            elided_parts2.append(line)
                        else:
                            elided_parts2.append(
                                fm_local.elidedText(line, QtCore.Qt.ElideRight, int(max_w))
                            )
                    txt2 = "\n".join(elided_parts2)
                else:
                    txt2 = fm_local.elidedText(txt, QtCore.Qt.ElideRight, int(max_w))

                br = fm_local.boundingRect(
                    QtCore.QRect(0, 0, int(max_w), 1000),
                    QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                    txt2,
                )
                return (br.height() <= rect_h, fm_local, txt2)

            current_font = QtGui.QFont(base_font)
            ok, fm_current, final_text = fits_height(current_font, safe_text)

            if not ok:
                # Schrift schrittweise verkleinern, bis sie in die Box passt oder min. 6pt erreicht sind
                for _ in range(10):
                    new_size = max(6, current_font.pointSize() - 1)
                    if new_size == current_font.pointSize():
                        break
                    current_font.setPointSize(new_size)
                    ok, fm_current, final_text = fits_height(current_font, safe_text)
                    if ok:
                        break

            # Zeichnen mit Rotation (Text „zeigt“ zum Mittelpunkt)
            p.save()
            p.translate(tx, ty)
            p.rotate(90.0 - theta_deg)  # Oberseite Richtung Zentrum
            p.setFont(current_font)
            p.drawText(rect, QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, final_text)
            p.restore()

        # ================= /LABELS =================

        p.end()
        self._cached = pm

    def paint(self, painter: QtGui.QPainter, *_):
        self._ensure_cache()
        if self._cached:
            painter.drawPixmap(-self.radius, -self.radius, self._cached)
    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if not self.names:
            return
        pos = event.pos()
        x, y = pos.x(), pos.y()
        # CW-Winkel (0° = rechts, zunehmende Winkel im Uhrzeigersinn)
        angle = (math.degrees(math.atan2(-y, x)) + 360.0) % 360.0
        n = len(self.names)
        angle_step = 360.0 / float(n)
        idx = int(angle // angle_step) % n
        label = self.names[idx]
        disabled = idx not in self.disabled_indices
        if disabled:
            self.disabled_indices.add(idx)
        else:
            self.disabled_indices.remove(idx)
        self._cached = None
        self.update()
        self.segmentToggled.emit(idx, disabled, label)
        super().mousePressEvent(event)
    
    def set_show_labels(self, show: bool):
        """Ein-/Ausschalten der Namensanzeige auf dem Rad."""
        if self.show_labels == show:
            return
        self.show_labels = show
        # Cache verwerfen, damit neu gezeichnet wird
        self._cached = None
        self.update()
    def set_disabled_indices(self, indices: set[int]):
        self.disabled_indices = {i for i in indices if 0 <= i < len(self.names)}
        self._cached = None
        self._cache_key = (tuple(self.names), self.radius, tuple(sorted(self.disabled_indices)))
        self.update()

    def set_names(self, names: List[str]):
        self.names = [n.strip() for n in names if n.strip()]
        self.disabled_indices.clear()
        self._cached = None
        self.update()
