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
import sys
import signal

# Add the current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Try importing the module
try:
    from tiktok_auto_poster.config import CONFIG
    from tiktok_auto_poster.logger import logger
    from tiktok_auto_poster.pipeline import Pipeline
except ModuleNotFoundError as e:
    print(f"ERROR: {e}")
    print(f"Current directory: {current_dir}")
    print("Contents of current directory:")
    for item in os.listdir(current_dir):
        print(f"  - {item}")
    
    # Check if tiktok_auto_poster exists
    if os.path.exists(os.path.join(current_dir, "tiktok_auto_poster")):
        print("\n'tiktok_auto_poster' folder exists but Python can't find it.")
        print("Make sure it has an __init__.py file.")
    else:
        print("\n'tiktok_auto_poster' folder not found!")
        print("Please create the folder and add the required files.")
    sys.exit(1)

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


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
    def _shutdown(signum, _frame) -> None:
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
