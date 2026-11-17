"""In-process scheduling (APScheduler). No external queue or broker."""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from .config import get_settings
from .db import org_session, session_factory, utcnow

log = logging.getLogger("pdpl.scheduler")
_lock = threading.Lock()
_scheduler = None
_last: dict = {"at": None, "results": []}


def collect_org_id() -> int:
    """Collector credentials come from the environment, so automated collection feeds one organisation."""
    return get_settings().collect_org_id


def collect_once() -> dict:
    """Run every evidence adapter once. Safe to call from the API, the CLI or the scheduler."""
    from .evidence.adapters import adapters

    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    try:
        results = []
        for adapter in adapters():
            with org_session(collect_org_id()) as db:
                try:
                    results.append(adapter.collect(db).as_dict())
                except Exception as e:  # one adapter failing never stops the others
                    db.rollback()
                    log.exception("adapter %s failed", adapter.name)
                    results.append({"adapter": adapter.name, "status": "error", "detail": e.__class__.__name__, "runs": 0})
        _last["at"] = utcnow().isoformat()
        _last["results"] = results
        _run_reminders()
        return {"status": "done", "at": _last["at"], "results": results}
    finally:
        _lock.release()


def _run_reminders() -> None:
    """Renewal reminders (added with the obligations tracker)."""
    try:
        from .obligations_service import generate_reminders
    except ModuleNotFoundError:
        return
    from sqlalchemy import select

    from .models import Organisation

    with session_factory()() as db:
        ids = list(db.execute(select(Organisation.id).where(Organisation.archived.is_(False))).scalars())
    for org_id in ids:
        with org_session(org_id) as db:
            generate_reminders(db)
            db.commit()


def last_collection() -> dict:
    return dict(_last)


def next_run_time() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("collect")
    return job.next_run_time if job else None


def start_scheduler():
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    hours = max(1, get_settings().collect_interval_hours)
    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.add_job(collect_once, "interval", hours=hours, id="collect", max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("evidence collection scheduled every %s h", hours)
    return _scheduler
