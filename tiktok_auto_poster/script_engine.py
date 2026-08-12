"""
Script Engine — uses Groq (Llama 3.3 70B) to generate viral TikTok scripts.
Niche: Motivation / Mind-blowing Facts.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from groq import Groq

from .config import CONFIG
from .logger import logger


@dataclass
class Script:
    topic: str          # the generated topic / title
    hook: str           # first line — the scroll-stopping hook
    body: str           # full narration text spoken by the voiceover
    caption: str        # TikTok caption with hashtags


_SYSTEM_PROMPT = (
    "You are a viral TikTok scriptwriter specialising in the Motivation and "
    "Mind-blowing Facts niche. You write punchy, fast-paced, emotionally engaging "
    "short-form video scripts (under 45 seconds spoken). "
    "Every script must start with a scroll-stopping hook in the first 3 seconds."
)

_USER_TEMPLATE = (
    "Generate ONE original TikTok video script about a random {niche} topic.\n\n"
    "Return STRICT JSON with exactly these keys:\n"
    '  "topic":     a short 2-6 word title for the video,\n'
    '  "hook":      a single attention-grabbing opening sentence (max 15 words),\n'
    '  "body":      the full narration text (40-70 words, no stage directions, '
    'purely the spoken words including the hook at the start),\n'
    '  "caption":   a TikTok caption with 3-5 relevant hashtags.\n\n'
    "Do NOT include markdown fences. Output JSON only."
)


class ScriptEngine:
    """Generates a viral script via Groq."""

    def __init__(self) -> None:
        if not CONFIG.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        self._client = Groq(api_key=CONFIG.groq_api_key)

    def generate(self) -> Script:
        logger.info("Generating script via Groq (%s)…", CONFIG.groq_model)

        completion = self._client.chat.completions.create(
            model=CONFIG.groq_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_TEMPLATE.format(niche=CONFIG.niche)},
            ],
            temperature=0.9,
            max_tokens=600,
            response_format={"type": "json_object"},
        )

        raw = completion.choices[0].message.content or ""
        logger.debug("Groq raw response: %s", raw)
        data = self._parse_json(raw)

        body = data.get("body", "").strip()
        if not body:
            raise ValueError("Groq returned an empty body — retry needed.")

        return Script(
            topic=data.get("topic", "Motivation"),
            hook=data.get("hook", body.split(".")[0]),
            body=body,
            caption=data.get("caption", "#motivation #facts #fyp"),
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Tolerant JSON extraction — strips fences / stray text."""
        text = raw.strip()
        # Remove markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Last-resort: extract the first {...} block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
