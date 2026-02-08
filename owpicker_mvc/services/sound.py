from PySide6 import QtCore, QtWidgets
from typing import Callable
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl
from pathlib import Path
import random, math, tempfile, wave
import config

AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3"}


class SoundManager:
    def __init__(self, base_dir: Path):
        """Lädt Spin- und Ding-Sounds.

        Erwartete Struktur (Entwicklungsmodus):
            base_dir/
              Spin/   *.wav / *.ogg / *.mp3
              Ding/   *.wav / *.ogg / *.mp3

        Wenn die Ordner leer sind oder nicht existieren, wird
        optional auf spin.wav / ding.wav im base_dir zurückgefallen.
        """
        self.spin_effects: dict[Path, QSoundEffect] = {}
        self.ding_effects: dict[Path, QSoundEffect] = {}
        self.spin_sources: list[Path] = []
        self.ding_sources: list[Path] = []
        self.master_volume: float = 1.0
        self.spin_base_volume = 0.35
        self.ding_base_volume = 0.7
        self.preview_base_volume = 0.35
        self.preview_effect: QSoundEffect | None = None
        self._preview_tmp_path: Path | None = None
        self._warmup_timer: QtCore.QTimer | None = None
        self._warmup_items: list[tuple[Path, dict[Path, QSoundEffect], float]] = []
        self._warmup_done_callbacks: list[Callable[[], None]] = []
        self._lazy_warmup_started = False

        spin_dir = base_dir / "Spin"
        ding_dir = base_dir / "Ding"

        self.spin_sources = self._collect_sources(spin_dir, default_path=base_dir / "spin.wav")
        self.ding_sources = self._collect_sources(ding_dir, default_path=base_dir / "ding.wav")

    def _collect_sources(self, folder: Path, default_path: Path) -> list[Path]:
        sources: list[Path] = []

        # 1) Load all files from the directory (if present)
        if folder.exists() and folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                    sources.append(entry)

        # 2) Fallback: single file in base dir (spin.wav / ding.wav)
        if not sources and default_path.exists():
            sources.append(default_path)

        return sources

    def _warmup_complete(self) -> bool:
        total_spin = len(self.spin_sources)
        total_ding = len(self.ding_sources)
        if total_spin == 0 and total_ding == 0:
            return True
        if len(self.spin_effects) < total_spin:
            return False
        if len(self.ding_effects) < total_ding:
            return False
        return True

    def _maybe_start_lazy_warmup(self) -> None:
        if self._lazy_warmup_started:
            return
        if self._warmup_timer is not None:
            return
        if self._warmup_complete():
            return
        self._lazy_warmup_started = True
        step_ms = int(getattr(config, "SOUND_WARMUP_LAZY_STEP_MS", 25))
        self.warmup_async(parent=None, step_ms=step_ms)

    def _get_or_create_effect(
        self,
        cache: dict[Path, QSoundEffect],
        path: Path,
        base_volume: float,
    ) -> QSoundEffect:
        eff = cache.get(path)
        if eff:
            return eff
        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(str(path)))
        eff.setLoopCount(1)
        eff.setVolume(base_volume * self.master_volume)
        cache[path] = eff
        return eff

    def warmup_async(
        self,
        parent: QtCore.QObject | None = None,
        step_ms: int = 15,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Warm up sounds incrementally to avoid blocking the UI thread."""
        if on_done is not None:
            self._warmup_done_callbacks.append(on_done)
        items: list[tuple[Path, dict[Path, QSoundEffect], float]] = []
        items.extend([(p, self.spin_effects, self.spin_base_volume) for p in self.spin_sources])
        items.extend([(p, self.ding_effects, self.ding_base_volume) for p in self.ding_sources])
        if not items:
            self._stop_warmup_timer()
            return
        self._warmup_items = items
        if self._warmup_timer is None:
            self._warmup_timer = QtCore.QTimer(parent)
            self._warmup_timer.timeout.connect(self._warmup_step)
        else:
            if parent is not None:
                self._warmup_timer.setParent(parent)
        self._warmup_timer.setSingleShot(False)
        self._warmup_timer.start(max(0, int(step_ms)))

    def _warmup_step(self) -> None:
        if not self._warmup_items:
            self._stop_warmup_timer()
            return
        path, cache, base_volume = self._warmup_items.pop(0)
        try:
            self._get_or_create_effect(cache, path, base_volume)
        except Exception:
            pass
        if not self._warmup_items:
            self._stop_warmup_timer()

    def _stop_warmup_timer(self) -> None:
        if self._warmup_timer is not None:
            self._warmup_timer.stop()
            self._warmup_timer.deleteLater()
            self._warmup_timer = None
        self._warmup_items = []
        callbacks = self._warmup_done_callbacks
        self._warmup_done_callbacks = []
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

    def _cleanup_preview_file(self) -> None:
        path = self._preview_tmp_path
        self._preview_tmp_path = None
        if not path:
            return
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Stop sounds/timers and release audio resources."""
        self._stop_warmup_timer()
        try:
            self.stop_spin()
            self.stop_ding()
        except Exception:
            pass
        if self.preview_effect:
            try:
                self.preview_effect.stop()
            except Exception:
                pass
        # Delete cached effects to release audio backend resources
        for eff in list(self.spin_effects.values()) + list(self.ding_effects.values()):
            try:
                eff.stop()
            except Exception:
                pass
            try:
                eff.deleteLater()
            except Exception:
                pass
        if self.preview_effect:
            try:
                self.preview_effect.deleteLater()
            except Exception:
                pass
        self.spin_effects.clear()
        self.ding_effects.clear()
        self.preview_effect = None
        self._cleanup_preview_file()

    # --- Control ---

    def play_spin(self):
        """Spielt einen zufälligen Spin-Sound oder Beep, falls nichts geladen."""
        try:
            self._maybe_start_lazy_warmup()
            if self.spin_sources:
                path = random.choice(self.spin_sources)
                eff = self._get_or_create_effect(self.spin_effects, path, self.spin_base_volume)
                self._play_effect(eff)
            else:
                QtWidgets.QApplication.beep()
        except Exception:
            QtWidgets.QApplication.beep()

    def stop_spin(self):
        try:
            for eff in self.spin_effects.values():
                eff.stop()
        except Exception:
            pass

    def set_master_volume(self, factor: float):
        """Setzt die Master-Lautstärke (0.0–1.0) für alle Effekte."""
        self.master_volume = max(0.0, min(1.0, float(factor)))
        self._apply_volume(self.spin_effects.values(), self.spin_base_volume)
        self._apply_volume(self.ding_effects.values(), self.ding_base_volume)
        if self.preview_effect:
            self._apply_volume([self.preview_effect], self.preview_base_volume)

    def _apply_volume(self, effects, base_volume: float):
        vol = max(0.0, min(1.0, base_volume * self.master_volume))
        for eff in effects:
            try:
                eff.setVolume(vol)
            except Exception:
                pass

    def play_ding(self):
        """Spielt einen zufälligen Ding-Sound oder Beep, falls nichts geladen."""
        try:
            self._maybe_start_lazy_warmup()
            if self.ding_sources:
                path = random.choice(self.ding_sources)
                eff = self._get_or_create_effect(self.ding_effects, path, self.ding_base_volume)
                self._play_effect(eff)
            else:
                QtWidgets.QApplication.beep()
        except Exception:
            QtWidgets.QApplication.beep()

    def stop_ding(self):
        try:
            for eff in self.ding_effects.values():
                eff.stop()
        except Exception:
            pass

    def play_preview(self):
        """Kurzer Test-Sound für Lautstärkevorschau."""
        try:
            self._maybe_start_lazy_warmup()
            if not self.preview_effect:
                self.preview_effect = self._create_preview_effect()
            if self.preview_effect:
                self._play_effect(self.preview_effect)
            elif self.ding_sources:
                path = random.choice(self.ding_sources)
                eff = self._get_or_create_effect(self.ding_effects, path, self.ding_base_volume)
                self._play_effect(eff)
            elif self.spin_sources:
                path = random.choice(self.spin_sources)
                eff = self._get_or_create_effect(self.spin_effects, path, self.spin_base_volume)
                self._play_effect(eff)
            else:
                QtWidgets.QApplication.beep()
        except Exception:
            QtWidgets.QApplication.beep()

    def _play_effect(self, eff: QSoundEffect):
        try:
            eff.stop()
            eff.play()
        except Exception:
            QtWidgets.QApplication.beep()

    def _create_preview_effect(self) -> QSoundEffect | None:
        """
        Erzeugt einen kurzen synthetischen Ton als WAV im Temp-Ordner,
        mit moderater Lautstärke (nicht lauter als die Standard-WAVs).
        """
        try:
            # Clean up any previous preview temp file to avoid leaks across runs.
            self._cleanup_preview_file()
            sr = 44100
            duration = 0.25
            samples = int(sr * duration)
            freq = 660.0
            amplitude = 0.22  # moderate so it does not exceed existing sounds

            data = bytearray()
            for n in range(samples):
                val = int(amplitude * 32767 * math.sin(2 * math.pi * freq * n / sr))
                data += val.to_bytes(2, byteorder="little", signed=True)

            with tempfile.NamedTemporaryFile(prefix="ow_preview_", suffix=".wav", delete=False) as tmp:
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(data)
                tmp_path = Path(tmp.name)
            self._preview_tmp_path = tmp_path

            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(str(tmp_path)))
            eff.setLoopCount(1)
            eff.setVolume(self.preview_base_volume * self.master_volume)
            return eff
        except Exception:
            return None
