from __future__ import annotations

from difflib import SequenceMatcher
import warnings
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from model.main_window_runtime_state import OCRPreloadPhase
from ..ocr.ocr_role_import import (
    PendingOCRImport,
    normalize_name_key as normalize_ocr_name_key,
    resolve_selected_candidates as resolve_selected_ocr_candidates,
)
from ..ocr import ocr_import_ui_helpers as _ocr_import_ui_helpers
from ..ocr.ocr_preload_coordinator import OCRPreloadCoordinator
from ..ocr.ocr_preload_worker import (
    OCRPreloadRelay as _OCRPreloadRelay,
    OCRPreloadWorker as _OCRPreloadWorker,
)
from utils import ui_helpers


class MainWindowOCRMixin:
    def _runtime_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "runtime", None)

    def _ocr_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "ocr", None)

    def _runtime_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _ocr_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _ocr_float(self, attr: str, key: str, default: float) -> float:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            try:
                return float(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        try:
            return float(self._cfg(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _warn_ocr_suppressed_exception(self, where: str, exc: Exception) -> None:
        try:
            if self._runtime_bool("quiet", "QUIET", False):
                return
        except Exception:
            pass
        signature = (str(where or "ocr"), type(exc).__name__, str(exc))
        seen = getattr(self, "_ocr_suppressed_exception_seen", None)
        if not isinstance(seen, set):
            seen = set()
            setattr(self, "_ocr_suppressed_exception_seen", seen)
        if signature in seen:
            return
        seen.add(signature)
        try:
            warnings.warn(
                f"OCR suppressed exception at {where}: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )
        except Exception:
            pass
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "ocr_suppressed_exception",
                    where=str(where or "ocr"),
                    error=repr(exc),
                )
            except Exception:
                pass

    def _ocr_name_hint_candidates(self, role_key: str) -> list[str]:
        key = str(role_key or "").strip().casefold()
        names: list[str] = []
        seen: set[str] = set()

        def _add(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            norm = normalize_ocr_name_key(text)
            if not norm or norm in seen:
                return
            seen.add(norm)
            names.append(text)

        cfg_hints = self._cfg("OCR_NAME_HINTS", [])
        if isinstance(cfg_hints, (list, tuple, set)):
            for raw in cfg_hints:
                _add(str(raw or ""))
        if names and self._ocr_bool("name_hints_only_when_set", "OCR_NAME_HINTS_ONLY_WHEN_SET", True):
            return names

        if key in {"tank", "dps", "support"}:
            wheel = self._target_wheel_for_ocr_role(key)
            if wheel is not None and hasattr(wheel, "get_current_names"):
                try:
                    for current in wheel.get_current_names():
                        _add(str(current or ""))
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("name_hint_candidates:role_list", exc)
        else:
            for role in self._ocr_distribution_role_keys():
                wheel = self._target_wheel_for_ocr_role(role)
                if wheel is None or not hasattr(wheel, "get_current_names"):
                    continue
                try:
                    for current in wheel.get_current_names():
                        _add(str(current or ""))
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("name_hint_candidates:all_roles_list", exc)

        return names

    def _ocr_name_similarity_score_keys(self, left: str, right: str) -> float:
        left_key = str(left or "").strip()
        right_key = str(right or "").strip()
        if not left_key or not right_key:
            return 0.0
        if left_key == right_key:
            return 1.0

        max_len = max(len(left_key), len(right_key))
        if max_len >= 8:
            len_delta_ratio = abs(len(left_key) - len(right_key)) / max_len
            if len_delta_ratio > 0.45:
                return 0.0

        score = SequenceMatcher(None, left_key, right_key).ratio()
        if left_key in right_key or right_key in left_key:
            score += 0.12
        if left_key[:1] == right_key[:1]:
            score += 0.05
        return min(1.0, score)

    def _apply_ocr_name_hints(self, role_key: str, names: list[str]) -> list[str]:
        if not self._ocr_bool("use_name_hints", "OCR_USE_NAME_HINTS", False):
            return list(names or [])
        hints = self._ocr_name_hint_candidates(role_key)
        if not hints:
            return list(names or [])

        min_score = self._ocr_float("hint_correction_min_score", "OCR_HINT_CORRECTION_MIN_SCORE", 0.62)
        low_conf_min_score = self._ocr_float(
            "hint_correction_low_conf_min_score",
            "OCR_HINT_CORRECTION_LOW_CONF_MIN_SCORE",
            0.28,
        )

        hint_entries: list[tuple[str, str]] = []
        seen_hint_keys: set[str] = set()
        for hint in list(hints or []):
            hint_text = str(hint or "").strip()
            hint_key = normalize_ocr_name_key(hint_text)
            if not hint_key or hint_key in seen_hint_keys:
                continue
            seen_hint_keys.add(hint_key)
            hint_entries.append((hint_text, hint_key))
        if not hint_entries:
            return list(names or [])

        normalized_input = [str(value or "").strip() for value in list(names or []) if str(value or "").strip()]
        if not normalized_input:
            return []
        expected = max(5, len(normalized_input))

        corrected: list[str] = []
        used_hints: set[str] = set()
        hint_keys = {hint_key for _hint, hint_key in hint_entries}
        unmatched_input = 0
        short_count = 0

        for raw_name in normalized_input:
            raw_key = normalize_ocr_name_key(raw_name)
            if len(raw_name) <= 3:
                short_count += 1
            best_hint = ""
            best_hint_key = ""
            best_score = 0.0
            for hint, hint_key in hint_entries:
                if not hint_key or hint_key in used_hints:
                    continue
                score = self._ocr_name_similarity_score_keys(raw_key, hint_key)
                if score > best_score:
                    best_score = score
                    best_hint = hint
                    best_hint_key = hint_key
            if best_hint and best_score >= min_score:
                corrected.append(best_hint)
                used_hints.add(best_hint_key)
            else:
                corrected.append(raw_name)
                unmatched_input += 1

        looks_noisy = (
            unmatched_input >= max(1, len(normalized_input) // 2)
            or (short_count / max(1, len(normalized_input))) >= 0.34
        )
        if looks_noisy:
            for idx, raw_name in enumerate(list(corrected)):
                raw_key = normalize_ocr_name_key(raw_name)
                if raw_key in hint_keys:
                    continue
                best_hint = ""
                best_hint_key = ""
                best_score = 0.0
                for hint, hint_key in hint_entries:
                    if not hint_key or hint_key in used_hints:
                        continue
                    score = self._ocr_name_similarity_score_keys(raw_key, hint_key)
                    if score > best_score:
                        best_score = score
                        best_hint = hint
                        best_hint_key = hint_key
                if best_hint and best_score >= low_conf_min_score:
                    corrected[idx] = best_hint
                    used_hints.add(best_hint_key)

            if len(hint_entries) <= (expected + 3):
                for idx, raw_name in enumerate(list(corrected)):
                    if normalize_ocr_name_key(raw_name) in hint_keys:
                        continue
                    replacement = ""
                    replacement_key = ""
                    for hint, hint_key in hint_entries:
                        if not hint_key or hint_key in used_hints:
                            continue
                        replacement = hint
                        replacement_key = hint_key
                        break
                    if replacement:
                        corrected[idx] = replacement
                        used_hints.add(replacement_key)

        deduped: list[str] = []
        seen: set[str] = set()
        for value in corrected:
            key_norm = normalize_ocr_name_key(value)
            if not key_norm or key_norm in seen:
                continue
            seen.add(key_norm)
            deduped.append(value)

        if looks_noisy and len(deduped) < expected:
            for hint, key_norm in hint_entries:
                if not key_norm or key_norm in seen:
                    continue
                deduped.append(hint)
                seen.add(key_norm)
                if len(deduped) >= expected:
                    break

        return deduped

    def _target_wheel_for_ocr_role(self, role_key: str):
        attr_map = {
            "tank": "tank",
            "dps": "dps",
            "support": "support",
        }
        attr = attr_map.get(str(role_key or "").strip().casefold())
        if not attr:
            return None
        return getattr(self, attr, None)

    def _register_role_ocr_button(self, role_key: str, button: QtWidgets.QPushButton) -> None:
        key = str(role_key or "").strip().casefold()
        if not key or button is None:
            return
        self._role_ocr_buttons[key] = button
        self._refresh_role_ocr_button_text(key)

    def _ocr_role_button_meta(self, role_key: str) -> tuple[str, str, int]:
        key = str(role_key or "").strip().casefold()
        meta = {
            "tank": ("ocr.tank_button", "ocr.tank_button_tooltip", 44),
            "dps": ("ocr.dps_button", "ocr.dps_button_tooltip", 44),
            "support": ("ocr.support_button", "ocr.support_button_tooltip", 44),
        }
        return meta.get(key, ("ocr.dps_button", "ocr.dps_button_tooltip", 44))

    def _ocr_role_display_name(self, role_key: str) -> str:
        key = str(role_key or "").strip().casefold()
        labels = {
            "tank": "Tank",
            "dps": "DPS",
            "support": "Support",
        }
        return labels.get(key, key.upper() or "DPS")

    def _refresh_role_ocr_button_text(self, role_key: str) -> None:
        key = str(role_key or "").strip().casefold()
        btn = self._role_ocr_buttons.get(key)
        if btn is None:
            return
        text_key, tooltip_key, padding = self._ocr_role_button_meta(key)
        btn.setText(i18n.t(text_key))
        self._set_ocr_button_tooltip(btn, self._ocr_button_tooltip_text(tooltip_key))
        ui_helpers.set_fixed_width_from_translations([btn], [text_key], padding=max(0, int(padding)))

    def _refresh_all_role_ocr_button_texts(self) -> None:
        for role_key in tuple(self._role_ocr_buttons.keys()):
            self._refresh_role_ocr_button_text(role_key)

    def _role_ocr_import_available(self, role_key: str) -> bool:
        key = str(role_key or "").strip().casefold()
        if getattr(self, "_closing", False):
            return False
        if getattr(self, "pending", 0) > 0:
            return False
        if getattr(self, "current_mode", "") == "maps":
            return False
        if getattr(self, "hero_ban_active", False):
            return False
        if key == "all":
            role_keys = self._ocr_distribution_role_keys()
            return bool(role_keys) and all(self._target_wheel_for_ocr_role(k) is not None for k in role_keys)
        return self._target_wheel_for_ocr_role(key) is not None

    def _ocr_preload_ui_block_active(self) -> bool:
        if not self._ocr_background_preload_enabled():
            return False
        if bool(getattr(self, "_ocr_runtime_activated", False)):
            return False
        if bool(getattr(self, "_ocr_preload_done", False)):
            return False
        return not bool(getattr(self, "_ocr_preload_attempted", False))

    def _ocr_button_tooltip_text(self, default_tooltip_key: str) -> str:
        key = str(default_tooltip_key or "").strip() or "ocr.dps_button_tooltip"
        if self._ocr_preload_ui_block_active():
            return i18n.t("ocr.loading_tooltip")
        return i18n.t(key)

    def _refresh_live_tooltip_for_widget(self, widget: QtWidgets.QWidget, text: str) -> None:
        if widget is None:
            return
        try:
            if not QtWidgets.QToolTip.isVisible():
                return
        except Exception:
            return
        try:
            global_pos = QtGui.QCursor.pos()
        except Exception:
            return
        try:
            local_pos = widget.mapFromGlobal(global_pos)
            if not widget.rect().contains(local_pos):
                return
        except Exception:
            try:
                if not bool(widget.underMouse()):
                    return
            except Exception:
                return
        try:
            QtWidgets.QToolTip.showText(global_pos, str(text or ""), widget, widget.rect())
        except Exception as exc:
            self._warn_ocr_suppressed_exception("refresh_live_tooltip:show_text", exc)

    def _set_ocr_button_tooltip(self, btn: QtWidgets.QWidget, text: str) -> None:
        if btn is None:
            return
        value = str(text or "")
        btn.setToolTip(value)
        self._refresh_live_tooltip_for_widget(btn, value)

    def _update_role_ocr_button_enabled(self, role_key: str) -> None:
        key = str(role_key or "").strip().casefold()
        btn = self._role_ocr_buttons.get(key)
        if btn is None:
            return
        _, tooltip_key, _ = self._ocr_role_button_meta(key)
        enabled = self._role_ocr_import_available(role_key)
        if self._overlay_choice_active():
            enabled = False
        waiting_preload = self._ocr_preload_ui_block_active()
        if waiting_preload:
            enabled = False
        btn.setEnabled(enabled)
        self._set_ocr_button_tooltip(btn, self._ocr_button_tooltip_text(tooltip_key))

    def _update_role_ocr_buttons_enabled(self) -> None:
        waiting_preload = self._ocr_preload_ui_block_active()
        for role_key in tuple(self._role_ocr_buttons.keys()):
            self._update_role_ocr_button_enabled(role_key)
        if hasattr(self, "btn_open_q_ocr"):
            enabled = self._role_ocr_import_available("all")
            if self._overlay_choice_active():
                enabled = False
            if waiting_preload:
                enabled = False
            self.btn_open_q_ocr.setEnabled(enabled)
            self._set_ocr_button_tooltip(
                self.btn_open_q_ocr,
                self._ocr_button_tooltip_text("ocr.open_q_button_tooltip"),
            )

    def _ocr_runtime_sleep_until_used(self) -> bool:
        return self._ocr_bool("runtime_sleep_until_used", "OCR_RUNTIME_SLEEP_UNTIL_USED", True)

    def _set_ocr_preload_phase(
        self,
        phase: str | OCRPreloadPhase,
        *,
        reason: str | None = None,
    ) -> None:
        phase_value = phase.value if isinstance(phase, OCRPreloadPhase) else str(phase or "").strip() or OCRPreloadPhase.IDLE.value
        reason_value = str(reason).strip() if reason is not None else None
        if not reason_value:
            reason_value = None
        current_phase = str(getattr(self, "_ocr_preload_phase", "") or "").strip()
        current_reason = getattr(self, "_ocr_preload_phase_reason", None)
        if current_phase == phase_value and current_reason == reason_value:
            return
        try:
            self._set_startup_runtime_state(
                ocr_preload_phase=phase_value,
                ocr_preload_phase_reason=reason_value,
            )
        except Exception:
            self._ocr_preload_phase = phase_value
            self._ocr_preload_phase_reason = reason_value
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "ocr_preload_phase",
                    phase=str(phase_value),
                    reason=str(reason_value or ""),
                )
            except Exception:
                pass

    def _mark_ocr_runtime_activated(self) -> None:
        self._ocr_runtime_activated = True
        self._ocr_preload_done = True
        self._ocr_preload_attempted = True
        self._set_ocr_preload_phase(OCRPreloadPhase.DONE, reason="runtime_activated")
        if hasattr(self, "_update_role_ocr_buttons_enabled") and hasattr(self, "_role_ocr_buttons"):
            try:
                self._update_role_ocr_buttons_enabled()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("mark_runtime_activated:update_buttons", exc)
        if hasattr(self, "_cancel_ocr_background_preload"):
            try:
                self._cancel_ocr_background_preload()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("mark_runtime_activated:cancel_preload", exc)

    def _ocr_preload_coordinator(self) -> OCRPreloadCoordinator:
        coordinator = getattr(self, "_ocr_preload_coordinator_obj", None)
        if isinstance(coordinator, OCRPreloadCoordinator):
            return coordinator
        coordinator = OCRPreloadCoordinator(
            self,
            worker_cls=_OCRPreloadWorker,
            relay_cls=_OCRPreloadRelay,
        )
        self._ocr_preload_coordinator_obj = coordinator
        return coordinator

    def _ocr_background_preload_enabled(self) -> bool:
        return self._ocr_preload_coordinator().background_preload_enabled()

    def _easyocr_resolution_kwargs(self) -> dict[str, object]:
        return self._ocr_preload_coordinator().easyocr_resolution_kwargs()

    def _ensure_ocr_background_preload_timer(self) -> QtCore.QTimer:
        return self._ocr_preload_coordinator().ensure_background_preload_timer()

    def _cancel_ocr_background_preload(self) -> None:
        self._ocr_preload_coordinator().cancel_background_preload()

    def _stop_ocr_background_preload_job(
        self,
        *,
        reason: str = "",
        wait_ms: int = 0,
    ) -> None:
        self._ocr_preload_coordinator().stop_background_preload_job(
            reason=reason,
            wait_ms=wait_ms,
        )

    def _schedule_ocr_background_preload(
        self,
        *,
        delay_ms: int | None = None,
        reason: str = "",
    ) -> None:
        self._ocr_preload_coordinator().schedule_background_preload(
            delay_ms=delay_ms,
            reason=reason,
        )

    def _ocr_background_preload_block_reason(self) -> str | None:
        return self._ocr_preload_coordinator().background_preload_block_reason()

    def _run_ocr_background_preload(self) -> None:
        self._ocr_preload_coordinator().run_background_preload()

    def _ensure_ocr_cache_release_timer(self) -> QtCore.QTimer:
        return self._ocr_preload_coordinator().ensure_cache_release_timer()

    def _cancel_ocr_runtime_cache_release(self) -> None:
        self._ocr_preload_coordinator().cancel_cache_release()

    def _schedule_ocr_runtime_cache_release(self) -> None:
        self._ocr_preload_coordinator().schedule_cache_release()

    def _spin_active_for_ocr_cache_release(self) -> bool:
        return self._ocr_preload_coordinator().spin_active_for_cache_release()

    def _release_ocr_runtime_cache(self) -> None:
        self._ocr_preload_coordinator().release_cache()

    def _release_ocr_runtime_cache_for_spin(self) -> None:
        """Optionally release OCR runtime cache on spin start."""
        self._ocr_preload_coordinator().release_cache_for_spin()

    def _ocr_distribution_role_keys(self) -> tuple[str, ...]:
        return _ocr_import_ui_helpers.ocr_distribution_role_keys()

    def _ocr_subrole_labels_for_role(self, role_key: str) -> list[str]:
        return _ocr_import_ui_helpers.ocr_subrole_labels_for_role(self, role_key)

    def _ocr_assignment_options(
        self,
        role_key: str,
    ) -> tuple[
        list[str],
        dict[str, str],
        dict[str, str],
        str,
    ]:
        return _ocr_import_ui_helpers.ocr_assignment_options(
            self,
            role_key,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _normalize_ocr_candidate_names(self, names: list[str]) -> list[str]:
        return _ocr_import_ui_helpers.normalize_ocr_candidate_names(names)

    def _request_ocr_import_selection(self, role_key: str, names: list[str]) -> bool:
        return _ocr_import_ui_helpers.request_ocr_import_selection(
            self,
            role_key,
            names,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _selected_ocr_entries_for_pending(
        self,
        pending: PendingOCRImport,
        selected_payload,
    ) -> list[dict]:
        return _ocr_import_ui_helpers.selected_ocr_entries_for_pending(
            self,
            pending,
            selected_payload,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
            resolve_selected_ocr_candidates_fn=resolve_selected_ocr_candidates,
        )

    def _role_subroles_from_main_flex_codes(self, role_key: str, codes: list[str] | None) -> list[str]:
        return _ocr_import_ui_helpers.role_subroles_from_main_flex_codes(self, role_key, codes)

    def _plan_distributed_ocr_entries_for_add(self, entries: list[dict]) -> dict[str, list[dict]]:
        return _ocr_import_ui_helpers.plan_distributed_ocr_entries_for_add(
            self,
            entries,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _add_ocr_entries_distributed(self, entries: list[dict]) -> tuple[int, dict[str, int]]:
        return _ocr_import_ui_helpers.add_ocr_entries_distributed(
            self,
            entries,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _replace_ocr_entries_distributed(self, entries: list[dict]) -> tuple[int, dict[str, int]]:
        return _ocr_import_ui_helpers.replace_ocr_entries_distributed(
            self,
            entries,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _add_ocr_entries_for_role(self, role_key: str, entries: list[dict]) -> int:
        return _ocr_import_ui_helpers.add_ocr_entries_for_role(
            self,
            role_key,
            entries,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _replace_ocr_entries_for_role(self, role_key: str, entries: list[dict]) -> int:
        return _ocr_import_ui_helpers.replace_ocr_entries_for_role(
            self,
            role_key,
            entries,
            normalize_ocr_name_key_fn=normalize_ocr_name_key,
        )

    def _show_ocr_import_result_for_role(self, role_key: str, *, added: int, total: int) -> None:
        _ocr_import_ui_helpers.show_ocr_import_result_for_role(
            self,
            role_key,
            added=added,
            total=total,
        )

    def _show_ocr_import_result_distributed(self, *, added: int, total: int, counts: dict[str, int]) -> None:
        _ocr_import_ui_helpers.show_ocr_import_result_distributed(
            self,
            added=added,
            total=total,
            counts=counts,
        )

    def _on_overlay_ocr_import_confirmed(self, selected_names):
        _ocr_import_ui_helpers.on_overlay_ocr_import_confirmed(self, selected_names)

    def _on_overlay_ocr_import_replace_requested(self, selected_names):
        _ocr_import_ui_helpers.on_overlay_ocr_import_replace_requested(self, selected_names)

    def _on_overlay_ocr_import_cancelled(self):
        _ocr_import_ui_helpers.on_overlay_ocr_import_cancelled(self)
