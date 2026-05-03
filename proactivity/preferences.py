# Preference learner — stores and retrieves context-based learned behaviors

import json
import logging
from typing import Optional

import settings
from memory.manager import get_memory

log = logging.getLogger(__name__)

ASK_PROMPT = """The user said they're about to do: "{activity}"
This is the first time we've encountered this situation type: "{context_type}"
Ask the user ONE concise question about what they'd like EDIS to do during this activity.
Keep it under 20 words. Be natural, not robotic."""

OFFER_PROMPT = """The user is about to do: "{activity}"
Based on past preference, they usually want: {actions}
Offer this in ONE short sentence (under 20 words), asking if they want the same again."""


class PreferenceLearner:
    def __init__(self):
        self._mem = get_memory()

    def handle_situation(self, context_type: str, activity: str) -> Optional[dict]:
        """
        Returns a dict describing what to do:
          { "action": "ask" | "offer" | "none", "message": str, "actions": list }
        """
        pref = self._mem.get_preference(context_type)

        if pref is None:
            # First time — ask what they want
            return {
                "action": "ask",
                "context_type": context_type,
                "activity": activity,
                "message": self._build_ask_message(context_type, activity),
            }

        confidence = pref.get("confidence", 0.0)
        if confidence < settings.PREFERENCE_CONFIDENCE_THRESHOLD:
            # Low confidence after declines — don't bother offering
            return {"action": "none"}

        actions = json.loads(pref["actions"]) if isinstance(pref["actions"], str) else pref["actions"]
        return {
            "action": "offer",
            "context_type": context_type,
            "activity": activity,
            "actions": actions,
            "message": self._build_offer_message(activity, actions),
        }

    def _build_ask_message(self, context_type: str, activity: str) -> str:
        try:
            from core.llm import get_llm
            llm = get_llm()
            response = llm.chat([{
                "role": "user",
                "content": ASK_PROMPT.format(activity=activity, context_type=context_type)
            }])
            return response.strip()
        except Exception:
            return f"What would you like me to do while you {activity}?"

    def _build_offer_message(self, activity: str, actions: list) -> str:
        try:
            from core.llm import get_llm
            llm = get_llm()
            response = llm.chat([{
                "role": "user",
                "content": OFFER_PROMPT.format(
                    activity=activity,
                    actions=", ".join(actions)
                )
            }])
            return response.strip()
        except Exception:
            return f"Want me to {', '.join(actions)} like usual?"

    def store_preference(self, context_type: str, actions: list):
        self._mem.set_preference(context_type, actions)
        log.info(f"Stored preference for {context_type}: {actions}")

    def record_outcome(self, context_type: str, accepted: bool):
        self._mem.record_preference_outcome(context_type, accepted)
        log.debug(f"Preference outcome for {context_type}: {'accepted' if accepted else 'declined'}")


_learner: PreferenceLearner | None = None


def get_learner() -> PreferenceLearner:
    global _learner
    if _learner is None:
        _learner = PreferenceLearner()
    return _learner
