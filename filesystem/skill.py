# Filesystem skill — open, search, read, launch anything

import logging
import mimetypes
import os
import subprocess
from pathlib import Path

import settings

log = logging.getLogger(__name__)


def open_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    subprocess.Popen(["gio", "open", str(p)], stderr=subprocess.DEVNULL)
    return f"Opened {p.name}"


def open_app(name: str) -> str:
    """Launch an application by name or .desktop file."""
    # try gtk-launch first (uses .desktop files)
    result = subprocess.run(
        ["gtk-launch", name], capture_output=True
    )
    if result.returncode == 0:
        return f"Launched {name}"
    # fallback: try direct exec
    result = subprocess.run(
        ["which", name], capture_output=True, text=True
    )
    if result.returncode == 0:
        subprocess.Popen([name], stderr=subprocess.DEVNULL)
        return f"Launched {name}"
    return f"Could not find application: {name}"


def search_files(query: str, location: str = "~", file_type: str = None,
                 content_search: bool = False) -> list[str]:
    """Search for files by name or content."""
    location = str(Path(location).expanduser())
    results = []

    # use fd if available (faster), fallback to find
    fd_available = subprocess.run(["which", "fd"], capture_output=True).returncode == 0

    if content_search:
        rg_available = subprocess.run(["which", "rg"], capture_output=True).returncode == 0
        if rg_available:
            cmd = ["rg", "--files-with-matches", "-l", query, location]
        else:
            cmd = ["grep", "-rl", query, location]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        results = result.stdout.strip().splitlines()[:20]
    else:
        if fd_available:
            cmd = ["fd", query, location, "--max-results", "20"]
            if file_type:
                cmd.extend(["-e", file_type])
            if not settings.FILES_SEARCH_HIDDEN:
                cmd.append("--no-hidden")
        else:
            cmd = ["find", location, "-iname", f"*{query}*", "-not", "-path", "*/.*"]
            if file_type:
                cmd = ["find", location, "-iname", f"*.{file_type}", "-not", "-path", "*/.*"]
            cmd.extend(["-maxdepth", "8"])

        for excl in settings.FILES_EXCLUDE_DIRS:
            if fd_available:
                cmd.extend(["--exclude", excl])
            else:
                cmd.extend(["-not", "-path", f"*/{excl}/*"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        results = result.stdout.strip().splitlines()[:20]

    return results


def read_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file: {path}"
    size_kb = p.stat().st_size / 1024
    if size_kb > settings.FILES_READ_MAX_KB:
        return f"File too large ({size_kb:.0f}KB > {settings.FILES_READ_MAX_KB}KB limit). Use search or open it."
    mime, _ = mimetypes.guess_type(str(p))
    if mime and not mime.startswith("text"):
        return f"Binary file ({mime}). Use open_file() to open with default application."
    try:
        return p.read_text(errors="replace")
    except Exception as e:
        return f"Could not read file: {e}"


def list_directory(path: str = "~", show_hidden: bool = False) -> list[str]:
    p = Path(path).expanduser()
    if not p.exists():
        return [f"Directory not found: {path}"]
    try:
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        result = []
        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                continue
            suffix = "/" if entry.is_dir() else ""
            result.append(f"{entry.name}{suffix}")
        return result
    except PermissionError:
        return ["Permission denied"]


def move_to_trash(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"Not found: {path}"
    subprocess.run(["gio", "trash", str(p)], check=True)
    return f"Moved to trash: {p.name}"


def get_recent_files(n: int = 10) -> list[str]:
    """Get recently accessed files via GNOME tracker."""
    try:
        result = subprocess.run(
            ["tracker3", "sparql", "-q",
             f"SELECT ?url WHERE {{ ?f a nfo:FileDataObject ; nie:url ?url }} ORDER BY DESC(?mtime) LIMIT {n}"],
            capture_output=True, text=True, timeout=5
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def create_file(path: str, content: str = "") -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Created: {p}"


def installed_apps() -> list[str]:
    """List installed applications from .desktop files."""
    apps = []
    dirs = [
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
    ]
    for d in dirs:
        if d.exists():
            for f in d.glob("*.desktop"):
                apps.append(f.stem)
    return sorted(apps)
