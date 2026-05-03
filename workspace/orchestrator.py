# Workspace orchestrator — learned modes, one command sets everything up

import json
import logging
import subprocess
from typing import Callable

import settings
from memory.memori import get_store

log = logging.getLogger(__name__)

EXTRACT_ACTIONS_PROMPT = """The user described their "{mode_name}" workspace mode.
Extract the specific actions as a JSON array of action objects.
Each action: {{"type": "open_app"|"close_app"|"set_volume"|"mute_notifications"|"unmute_notifications"|"set_brightness"|"play_music"|"open_url"|"run_command", "value": "..."}}
User description: "{description}"
Return only valid JSON array."""


class WorkspaceOrchestrator:
    def __init__(self):
        self._store = get_store()

    def get_mode(self, name: str) -> list | None:
        rows = self._store.get(category="rule", key=f"workspace_mode_{name}")
        if rows:
            try:
                return json.loads(rows[0]["content"])
            except Exception:
                return None
        return None

    def all_modes(self) -> list[str]:
        rows = self._store.get(category="rule")
        return [
            r["key"].replace("workspace_mode_", "")
            for r in rows
            if r.get("key", "").startswith("workspace_mode_")
        ]

    def save_mode(self, name: str, actions: list):
        existing = self._store.get(category="rule", key=f"workspace_mode_{name}")
        if existing:
            self._store.update(existing[0]["id"], content=json.dumps(actions))
        else:
            self._store.add(
                category="rule",
                content=json.dumps(actions),
                key=f"workspace_mode_{name}",
                context="workspace",
            )
        log.info(f"Saved workspace mode '{name}' with {len(actions)} actions")

    def extract_actions_from_description(self, mode_name: str, description: str) -> list:
        try:
            from core.llm import get_llm
            llm = get_llm()
            response = llm.chat([{
                "role": "user",
                "content": EXTRACT_ACTIONS_PROMPT.format(
                    mode_name=mode_name, description=description
                )
            }])
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except Exception as e:
            log.error(f"Could not extract workspace actions: {e}")
            return []

    def activate(self, name: str) -> tuple[bool, str]:
        actions = self.get_mode(name)
        if not actions:
            return False, f"No workspace mode named '{name}' found."

        results = []
        for action in actions:
            msg = self._execute_action(action)
            if msg:
                results.append(msg)

        summary = f"'{name}' mode activated." + (
            " " + ", ".join(results) if results else ""
        )
        log.info(summary)
        return True, summary

    def _execute_action(self, action: dict) -> str | None:
        t = action.get("type", "")
        v = action.get("value", "")
        try:
            if t == "open_app":
                subprocess.Popen(["gtk-launch", v], stderr=subprocess.DEVNULL)
                return f"Opened {v}"
            elif t == "close_app":
                subprocess.run(["pkill", "-f", v], capture_output=True)
                return f"Closed {v}"
            elif t == "mute_notifications":
                subprocess.run(["gsettings", "set",
                                 "org.gnome.desktop.notifications",
                                 "show-banners", "false"], capture_output=True)
                return "Notifications muted"
            elif t == "unmute_notifications":
                subprocess.run(["gsettings", "set",
                                 "org.gnome.desktop.notifications",
                                 "show-banners", "true"], capture_output=True)
                return "Notifications unmuted"
            elif t == "set_volume":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@",
                                 f"{v}%"], capture_output=True)
                return f"Volume set to {v}%"
            elif t == "set_brightness":
                subprocess.run(["brightnessctl", "set", f"{v}%"], capture_output=True)
                return f"Brightness set to {v}%"
            elif t == "play_music":
                subprocess.Popen(["xdg-open", v], stderr=subprocess.DEVNULL)
                return f"Playing {v}"
            elif t == "open_url":
                subprocess.Popen(["xdg-open", v], stderr=subprocess.DEVNULL)
                return f"Opened {v}"
            elif t == "run_command":
                subprocess.Popen(v, shell=True)
                return f"Ran: {v}"
        except Exception as e:
            log.warning(f"Workspace action failed ({t}={v}): {e}")
        return None


_orch: WorkspaceOrchestrator | None = None


def get_orchestrator() -> WorkspaceOrchestrator:
    global _orch
    if _orch is None:
        _orch = WorkspaceOrchestrator()
    return _orch
