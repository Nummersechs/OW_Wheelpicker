from PySide6 import QtWidgets
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl
from pathlib import Path
import random, math, tempfile, wave

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
        self.spin_effects: list[QSoundEffect] = []
        self.ding_effects: list[QSoundEffect] = []
        self.master_volume: float = 1.0
        self.spin_base_volume = 0.35
        self.ding_base_volume = 0.7
        self.preview_base_volume = 0.35
        self.preview_effect: QSoundEffect | None = None

        spin_dir = base_dir / "Spin"
        ding_dir = base_dir / "Ding"

        self.spin_effects = self._load_effects(spin_dir, default_path=base_dir / "spin.wav", volume=self.spin_base_volume)
        self.ding_effects = self._load_effects(ding_dir, default_path=base_dir / "ding.wav", volume=self.ding_base_volume)
        self.preview_effect = self._create_preview_effect()

    def _load_effects(self, folder: Path, default_path: Path, volume: float) -> list[QSoundEffect]:
        effects: list[QSoundEffect] = []

        # 1) Alle Dateien aus dem Ordner laden (falls vorhanden)
        if folder.exists() and folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                    eff = QSoundEffect()
                    eff.setSource(QUrl.fromLocalFile(str(entry)))
                    eff.setLoopCount(1)
                    eff.setVolume(volume * self.master_volume)
                    effects.append(eff)

        # 2) Fallback: einzelne Datei im Basisordner (spin.wav / ding.wav)
        if not effects and default_path.exists():
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(str(default_path)))
            eff.setLoopCount(1)
            eff.setVolume(volume * self.master_volume)
            effects.append(eff)

        return effects

    # --- Steuerung ---

    def play_spin(self):
        """Spielt einen zufälligen Spin-Sound oder Beep, falls nichts geladen."""
        try:
            if self.spin_effects:
                eff = random.choice(self.spin_effects)
                eff.stop()
                eff.play()
            else:
                QtWidgets.QApplication.beep()
        except Exception:
            QtWidgets.QApplication.beep()

    def stop_spin(self):
        try:
            for eff in self.spin_effects:
                eff.stop()
        except Exception:
            pass

    def set_master_volume(self, factor: float):
        """Setzt die Master-Lautstärke (0.0–1.0) für alle Effekte."""
        self.master_volume = max(0.0, min(1.0, float(factor)))
        self._apply_volume(self.spin_effects, self.spin_base_volume)
        self._apply_volume(self.ding_effects, self.ding_base_volume)
        if self.preview_effect:
            self._apply_volume([self.preview_effect], self.preview_base_volume)

    def _apply_volume(self, effects: list[QSoundEffect], base_volume: float):
        vol = max(0.0, min(1.0, base_volume * self.master_volume))
        for eff in effects:
            try:
                eff.setVolume(vol)
            except Exception:
                pass

    def play_ding(self):
        """Spielt einen zufälligen Ding-Sound oder Beep, falls nichts geladen."""
        try:
            if self.ding_effects:
                self._play_effect(random.choice(self.ding_effects))
            else:
                QtWidgets.QApplication.beep()
        except Exception:
            QtWidgets.QApplication.beep()

    def stop_ding(self):
        try:
            for eff in self.ding_effects:
                eff.stop()
        except Exception:
            pass

    def play_preview(self):
        """Kurzer Test-Sound für Lautstärkevorschau."""
        try:
            if self.preview_effect:
                self._play_effect(self.preview_effect)
            elif self.ding_effects:
                self._play_effect(random.choice(self.ding_effects))
            elif self.spin_effects:
                self._play_effect(random.choice(self.spin_effects))
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
            sr = 44100
            duration = 0.25
            samples = int(sr * duration)
            freq = 660.0
            amplitude = 0.22  # moderat, damit nicht lauter als vorhandene Sounds

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

            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(str(tmp_path)))
            eff.setLoopCount(1)
            eff.setVolume(self.preview_base_volume * self.master_volume)
            return eff
        except Exception:
            return None
