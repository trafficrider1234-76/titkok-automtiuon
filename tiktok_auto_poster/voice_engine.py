"""
Voice Engine — generates a free, high-quality human-like voiceover using
Microsoft Edge TTS (edge-tts), and extracts sentence-level timing data
for subtitle generation.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from .config import CONFIG
from .logger import logger


@dataclass
class SubtitleCue:
    text: str
    start: float   # seconds
    end: float     # seconds


def _srt_to_cues(srt: str) -> list[SubtitleCue]:
    """Parse an SRT string into a list of SubtitleCue objects."""
    cues: list[SubtitleCue] = []
    blocks = re.split(r"\n\s*\n", srt.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # line 0 = index, line 1 = time range, line 2+ = text
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            lines[1],
        )
        if not time_match:
            continue
        start = _srt_time_to_seconds(time_match.group(1))
        end = _srt_time_to_seconds(time_match.group(2))
        text = " ".join(lines[2:]).strip()
        cues.append(SubtitleCue(text=text, start=start, end=end))
    return cues


def _srt_time_to_seconds(ts: str) -> float:
    """Convert SRT timestamp (00:00:01,234) to float seconds."""
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


class VoiceEngine:
    """Synthesises an MP3 voiceover from the script body via edge-tts."""

    def __init__(self, voice: str | None = None, rate: str = "+8%") -> None:
        self.voice = voice or CONFIG.voice
        self.rate = rate  # slightly faster for TikTok pacing

    def generate(self, text: str, output_path: Path) -> Path:
        """Synthesise *text* to *output_path* (mp3)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Generating voiceover (%s, %d chars)…", self.voice, len(text))
        asyncio.run(self._synth(text, output_path))
        logger.debug("Voiceover saved: %s", output_path)
        return output_path

    async def _synth(self, text: str, path: Path) -> None:
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
        )
        await communicate.save(str(path))

    # ------------------------------------------------------------------
    # Voiceover + subtitle timing extraction
    # ------------------------------------------------------------------

    def generate_with_timings(self, text: str, audio_path: Path) -> tuple[Path, list[dict]]:
        """Synthesise audio AND return sentence-level timing data.

        Uses edge-tts SubMaker to capture boundary events (SentenceBoundary
        in edge-tts 7.x) and parse them into structured timings.

        Returns (audio_path, timings) where timings is a list of
        {"text": str, "start": float_seconds, "end": float_seconds}.
        """
        logger.info("Generating voiceover with subtitle timings…")
        return asyncio.run(self._synth_with_timings(text, audio_path))

    async def _synth_with_timings(
        self, text: str, audio_path: Path
    ) -> tuple[Path, list[dict]]:
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
        )

        audio_chunks: list[bytes] = []
        sub_maker = edge_tts.SubMaker()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            else:
                # SentenceBoundary or WordBoundary
                sub_maker.feed(chunk)

        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"".join(audio_chunks))

        cues = _srt_to_cues(sub_maker.get_srt())
        timings = [
            {"text": cue.text, "start": cue.start, "end": cue.end}
            for cue in cues
        ]
        logger.debug("Captured %d subtitle cues", len(timings))
        return audio_path, timings
