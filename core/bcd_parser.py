"""Run and parse ``bcdedit``.

The module is deliberately free of UI imports so it can be exercised by unit
tests with captured ``bcdedit /enum firmware`` output.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from core.safety import ProtectedItemError, is_protected_identifier

Level = str  # "info" | "cmd" | "out" | "err" | "ok" | "warn" | "dim"
LogFn = Callable[[Level, str], None]

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_HEADER_RULE = re.compile(r"^\s*-{3,}\s*$")
_KEY_VALUE = re.compile(r"^([^\s=]+)\s*[=:]?\s+(.+)$")
_ERROR_HINTS = (
    "the boot configuration data store could not be opened",
    "access is denied",
    "an error occurred",
    "the specified entry is not valid",
)


class BcdEditError(RuntimeError):
    """Raised when ``bcdedit`` fails or returns something unparseable."""


@dataclass(slots=True)
class CommandResult:
    """Result of a command invocation (also used for dry runs)."""

    args: list[str]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def command_line(self) -> str:
        return format_command(self.args)

    @property
    def output(self) -> str:
        text = "\n".join(part.strip() for part in (self.stdout, self.stderr) if part.strip())
        return text or "(no output)"


@dataclass(slots=True)
class BootEntry:
    """A single firmware boot entry as reported by ``bcdedit``."""

    identifier: str
    description: str = ""
    device: str = ""
    path: str = ""
    header: str = ""
    values: dict[str, str] = field(default_factory=dict)

    @property
    def clean_path(self) -> str:
        """Path without surrounding quotes."""
        return self.path.strip().strip('"')

    @property
    def label(self) -> str:
        return self.description.strip() or self.header.strip() or self.identifier


def format_command(args: Sequence[str]) -> str:
    """Join an argument list into a copy-pasteable command line."""
    parts: list[str] = []
    for arg in args:
        if arg and not any(ch.isspace() for ch in arg) and '"' not in arg:
            parts.append(arg)
        else:
            parts.append('"' + arg.replace('"', '\\"') + '"')
    return " ".join(parts)


def _decode(raw: bytes) -> str:
    """Decode console output using the OEM code page when possible."""
    for encoding in ("oem", "mbcs", "utf-8"):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def run_command(args: Sequence[str], timeout: int = 120) -> CommandResult:
    """Run a command, capturing output without flashing a console window."""
    command = [str(part) for part in args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:  # pragma: no cover - Windows only
        raise BcdEditError(f"Could not find '{command[0]}'. Is it on PATH?") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        raise BcdEditError(f"Command timed out: {format_command(command)}") from exc
    return CommandResult(
        args=command,
        returncode=completed.returncode,
        stdout=_decode(completed.stdout),
        stderr=_decode(completed.stderr),
    )


def run_bcdedit(
    args: Sequence[str],
    logger: LogFn | None = None,
    *,
    log_output: bool = True,
    runner: Callable[[Sequence[str]], CommandResult] | None = None,
) -> CommandResult:
    """Run ``bcdedit`` with the given arguments and stream it to the log."""
    command = ["bcdedit", *[str(part) for part in args]]
    if logger:
        logger("cmd", format_command(command))
    result = (runner or run_command)(command)
    if logger and log_output:
        for line in result.stdout.splitlines():
            if line.strip():
                logger("out", line.rstrip())
        for line in result.stderr.splitlines():
            if line.strip():
                logger("err", line.rstrip())
    return result


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_bcdedit_output(text: str) -> list[BootEntry]:
    """Parse ``bcdedit /enum`` output into :class:`BootEntry` objects.

    Blocks look like::

        Windows Boot Manager
        --------------------
        identifier              {bootmgr}
        description             Windows Boot Manager
        path                    \\EFI\\Microsoft\\Boot\\bootmgfw.efi

    Multi-line values (``displayorder``) are joined with newlines and
    indentation/whitespace variations are tolerated.
    """
    if not text or not text.strip():
        return []

    lines = _split_lines(text)
    has_block_rule = any(_HEADER_RULE.match(line) for line in lines)
    if not has_block_rule:
        message = " ".join(part.strip() for part in text.strip().splitlines() if part.strip())
        raise BcdEditError(message or "Unexpected bcdedit output")

    entries: list[BootEntry] = []
    current: dict[str, str] | None = None
    current_header = ""
    last_key: str | None = None
    index = 0

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped:
            index += 1
            continue

        starts_block = (
            not raw[:1].isspace()
            and index + 1 < len(lines)
            and _HEADER_RULE.match(lines[index + 1])
        )
        if starts_block:
            if current is not None:
                entries.append(_build_entry(current_header, current))
            current_header = stripped
            current = {}
            last_key = None
            index += 2
            continue

        if current is None:
            # Text before the first block: usually an error from bcdedit.
            if any(hint in stripped.casefold() for hint in _ERROR_HINTS):
                raise BcdEditError(stripped)
            index += 1
            continue

        if _HEADER_RULE.match(stripped):
            index += 1
            continue

        if raw[:1].isspace() and last_key is not None:
            # Continuation of a multi-line value such as displayorder.
            previous = current.get(last_key, "")
            current[last_key] = f"{previous}\n{stripped}".strip()
        else:
            match = _KEY_VALUE.match(stripped)
            if match:
                key = match.group(1).strip().casefold()
                value = match.group(2).strip()
                current[key] = value
                last_key = key
        index += 1

    if current is not None:
        entries.append(_build_entry(current_header, current))

    return [entry for entry in entries if entry.identifier]


def _build_entry(header: str, values: dict[str, str]) -> BootEntry:
    description = values.get("description", "").strip()
    return BootEntry(
        identifier=values.get("identifier", "").strip(),
        description=description,
        device=values.get("device", "").strip(),
        path=values.get("path", "").strip(),
        header=header,
        values=dict(values),
    )


def list_firmware_entries(
    logger: LogFn | None = None,
    *,
    runner: Callable[[Sequence[str]], CommandResult] | None = None,
) -> list[BootEntry]:
    """Return every entry in the firmware BCD store."""
    result = run_bcdedit(["/enum", "firmware"], logger, log_output=False, runner=runner)
    if not result.ok:
        raise BcdEditError(result.output)
    return parse_bcdedit_output(result.stdout)


def list_all_entries(
    logger: LogFn | None = None,
    *,
    runner: Callable[[Sequence[str]], CommandResult] | None = None,
) -> list[BootEntry]:
    """Return entries from the system store (used for the backup report)."""
    result = run_bcdedit(["/enum"], logger, log_output=False, runner=runner)
    if not result.ok:
        raise BcdEditError(result.output)
    return parse_bcdedit_output(result.stdout)


def delete_entry(
    identifier: str,
    logger: LogFn | None = None,
    *,
    dry_run: bool = False,
    runner: Callable[[Sequence[str]], CommandResult] | None = None,
) -> CommandResult:
    """Delete a firmware boot entry.

    Guards protected identifiers again (defence in depth) and retries with
    ``/f`` when Windows asks for a forced delete.
    """
    if is_protected_identifier(identifier):
        raise ProtectedItemError(f"'{identifier}' is protected and cannot be deleted.")

    if dry_run:
        result = CommandResult(
            args=["bcdedit", "/delete", identifier],
            stdout="[dry-run] command not executed",
            dry_run=True,
        )
        if logger:
            logger("warn", f"DRY-RUN would run: {result.command_line}")
        return result

    result = run_bcdedit(["/delete", identifier], logger, runner=runner)
    if result.ok:
        return result

    output = result.output.casefold()
    if "access is denied" in output or "could not be opened" in output:
        return result  # elevation problem, forcing will not help

    if logger:
        logger("warn", f"Retrying with /f: {identifier}")
    forced = run_bcdedit(["/delete", identifier, "/f"], logger, runner=runner)
    return forced


def export_store(
    destination_dir: str | os.PathLike[str],
    logger: LogFn | None = None,
    *,
    dry_run: bool = False,
    runner: Callable[[Sequence[str]], CommandResult] | None = None,
) -> Path:
    """Export the system BCD store to ``<destination_dir>\\bcd_backup``."""
    directory = Path(destination_dir)
    target = directory / "bcd_backup"
    if dry_run:
        if logger:
            logger(
                "warn", f"DRY-RUN would run: {format_command(['bcdedit', '/export', str(target)])}"
            )
        return target

    directory.mkdir(parents=True, exist_ok=True)
    result = run_bcdedit(["/export", str(target)], logger, runner=runner)
    if not result.ok:
        raise BcdEditError(f"BCD export failed: {result.output}")
    if not target.exists():
        raise BcdEditError(f"BCD export finished but '{target}' was not created.")
    return target


def save_firmware_snapshot(
    destination_dir: str | os.PathLike[str],
    text: str,
    *,
    dry_run: bool = False,
) -> Path:
    """Keep a plain-text copy of ``bcdedit /enum firmware`` next to the export."""
    target = Path(destination_dir) / "firmware_entries.txt"
    if dry_run:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", errors="replace")
    return target
