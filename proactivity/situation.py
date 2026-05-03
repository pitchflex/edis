# Situation detector — classifies user message into a context type using LLM

import json
import logging

from core.llm import get_llm

log = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Analyze this user message and classify the situation.
Return a JSON object with:
  - type: snake_case situation type (e.g. "focus_session", "before_meeting", "leisure_time", "exercise", "commute", "meal_time", "coding_session", "unknown")
  - confidence: 0.0-1.0
  - duration_minutes: estimated duration if mentioned, else null
  - activity: specific activity if mentioned, else null
  - details: dict of any other relevant extracted info

Message: "{message}"

Return only valid JSON."""


def classify(message: str) -> dict:
    """Classify a user message into a situation context."""
    try:
        llm = get_llm()
        response = llm.chat([{"role": "user", "content": CLASSIFY_PROMPT.format(message=message)}])
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        log.debug(f"Situation classified: {result}")
        return result
    except Exception as e:
        log.debug(f"Situation classification failed: {e}")
        return {"type": "unknown", "confidence": 0.0, "duration_minutes": None,
                "activity": None, "details": {}}


def is_focus_session(situation: dict) -> bool:
    return situation.get("type") in (
        "focus_session", "study_session", "coding_session", "deep_work"
    ) and situation.get("confidence", 0) > 0.6
