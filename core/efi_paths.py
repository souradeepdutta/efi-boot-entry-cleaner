"""Helpers for normalising and comparing EFI paths.

BCD stores paths as ``\\EFI\\ubuntu\\grubx64.efi`` while the file system and
user input are case-insensitive and may use forward slashes. All comparisons
in the app go through these helpers so ``\\EFI\\Ubuntu\\GRUBX64.EFI`` and
``\\efi\\ubuntu\\grubx64.efi`` are treated as the same file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_EFI_PREFIX = re.compile(r"^\\efi\\([^\\]+)(\\|$)")
_DEVICE_PREFIXES = ("\\??\\", "\\\\?\\")


def normalize_efi_path(path: str | None) -> str:
    """Return a case-folded, backslash-separated form of an EFI path."""
    value = (path or "").strip().strip('"').replace("\x00", "")
    value = value.replace("/", "\\")
    lowered = value.casefold()
    for prefix in _DEVICE_PREFIXES:
        if lowered.startswith(prefix):
            value = "\\" + value[len(prefix) :].lstrip("\\")
            break
    value = re.sub(r"\\{2,}", r"\\", value)
    return value.casefold()


def efi_folder_name(path: str | None) -> str | None:
    """Return the top-level folder under ``\\EFI\\`` for a boot path.

    ``\\EFI\\cachyos\\grubx64.efi`` -> ``"cachyos"`` (case-folded).
    Returns ``None`` when the path does not live under ``\\EFI\\``.
    """
    match = _EFI_PREFIX.match(normalize_efi_path(path))
    return match.group(1) if match else None


def efi_relative_path(path: str | None) -> str | None:
    """Return the path relative to the ``\\EFI\\`` root, or ``None``."""
    normalized = normalize_efi_path(path)
    if not normalized.startswith("\\efi\\"):
        return None
    relative = normalized[len("\\efi\\") :]
    return relative or None


def is_path_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    """True when *child* is strictly inside *parent* (after resolving)."""
    try:
        child_path = Path(child).resolve()
        parent_path = Path(parent).resolve()
    except (OSError, ValueError):
        return False
    if child_path == parent_path:
        return False
    return parent_path in child_path.parents


def format_size(size_bytes: int | None) -> str:
    """Human readable size, e.g. ``14.7 MB``."""
    if size_bytes is None:
        return "—"
    value = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
