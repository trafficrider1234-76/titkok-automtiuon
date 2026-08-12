"""
TikTok Uploader — uses the Content Posting API to upload and publish a video.

Two-phase flow (per TikTok docs):
  1. POST /v2/post/publish/video/init/  → get publish_id + upload_url
  2. PUT <upload_url>                    → upload the raw video bytes (chunked)

Optionally fetches post status via /v2/post/publish/status/fetch/.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

from .config import CONFIG
from .logger import logger
from .tiktok_auth import TikTokAuth

# Max chunk size TikTok accepts is 64 MB; we use 10 MB to be safe
_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB


class TikTokUploader:
    """Uploads a final video to TikTok via the Content Posting API."""

    def __init__(self, auth: TikTokAuth | None = None) -> None:
        self.auth = auth or TikTokAuth()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def upload_video(self, video_path: Path, caption: str, privacy_level: str = "PUBLIC_TO_EVERYONE") -> str:
        """Upload *video_path* and publish it to TikTok.

        Returns the publish_id.
        """
        token = self.auth.get_access_token()
        file_size = video_path.stat().st_size
        total_chunks = max(1, (file_size + _CHUNK_SIZE - 1) // _CHUNK_SIZE)

        logger.info(
            "Initialising TikTok post — file: %s (%.2f MB, %d chunk(s))",
            video_path.name, file_size / 1e6, total_chunks,
        )

        # Phase 1 — init
        publish_id, upload_url = self._init_post(
            token, file_size, total_chunks, caption, privacy_level
        )
        logger.info("TikTok init OK — publish_id: %s", publish_id)

        # Phase 2 — upload (chunked)
        self._upload_chunks(upload_url, video_path, file_size, total_chunks)
        logger.info("Video uploaded to TikTok successfully.")

        # Phase 3 — poll status
        self._poll_status(token, publish_id)

        return publish_id

    # ------------------------------------------------------------------
    # Phase 1: initialise
    # ------------------------------------------------------------------

    def _init_post(
        self,
        token: str,
        video_size: int,
        total_chunks: int,
        caption: str,
        privacy_level: str,
    ) -> tuple[str, str]:
        payload = {
            "post_info": {
                "title": caption,
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "is_aigc": True,  # content is AI-generated — required labelling
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": _CHUNK_SIZE,
                "total_chunk_count": total_chunks,
            },
        }

        resp = requests.post(
            CONFIG.tiktok_init_post_url,
            json=payload,
            headers=self._headers(token),
            timeout=30,
        )
        data = resp.json()

        if data.get("error", {}).get("code") != "ok":
            raise RuntimeError(f"TikTok init failed: {data}")

        d = data["data"]
        return d["publish_id"], d["upload_url"]

    # ------------------------------------------------------------------
    # Phase 2: upload chunks
    # ------------------------------------------------------------------

    def _upload_chunks(
        self, upload_url: str, video_path: Path, file_size: int, total_chunks: int
    ) -> None:
        with open(video_path, "rb") as fh:
            for idx in range(total_chunks):
                chunk = fh.read(_CHUNK_SIZE)
                start = idx * _CHUNK_SIZE
                end = min(start + len(chunk) - 1, file_size - 1)
                content_range = f"bytes {start}-{end}/{file_size}"

                logger.debug("Uploading chunk %d/%d (%s)", idx + 1, total_chunks, content_range)
                resp = requests.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Range": content_range,
                        "Content-Type": "video/mp4",
                    },
                    timeout=120,
                )
                if resp.status_code not in (200, 201, 204):
                    raise RuntimeError(
                        f"Chunk {idx + 1} upload failed: HTTP {resp.status_code} — {resp.text[:300]}"
                    )

    # ------------------------------------------------------------------
    # Phase 3: poll status
    # ------------------------------------------------------------------

    def _poll_status(self, token: str, publish_id: str, max_wait: int = 120) -> None:
        """Poll the post status until it's processing or published."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            resp = requests.post(
                CONFIG.tiktok_status_url,
                json={"publish_id": publish_id},
                headers=self._headers(token),
                timeout=30,
            )
            data = resp.json()
            status = data.get("data", {}).get("status", "")
            # statuses: PROCESSING_UPLOAD, PROCESSING_DOWNLOAD, SEND_TO_USER_INBOX, PUBLISH_COMPLETE
            logger.info("TikTok post status: %s", status or data)

            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                return
            if "FAIL" in str(status).upper():
                raise RuntimeError(f"TikTok post failed with status: {status}")
            time.sleep(10)

        logger.warning("Timed out waiting for TikTok post status — upload likely still processing.")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
