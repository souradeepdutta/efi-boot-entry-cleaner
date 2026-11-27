"""Tests for EFI path normalisation and human readable sizes."""

from __future__ import annotations

from pathlib import Path

from core.efi_paths import (
    efi_folder_name,
    efi_relative_path,
    format_size,
    is_path_within,
    normalize_efi_path,
)


def test_normalizes_case_slashes_quotes_and_device_prefix() -> None:
    assert normalize_efi_path("\\EFI\\Ubuntu\\grubx64.efi") == "\\efi\\ubuntu\\grubx64.efi"
    assert normalize_efi_path("\\EFI/Ubuntu/GRUBX64.EFI") == "\\efi\\ubuntu\\grubx64.efi"
    assert normalize_efi_path('"\\EFI\\\\Boot\\\\bootx64.efi"') == "\\efi\\boot\\bootx64.efi"
    assert normalize_efi_path("\\??\\EFI\\ubuntu\\grubx64.efi") == "\\efi\\ubuntu\\grubx64.efi"


def test_efi_folder_name() -> None:
    assert efi_folder_name("\\EFI\\cachyos\\grubx64.efi") == "cachyos"
    assert efi_folder_name("\\EFI\\Microsoft\\Boot\\bootmgfw.efi") == "microsoft"
    assert efi_folder_name("\\EFI\\ubuntu") == "ubuntu"
    assert efi_folder_name("\\Windows\\system32\\winload.efi") is None
    assert efi_folder_name("") is None
    assert efi_folder_name(None) is None


def test_efi_relative_path() -> None:
    assert efi_relative_path("\\EFI\\ubuntu\\grubx64.efi") == "ubuntu\\grubx64.efi"
    assert efi_relative_path("\\EFI\\") is None
    assert efi_relative_path("\\bootmgr") is None


def test_is_path_within(tmp_path: Path) -> None:
    root = tmp_path / "EFI"
    child = root / "ubuntu"
    child.mkdir(parents=True)
    assert is_path_within(child, root)
    assert not is_path_within(root, root)
    assert not is_path_within(tmp_path / "Windows", root)
    assert not is_path_within(root / "ubuntu" / ".." / ".." / "Windows", root)


def test_format_size() -> None:
    assert format_size(None) == "—"
    assert format_size(0) == "0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(12_400_000) == "11.8 MB"
    assert format_size(118_600_000) == "113.1 MB"
    assert format_size(5_000_000_000) == "4.7 GB"
