"""
Pipeline — orchestrates the full daily run:

  Script → Video → Voice → Process → Upload to TikTok

Each step is isolated so a failure in one is logged clearly.
"""
from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

from .config import CONFIG
from .logger import logger
from .processing_engine import ProcessingEngine
from .script_engine import ScriptEngine
from .tiktok_uploader import TikTokUploader
from .video_engine import VideoEngine
from .voice_engine import VoiceEngine


class Pipeline:
    """Runs the complete generate-and-post pipeline once."""

    def run(self) -> dict:
        CONFIG.ensure_dirs()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info("=== Pipeline run %s started ===", run_id)

        result: dict = {"run_id": run_id}

        # 1. Script
        try:
            script = ScriptEngine().generate()
            logger.info("Script: '%s' — %d chars", script.topic, len(script.body))
            result["script"] = {"topic": script.topic, "body": script.body, "caption": script.caption}
        except Exception as exc:
            logger.error("Script generation failed: %s\n%s", exc, traceback.format_exc())
            result["error"] = f"script: {exc}"
            return result

        # 2. Background video
        try:
            video_path = VideoEngine().download_background(script.topic)
            result["video_path"] = str(video_path)
        except Exception as exc:
            logger.error("Video download failed: %s\n%s", exc, traceback.format_exc())
            result["error"] = f"video: {exc}"
            return result

        # 3. Voiceover (with word timings for subtitles)
        try:
            audio_path = CONFIG.audio_dir / f"voice_{run_id}.mp3"
            audio_path, timings = VoiceEngine().generate_with_timings(script.body, audio_path)
            result["audio_path"] = str(audio_path)
            result["timings_count"] = len(timings)
        except Exception as exc:
            logger.error("Voice generation failed: %s\n%s", exc, traceback.format_exc())
            result["error"] = f"voice: {exc}"
            return result

        # 4. Compose final video
        try:
            output_path = CONFIG.output_dir / f"tiktok_{run_id}.mp4"
            ProcessingEngine().compose(
                video_path=Path(result["video_path"]),
                audio_path=audio_path,
                timings=timings,
                output_path=output_path,
            )
            result["output_path"] = str(output_path)
        except Exception as exc:
            logger.error("Video composition failed: %s\n%s", exc, traceback.format_exc())
            result["error"] = f"compose: {exc}"
            return result

        # 5. Upload to TikTok
        try:
            publish_id = TikTokUploader().upload_video(
                video_path=output_path,
                caption=script.caption,
            )
            result["publish_id"] = publish_id
            logger.info("=== Pipeline run %s complete — publish_id: %s ===", run_id, publish_id)
        except Exception as exc:
            logger.error("TikTok upload failed: %s\n%s", exc, traceback.format_exc())
            result["error"] = f"upload: {exc}"
            result["note"] = (
                "Video was generated successfully and saved to "
                f"{result.get('output_path', 'output/')}. "
                "The upload failed — check the error above."
            )

        return result
