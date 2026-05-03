# Core conversation engine — processes input, calls tools, updates memory

import json
import logging
from typing import Callable

import settings
from core import interrupt
from core.llm import get_llm
from core.tools import TOOL_DEFINITIONS, dispatch
from memory.manager import get_memory

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, on_speak: Callable[[str], None] = None,
                 on_ui_update: Callable[[str, str], None] = None):
        """
        on_speak: called with text to speak aloud
        on_ui_update: called with (role, text) to update the UI log
        """
        self.on_speak = on_speak or (lambda t: None)
        self.on_ui_update = on_ui_update or (lambda r, t: None)
        self._conversation: list[dict] = []
        self._llm = get_llm()
        self._memory = get_memory()

    def process(self, user_input: str) -> str:
        """Process user input and return EDIS response."""
        interrupt.clear()

        self.on_ui_update("user", user_input)

        # build memory context
        mem_context = self._memory.get_context_summary(user_input)
        recent = self._memory.get_recent_episodes(3)

        system = settings.SYSTEM_PROMPT
        if mem_context:
            system += f"\n\n{mem_context}"
        if recent:
            system += f"\n\n{recent}"

        messages = [{"role": "system", "content": system}]
        messages.extend(self._conversation[-10:])  # last 5 exchanges
        messages.append({"role": "user", "content": user_input})

        response_text = self._run_with_tools(messages)

        if not response_text:
            response_text = "I'm not sure how to help with that."

        # update conversation history
        self._conversation.append({"role": "user", "content": user_input})
        self._conversation.append({"role": "assistant", "content": response_text})

        # store episode + extract memories in background
        import threading
        threading.Thread(
            target=self._post_process,
            args=(user_input, response_text),
            daemon=True
        ).start()

        self.on_ui_update("edis", response_text)
        return response_text

    def _run_with_tools(self, messages: list) -> str:
        max_tool_rounds = 6
        for _ in range(max_tool_rounds):
            interrupt.check()

            response = self._llm.chat(messages, tools=TOOL_DEFINITIONS)

            # plain text response
            if isinstance(response, str):
                return response

            # tool calls
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return response.content or ""

            # add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in tool_calls
                ],
            })

            # execute each tool
            for tc in tool_calls:
                interrupt.check()
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                self.on_ui_update("tool", f"→ {tool_name}({self._fmt_args(args)})")

                result = dispatch(
                    tool_name, args,
                    on_step=lambda msg: self.on_ui_update("tool", msg)
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return "I completed the requested actions."

    def _post_process(self, user_msg: str, edis_msg: str):
        try:
            self._memory.log_episode(user_msg, edis_msg)
            self._memory.extract_and_store(user_msg, edis_msg)
        except Exception as e:
            log.debug(f"Post-process error: {e}")

    def _fmt_args(self, args: dict) -> str:
        s = json.dumps(args)
        return s[:80] + "..." if len(s) > 80 else s

    def clear_history(self):
        self._conversation.clear()


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        raise RuntimeError("Engine not initialized — call init() first")
    return _engine


def init(on_speak: Callable = None, on_ui_update: Callable = None) -> Engine:
    global _engine
    _engine = Engine(on_speak=on_speak, on_ui_update=on_ui_update)
    return _engine
