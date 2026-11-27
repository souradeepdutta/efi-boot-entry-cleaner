"""Controller tests: backup ordering, dry runs and shared-folder protection."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.bcd_parser import BootEntry, CommandResult
from core.controller import AppController, BackupError, BackupResult
from core.correlator import Status, correlate
from core.esp_manager import EspFolder

ROOT = Path("Z:/")
UBUNTU_ID = "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}"
FEDORA_ID = "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}"
DEBIAN_ID = "{77aa66bb-55cc-44dd-9ee1-223344556677}"
BOOTMGR_ID = "{bootmgr}"


def entry(identifier: str, description: str, path: str) -> BootEntry:
    return BootEntry(
        identifier=identifier,
        description=description,
        device="partition=\\Device\\HarddiskVolume2",
        path=path,
        header=description,
        values={"identifier": identifier, "path": path},
    )


class FakeEsp:
    def __init__(self, folders: list[EspFolder], root: Path = ROOT) -> None:
        self._folders = folders
        self._root = root
        self.letter = "Z"
        self.mounted_by_us = True
        self.deleted: list[Path] = []
        self.copied: list[tuple[Path, ...]] = []
        self.messages: list[tuple[str, str]] = []

    @property
    def root(self) -> Path:
        return self._root

    def mount(self) -> str:
        return "Z"

    def scan_folders(self) -> list[EspFolder]:
        return list(self._folders)

    def copy_folders(self, folders, destination) -> list[Path]:
        folders = tuple(folders)
        self.copied.append(folders)
        return [Path(destination) / folder.name for folder in folders]

    def delete_folder(self, path, dry_run: bool = False) -> bool:
        if dry_run:
            return False
        self.deleted.append(Path(path))
        return True

    def unmount(self) -> None:
        pass


def build(tmp_path: Path, root: Path = ROOT, create_files: bool = False):
    folders = [
        EspFolder("Microsoft", root / "EFI" / "Microsoft", 40_000_000, 30),
        EspFolder("ubuntu", root / "EFI" / "ubuntu", 12_000_000, 12),
        EspFolder("fedora", root / "EFI" / "fedora", 8_000_000, 9),
        EspFolder("endeavouros", root / "EFI" / "endeavouros", 90_000_000, 50),
    ]
    entries = [
        entry(BOOTMGR_ID, "Windows Boot Manager", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"),
        entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi"),
        entry(DEBIAN_ID, "Debian", "\\EFI\\ubuntu\\grubx64.efi"),
        entry(FEDORA_ID, "Fedora Linux", "\\EFI\\fedora\\shimx64.efi"),
    ]
    if create_files:
        for relative in ("Microsoft\\Boot\\bootmgfw.efi", "ubuntu\\grubx64.efi"):
            target = root / "EFI" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"efi")
        rows = correlate(entries, folders, root)
    else:
        existing = {"microsoft\\boot\\bootmgfw.efi", "ubuntu\\grubx64.efi"}

        def path_exists(candidate) -> bool:
            try:
                relative = Path(candidate).relative_to(root / "EFI")
            except ValueError:
                return False
            return str(relative).casefold() in existing

        rows = correlate(entries, folders, root, path_exists=path_exists)
    esp = FakeEsp(folders, root)
    logs: list[tuple[str, str]] = []
    controller = AppController(
        logger=lambda level, message: logs.append((level, message)),
        esp=esp,
        backup_root=tmp_path / "backups",
    )
    return controller, esp, rows, logs


def row(rows, identifier: str):
    return next(item for item in rows if item.identifier == identifier)


def test_scan_combines_bcd_and_esp(monkeypatch, tmp_path) -> None:
    root = tmp_path / "esp"
    controller, _esp, _rows, _logs = build(tmp_path, root=root, create_files=True)
    monkeypatch.setattr(
        "core.controller.list_firmware_entries",
        lambda _logger: [
            entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi"),
        ],
    )
    result = controller.scan()
    assert result.drive == "Z"
    assert len(result.rows) == 4  # ubuntu + Microsoft + fedora + endeavouros
    assert result.esp_root == root
    assert any(item.status is Status.LINKED for item in result.rows)


def test_dry_run_never_backs_up_or_deletes(monkeypatch, tmp_path) -> None:
    controller, esp, rows, logs = build(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry run must not touch the system")

    monkeypatch.setattr(controller, "backup", forbidden)
    monkeypatch.setattr("core.controller.delete_entry", forbidden)

    fedora = row(rows, FEDORA_ID)
    report = controller.remove([fedora], rows, dry_run=True)

    assert report.dry_run
    assert report.deleted_entries == []
    assert report.deleted_folders == []
    assert esp.deleted == []
    assert any(FEDORA_ID in message for _level, message in logs)
    assert any("DRY-RUN" in message for _level, message in logs)


def test_real_removal_backs_up_before_deleting(monkeypatch, tmp_path) -> None:
    controller, esp, rows, logs = build(tmp_path)
    order: list[str] = []

    def fake_backup(folders, when=None):
        order.append("backup")
        return BackupResult(directory=tmp_path / "backup")

    def fake_delete(identifier, logger=None, **_kwargs):
        order.append(f"delete:{identifier}")
        return CommandResult(args=["bcdedit", "/delete", identifier])

    monkeypatch.setattr(controller, "backup", fake_backup)
    monkeypatch.setattr("core.controller.delete_entry", fake_delete)

    fedora = row(rows, FEDORA_ID)
    report = controller.remove([fedora], rows)

    assert report.ok
    assert report.deleted_entries == [FEDORA_ID]
    assert report.deleted_folders == [ROOT / "EFI" / "fedora"]
    assert order == ["backup", f"delete:{FEDORA_ID}"]
    assert esp.deleted == [ROOT / "EFI" / "fedora"]
    assert any("Removed boot entry" in message for _level, message in logs)


def test_backup_failure_aborts_everything(monkeypatch, tmp_path) -> None:
    controller, esp, rows, _logs = build(tmp_path)

    def failing_backup(_folders, when=None):
        raise BackupError("disk full")

    monkeypatch.setattr(controller, "backup", failing_backup)
    monkeypatch.setattr(
        "core.controller.delete_entry",
        lambda *_a, **_k: pytest.fail("must not delete after a failed backup"),
    )

    report = controller.remove([row(rows, FEDORA_ID)], rows)
    assert report.aborted
    assert report.errors and "disk full" in report.errors[0]
    assert esp.deleted == []


def test_shared_folder_is_kept_for_the_other_entry(monkeypatch, tmp_path) -> None:
    controller, esp, rows, logs = build(tmp_path)
    monkeypatch.setattr(
        controller,
        "backup",
        lambda folders, when=None: BackupResult(directory=tmp_path / "backup"),
    )
    monkeypatch.setattr(
        "core.controller.delete_entry",
        lambda identifier, logger=None, **_kwargs: CommandResult(
            args=["bcdedit", "/delete", identifier]
        ),
    )

    # Debian and Ubuntu both point at \EFI\ubuntu; removing only Debian must
    # keep the folder for Ubuntu.
    report = controller.remove([row(rows, DEBIAN_ID)], rows)
    assert report.deleted_entries == [DEBIAN_ID]
    assert report.deleted_folders == []
    assert esp.deleted == []
    assert any("Keeping folder" in message for _level, message in logs)


def test_selecting_a_protected_row_does_nothing(tmp_path) -> None:
    controller, esp, rows, logs = build(tmp_path)
    report = controller.remove([row(rows, BOOTMGR_ID)], rows)
    assert report.aborted
    assert esp.deleted == []
    assert any("Nothing to remove" in message for _level, message in logs)


def test_protected_folder_is_never_deleted_even_if_selected() -> None:
    controller, esp, rows, _logs = build(Path("."))
    microsoft_entry = row(rows, BOOTMGR_ID)
    assert not microsoft_entry.deletable
    report = controller.remove([microsoft_entry], rows)
    assert report.aborted
    assert esp.deleted == []


def test_delete_folders_can_be_disabled(monkeypatch, tmp_path) -> None:
    controller, esp, rows, _logs = build(tmp_path)
    monkeypatch.setattr(
        controller,
        "backup",
        lambda folders, when=None: BackupResult(directory=tmp_path / "backup"),
    )
    monkeypatch.setattr(
        "core.controller.delete_entry",
        lambda identifier, logger=None, **_kwargs: CommandResult(
            args=["bcdedit", "/delete", identifier]
        ),
    )
    report = controller.remove([row(rows, FEDORA_ID)], rows, delete_folders=False)
    assert report.deleted_entries == [FEDORA_ID]
    assert esp.deleted == []
    assert esp.copied == []


def test_backup_directory_names_are_unique(tmp_path) -> None:
    controller, _esp, _rows, _logs = build(tmp_path)
    from datetime import datetime

    when = datetime(2026, 1, 2, 3, 4, 5)
    first = controller.next_backup_directory(when)
    assert first.name == "2026-01-02_03-04-05"
    first.mkdir(parents=True)
    second = controller.next_backup_directory(when)
    assert second.name == "2026-01-02_03-04-05_2"
