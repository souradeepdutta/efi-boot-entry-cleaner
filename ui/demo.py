"""Demo data so the UI can be explored (and screenshotted) without an ESP."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.bcd_parser import BootEntry
from core.controller import BackupResult, RemovalReport, ScanResult, backups_root
from core.correlator import correlate
from core.esp_manager import EspFolder


def _entry(
    identifier: str,
    description: str,
    path: str,
    device: str = "partition=\\Device\\HarddiskVolume2",
) -> BootEntry:
    header = description or "Firmware Application"
    return BootEntry(
        identifier=identifier,
        description=description,
        device=device,
        path=path,
        header=header,
        values={"identifier": identifier, "description": description, "path": path},
    )


class DemoController:
    """Drop-in replacement for :class:`AppController` with fixed data."""

    def __init__(self, logger=None) -> None:
        self.log = logger or (lambda _level, _message: None)
        self.backup_root = backups_root()
        self.esp = None

    def scan(self) -> ScanResult:
        self.log("cmd", "bcdedit /enum firmware")
        self.log("info", "Demo mode: showing simulated boot entries and EFI folders.")
        root = Path("E:/")

        entries = [
            _entry(
                "{fwbootmgr}", "Firmware Boot Manager", "", "partition=\\Device\\HarddiskVolume1"
            ),
            _entry(
                "{bootmgr}",
                "Windows Boot Manager",
                "\\EFI\\Microsoft\\Boot\\bootmgfw.efi",
                "partition=\\Device\\HarddiskVolume1",
            ),
            _entry(
                "{memdiag}",
                "Windows Memory Diagnostic",
                "\\EFI\\Microsoft\\Boot\\memtest.efi",
            ),
            _entry(
                "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}",
                "Ubuntu",
                "\\EFI\\ubuntu\\grubx64.efi",
            ),
            _entry(
                "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}",
                "Fedora Linux",
                "\\EFI\\fedora\\shimx64.efi",
            ),
            _entry(
                "{c92e6b44-1f08-4d13-9a67-7de35c118022}",
                "cachyos",
                "\\EFI\\cachyos\\grubx64.efi",
            ),
        ]

        folders = [
            EspFolder("Boot", root / "EFI" / "Boot", 1_240_000, 6),
            EspFolder("Microsoft", root / "EFI" / "Microsoft", 46_800_000, 38),
            EspFolder("cachyos", root / "EFI" / "cachyos", 118_600_000, 71),
            EspFolder("endeavouros", root / "EFI" / "endeavouros", 92_100_000, 54),
            EspFolder("manjaro", root / "EFI" / "manjaro", 74_300_000, 41),
            EspFolder("ubuntu", root / "EFI" / "ubuntu", 12_400_000, 17),
        ]

        existing = {
            "e:\\efi\\microsoft\\boot\\bootmgfw.efi",
            "e:\\efi\\microsoft\\boot\\memtest.efi",
            "e:\\efi\\ubuntu\\grubx64.efi",
            "e:\\efi\\cachyos\\grubx64.efi",
        }

        def path_exists(candidate) -> bool:
            return str(candidate).casefold() in existing

        rows = correlate(entries, folders, root, path_exists=path_exists)
        self.log(
            "ok",
            f"Demo scan complete: {len(entries)} boot entries, {len(folders)} EFI folders.",
        )
        return ScanResult(
            rows=rows,
            entries=entries,
            folders=folders,
            esp_root=root,
            drive="E",
            already_mounted=True,
        )

    def next_backup_directory(self, when: datetime | None = None) -> Path:
        stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        return self.backup_root / stamp

    def remove(
        self,
        selected,
        all_rows,
        *,
        dry_run: bool = False,
        delete_folders: bool = True,
    ) -> RemovalReport:
        report = RemovalReport(dry_run=dry_run)
        if dry_run:
            self.log("warn", "DRY-RUN mode — no changes will be made.")
            for row in selected:
                if row.identifier:
                    self.log("warn", f"DRY-RUN would run: bcdedit /delete {row.identifier}")
                if row.folder_path and delete_folders:
                    self.log("warn", f"DRY-RUN would delete folder: {row.folder_path}")
            return report

        self.log("info", "Demo mode: pretending to create a backup.")
        report.backup = BackupResult(directory=self.next_backup_directory())
        report.deleted_entries = [row.identifier for row in selected if row.identifier]
        report.deleted_folders = [
            row.folder_path for row in selected if row.folder_path and delete_folders
        ]
        self.log("ok", "Demo mode: nothing was actually changed.")
        return report

    def open_backups_folder(self) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.log("info", f"Demo mode: backups folder is {self.backup_root}")
        return self.backup_root

    def cleanup(self) -> None:
        self.log("dim", "Demo mode: no EFI System Partition was mounted.")

    @staticmethod
    def describe_rows(rows) -> str:
        from core.efi_paths import format_size

        if not rows:
            return "No items selected"
        size = sum(row.folder_size or 0 for row in rows)
        return f"{len(rows)} item(s) selected · {format_size(size)} on disk"
