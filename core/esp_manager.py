"""Mounting, scanning and safely deleting folders on the EFI System Partition.

The ESP has no drive letter by default. We mount it temporarily with
``mountvol <letter>: /S`` as late as possible and always unmount it again in
``finally`` blocks, ``atexit`` and the Qt ``aboutToQuit`` hook.
"""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import os
import shutil
import stat
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from core.bcd_parser import run_command
from core.efi_paths import is_path_within
from core.safety import is_protected_folder_name

Level = str
LogFn = Callable[[Level, str], None]

_FIRST_LETTER = ord("M")
_LAST_LETTER = ord("Z")


class EspError(RuntimeError):
    """Raised when the EFI System Partition cannot be mounted or read."""


class UnsafePathError(EspError):
    """Raised when a deletion target is outside the ESP or protected."""


@dataclass(slots=True)
class EspFolder:
    """A top-level folder inside ``<ESP>:\\EFI``."""

    name: str
    path: Path
    size_bytes: int = 0
    file_count: int = 0


def get_logical_drives() -> int:
    """Bitmask of used drive letters (A=bit 0)."""
    if sys.platform != "win32":  # pragma: no cover - defensive
        return 0
    return int(ctypes.windll.kernel32.GetLogicalDrives())


def find_free_letter(first: str = "M", last: str = "Z", used_mask: int | None = None) -> str | None:
    """Find an unused drive letter, scanning backwards (Z -> M by default)."""
    mask = get_logical_drives() if used_mask is None else used_mask
    for code in range(ord(last.upper()), ord(first.upper()) - 1, -1):
        if not mask & (1 << (code - ord("A"))):
            return chr(code)
    return None


def folder_stats(path: str | os.PathLike[str]) -> tuple[int, int]:
    """Return ``(total_bytes, file_count)`` for a directory tree."""
    total = 0
    count = 0
    for directory, _dirs, files in os.walk(path, onerror=lambda _err: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(directory, name))
                count += 1
            except OSError:
                continue
    return total, count


def _make_writable(root: str | os.PathLike[str]) -> None:
    for directory, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            try:
                os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                continue
    with contextlib.suppress(OSError):
        os.chmod(root, stat.S_IWRITE | stat.S_IREAD)


def remove_tree(path: str | os.PathLike[str]) -> None:
    """Delete a tree, retrying once without read-only bits.

    Avoids ``shutil.rmtree(onerror=...)``, which is deprecated on Python 3.12+.
    """
    try:
        shutil.rmtree(path)
    except PermissionError:
        _make_writable(path)
        shutil.rmtree(path)


class EspManager:
    """Owns the temporary ESP mount for the lifetime of the application."""

    def __init__(self, logger: LogFn | None = None) -> None:
        self.log: LogFn = logger or (lambda _level, _message: None)
        self._letter: str | None = None
        self._mounted_by_us = False
        self._atexit_registered = False

    # ------------------------------------------------------------------ mount
    @property
    def letter(self) -> str | None:
        return self._letter

    @property
    def root(self) -> Path:
        """Root of the mounted partition, e.g. ``Z:/``."""
        if not self._letter:
            raise EspError("The EFI System Partition is not mounted.")
        return Path(f"{self._letter}:/")

    @property
    def efi_root(self) -> Path:
        """``<ESP>:\\EFI``."""
        return self.root / "EFI"

    @property
    def mounted_by_us(self) -> bool:
        return self._mounted_by_us

    @property
    def is_ready(self) -> bool:
        return bool(self._letter) and self.efi_root.is_dir()

    def mount(self) -> str:
        """Return the ESP drive letter, mounting the partition when needed."""
        if self.is_ready:
            return str(self._letter)

        existing = self._detect_existing_esp()
        if existing:
            self._letter = existing
            self._mounted_by_us = False
            self.log(
                "info",
                f"Using the EFI System Partition already mounted at {existing}: "
                "(it will not be unmounted on exit).",
            )
            return existing

        letter = find_free_letter()
        if letter is None:
            raise EspError("No free drive letter between M: and Z: to mount the ESP.")
        self._mount(letter)
        return letter

    def _mount(self, letter: str) -> None:
        drive = f"{letter}:"
        self.log("info", f"Mounting the EFI System Partition at {drive} ...")
        result = run_command(["mountvol", drive, "/S"])
        if not result.ok:
            raise EspError(f"mountvol {drive} /S failed ({result.returncode}): {result.output}")

        if not (Path(f"{letter}:/") / "EFI").is_dir():
            raise EspError(
                f"Mountvol reported success but no \\EFI folder appeared on {drive}. "
                "Is the disk an EFI System Partition?"
            )

        self._letter = letter
        self._mounted_by_us = True
        self._register_atexit()
        self.log("ok", f"EFI System Partition mounted at {drive}")

    def _register_atexit(self) -> None:
        if not self._atexit_registered:
            atexit.register(self.unmount)
            self._atexit_registered = True

    def _detect_existing_esp(self) -> str | None:
        """Find an already mounted ESP so we never unmount someone else's."""

        system_drive = (os.environ.get("SYSTEMDRIVE") or "C:").rstrip("\\").casefold()
        mask = get_logical_drives()
        for code in range(ord("A"), ord("Z") + 1):
            if not mask & (1 << (code - ord("A"))):
                continue
            letter = chr(code)
            if f"{letter}:".casefold() == system_drive:
                continue
            candidate = Path(f"{letter}:/EFI/Microsoft/Boot")
            try:
                if candidate.is_dir():
                    return letter
            except OSError:
                continue
        return None

    def unmount(self) -> None:
        """Unmount the partition if (and only if) this app mounted it."""
        if self._mounted_by_us and self._letter:
            drive = f"{self._letter}:"
            self.log("info", f"Unmounting the EFI System Partition from {drive} ...")
            result = run_command(["mountvol", drive, "/D"])
            if result.ok:
                self.log("ok", f"Unmounted {drive}")
            else:
                self.log("err", f"Could not unmount {drive}: {result.output}")
        self._letter = None
        self._mounted_by_us = False

    def cleanup(self) -> None:
        """Idempotent alias used by the Qt ``aboutToQuit`` handler."""
        self.unmount()

    def __enter__(self) -> EspManager:
        self.mount()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.unmount()

    # ------------------------------------------------------------------ scan
    def scan_folders(self) -> list[EspFolder]:
        """List the folders inside ``\\EFI`` with their sizes."""
        root = self.efi_root
        if not root.is_dir():
            raise EspError(f"'{root}' does not exist or is not readable.")
        folders: list[EspFolder] = []
        for child in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue
            size, count = folder_stats(child)
            folders.append(
                EspFolder(name=child.name, path=child, size_bytes=size, file_count=count)
            )
        self.log("info", f"Found {len(folders)} folder(s) inside \\EFI.")
        return folders

    # --------------------------------------------------------------- deletion
    def assert_safe_to_delete(self, path: str | os.PathLike[str]) -> Path:
        """Validate that *path* is a top-level, non-protected ESP folder."""
        target = Path(path)
        root = self.efi_root
        if not is_path_within(target, root):
            raise UnsafePathError(f"Refusing to delete '{target}': outside '{root}'.")
        try:
            resolved = target.resolve()
            resolved_root = root.resolve()
        except OSError as exc:
            raise UnsafePathError(f"Could not resolve '{target}': {exc}") from exc
        if resolved.parent != resolved_root:
            raise UnsafePathError(f"Refusing to delete '{target}': only top-level folders.")
        if is_protected_folder_name(resolved.name):
            raise UnsafePathError(f"'{resolved.name}' is a protected Windows folder.")
        return resolved

    def delete_folder(
        self,
        path: str | os.PathLike[str],
        *,
        dry_run: bool = False,
    ) -> bool:
        """Delete a single top-level ESP folder. Returns True if removed."""
        target = self.assert_safe_to_delete(path)
        if dry_run:
            self.log("warn", f"DRY-RUN would delete folder: {target}")
            return False
        if not target.exists():
            self.log("warn", f"Folder already gone: {target}")
            return False
        self.log("info", f"Deleting folder: {target}")
        try:
            remove_tree(target)
        except OSError as exc:
            raise EspError(f"Could not delete '{target}': {exc}") from exc
        self.log("ok", f"Deleted folder: {target}")
        return True

    # ---------------------------------------------------------------- backups
    def copy_folder(
        self, source: str | os.PathLike[str], destination_root: str | os.PathLike[str]
    ) -> Path:
        """Copy an ESP folder into the backup directory."""
        src = Path(source)
        if not src.is_dir():
            raise EspError(f"Cannot back up '{src}': folder not found.")
        destination_root = Path(destination_root)
        destination_root.mkdir(parents=True, exist_ok=True)
        target = destination_root / src.name
        if target.exists():
            remove_tree(target)
        self.log("info", f"Backing up {src} -> {target}")
        try:
            shutil.copytree(src, target)
        except OSError as exc:
            raise EspError(f"Backup of '{src}' failed: {exc}") from exc
        self.log("ok", f"Backed up folder: {src.name}")
        return target

    def copy_folders(
        self, folders: Iterable[str | os.PathLike[str]], destination_root: str | os.PathLike[str]
    ) -> list[Path]:
        return [self.copy_folder(folder, destination_root) for folder in folders]
