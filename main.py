#!/usr/bin/env python3
"""
main.py — entry point for the TikTok Auto-Poster.
"""
from __future__ import annotations

import argparse
import os
import sys
import signal

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import directly from files (since they're in the same directory)
try:
    # Direct imports since files are in the same folder
    import config
    import logger
    import pipeline
    import processing_engine
    import script_engine
    import tiktok_author
    import tiktok_uploader
    import video_engine
    import voice_engine
    
    # Now use them
    CONFIG = config.CONFIG
    logger = logger.logger
    Pipeline = pipeline.Pipeline
    
except ImportError as e:
    print(f"ERROR: Failed to import modules: {e}")
    print(f"Current directory: {current_dir}")
    print("\nFiles in current directory:")
    for item in os.listdir(current_dir):
        if os.path.isfile(item):
            print(f"  - {item}")
        elif os.path.isdir(item):
            print(f"  - {item}/ (folder)")
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
