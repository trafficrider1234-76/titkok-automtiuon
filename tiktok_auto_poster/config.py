"""
Central configuration loader.
All secrets are read from environment variables (see .env).
No credentials are ever hardcoded in this file or any source file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this package)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Config:
    # --- Paths ---
    root: Path = _PROJECT_ROOT
    assets_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "assets"
    videos_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "assets" / "videos"
    audio_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "assets" / "audio"
    subtitles_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "assets" / "subtitles"
    output_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "output"
    data_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "data"
    logs_dir: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "logs"

    # --- API keys ---
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    pexels_api_key: str = field(default_factory=lambda: _env("PEXELS_API_KEY"))
    tiktok_client_key: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_KEY"))
    tiktok_client_secret: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_SECRET"))

    # --- Groq ---
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Content ---
    niche: str = "Motivation / Mind-blowing Facts"
    voice: str = "en-US-GuyNeural"
    video_resolution: tuple[int, int] = (1080, 1920)  # 9:16 vertical
    video_fps: int = 30

    # --- TikTok ---
    tiktok_auth_base: str = "https://www.tiktok.com/v2/auth/authorize/"
    tiktok_token_url: str = "https://open.tiktokapis.com/v2/oauth/token/"
    tiktok_init_post_url: str = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    tiktok_creator_info_url: str = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
    tiktok_status_url: str = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    tiktok_scope: str = "video.publish,video.upload,user.info.basic"
    tiktok_redirect_uri: str = "http://localhost:8765/callback"

    # --- Scheduling ---
    run_hour: int = field(default_factory=lambda: int(_env("RUN_HOUR", "12")))

    # --- Token persistence ---
    token_file: Path = _PROJECT_ROOT / "tiktok_auto_poster" / "data" / "token.json"

    def ensure_dirs(self) -> None:
        """Create every directory the pipeline needs."""
        for d in (
            self.assets_dir, self.videos_dir, self.audio_dir,
            self.subtitles_dir, self.output_dir, self.data_dir, self.logs_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


# Singleton
CONFIG = Config()
