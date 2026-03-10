from __future__ import annotations


def build_job_callbacks(
    mw,
    *,
    job: dict,
    thread,
    busy_overlay_shown: bool,
    cleanup_temp_paths_fn,
    hide_ocr_busy_overlay_fn,
    restore_override_cursor_fn,
    schedule_ocr_cache_release_fn,
    qtcore,
) -> tuple:
    def finalize_job() -> None:
        current = getattr(mw, "_ocr_async_job", None)
        if current is not None and current is not job:
            return
        if bool(job.get("_finalized", False)):
            return
        job["_finalized"] = True
        cleanup_temp_paths_fn(list(job.get("paths") or []))
        hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
        restore_override_cursor_fn()
        try:
            if thread.isRunning() and qtcore.QThread.currentThread() is not thread:
                thread.quit()
        except Exception:
            pass
        mw._update_role_ocr_buttons_enabled()
        schedule_ocr_cache_release_fn(mw)
        if current is job:
            running = False
            try:
                running = bool(thread.isRunning())
            except Exception:
                running = False
            if not running:
                setattr(mw, "_ocr_async_job", None)

    def cleanup_finished_job() -> None:
        current = getattr(mw, "_ocr_async_job", None)
        if current is job:
            setattr(mw, "_ocr_async_job", None)

    return finalize_job, cleanup_finished_job
