"""Daily job push: one interval job checks which users' push time has come."""

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.app.config import PUSH_TICK_MINUTES, TIMEZONE
from backend.app.services.jobs import push_tick

scheduler = BackgroundScheduler(timezone=TIMEZONE)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(push_tick, "interval", minutes=PUSH_TICK_MINUTES, id="daily_push_tick",
                      replace_existing=True, max_instances=1, coalesce=True,
                      next_run_time=datetime.now() + timedelta(seconds=20))
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
