"""
Video Engine — downloads a random 9:16 vertical background video from Pexels
that matches the script topic.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import requests

from .config import CONFIG
from .logger import logger

_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


class VideoEngine:
    """Fetches a vertical background clip from Pexels."""

    def __init__(self) -> None:
        if not CONFIG.pexels_api_key:
            raise RuntimeError("PEXELS_API_KEY is not set in .env")
        self._headers = {"Authorization": CONFIG.pexels_api_key}
        self._session = requests.Session()
        self._session.headers.update(self._headers)

    def download_background(self, query: str) -> Path:
        """Search Pexels for a vertical video matching *query* and download it.

        Falls back to broader motivation-themed queries if the specific topic
        yields no portrait results.
        """
        queries = [query, "motivation", "success", "nature", "city night"]
        for q in queries:
            video_url = self._search_one(q)
            if video_url:
                path = self._download(video_url, q)
                logger.info("Downloaded background video: %s", path.name)
                return path

        raise RuntimeError("Pexels returned no usable vertical videos after all fallbacks.")

    # -- internal --

    def _search_one(self, query: str) -> Optional[str]:
        params = {
            "query": query,
            "orientation": "portrait",   # 9:16
            "size": "medium",            # at least HD
            "per_page": 15,
        }
        try:
            resp = self._session.get(_PEXELS_VIDEO_SEARCH, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Pexels search failed for '%s': %s", query, exc)
            return None

        videos = resp.json().get("videos", [])
        random.shuffle(videos)

        for vid in videos:
            # Pick the best vertical file — prefer HD or Full HD
            best_file = None
            best_score = -1
            for f in vid.get("video_files", []):
                w = f.get("width", 0)
                h = f.get("height", 0)
                if h > w:  # portrait
                    # prefer 1080p, then 720p
                    score = w * h
                    if score > best_score:
                        best_score = score
                        best_file = f
            if best_file and best_file.get("link"):
                return best_file["link"]

        return None

    def _download(self, url: str, label: str) -> Path:
        ext = ".mp4"
        # Derive extension from content-type if possible
        path = CONFIG.videos_dir / f"bg_{label.replace(' ', '_')}_{random.randint(1000,9999)}{ext}"
        with self._session.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
        return path
