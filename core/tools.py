# Tool definitions and dispatcher for the LLM engine
# All tools EDIS can call, defined in OpenAI function-calling format.

import json
import logging
import subprocess

import settings

log = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "Open a file with its default application",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Absolute or ~ path to the file"}
            }, "required": ["path"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launch an installed application",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "App name or .desktop file name"}
            }, "required": ["name"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files by name or content",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "location": {"type": "string", "default": "~"},
                "file_type": {"type": "string", "description": "Extension without dot"},
                "content_search": {"type": "boolean", "default": False},
            }, "required": ["query"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a text file",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}
            }, "required": ["path"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command and return output. Use for system tasks.",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "default": 10},
            }, "required": ["command"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_automation",
            "description": "Automate a GUI task on screen — user will see it happening",
            "parameters": {"type": "object", "properties": {
                "task": {"type": "string", "description": "Natural language task description"}
            }, "required": ["task"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "activate_workspace_mode",
            "description": "Activate a saved workspace mode by name",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string"}
            }, "required": ["name"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_workspace_mode",
            "description": "Save a new workspace mode from user description",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            }, "required": ["name", "description"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Store something in EDIS long-term memory",
            "parameters": {"type": "object", "properties": {
                "content": {"type": "string"},
                "category": {"type": "string", "enum": ["fact", "preference", "rule", "summary"]},
                "key": {"type": "string"},
            }, "required": ["content", "category"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search EDIS memory for relevant information",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}
            }, "required": ["query"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set system volume",
            "parameters": {"type": "object", "properties": {
                "percent": {"type": "integer", "minimum": 0, "maximum": 100}
            }, "required": ["percent"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Set screen brightness",
            "parameters": {"type": "object", "properties": {
                "percent": {"type": "integer", "minimum": 1, "maximum": 100}
            }, "required": ["percent"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Send a desktop notification",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            }, "required": ["title", "body"]},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and return a summary",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}
            }, "required": ["query"]},
        }
    },
]


def dispatch(tool_name: str, args: dict, on_step=None) -> str:
    """Execute a tool call and return the result as a string."""
    log.info(f"Tool: {tool_name}({json.dumps(args)[:100]})")

    try:
        if tool_name == "open_file":
            from filesystem.skill import open_file
            return open_file(args["path"])

        elif tool_name == "open_app":
            from filesystem.skill import open_app
            return open_app(args["name"])

        elif tool_name == "search_files":
            from filesystem.skill import search_files
            results = search_files(**args)
            return "\n".join(results) if results else "No files found"

        elif tool_name == "read_file":
            from filesystem.skill import read_file
            return read_file(args["path"])

        elif tool_name == "run_shell":
            cmd = args["command"]
            timeout = args.get("timeout", 10)
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout + result.stderr
            return output[:2000] if output else "(no output)"

        elif tool_name == "gui_automation":
            from gui_automation.loop import run_task
            return run_task(args["task"], on_step=on_step)

        elif tool_name == "activate_workspace_mode":
            from workspace.orchestrator import get_orchestrator
            ok, msg = get_orchestrator().activate(args["name"])
            return msg

        elif tool_name == "save_workspace_mode":
            from workspace.orchestrator import get_orchestrator
            orch = get_orchestrator()
            actions = orch.extract_actions_from_description(args["name"], args["description"])
            orch.save_mode(args["name"], actions)
            return f"Saved workspace mode '{args['name']}' with {len(actions)} actions"

        elif tool_name == "remember":
            from memory.manager import get_memory
            get_memory().remember(
                category=args["category"],
                content=args["content"],
                key=args.get("key"),
            )
            return "Remembered"

        elif tool_name == "recall":
            from memory.manager import get_memory
            results = get_memory().recall(args["query"])
            if not results:
                return "Nothing found in memory"
            return "\n".join(f"[{r['category']}] {r['content']}" for r in results)

        elif tool_name == "set_volume":
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@",
                 f"{args['percent']}%"],
                capture_output=True
            )
            return f"Volume set to {args['percent']}%"

        elif tool_name == "set_brightness":
            subprocess.run(
                ["brightnessctl", "set", f"{args['percent']}%"],
                capture_output=True
            )
            return f"Brightness set to {args['percent']}%"

        elif tool_name == "send_notification":
            subprocess.run(
                ["notify-send", args["title"], args.get("body", "")],
                capture_output=True
            )
            return "Notification sent"

        elif tool_name == "web_search":
            return _web_search(args["query"])

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        log.error(f"Tool {tool_name} failed: {e}")
        return f"Error: {e}"


def _web_search(query: str) -> str:
    try:
        import urllib.request
        import urllib.parse
        url = f"https://ddg-webapp-aagd.vercel.app/search?q={urllib.parse.quote(query)}&max_results=3"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        results = data if isinstance(data, list) else data.get("results", [])
        snippets = [f"{r.get('title','')}: {r.get('body','')}" for r in results[:3]]
        return "\n\n".join(snippets) or "No results found"
    except Exception as e:
        return f"Search failed: {e}"
