"""
Processing Engine — combines background video, voiceover audio, and
auto-generated subtitles into a final 9:16 TikTok-ready video using MoviePy.

Subtitle timings come from edge-tts SentenceBoundary events (via SubMaker),
so no external ASR / Whisper dependency is required.
"""
from __future__ import annotations

from pathlib import Path

from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

from .config import CONFIG
from .logger import logger


class ProcessingEngine:
    """Assembles the final TikTok video from its parts."""

    def __init__(self) -> None:
        self.w, self.h = CONFIG.video_resolution
        self.fps = CONFIG.video_fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compose(
        self,
        video_path: Path,
        audio_path: Path,
        timings: list[dict],
        output_path: Path,
    ) -> Path:
        """Create the final video.

        Parameters
        ----------
        video_path : background clip (any resolution, will be cropped to 9:16)
        audio_path : voiceover mp3
        timings    : sentence-level timings from VoiceEngine
        output_path: final .mp4 destination
        """
        logger.info("Composing final video → %s", output_path.name)

        audio_clip = AudioFileClip(str(audio_path))
        target_duration = audio_clip.duration

        # 1. Prepare background video (loop / trim to audio length, crop to 9:16)
        bg = self._prepare_background(video_path, target_duration)

        # 2. Build subtitle clips
        subtitle_clips = self._build_subtitles(timings, target_duration)

        # 3. Optional dark overlay for subtitle readability
        overlay = ColorClip(
            size=(self.w, self.h), color=(0, 0, 0)
        ).set_duration(target_duration).set_opacity(0.25)

        # 4. Composite everything
        final = CompositeVideoClip(
            [bg, overlay, *subtitle_clips],
            size=(self.w, self.h),
        ).set_audio(audio_clip).set_duration(target_duration)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        final.write_videofile(
            str(output_path),
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger="bar",
        )

        # Clean up
        bg.close()
        audio_clip.close()
        final.close()

        logger.info("Final video written: %s (%.1fs)", output_path.name, target_duration)
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prepare_background(self, path: Path, duration: float) -> VideoFileClip:
        """Load, crop to 9:16, loop/trim to *duration*, resize to target."""
        clip = VideoFileClip(str(path))

        # Trim or loop to match audio duration
        if clip.duration >= duration:
            clip = clip.subclip(0, duration)
        else:
            # Loop the clip to fill the needed duration
            loops_needed = int(duration // clip.duration) + 1
            clip = concatenate_videoclips([clip] * loops_needed).subclip(0, duration)

        # Crop to 9:16 aspect ratio (centre crop)
        clip = self._crop_to_ratio(clip, self.w / self.h)
        clip = clip.resize((self.w, self.h))
        clip = clip.without_audio()  # we provide our own voiceover
        return clip

    @staticmethod
    def _crop_to_ratio(clip: VideoFileClip, target_ratio: float) -> VideoFileClip:
        """Centre-crop *clip* to *target_ratio* (width/height)."""
        cw, ch = clip.w, clip.h
        current_ratio = cw / ch

        if current_ratio > target_ratio:
            # Too wide — crop sides
            new_w = int(ch * target_ratio)
            x1 = (cw - new_w) // 2
            clip = clip.crop(x1=x1, x2=x1 + new_w, y1=0, y2=ch)
        elif current_ratio < target_ratio:
            # Too tall — crop top/bottom
            new_h = int(cw / target_ratio)
            y1 = (ch - new_h) // 2
            clip = clip.crop(x1=0, x2=cw, y1=y1, y2=y1 + new_h)

        return clip

    def _build_subtitles(
        self, timings: list[dict], total_duration: float
    ) -> list[TextClip]:
        """Create subtitle clips from edge-tts sentence-level timings.

        Each timing entry is one sentence — already a natural subtitle unit.
        Long sentences are split into two lines for readability.
        """
        if not timings:
            logger.warning("No subtitle timings available — skipping subtitles.")
            return []

        logger.debug("Building %d subtitle clips", len(timings))

        clips: list[TextClip] = []
        for t in timings:
            text = t["text"].strip()
            if not text:
                continue
            dur = max(t["end"] - t["start"], 0.3)
            dur = min(dur, total_duration - t["start"])
            if dur <= 0:
                continue
            txt = self._make_text_clip(text, t["start"], dur)
            clips.append(txt)

        return clips

    def _make_text_clip(self, text: str, start: float, duration: float) -> TextClip:
        """Style a single subtitle phrase."""
        # Word-wrap long phrases
        if len(text) > 28:
            mid = len(text) // 2
            # Find nearest space
            for offset in range(10):
                if text[mid + offset] == " ":
                    text = text[:mid + offset] + "\n" + text[mid + offset + 1:]
                    break
                if text[mid - offset] == " ":
                    text = text[:mid - offset] + "\n" + text[mid - offset + 1:]
                    break

        clip = TextClip(
            text,
            fontsize=52,
            color="white",
            stroke_color="black",
            stroke_width=2,
            font="Arial-Bold",
            method="caption",
            size=(int(self.w * 0.85), None),
            align="center",
        )
        clip = clip.set_position(("center", self.h * 0.72))
        clip = clip.set_start(start).set_duration(duration)

        # Fade in/out for polish
        clip = clip.crossfadein(0.08).crossfadeout(0.08)
        return clip
