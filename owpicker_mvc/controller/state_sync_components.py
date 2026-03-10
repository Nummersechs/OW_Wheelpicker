from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Protocol

from model.role_keys import role_wheel_map


class StateFilePersistence:
    """Local JSON persistence primitives for saved_state."""

    @staticmethod
    def load_state(path: Path) -> Dict[str, Any]:
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return {}

    @staticmethod
    def save_state(path: Path, data: Dict[str, Any]) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, TypeError, ValueError):
            return False

    @staticmethod
    def state_signature(data: Dict[str, Any]) -> str | None:
        try:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return None


class StateSnapshotBuilder:
    """Builds saved-state snapshots from an injected snapshot source."""

    def __init__(self, source) -> None:
        if hasattr(source, "gather_state") and callable(getattr(source, "gather_state", None)):
            self._source = source
        else:
            self._source = MainWindowSnapshotSource(source)

    def gather_state(self) -> dict:
        return self._source.gather_state()


class SnapshotSource(Protocol):
    def gather_state(self) -> dict:
        ...


class MainWindowSnapshotSource:
    """Adapter that delegates snapshot capture to MainWindow's public API."""

    def __init__(self, main_window) -> None:
        self._main_window = main_window
        provider = getattr(main_window, "gather_state_snapshot", None)
        if not callable(provider):
            raise TypeError("snapshot source must expose gather_state_snapshot()")
        self._provider = provider

    def gather_state(self) -> dict:
        try:
            state = self._provider()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            state = None
        if isinstance(state, dict):
            return state
        return {}


class LocalStatePersistenceQueue:
    """Tracks debounced save-state queue + deduplicated persistence signature."""

    def __init__(
        self,
        *,
        state_file: Path,
        load_state_fn: Callable[[Path], Dict[str, Any]],
        save_state_fn: Callable[[Path, Dict[str, Any]], bool],
        state_signature_fn: Callable[[Dict[str, Any]], str | None],
    ) -> None:
        self._state_file = state_file
        self._load_state_fn = load_state_fn
        self._save_state_fn = save_state_fn
        self._state_signature_fn = state_signature_fn
        self.pending_state: Dict[str, Any] | None = None
        self.pending_state_dirty: bool = False
        self.pending_save_sync: bool = False
        self.last_saved_signature: str | None = None
        existing = self._load_state_fn(self._state_file)
        if existing:
            self.last_saved_signature = self._state_signature_fn(existing)

    def queue_save(self, *, sync: bool = False) -> None:
        self.pending_state_dirty = True
        self.pending_save_sync = bool(self.pending_save_sync or sync)

    def clear_pending(self) -> None:
        self.pending_state = None
        self.pending_state_dirty = False
        self.pending_save_sync = False

    def consume_pending(
        self,
        *,
        gather_state_fn: Callable[[], Dict[str, Any]],
    ) -> tuple[Dict[str, Any] | None, bool]:
        state = self.pending_state
        sync = bool(self.pending_save_sync)
        dirty = bool(self.pending_state_dirty)
        self.clear_pending()
        if state is None and not dirty:
            return None, sync
        if state is None:
            state = gather_state_fn()
        return state, sync

    def persist_state(self, state: Dict[str, Any]) -> bool:
        return self.persist_state_with(
            state,
            save_state_fn=self._save_state_fn,
            state_signature_fn=self._state_signature_fn,
        )

    def persist_state_with(
        self,
        state: Dict[str, Any],
        *,
        save_state_fn: Callable[[Path, Dict[str, Any]], bool],
        state_signature_fn: Callable[[Dict[str, Any]], str | None],
    ) -> bool:
        signature = state_signature_fn(state)
        if signature is not None and signature == self.last_saved_signature:
            return False
        saved = bool(save_state_fn(self._state_file, state))
        if saved and signature is not None:
            self.last_saved_signature = signature
        return saved


class RoleSyncPayloadBuilder:
    """Build payloads for role-sync and spin-result endpoints."""

    @staticmethod
    def pair_modes(main_window) -> Dict[str, bool]:
        return {
            role: getattr(wheel, "pair_mode", False)
            for role, wheel in role_wheel_map(main_window).items()
        }

    @staticmethod
    def roles_payload(main_window) -> List[Dict[str, Any]]:
        return [
            {"role": role, "names": wheel.get_current_names()}
            for role, wheel in role_wheel_map(main_window).items()
        ]

    @staticmethod
    def split_pair_label(label: str, is_pair_mode: bool) -> tuple[str, str]:
        label = (label or "").strip()
        if not label:
            return "", ""
        if not is_pair_mode:
            return label, ""
        parts = [p.strip() for p in label.split("+") if p.strip()]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " + ".join(parts[1:])

    @classmethod
    def spin_result_payload(
        cls,
        *,
        tank: str,
        damage: str,
        support: str,
        pair_modes: Dict[str, bool],
    ) -> Dict[str, str]:
        tank1, tank2 = cls.split_pair_label(tank, pair_modes.get("Tank", False))
        dps1, dps2 = cls.split_pair_label(damage, pair_modes.get("Damage", False))
        sup1, sup2 = cls.split_pair_label(support, pair_modes.get("Support", False))
        return {
            "tank1": tank1,
            "tank2": tank2,
            "dps1": dps1,
            "dps2": dps2,
            "support1": sup1,
            "support2": sup2,
        }


class RemoteRoleSyncService:
    """Remote role-sync transport with async worker/executor lifecycle."""

    def __init__(
        self,
        *,
        cfg_resolver: Callable[[str, Any], Any],
        debug_print: Callable[..., None],
        executor_workers: int = 2,
        executor_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
        thread_name_prefix: str = "state_sync",
    ) -> None:
        self._cfg_resolver = cfg_resolver
        self._debug_print = debug_print
        self._executor_workers = max(1, int(executor_workers))
        self._executor_cls = executor_cls
        self._thread_name_prefix = str(thread_name_prefix or "state_sync")
        self._closed = False
        self._network_threads_active = 0
        self._network_threads_lock = threading.Lock()
        self._network_futures: set[Future] = set()
        self._network_futures_lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._requests_checked = False
        self._requests_module: Any | None = None

    @property
    def executor(self) -> ThreadPoolExecutor | None:
        return self._executor

    @executor.setter
    def executor(self, value: ThreadPoolExecutor | None) -> None:
        self._executor = value

    def resource_snapshot(self) -> dict[str, int]:
        with self._network_threads_lock:
            active_threads = int(self._network_threads_active)
        with self._network_futures_lock:
            pending_futures = len(self._network_futures)
        return {
            "network_threads_active": active_threads,
            "network_futures_pending": pending_futures,
        }

    def shutdown(self) -> None:
        self._closed = True
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=False)
            self._executor = None
        with self._network_futures_lock:
            self._network_futures.clear()

    def ensure_executor(self, *, closed: bool = False) -> ThreadPoolExecutor | None:
        if self._closed or closed:
            return None
        if self._executor is not None:
            return self._executor
        self._executor = self._executor_cls(
            max_workers=self._executor_workers,
            thread_name_prefix=self._thread_name_prefix,
        )
        return self._executor

    def get_requests_module(self) -> Any | None:
        if self._requests_checked:
            return self._requests_module
        self._requests_checked = True
        try:
            self._requests_module = importlib.import_module("requests")
        except (ModuleNotFoundError, ImportError):
            self._requests_module = None
        return self._requests_module

    def post_json_async_prepared(
        self,
        *,
        endpoint: str,
        payload: Dict[str, Any],
        payload_log: str,
        success_log: str,
        error_log: str,
        missing_requests_log: str,
        requests_module: Any | None,
        executor: ThreadPoolExecutor | None,
    ) -> None:
        if self._closed:
            return
        if requests_module is None:
            self._debug_print(missing_requests_log)
            return
        if executor is None:
            return

        def _worker() -> None:
            with self._network_threads_lock:
                self._network_threads_active += 1
            request_exception = getattr(requests_module, "RequestException", None)
            known_errors: tuple[type[BaseException], ...] = (
                OSError,
                RuntimeError,
                TimeoutError,
                TypeError,
                ValueError,
            )
            if isinstance(request_exception, type) and issubclass(request_exception, BaseException):
                known_errors = (request_exception, *known_errors)
            try:
                base = str(self._cfg_resolver("API_BASE_URL", "http://localhost:5326"))
                url = base.rstrip("/") + str(endpoint)
                self._debug_print(payload_log, payload)
                resp = requests_module.post(url, json=payload, timeout=3)
                resp.raise_for_status()
                self._debug_print(success_log, resp.json())
            except known_errors as e:
                self._debug_print(error_log, e)
            finally:
                with self._network_threads_lock:
                    self._network_threads_active = max(0, self._network_threads_active - 1)

        try:
            future = executor.submit(_worker)
        except RuntimeError:
            return
        with self._network_futures_lock:
            self._network_futures.add(future)

        def _on_done(done: Future) -> None:
            with self._network_futures_lock:
                self._network_futures.discard(done)

        future.add_done_callback(_on_done)
