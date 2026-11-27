"""Merge firmware boot entries with the contents of the EFI System Partition.

The correlator is the only place that decides what a row *is* and whether it
may be deleted. It never touches the system itself, which makes the safety
rules straightforward to test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.bcd_parser import BootEntry
from core.efi_paths import efi_folder_name, efi_relative_path, normalize_efi_path
from core.esp_manager import EspFolder
from core.safety import (
    is_active_windows_boot_manager,
    is_protected_folder_name,
    is_protected_identifier,
)


class Status(StrEnum):
    PROTECTED = "Protected"
    LINKED = "Linked"
    ORPHANED_ENTRY = "Orphaned Entry"
    ORPHANED_FOLDER = "Orphaned Folder"

    @property
    def priority(self) -> int:
        return {
            Status.ORPHANED_ENTRY: 0,
            Status.ORPHANED_FOLDER: 1,
            Status.LINKED: 2,
            Status.PROTECTED: 3,
        }[self]


@dataclass(slots=True)
class RowItem:
    """One row in the UI table."""

    key: str
    status: Status
    title: str
    identifier: str = ""
    efi_path: str = ""
    folder_path: Path | None = None
    folder_size: int | None = None
    file_exists: bool = False
    folder_exists: bool = False
    deletable: bool = True
    protection_reason: str = ""
    note: str = ""

    @property
    def is_protected(self) -> bool:
        return not self.deletable

    @property
    def has_entry(self) -> bool:
        return bool(self.identifier)


def _protection_reason(entry: BootEntry, folder_name: str | None) -> str:
    if is_protected_identifier(entry.identifier):
        return f"Well-known BCD identifier {entry.identifier}"
    if is_active_windows_boot_manager(entry.identifier, entry.description, entry.path):
        return "Active Windows Boot Manager"
    if folder_name and is_protected_folder_name(folder_name):
        return f"Windows system folder \\EFI\\{folder_name}"
    return ""


def correlate(
    entries: Iterable[BootEntry],
    folders: Iterable[EspFolder],
    esp_root: str | Path,
    path_exists: Callable[[str | Path], bool] | None = None,
) -> list[RowItem]:
    """Correlate BCD entries with ESP folders and classify every row.

    *esp_root* is the root of the mounted partition, e.g. ``Path("Z:/")``.
    """
    exists: Callable[[str | Path], bool] = path_exists or (
        lambda candidate: Path(candidate).exists()
    )
    root = Path(esp_root)
    folder_list = list(folders)
    folders_by_name = {folder.name.casefold(): folder for folder in folder_list}
    claimed: set[str] = set()
    rows: list[RowItem] = []

    for entry in entries:
        if not entry.identifier:
            continue

        folder_name = efi_folder_name(entry.path)
        folder = folders_by_name.get(folder_name) if folder_name else None
        if folder is not None:
            claimed.add(folder.name.casefold())

        relative = efi_relative_path(entry.path)
        efi_file = (root / "EFI").joinpath(*relative.split("\\")) if relative else None
        file_exists = bool(efi_file is not None and exists(efi_file))

        reason = _protection_reason(entry, folder_name)
        if reason:
            status = Status.PROTECTED
        elif file_exists and folder is not None:
            status = Status.LINKED
        else:
            status = Status.ORPHANED_ENTRY

        notes: list[str] = []
        if not entry.path:
            notes.append("Entry has no EFI path (firmware application)")
        elif not relative:
            notes.append("Entry points outside the EFI System Partition")
        elif not file_exists:
            notes.append(f"Missing file: {entry.clean_path}")
        if folder_name and folder is None:
            notes.append(f"Missing folder: \\EFI\\{folder_name}")
        if status is Status.LINKED:
            notes.append("Entry and EFI folder are both present")

        rows.append(
            RowItem(
                key=f"entry:{normalize_efi_path(entry.identifier)}",
                status=status,
                title=entry.label,
                identifier=entry.identifier,
                efi_path=entry.clean_path or entry.device,
                folder_path=folder.path if folder else None,
                folder_size=folder.size_bytes if folder else None,
                file_exists=file_exists,
                folder_exists=folder is not None,
                deletable=not reason,
                protection_reason=reason,
                note=" · ".join(notes),
            )
        )

    for folder in folder_list:
        if folder.name.casefold() in claimed:
            continue
        protected = is_protected_folder_name(folder.name)
        reason = f"Windows system folder \\EFI\\{folder.name}" if protected else ""
        rows.append(
            RowItem(
                key=f"folder:{folder.name.casefold()}",
                status=Status.PROTECTED if protected else Status.ORPHANED_FOLDER,
                title=folder.name,
                efi_path=str(folder.path),
                folder_path=folder.path,
                folder_size=folder.size_bytes,
                folder_exists=True,
                deletable=not protected,
                protection_reason=reason,
                note="No UEFI boot entry references this folder",
            )
        )

    rows.sort(key=lambda row: (row.status.priority, row.title.casefold()))
    return rows


def count_by_status(rows: Iterable[RowItem]) -> dict[Status, int]:
    """Count rows per status (missing statuses default to zero)."""
    counts = {status: 0 for status in Status}
    for row in rows:
        counts[row.status] += 1
    return counts


def folders_for_rows(rows: Iterable[RowItem]) -> list[Path]:
    """Unique, ordered ESP folders referenced by the given rows.

    Rows whose folder is missing on disk are skipped: there is nothing to copy
    or delete, and the boot entry alone is the orphan.
    """
    seen: set[str] = set()
    result: list[Path] = []
    for row in rows:
        if row.folder_path is None or not row.deletable or not row.folder_exists:
            continue
        key = str(row.folder_path).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(row.folder_path)
    return result


def entries_for_rows(rows: Iterable[RowItem]) -> list[RowItem]:
    """Rows that carry a deletable BCD identifier."""
    return [row for row in rows if row.identifier and row.deletable]
