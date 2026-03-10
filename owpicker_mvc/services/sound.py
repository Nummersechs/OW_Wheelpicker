from __future__ import annotations

from PySide6 import QtCore, QtWidgets
from typing import Callable, Any
from PySide6.QtCore import QUrl
from pathlib import Path
import random, math, tempfile, wave
import sys
import time

AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3"}
_QSOUND_EFFECT_UNSET = object()
_QSOUND_EFFECT_CLASS: Any = _QSOUND_EFFECT_UNSET
_SOUND_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
    ImportError,
)


def _resolve_qsoundeffect() -> Any | None:
    global _QSOUND_EFFECT_CLASS
    if _QSOUND_EFFECT_CLASS is _QSOUND_EFFECT_UNSET:
        try:
            from PySide6.QtMultimedia import QSoundEffect as _QSoundEffect  # type: ignore
            _QSOUND_EFFECT_CLASS = _QSoundEffect
        except _SOUND_GUARD_ERRORS:
            _QSOUND_EFFECT_CLASS = None
    return _QSOUND_EFFECT_CLASS


class SoundManager:
    def __init__(self, base_dir: Path, *, settings: Any | None = None):
        """Lädt Spin- und Ding-Sounds.

        Erwartete Struktur (Entwicklungsmodus):
            base_dir/
              Spin/   *.wav / *.ogg / *.mp3
              Ding/   *.wav / *.ogg / *.mp3

        Wenn die Ordner leer sind oder nicht existieren, wird
        optional auf spin.wav / ding.wav im base_dir zurückgefallen.
        """
        self.spin_effects: dict[Path, Any] = {}
        self.ding_effects: dict[Path, Any] = {}
        self.spin_sources: list[Path] = []
        self.ding_sources: list[Path] = []
        self.master_volume: float = 1.0
        self.spin_base_volume = 0.35
        self.ding_base_volume = 0.7
        self.preview_base_volume = 0.35
        self.preview_effect: Any | None = None
        self._preview_tmp_path: Path | None = None
        self._warmup_timer: QtCore.QTimer | None = None
        self._warmup_items: list[tuple[Path, dict[Path, Any], float]] = []
        self._warmup_done_callbacks: list[Callable[[], None]] = []
        self._lazy_warmup_started = False
        self._warmup_paused = False
        self._pending_spin_timer: QtCore.QTimer | None = None
        self._pending_spin_effect: Any | None = None
        self._last_active_audio_stop_monotonic = 0.0
        self._settings = settings

        spin_dir = base_dir / "Spin"
        ding_dir = base_dir / "Ding"

        self.spin_sources = self._collect_sources(spin_dir, default_path=base_dir / "spin.wav")
        self.ding_sources = self._collect_sources(ding_dir, default_path=base_dir / "ding.wav")

    def _cfg(self, key: str, default: Any = None) -> Any:
        settings = self._settings
        if settings is not None and hasattr(settings, "resolve"):
            try:
                return settings.resolve(key, default)
            except _SOUND_GUARD_ERRORS:
                pass
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except _SOUND_GUARD_ERRORS:
                pass
        return default

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
        if self._warmup_paused:
            return
        if self._warmup_complete():
            return
        self._lazy_warmup_started = True
        step_ms = int(self._cfg("SOUND_WARMUP_LAZY_STEP_MS", 25))
        self.warmup_async(parent=None, step_ms=step_ms)

    def _get_or_create_effect(
        self,
        cache: dict[Path, Any],
        path: Path,
        base_volume: float,
    ) -> Any:
        eff = cache.get(path)
        if eff:
            return eff
        qsound_effect_cls = _resolve_qsoundeffect()
        if qsound_effect_cls is None:
            raise RuntimeError("QtMultimedia unavailable")
        eff = qsound_effect_cls()
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
        items: list[tuple[Path, dict[Path, Any], float]] = []
        items.extend(
            [(p, self.spin_effects, self.spin_base_volume) for p in self.spin_sources if p not in self.spin_effects]
        )
        items.extend(
            [(p, self.ding_effects, self.ding_base_volume) for p in self.ding_sources if p not in self.ding_effects]
        )
        if self._warmup_items:
            queued = {(path, id(cache)) for path, cache, _base_volume in self._warmup_items}
            for path, cache, base_volume in items:
                key = (path, id(cache))
                if key in queued:
                    continue
                queued.add(key)
                self._warmup_items.append((path, cache, base_volume))
        else:
            self._warmup_items = list(items)
        if not self._warmup_items:
            self._stop_warmup_timer()
            return
        if self._warmup_timer is None:
            self._warmup_timer = QtCore.QTimer(parent)
            self._warmup_timer.timeout.connect(self._warmup_step)
        else:
            if parent is not None:
                self._warmup_timer.setParent(parent)
        self._warmup_timer.setSingleShot(False)
        if not self._warmup_paused:
            self._warmup_timer.start(max(0, int(step_ms)))

    def _warmup_step(self) -> None:
        if not self._warmup_items:
            self._stop_warmup_timer()
            return
        path, cache, base_volume = self._warmup_items.pop(0)
        try:
            self._get_or_create_effect(cache, path, base_volume)
        except _SOUND_GUARD_ERRORS:
            pass
        if not self._warmup_items:
            self._stop_warmup_timer()

    def _stop_warmup_timer(self) -> None:
        if self._warmup_timer is not None:
            self._warmup_timer.stop()
            self._warmup_timer.deleteLater()
            self._warmup_timer = None
        self._warmup_items = []
        self._warmup_paused = False
        callbacks = self._warmup_done_callbacks
        self._warmup_done_callbacks = []
        for cb in callbacks:
            try:
                cb()
            except _SOUND_GUARD_ERRORS:
                pass

    def pause_background_warmup(self) -> None:
        timer = self._warmup_timer
        if timer is None:
            return
        try:
            if not timer.isActive():
                return
            timer.stop()
            self._warmup_paused = True
        except _SOUND_GUARD_ERRORS:
            pass

    def resume_background_warmup(self) -> None:
        if not self._warmup_paused:
            return
        timer = self._warmup_timer
        if timer is None:
            self._warmup_paused = False
            return
        if not self._warmup_items:
            self._warmup_paused = False
            return
        self._warmup_paused = False
        try:
            step_ms = int(self._cfg("SOUND_WARMUP_LAZY_STEP_MS", 25))
            timer.start(max(0, step_ms))
        except _SOUND_GUARD_ERRORS:
            pass

    def _cleanup_preview_file(self) -> None:
        path = self._preview_tmp_path
        self._preview_tmp_path = None
        if not path:
            return
        try:
            if path.exists():
                path.unlink()
        except _SOUND_GUARD_ERRORS:
            pass

    @staticmethod
    def _effects_snapshot(effects) -> list[Any]:
        try:
            return list(effects or [])
        except _SOUND_GUARD_ERRORS:
            return []

    @staticmethod
    def _effect_is_playing(eff: Any) -> bool:
        checker = getattr(eff, "isPlaying", None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except _SOUND_GUARD_ERRORS:
            return False

    @staticmethod
    def _stop_effects(effects) -> bool:
        had_active = False
        for eff in SoundManager._effects_snapshot(effects):
            had_active = had_active or SoundManager._effect_is_playing(eff)
            try:
                eff.stop()
            except _SOUND_GUARD_ERRORS:
                pass
        return had_active

    def _mark_active_audio_stop(self, had_active: bool) -> None:
        if not had_active:
            return
        try:
            self._last_active_audio_stop_monotonic = float(time.monotonic())
        except _SOUND_GUARD_ERRORS:
            self._last_active_audio_stop_monotonic = 0.0

    def _stop_preview_effect(self) -> None:
        if not self.preview_effect:
            return
        had_active = self._effect_is_playing(self.preview_effect)
        try:
            self.preview_effect.stop()
        except _SOUND_GUARD_ERRORS:
            pass
        self._mark_active_audio_stop(had_active)

    def _cancel_pending_spin_start(self) -> None:
        timer = self._pending_spin_timer
        self._pending_spin_timer = None
        self._pending_spin_effect = None
        if timer is None:
            return
        try:
            timer.stop()
        except _SOUND_GUARD_ERRORS:
            pass
        try:
            timer.deleteLater()
        except _SOUND_GUARD_ERRORS:
            pass

    def _schedule_spin_start(self, eff: Any, delay_ms: int) -> None:
        self._cancel_pending_spin_start()
        if delay_ms <= 0:
            self._play_effect(eff)
            return

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        self._pending_spin_timer = timer
        self._pending_spin_effect = eff

        def _on_timeout() -> None:
            pending_eff = self._pending_spin_effect
            self._pending_spin_effect = None
            self._pending_spin_timer = None
            try:
                timer.deleteLater()
            except _SOUND_GUARD_ERRORS:
                pass
            if pending_eff is None:
                return
            self._play_effect(pending_eff)

        timer.timeout.connect(_on_timeout)
        timer.start(int(delay_ms))

    def _resolve_spin_restart_gap_ms(self) -> int:
        try:
            configured_gap_ms = int(self._cfg("SOUND_SPIN_RESTART_GAP_MS", -1))
        except _SOUND_GUARD_ERRORS:
            configured_gap_ms = -1
        if configured_gap_ms >= 0:
            return max(0, configured_gap_ms)
        if not sys.platform.startswith("win"):
            return 0
        try:
            profile = str(self._cfg("SOUND_SPIN_RESTART_GAP_PROFILE", "balanced") or "balanced").strip().lower()
        except _SOUND_GUARD_ERRORS:
            profile = "balanced"
        profile_gap_ms = {
            "low": 20,
            "balanced": 30,
            "high": 40,
            "auto": 35,
            "custom": 35,
        }
        return int(profile_gap_ms.get(profile, 30))

    def _resolve_audio_stop_guard_ms(self) -> int:
        try:
            configured_guard_ms = int(self._cfg("SOUND_AUDIO_STOP_GUARD_MS", -1))
        except _SOUND_GUARD_ERRORS:
            configured_guard_ms = -1
        if configured_guard_ms >= 0:
            return max(0, configured_guard_ms)
        if not sys.platform.startswith("win"):
            return 0
        try:
            profile = str(self._cfg("SOUND_SPIN_RESTART_GAP_PROFILE", "balanced") or "balanced").strip().lower()
        except _SOUND_GUARD_ERRORS:
            profile = "balanced"
        profile_guard_ms = {
            "low": 45,
            "balanced": 65,
            "high": 80,
            "auto": 72,
            "custom": 72,
        }
        return int(profile_guard_ms.get(profile, 65))

    def _remaining_audio_stop_guard_ms(self) -> int:
        stop_at = float(self._last_active_audio_stop_monotonic or 0.0)
        if stop_at <= 0.0:
            return 0
        guard_ms = self._resolve_audio_stop_guard_ms()
        if guard_ms <= 0:
            self._last_active_audio_stop_monotonic = 0.0
            return 0
        try:
            elapsed_ms = int(max(0.0, (time.monotonic() - stop_at) * 1000.0))
        except _SOUND_GUARD_ERRORS:
            elapsed_ms = 0
        remaining_ms = guard_ms - elapsed_ms
        if remaining_ms <= 0:
            self._last_active_audio_stop_monotonic = 0.0
            return 0
        return int(remaining_ms)

    def shutdown(self) -> None:
        """Stop sounds/timers and release audio resources."""
        self._stop_warmup_timer()
        self._cancel_pending_spin_start()
        try:
            self.stop_spin()
            self.stop_ding()
        except _SOUND_GUARD_ERRORS:
            pass
        self._stop_preview_effect()
        # Delete cached effects to release audio backend resources
        for eff in self._effects_snapshot(self.spin_effects.values()) + self._effects_snapshot(self.ding_effects.values()):
            try:
                eff.stop()
            except _SOUND_GUARD_ERRORS:
                pass
            try:
                eff.deleteLater()
            except _SOUND_GUARD_ERRORS:
                pass
        if self.preview_effect:
            try:
                self.preview_effect.deleteLater()
            except _SOUND_GUARD_ERRORS:
                pass
        self.spin_effects.clear()
        self.ding_effects.clear()
        self.preview_effect = None
        self._cleanup_preview_file()

    def resource_snapshot(self) -> dict:
        warmup_active = False
        if self._warmup_timer is not None:
            try:
                warmup_active = bool(self._warmup_timer.isActive())
            except _SOUND_GUARD_ERRORS:
                warmup_active = False
        preview_tmp_exists = False
        if self._preview_tmp_path is not None:
            try:
                preview_tmp_exists = bool(self._preview_tmp_path.exists())
            except _SOUND_GUARD_ERRORS:
                preview_tmp_exists = False
        return {
            "qt_multimedia_available": bool(_resolve_qsoundeffect() is not None),
            "spin_sources": len(self.spin_sources),
            "ding_sources": len(self.ding_sources),
            "spin_effects": len(self.spin_effects),
            "ding_effects": len(self.ding_effects),
            "has_preview_effect": bool(self.preview_effect is not None),
            "warmup_timer_active": warmup_active,
            "warmup_items": len(self._warmup_items),
            "warmup_callbacks": len(self._warmup_done_callbacks),
            "preview_tmp_exists": preview_tmp_exists,
            "lazy_warmup_started": bool(self._lazy_warmup_started),
            "pending_spin_timer": bool(self._pending_spin_timer is not None),
        }

    # --- Control ---

    def play_spin(self):
        """Spielt einen zufälligen Spin-Sound oder Beep, falls nichts geladen."""
        try:
            self._maybe_start_lazy_warmup()
            # Prevent audible tail overlap from a previously chosen random spin effect.
            self._cancel_pending_spin_start()
            self.stop_spin()
            self.stop_ding()
            self._stop_preview_effect()
            if self.spin_sources:
                path = random.choice(self.spin_sources)
                eff = self._get_or_create_effect(self.spin_effects, path, self.spin_base_volume)
                gap_ms = self._resolve_spin_restart_gap_ms()
                tail_guard_ms = self._remaining_audio_stop_guard_ms()
                self._schedule_spin_start(eff, delay_ms=max(gap_ms, tail_guard_ms))
            else:
                QtWidgets.QApplication.beep()
        except _SOUND_GUARD_ERRORS:
            QtWidgets.QApplication.beep()

    def stop_spin(self):
        self._cancel_pending_spin_start()
        had_active = self._stop_effects(self.spin_effects.values())
        self._mark_active_audio_stop(had_active)

    def set_master_volume(self, factor: float):
        """Setzt die Master-Lautstärke (0.0–1.0) für alle Effekte."""
        try:
            self.master_volume = max(0.0, min(1.0, float(factor)))
        except _SOUND_GUARD_ERRORS:
            self.master_volume = 1.0
        self._apply_volume(self.spin_effects.values(), self.spin_base_volume)
        self._apply_volume(self.ding_effects.values(), self.ding_base_volume)
        if self.preview_effect:
            self._apply_volume([self.preview_effect], self.preview_base_volume)

    def _apply_volume(self, effects, base_volume: float):
        vol = max(0.0, min(1.0, base_volume * self.master_volume))
        for eff in self._effects_snapshot(effects):
            try:
                eff.setVolume(vol)
            except _SOUND_GUARD_ERRORS:
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
        except _SOUND_GUARD_ERRORS:
            QtWidgets.QApplication.beep()

    def stop_ding(self):
        had_active = self._stop_effects(self.ding_effects.values())
        self._mark_active_audio_stop(had_active)

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
        except _SOUND_GUARD_ERRORS:
            QtWidgets.QApplication.beep()

    def _play_effect(self, eff: Any):
        try:
            eff.stop()
            eff.play()
        except _SOUND_GUARD_ERRORS:
            QtWidgets.QApplication.beep()

    def _create_preview_effect(self) -> Any | None:
        """
        Erzeugt einen kurzen synthetischen Ton als WAV im Temp-Ordner,
        mit moderater Lautstärke (nicht lauter als die Standard-WAVs).
        """
        try:
            qsound_effect_cls = _resolve_qsoundeffect()
            if qsound_effect_cls is None:
                return None
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

            eff = qsound_effect_cls()
            eff.setSource(QUrl.fromLocalFile(str(tmp_path)))
            eff.setLoopCount(1)
            eff.setVolume(self.preview_base_volume * self.master_volume)
            return eff
        except _SOUND_GUARD_ERRORS:
            return None
