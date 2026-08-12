#!/usr/bin/env python3
"""
setup_auth.py — one-time TikTok authorisation.

Run this ONCE before starting the scheduler:
    python setup_auth.py

It opens a browser for you to log into TikTok and approve the app.
The resulting access + refresh tokens are saved to
tiktok_auto_poster/data/token.json  (git-ignored).

After this, main.py will automatically refresh tokens — no manual
intervention needed.
"""
from tiktok_auto_poster.logger import logger
from tiktok_auto_poster.tiktok_auth import TikTokAuth


def main() -> None:
    logger.info("Starting one-time TikTok authorisation…")
    auth = TikTokAuth()
    auth.authorise_interactive()
    logger.info("Done! You can now run  python main.py  to start the daily scheduler.")


if __name__ == "__main__":
    main()
