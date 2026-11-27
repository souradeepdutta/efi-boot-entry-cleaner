"""Safety and correlation tests.

The most important property of the whole project lives here: a protected row
must never become deletable, no matter what the disk or the BCD store says.
"""

from __future__ import annotations

from pathlib import Path

from core.bcd_parser import BootEntry
from core.correlator import (
    Status,
    correlate,
    count_by_status,
    entries_for_rows,
    folders_for_rows,
)
from core.esp_manager import EspFolder

ROOT = Path("Z:/")
UBUNTU_ID = "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}"
FEDORA_ID = "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}"
CACHYOS_ID = "{c92e6b44-1f08-4d13-9a67-7de35c118022}"


def make_entry(identifier: str, description: str = "", path: str = "") -> BootEntry:
    return BootEntry(
        identifier=identifier,
        description=description,
        device="partition=\\Device\\HarddiskVolume2",
        path=path,
        header=description or "Firmware Application",
        values={"identifier": identifier, "description": description, "path": path},
    )


def make_folder(name: str, size: int = 1024) -> EspFolder:
    return EspFolder(name=name, path=ROOT / "EFI" / name, size_bytes=size, file_count=4)


def exists_only(*paths: str):
    normalized = {path.casefold() for path in paths}
    return lambda candidate: str(candidate).casefold() in normalized


def test_protected_identifiers_are_never_deletable_even_when_orphaned() -> None:
    entries = [
        make_entry("{bootmgr}", "Windows Boot Manager", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"),
        make_entry("{fwbootmgr}"),
        make_entry("{current}"),
        make_entry("{default}"),
        make_entry("{memdiag}", "Windows Memory Diagnostic", "\\EFI\\Microsoft\\Boot\\memtest.efi"),
    ]
    rows = correlate(entries, [], ROOT, path_exists=lambda _path: False)

    assert len(rows) == 5
    assert all(row.status is Status.PROTECTED for row in rows)
    assert all(not row.deletable for row in rows)
    assert entries_for_rows(rows) == []
    assert folders_for_rows(rows) == []


def test_active_windows_boot_manager_is_protected_even_with_another_identifier() -> None:
    entry = make_entry(
        "{deadbeef-0000-0000-0000-000000000000}",
        "Windows Boot Manager",
        "\\EFI\\Microsoft\\Boot\\bootmgfw.efi",
    )
    row = correlate([entry], [], ROOT, path_exists=lambda _path: True)[0]
    assert row.status is Status.PROTECTED
    assert not row.deletable
    assert "Windows Boot Manager" in row.protection_reason


def test_microsoft_and_boot_folders_are_protected() -> None:
    entries = [
        make_entry("{aaaa}", "Windows", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"),
        make_entry("{bbbb}", "Fallback", "\\EFI\\Boot\\bootx64.efi"),
    ]
    exists = exists_only(
        "Z:\\EFI\\Microsoft\\Boot\\bootmgfw.efi",
        "Z:\\EFI\\Boot\\bootx64.efi",
    )
    folders = [make_folder("Microsoft"), make_folder("Boot")]
    rows = correlate(entries, folders, ROOT, path_exists=exists)
    assert all(row.status is Status.PROTECTED for row in rows)
    assert all(not row.deletable for row in rows)


def test_protected_folder_stays_protected_without_any_bcd_entry() -> None:
    rows = correlate([], [make_folder("Microsoft")], ROOT, path_exists=lambda _p: True)
    assert len(rows) == 1
    assert rows[0].status is Status.PROTECTED
    assert not rows[0].deletable


def test_linked_entry_and_folder() -> None:
    entries = [make_entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi")]
    exists = exists_only("Z:\\EFI\\ubuntu\\grubx64.efi")
    rows = correlate(entries, [make_folder("ubuntu", 12_400_000)], ROOT, path_exists=exists)
    assert len(rows) == 1
    row = rows[0]
    assert row.status is Status.LINKED
    assert row.deletable
    assert row.folder_path == ROOT / "EFI" / "ubuntu"
    assert row.folder_size == 12_400_000
    assert row.file_exists and row.folder_exists


def test_orphaned_entry_when_the_efi_file_is_missing() -> None:
    entries = [make_entry(FEDORA_ID, "Fedora Linux", "\\EFI\\fedora\\shimx64.efi")]
    rows = correlate(entries, [], ROOT, path_exists=lambda _path: False)
    row = rows[0]
    assert row.status is Status.ORPHANED_ENTRY
    assert row.deletable
    assert "Missing file" in row.note


def test_orphaned_entry_when_the_folder_still_exists() -> None:
    entries = [make_entry(FEDORA_ID, "Fedora Linux", "\\EFI\\fedora\\shimx64.efi")]
    rows = correlate(entries, [make_folder("fedora")], ROOT, path_exists=lambda _path: False)
    row = rows[0]
    assert row.status is Status.ORPHANED_ENTRY
    assert row.folder_path == ROOT / "EFI" / "fedora"
    assert row.deletable


def test_orphaned_folder_without_any_entry() -> None:
    rows = correlate(
        [], [make_folder("endeavouros", 92_100_000)], ROOT, path_exists=lambda _p: True
    )
    row = rows[0]
    assert row.status is Status.ORPHANED_FOLDER
    assert row.deletable
    assert row.identifier == ""
    assert row.folder_size == 92_100_000


def test_claimed_folder_does_not_appear_twice() -> None:
    entries = [make_entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi")]
    folders = [make_folder("ubuntu"), make_folder("manjaro")]
    exists = exists_only("Z:\\EFI\\ubuntu\\grubx64.efi")
    rows = correlate(entries, folders, ROOT, path_exists=exists)
    assert len(rows) == 2
    assert {row.title for row in rows} == {"Ubuntu", "manjaro"}


def test_paths_are_matched_case_insensitively_and_with_forward_slashes() -> None:
    entries = [make_entry(UBUNTU_ID, "Ubuntu", "\\EFI/Ubuntu/GRUBX64.EFI")]
    exists = exists_only("Z:\\EFI\\ubuntu\\grubx64.efi")
    rows = correlate(entries, [make_folder("ubuntu")], ROOT, path_exists=exists)
    assert rows[0].status is Status.LINKED
    assert rows[0].folder_path == ROOT / "EFI" / "ubuntu"


def test_entry_outside_the_esp_is_an_orphaned_entry_without_a_folder() -> None:
    entries = [make_entry("{cccc}", "Legacy", "\\Windows\\system32\\winload.efi")]
    rows = correlate(entries, [make_folder("ubuntu")], ROOT, path_exists=lambda _p: True)
    legacy = next(row for row in rows if row.identifier == "{cccc}")
    assert legacy.status is Status.ORPHANED_ENTRY
    assert legacy.folder_path is None
    assert legacy.deletable
    assert "outside" in legacy.note


def test_rows_are_sorted_with_cleanup_targets_first() -> None:
    entries = [
        make_entry("{bootmgr}", "Windows Boot Manager", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"),
        make_entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi"),
        make_entry(FEDORA_ID, "Fedora Linux", "\\EFI\\fedora\\shimx64.efi"),
    ]
    folders = [make_folder("ubuntu"), make_folder("manjaro")]
    exists = exists_only("Z:\\EFI\\ubuntu\\grubx64.efi")
    rows = correlate(entries, folders, ROOT, path_exists=exists)
    assert [row.status for row in rows] == [
        Status.ORPHANED_ENTRY,
        Status.ORPHANED_FOLDER,
        Status.LINKED,
        Status.PROTECTED,
    ]


def test_folders_for_rows_deduplicates_and_skips_protected() -> None:
    entries = [
        make_entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi"),
        make_entry(CACHYOS_ID, "cachyos", "\\EFI\\ubuntu\\grubx64.efi"),
        make_entry("{bootmgr}", "Windows Boot Manager", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"),
    ]
    folders = [make_folder("ubuntu"), make_folder("Microsoft")]
    rows = correlate(entries, folders, ROOT, path_exists=lambda _p: False)
    folders_to_delete = folders_for_rows(rows)
    assert folders_to_delete == [ROOT / "EFI" / "ubuntu"]


def test_count_by_status_includes_zeroes() -> None:
    rows = correlate(
        [make_entry(UBUNTU_ID, "Ubuntu", "\\EFI\\ubuntu\\grubx64.efi")],
        [make_folder("ubuntu")],
        ROOT,
        path_exists=lambda _p: True,
    )
    counts = count_by_status(rows)
    assert counts[Status.LINKED] == 1
    assert counts[Status.PROTECTED] == 0
    assert counts[Status.ORPHANED_ENTRY] == 0
    assert counts[Status.ORPHANED_FOLDER] == 0
