"""Application service layer: scan, back up, remove.

The UI never runs ``bcdedit`` or deletes files itself; it calls this controller
so every destructive step has the same guards, logging and ordering.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.bcd_parser import (
    BcdEditError,
    BootEntry,
    delete_entry,
    export_store,
    list_firmware_entries,
    run_bcdedit,
    save_firmware_snapshot,
)
from core.correlator import (
    RowItem,
    Status,
    correlate,
    entries_for_rows,
    folders_for_rows,
)
from core.efi_paths import format_size
from core.esp_manager import EspError, EspFolder, EspManager

Level = str
LogFn = Callable[[Level, str], None]

APP_DATA_DIR = "EFIBootCleaner"


class ScanError(RuntimeError):
    """Raised when the boot configuration or ESP cannot be read."""


class BackupError(RuntimeError):
    """Raised when the pre-deletion backup cannot be completed."""


def local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def backups_root() -> Path:
    """``%LOCALAPPDATA%\\EFIBootCleaner\\backups``."""
    return local_app_data() / APP_DATA_DIR / "backups"


def logs_root() -> Path:
    return local_app_data() / APP_DATA_DIR / "logs"


@dataclass(slots=True)
class ScanResult:
    rows: list[RowItem]
    entries: list[BootEntry]
    folders: list[EspFolder]
    esp_root: Path | None
    drive: str | None
    already_mounted: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BackupResult:
    directory: Path
    bcd_file: Path | None = None
    snapshot_file: Path | None = None
    copied_folders: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class RemovalReport:
    dry_run: bool = False
    backup: BackupResult | None = None
    deleted_entries: list[str] = field(default_factory=list)
    deleted_folders: list[Path] = field(default_factory=list)
    skipped_folders: list[tuple[Path, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    aborted: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and not self.aborted

    @property
    def changed_anything(self) -> bool:
        return bool(self.deleted_entries or self.deleted_folders)


class AppController:
    """Headless facade used by the main window."""

    def __init__(
        self,
        logger: LogFn | None = None,
        esp: EspManager | None = None,
        backup_root: Path | None = None,
    ) -> None:
        self.log: LogFn = logger or (lambda _level, _message: None)
        self.esp = esp or EspManager(self.log)
        self.backup_root = backup_root or backups_root()

    # ------------------------------------------------------------------ scan
    def scan(self) -> ScanResult:
        try:
            self.esp.mount()
        except EspError as exc:
            raise ScanError(str(exc)) from exc

        self.log("info", "Reading firmware boot entries with bcdedit ...")
        try:
            entries = list_firmware_entries(self.log)
        except BcdEditError as exc:
            raise ScanError(
                f"Could not read the firmware boot entries: {exc}. "
                "Make sure the app is running as Administrator."
            ) from exc

        try:
            folders = self.esp.scan_folders()
        except EspError as exc:
            raise ScanError(str(exc)) from exc

        rows = correlate(entries, folders, self.esp.root)
        warnings = [row.note for row in rows if row.status is Status.ORPHANED_ENTRY]
        self.log(
            "ok",
            f"Scan complete: {len(entries)} boot entr"
            f"{'y' if len(entries) == 1 else 'ies'}, {len(folders)} EFI folder(s).",
        )
        return ScanResult(
            rows=rows,
            entries=entries,
            folders=folders,
            esp_root=self.esp.root,
            drive=self.esp.letter,
            already_mounted=not self.esp.mounted_by_us,
            warnings=warnings,
        )

    # ---------------------------------------------------------------- backup
    def next_backup_directory(self, when: datetime | None = None) -> Path:
        """Preview the folder that the next backup will use."""
        stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        candidate = self.backup_root / stamp
        suffix = 2
        while candidate.exists():
            candidate = self.backup_root / f"{stamp}_{suffix}"
            suffix += 1
        return candidate

    # Kept for readability at the call sites below.
    _next_backup_directory = next_backup_directory

    def backup(
        self,
        folders: Iterable[Path],
        when: datetime | None = None,
    ) -> BackupResult:
        """Export the BCD store and copy the ESP folders that are about to go."""
        directory = self._next_backup_directory(when)
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise BackupError(f"Could not create backup folder '{directory}': {exc}") from exc

        self.log("info", f"Creating backup in {directory}")
        result = BackupResult(directory=directory)

        try:
            snapshot = run_bcdedit(["/enum", "firmware"], self.log, log_output=False)
            if snapshot.ok:
                result.snapshot_file = save_firmware_snapshot(directory, snapshot.stdout)
                self.log("ok", f"Saved firmware entry snapshot: {result.snapshot_file}")

            result.bcd_file = export_store(directory, self.log)
            self.log("ok", f"Exported BCD store: {result.bcd_file}")

            folder_list = list(folders)
            if folder_list:
                existing = [folder for folder in folder_list if Path(folder).is_dir()]
                for folder in folder_list:
                    if folder not in existing:
                        self.log("warn", f"Skipping backup of missing folder: {folder}")
                result.copied_folders = self.esp.copy_folders(existing, directory / "efi_files")
        except (BcdEditError, EspError, OSError) as exc:
            raise BackupError(f"Backup failed, nothing was deleted: {exc}") from exc

        self.log("ok", f"Backup complete: {directory}")
        return result

    # --------------------------------------------------------------- removal
    def remove(
        self,
        selected: Sequence[RowItem],
        all_rows: Sequence[RowItem],
        *,
        dry_run: bool = False,
        delete_folders: bool = True,
    ) -> RemovalReport:
        """Remove the selected boot entries and, optionally, their ESP folders."""
        report = RemovalReport(dry_run=dry_run)

        entry_rows = [row for row in entries_for_rows(selected)]
        folder_rows = folders_for_rows(selected) if delete_folders else []
        folder_targets = self._folders_kept_by_other_entries(
            folder_rows, selected, all_rows, report
        )

        if not entry_rows and not folder_targets:
            self.log("warn", "Nothing to remove: the selection has no deletable items.")
            report.aborted = True
            return report

        if dry_run:
            self.log("warn", "DRY-RUN mode — no changes will be made.")
            for row in entry_rows:
                self.log("warn", f"DRY-RUN would run: bcdedit /delete {row.identifier}")
            for folder in folder_targets:
                self.log("warn", f"DRY-RUN would delete folder: {folder}")
            if entry_rows or folder_targets:
                planned = self.next_backup_directory()
                self.log("warn", f"DRY-RUN backup would be written to: {planned}")
            return report

        try:
            report.backup = self.backup(folder_targets)
        except BackupError as exc:
            report.errors.append(str(exc))
            report.aborted = True
            self.log("err", str(exc))
            return report

        failed_identifiers: set[str] = set()
        for row in entry_rows:
            try:
                result = delete_entry(row.identifier, self.log)
                if result.ok:
                    report.deleted_entries.append(row.identifier)
                    self.log("ok", f"Removed boot entry {row.identifier} ({row.title})")
                else:
                    failed_identifiers.add(row.identifier.casefold())
                    message = f"Could not delete {row.identifier}: {result.output}"
                    report.errors.append(message)
                    self.log("err", message)
            except Exception as exc:
                failed_identifiers.add(row.identifier.casefold())
                message = f"Could not delete {row.identifier}: {exc}"
                report.errors.append(message)
                self.log("err", message)

        for folder in folder_targets:
            if self._folder_is_referenced_by_failed_entry(folder, entry_rows, failed_identifiers):
                reason = "its boot entry could not be deleted"
                report.skipped_folders.append((folder, reason))
                self.log("warn", f"Kept folder {folder}: {reason}.")
                continue
            try:
                if self.esp.delete_folder(folder):
                    report.deleted_folders.append(folder)
            except (EspError, OSError) as exc:
                message = f"Could not delete folder {folder}: {exc}"
                report.errors.append(message)
                self.log("err", message)

        if report.ok:
            self.log(
                "ok",
                f"Finished: {len(report.deleted_entries)} entr"
                f"{'y' if len(report.deleted_entries) == 1 else 'ies'} and "
                f"{len(report.deleted_folders)} folder(s) removed.",
            )
        else:
            self.log("err", "Finished with errors — see the console above.")
        return report

    def _folders_kept_by_other_entries(
        self,
        folder_rows: Sequence[Path],
        selected: Sequence[RowItem],
        all_rows: Sequence[RowItem],
        report: RemovalReport,
    ) -> list[Path]:
        """Never delete a folder that an unselected boot entry still uses."""
        selected_keys = {row.key for row in selected}
        retained: dict[str, list[str]] = {}
        for row in all_rows:
            if row.key in selected_keys or row.folder_path is None:
                continue
            retained.setdefault(str(row.folder_path).casefold(), []).append(row.title)

        kept: list[Path] = []
        for folder in folder_rows:
            owners = retained.get(str(folder).casefold())
            if owners:
                reason = f"still used by {', '.join(owners)}"
                report.skipped_folders.append((folder, reason))
                self.log("warn", f"Keeping folder {folder}: {reason}.")
                continue
            kept.append(folder)
        return kept

    @staticmethod
    def _folder_is_referenced_by_failed_entry(
        folder: Path, entry_rows: Sequence[RowItem], failed: set[str]
    ) -> bool:
        for row in entry_rows:
            if row.identifier.casefold() not in failed:
                continue
            if row.folder_path and str(row.folder_path).casefold() == str(folder).casefold():
                return True
        return False

    # --------------------------------------------------------------- helpers
    def open_backups_folder(self) -> Path:
        directory = self.backup_root
        directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(directory))
        return directory

    def cleanup(self) -> None:
        self.esp.unmount()

    @staticmethod
    def describe_rows(rows: Sequence[RowItem]) -> str:
        if not rows:
            return "No items selected"
        size = sum(row.folder_size or 0 for row in rows)
        return f"{len(rows)} item(s) selected · {format_size(size)} on disk"
