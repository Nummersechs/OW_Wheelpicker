from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import concurrent.futures.thread as _futures_thread
from pathlib import Path
import threading
import weakref
from typing import Any, Dict, List

from PySide6 import QtCore

from controller.state_sync_components import (
    LocalStatePersistenceQueue,
    MainWindowSnapshotSource,
    RemoteRoleSyncService,
    RoleSyncPayloadBuilder,
    StateFilePersistence,
    StateSnapshotBuilder,
)


class _DaemonThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor variant whose workers are daemon threads."""

    def _adjust_thread_count(self) -> None:  # pragma: no cover - stdlib private API shim
        # If idle threads are available, don't spin new threads.
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads >= self._max_workers:
            return
        thread_name = f"{self._thread_name_prefix or self}_{num_threads}"
        worker = threading.Thread(
            name=thread_name,
            target=_futures_thread._worker,
            args=(
                weakref.ref(self, weakref_cb),
                self._work_queue,
                self._initializer,
                self._initargs,
            ),
            daemon=True,
        )
        worker.start()
        self._threads.add(worker)
        _futures_thread._threads_queues[worker] = self._work_queue


class StateSyncController(QtCore.QObject):
    """Handle saved_state persistence + online sync outside MainWindow."""

    def __init__(self, main_window, state_file: Path) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._settings = getattr(main_window, "settings", None)
        self._state_file = state_file
        self._snapshot_builder = StateSnapshotBuilder(MainWindowSnapshotSource(main_window))
        self._role_payload_builder = RoleSyncPayloadBuilder()
        self._local_persistence = LocalStatePersistenceQueue(
            state_file=self._state_file,
            load_state_fn=self._load_state,
            save_state_fn=self._save_state,
            state_signature_fn=self._state_signature,
        )
        self._closed = False
        self._save_debounce_ms = max(0, int(self._cfg("STATE_SAVE_DEBOUNCE_MS", 220)))
        self._sync_debounce_ms = max(0, int(self._cfg("NETWORK_SYNC_DEBOUNCE_MS", 220)))
        workers = max(1, int(self._cfg("NETWORK_SYNC_WORKERS", 2)))
        self._remote_sync = RemoteRoleSyncService(
            cfg_resolver=self._cfg,
            debug_print=self._debug_print,
            executor_workers=workers,
            executor_cls=_DaemonThreadPoolExecutor,
            thread_name_prefix="state_sync",
        )
        self._pending_state: Dict[str, Any] | None = None
        self._pending_state_dirty = False
        self._pending_save_sync = False
        self._last_saved_signature: str | None = None
        self._sync_local_persistence_mirror()
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_pending_save)
        self._pending_sync_payload: list[dict] | None = None
        self._pending_sync_dirty = False
        self._last_synced_roles_signature: str | None = None
        self._sync_timer = QtCore.QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_role_sync)

    @property
    def _executor(self) -> ThreadPoolExecutor | None:
        return self._remote_sync.executor

    @_executor.setter
    def _executor(self, value: ThreadPoolExecutor | None) -> None:
        self._remote_sync.executor = value

    def _cfg(self, key: str, default: Any = None) -> Any:
        settings = self._settings
        if settings is not None and hasattr(settings, "resolve"):
            try:
                return settings.resolve(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        return default

    def _debug_print(self, *args, **kwargs) -> None:
        runtime = getattr(self._settings, "runtime", None)
        if runtime is not None:
            debug_enabled = bool(getattr(runtime, "debug", False))
            quiet_enabled = bool(getattr(runtime, "quiet", False))
        else:
            debug_enabled = bool(self._cfg("DEBUG", False))
            quiet_enabled = bool(self._cfg("QUIET", False))
        if not debug_enabled or quiet_enabled:
            return
        try:
            print(*args, **kwargs)
        except OSError:
            pass

    @staticmethod
    def state_file(base_dir: Path) -> Path:
        """Return the path to saved_state.json relative to the running package."""
        return base_dir / "saved_state.json"

    @staticmethod
    def _load_state(path: Path) -> Dict[str, Any]:
        """Load saved state or return an empty dict on failure."""
        return StateFilePersistence.load_state(path)

    @staticmethod
    def _save_state(path: Path, data: Dict[str, Any]) -> bool:
        """Write state as JSON. Returns True on success."""
        return StateFilePersistence.save_state(path, data)

    @staticmethod
    def _state_signature(data: Dict[str, Any]) -> str | None:
        return StateFilePersistence.state_signature(data)

    @staticmethod
    def load_saved_state(state_file: Path) -> dict:
        data = StateSyncController._load_state(state_file)
        if isinstance(data, dict):
            return data
        return {}

    def _sync_local_persistence_mirror(self) -> None:
        local = self._local_persistence
        self._pending_state = local.pending_state
        self._pending_state_dirty = bool(local.pending_state_dirty)
        self._pending_save_sync = bool(local.pending_save_sync)
        self._last_saved_signature = local.last_saved_signature

    def _push_local_persistence_from_mirror(self) -> None:
        local = self._local_persistence
        local.pending_state = self._pending_state
        local.pending_state_dirty = bool(self._pending_state_dirty)
        local.pending_save_sync = bool(self._pending_save_sync)
        local.last_saved_signature = self._last_saved_signature

    def gather_state(self) -> dict:
        return self._snapshot_builder.gather_state()

    def save_state(self, sync: bool = True, immediate: bool = False) -> None:
        if self._closed:
            return
        if getattr(self._mw, "_restoring_state", False):
            return
        if getattr(self._mw, "_closing", False):
            sync = False
            immediate = True
        if immediate:
            state = self.gather_state()
            if self._save_timer.isActive():
                self._save_timer.stop()
            self._push_local_persistence_from_mirror()
            self._local_persistence.clear_pending()
            self._sync_local_persistence_mirror()
            self._persist_state(state)
            if sync:
                self.sync_all_roles()
        else:
            # Build state once on flush instead of on every UI event while typing.
            self._push_local_persistence_from_mirror()
            self._local_persistence.queue_save(sync=sync)
            self._sync_local_persistence_mirror()
            self._save_timer.start(self._save_debounce_ms)
        if self._mw.hero_ban_active and not getattr(self._mw, "_closing", False):
            self._mw._update_hero_ban_wheel()

    def _persist_state(self, state: Dict[str, Any]) -> None:
        self._push_local_persistence_from_mirror()
        self._local_persistence.persist_state_with(
            state,
            save_state_fn=self._save_state,
            state_signature_fn=self._state_signature,
        )
        self._sync_local_persistence_mirror()

    def _flush_pending_save(self) -> None:
        self._push_local_persistence_from_mirror()
        state, sync = self._local_persistence.consume_pending(gather_state_fn=self.gather_state)
        self._sync_local_persistence_mirror()
        if state is None:
            return
        self._persist_state(state)
        if sync:
            self.sync_all_roles()

    def shutdown(self, flush: bool = True) -> None:
        """Stop pending timers and clear queued sync payloads."""
        self._closed = True
        if flush:
            self._flush_pending_save()
        if self._save_timer.isActive():
            self._save_timer.stop()
        if self._sync_timer.isActive():
            self._sync_timer.stop()
        self._push_local_persistence_from_mirror()
        self._local_persistence.clear_pending()
        self._sync_local_persistence_mirror()
        self._pending_sync_payload = None
        self._pending_sync_dirty = False
        self._remote_sync.shutdown()

    def resource_snapshot(self) -> dict:
        save_timer_active = False
        sync_timer_active = False
        try:
            save_timer_active = bool(self._save_timer.isActive())
        except RuntimeError:
            pass
        try:
            sync_timer_active = bool(self._sync_timer.isActive())
        except RuntimeError:
            pass
        remote_snapshot = self._remote_sync.resource_snapshot()
        return {
            "closed": bool(self._closed),
            "save_timer_active": save_timer_active,
            "sync_timer_active": sync_timer_active,
            "has_pending_state": bool(self._pending_state is not None or self._pending_state_dirty),
            "pending_save_sync": bool(self._pending_save_sync),
            "has_pending_sync_payload": bool(self._pending_sync_payload is not None or self._pending_sync_dirty),
            "network_threads_active": int(remote_snapshot.get("network_threads_active", 0)),
            "network_futures_pending": int(remote_snapshot.get("network_futures_pending", 0)),
        }

    def _ensure_executor(self) -> ThreadPoolExecutor | None:
        return self._remote_sync.ensure_executor(
            closed=bool(self._closed),
        )

    def _get_requests_module(self) -> Any | None:
        return self._remote_sync.get_requests_module()

    def send_spin_result(self, tank: str, damage: str, support: str) -> None:
        if self._closed:
            return
        if not getattr(self._mw, "online_mode", False):
            self._debug_print("Spin-Result: Offline-Modus - kein Senden.")
            return
        pair_modes = self._role_payload_builder.pair_modes(self._mw)
        self._send_spin_result(tank, damage, support, pair_modes)

    def sync_all_roles(self) -> None:
        if self._closed:
            return
        if not getattr(self._mw, "online_mode", False):
            self._debug_print("Sync uebersprungen: Offline-Modus.")
            self._pending_sync_payload = None
            self._pending_sync_dirty = False
            if self._sync_timer.isActive():
                self._sync_timer.stop()
            return
        self._pending_sync_dirty = True
        # kurze Verzoegerung, um schnelle State-Aenderungen zu buendeln
        self._sync_timer.start(self._sync_debounce_ms)

    def _flush_role_sync(self) -> None:
        """Sendet den letzten vorbereiteten Sync-Payload (debounced)."""
        if not getattr(self._mw, "online_mode", False):
            self._pending_sync_payload = None
            self._pending_sync_dirty = False
            return
        if self._pending_sync_dirty:
            self._pending_sync_payload = self._role_payload_builder.roles_payload(self._mw)
            self._pending_sync_dirty = False
        payload = self._pending_sync_payload
        self._pending_sync_payload = None
        if not payload:
            return
        signature = self._state_signature({"roles": payload})
        if signature is not None and signature == self._last_synced_roles_signature:
            return
        self._sync_roles(payload)
        if signature is not None:
            self._last_synced_roles_signature = signature

    @staticmethod
    def _split_pair_label(label: str, is_pair_mode: bool) -> tuple[str, str]:
        return RoleSyncPayloadBuilder.split_pair_label(label, is_pair_mode)

    def _post_json_async(
        self,
        *,
        endpoint: str,
        payload: Dict[str, Any],
        payload_log: str,
        success_log: str,
        error_log: str,
        missing_requests_log: str,
    ) -> None:
        """Post JSON payload in a daemon thread (transport delegated)."""
        if self._closed:
            return
        requests_module = self._get_requests_module()
        if requests_module is None:
            self._debug_print(missing_requests_log)
            return
        executor = self._ensure_executor()
        if executor is None:
            return
        self._remote_sync.post_json_async_prepared(
            endpoint=endpoint,
            payload=payload,
            payload_log=payload_log,
            success_log=success_log,
            error_log=error_log,
            missing_requests_log=missing_requests_log,
            requests_module=requests_module,
            executor=executor,
        )

    def _send_spin_result(self, tank: str, damage: str, support: str, pair_modes: Dict[str, bool]) -> None:
        """Send spin result to the server in a background thread."""
        payload = self._role_payload_builder.spin_result_payload(
            tank=tank,
            damage=damage,
            support=support,
            pair_modes=pair_modes,
        )
        self._post_json_async(
            endpoint="/spin-result",
            payload=payload,
            payload_log="Sende Payload:",
            success_log="Spin-Ergebnis erfolgreich an Server gesendet:",
            error_log="Fehler beim Senden des Spin-Ergebnisses:",
            missing_requests_log="Requests not available – spin result not sent.",
        )

    def _sync_roles(self, roles: List[Dict[str, Any]]) -> None:
        """Sync role lists to the server in a background thread."""
        self._post_json_async(
            endpoint="/roles-sync",
            payload={"roles": roles},
            payload_log="SYNC →",
            success_log="SYNC OK:",
            error_log="Fehler beim Rollen-Sync:",
            missing_requests_log="Requests not available – roles not synced.",
        )
