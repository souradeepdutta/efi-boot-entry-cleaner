"""Windows privilege helpers (UAC detection and relaunch)."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    """True when the current process is elevated."""
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):  # pragma: no cover - defensive
        return False


def _launch_command(extra_args: Sequence[str]) -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        arguments = list(sys.argv[1:])
    else:
        executable = sys.executable
        script = str(Path(sys.argv[0]).resolve())
        arguments = [script, *sys.argv[1:]]
    arguments.extend(extra_args)
    return executable, subprocess.list2cmdline(arguments)


def relaunch_as_admin(extra_args: Sequence[str] = ()) -> bool:
    """Relaunch this process elevated. Returns True when a UAC prompt ran."""
    if not is_windows():
        return False
    executable, arguments = _launch_command(extra_args)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, arguments, None, 1)
    return int(result) > 32


def show_error_dialog(title: str, message: str) -> None:
    """Show a native message box without needing Qt/the UI."""
    if is_windows():
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    else:  # pragma: no cover - the app is Windows-only
        print(f"{title}: {message}", file=sys.stderr)
