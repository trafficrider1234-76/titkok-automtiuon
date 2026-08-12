#!/usr/bin/env python3
"""
main.py — entry point for the TikTok Auto-Poster.

Two modes:
  python main.py --now          # run the pipeline once immediately, then exit
  python main.py                # start the daily scheduler (default)
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

# Ensure Python can find local modules when run from GitHub Actions
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from tiktok_auto_poster.config import CONFIG
from tiktok_auto_poster.logger import logger
from tiktok_auto_poster.pipeline import Pipeline


def _job() -> None:
    """Scheduled job wrapper with top-level error capture."""
    try:
        Pipeline().run()
    except Exception as exc:
        logger.error("Unhandled error in scheduled job: %s", exc, exc_info=True)


def run_once() -> None:
    logger.info("Running pipeline once (manual mode)…")
    _job()


def run_scheduler() -> None:
    hour = CONFIG.run_hour
    logger.info("Starting daily scheduler — will run every day at %02d:00.", hour)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        _job,
        trigger=CronTrigger(hour=hour, minute=0, timezone="UTC"),
        id="daily_tiktok_post",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Graceful shutdown
    def _shutdown(signum, _frame) -> None:  # noqa: ANN001
        logger.info("Received signal %d — shutting down scheduler.", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Run once immediately on first start
    logger.info("Triggering an immediate first run…")
    _job()

    logger.info("Scheduler active — press Ctrl+C to stop.")
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok Auto-Poster")
    parser.add_argument(
        "--now", action="store_true",
        help="Run the pipeline once immediately and exit (no scheduler).",
    )
    args = parser.parse_args()

    CONFIG.ensure_dirs()

    if args.now:
        run_once()
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
