from __future__ import annotations

import logging

from services.sound import SoundManager


_MAIN_WINDOW_SOUND_GUARD_ERRORS = (AttributeError, RuntimeError, TypeError, ValueError, LookupError, OSError)
_LOG = logging.getLogger(__name__)


class MainWindowSoundMixin:
    def _init_sound_manager(self) -> None:
        self.sound = SoundManager(base_dir=self._asset_dir, settings=getattr(self, "settings", None))
        # Ensure clean audio state on startup (no lingering backend playback).
        self.sound.stop_spin()
        self.sound.stop_ding()

    def _warmup_sound_async_if_enabled(
        self,
        *,
        step_ms: int,
        on_done=None,
    ) -> bool:
        if not bool(self._cfg("SOUND_WARMUP_ON_START", False)):
            return False
        try:
            self.sound.warmup_async(self, step_ms=int(step_ms), on_done=on_done)
            return True
        except _MAIN_WINDOW_SOUND_GUARD_ERRORS as exc:
            _LOG.debug("Sound warmup_async failed", exc_info=exc)
            return False

    def _startup_task_sound(self) -> None:
        started = self._warmup_sound_async_if_enabled(
            step_ms=int(self._post_choice_warmup_step_ms),
            on_done=lambda: self._startup_task_done("sound_warmup"),
        )
        if not started:
            self._startup_task_done("sound_warmup")

    def _pause_sound_background_warmup(self) -> None:
        if not bool(self._cfg("PAUSE_SOUND_WARMUP_DURING_SPIN", True)):
            return
        sound = getattr(self, "sound", None)
        if sound is None or not hasattr(sound, "pause_background_warmup"):
            return
        try:
            sound.pause_background_warmup()
        except _MAIN_WINDOW_SOUND_GUARD_ERRORS as exc:
            _LOG.debug("pause_background_warmup failed", exc_info=exc)

    def _resume_sound_background_warmup(self) -> None:
        if not bool(self._cfg("PAUSE_SOUND_WARMUP_DURING_SPIN", True)):
            return
        sound = getattr(self, "sound", None)
        if sound is None or not hasattr(sound, "resume_background_warmup"):
            return
        try:
            sound.resume_background_warmup()
        except _MAIN_WINDOW_SOUND_GUARD_ERRORS as exc:
            _LOG.debug("resume_background_warmup failed", exc_info=exc)

    def _on_volume_changed(self, value: int):
        factor = max(0.0, min(1.0, value / 100.0))
        try:
            self.sound.set_master_volume(factor)
        except _MAIN_WINDOW_SOUND_GUARD_ERRORS as exc:
            # Keep UI responsive even if an audio backend call fails.
            _LOG.debug("set_master_volume failed", exc_info=exc)
        self._update_volume_icon(value)
        # Wenn per Slider verändert, aktuell nicht mehr stumm gespeichert
        self._last_volume_before_mute = value if value > 0 else self._last_volume_before_mute
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state()

    def _update_volume_icon(self, value: int):
        if value <= 0:
            icon = "🔇"
        elif value <= 30:
            icon = "🔈"
        elif value <= 70:
            icon = "🔉"
        else:
            icon = "🔊"
        self.lbl_volume_icon.setText(icon)

    def _play_volume_preview(self):
        if getattr(self, "pending", 0) > 0:
            return
        if self.volume_slider.value() > 0:
            self.sound.play_preview()

    def _on_volume_icon_clicked(self):
        current = self.volume_slider.value()
        if current > 0:
            # mute und Wert merken
            self._last_volume_before_mute = current
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(0)
            self.volume_slider.blockSignals(False)
            self._on_volume_changed(0)
        else:
            # unmute auf letzten Wert oder Default 100
            new_val = self._last_volume_before_mute if self._last_volume_before_mute > 0 else 100
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(new_val)
            self.volume_slider.blockSignals(False)
            self._on_volume_changed(new_val)
