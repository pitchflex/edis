# GUI automation loop — vision → action → repeat, fully visible on screen

import json
import logging
import subprocess
import time

import settings
from core.interrupt import InterruptibleTask, check as interrupt_check
from gui_automation import executor

log = logging.getLogger(__name__)

VISION_ACTION_PROMPT = """You are controlling a Linux desktop to complete this task: "{task}"

Previous actions taken: {history}

Look at the current screenshot and decide the SINGLE next action to take.
Return JSON with one of these formats:
  {{"type": "click", "x": 123, "y": 456, "reason": "clicking X button"}}
  {{"type": "right_click", "x": 123, "y": 456, "reason": "..."}}
  {{"type": "double_click", "x": 123, "y": 456, "reason": "..."}}
  {{"type": "type", "text": "hello world", "reason": "..."}}
  {{"type": "key", "key": "Return", "reason": "..."}}
  {{"type": "scroll", "x": 123, "y": 456, "direction": "down", "reason": "..."}}
  {{"type": "wait", "seconds": 1, "reason": "waiting for page to load"}}
  {{"type": "done", "result": "Task completed successfully"}}

Be precise with coordinates. Only JSON, no explanation."""


class AutomationLoop:
    def __init__(self, task: str, on_step: callable = None):
        self.task = task
        self.on_step = on_step or (lambda msg: None)
        self._history: list[dict] = []
        self._running = False

    def run(self) -> str:
        """Run the full automation loop. Returns result string."""
        from core.llm import get_llm
        llm = get_llm()

        self._running = True
        self.on_step(f"Starting: {self.task}")

        with InterruptibleTask("gui_automation") as task:
            for step in range(settings.GUI_MAX_STEPS):
                task.check()

                # take screenshot
                screenshot = settings.SCREENSHOT_TMP
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(["grim", str(screenshot)],
                                   check=True, capture_output=True, timeout=5)
                except Exception as e:
                    return f"Screenshot failed: {e}"

                # get next action from vision LLM
                history_str = json.dumps(self._history[-5:]) if self._history else "none"
                prompt = VISION_ACTION_PROMPT.format(
                    task=self.task,
                    history=history_str,
                )
                try:
                    result_text = llm.vision(str(screenshot), prompt)
                    result_text = result_text.strip()
                    if result_text.startswith("```"):
                        result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0]
                    action = json.loads(result_text)
                except Exception as e:
                    log.error(f"Vision LLM error: {e}")
                    return f"Failed to determine next action: {e}"
                finally:
                    if settings.FOCUS_DELETE_SCREENSHOT and screenshot.exists():
                        screenshot.unlink()

                # log action
                reason = action.get("reason", "")
                self.on_step(f"Step {step + 1}: {reason or action['type']}")
                self._history.append(action)

                # check for completion
                if action.get("type") == "done":
                    result = action.get("result", "Task completed")
                    self.on_step(result)
                    return result

                # confirm before send if needed
                if settings.GUI_CONFIRM_SEND and self._is_send_action(action):
                    self.on_step("⚠ Ready to send — please confirm by saying 'yes' or 'confirm'")
                    return "__needs_confirmation__"

                # execute
                executor.execute_action(action)

        return "Automation stopped"

    def _is_send_action(self, action: dict) -> bool:
        if action.get("type") == "key" and action.get("key") in ("Return", "KP_Enter"):
            return True
        if action.get("type") == "click":
            reason = action.get("reason", "").lower()
            return any(w in reason for w in ("send", "submit", "post", "confirm"))
        return False


def run_task(task: str, on_step: callable = None) -> str:
    loop = AutomationLoop(task, on_step=on_step)
    return loop.run()
