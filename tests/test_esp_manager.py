"""Tests for ESP letter selection and deletion guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.esp_manager import EspManager, UnsafePathError, find_free_letter, folder_stats


class LocalEsp(EspManager):
    """EspManager rooted at a temporary folder instead of a real drive."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._fake_root = root
        self.messages: list[tuple[str, str]] = []
        self.log = lambda level, message: self.messages.append((level, message))

    @property
    def root(self) -> Path:  # type: ignore[override]
        return self._fake_root


def make_esp(tmp_path: Path) -> LocalEsp:
    (tmp_path / "EFI" / "ubuntu").mkdir(parents=True)
    (tmp_path / "EFI" / "Microsoft").mkdir(parents=True)
    return LocalEsp(tmp_path)


def test_find_free_letter_scans_backwards() -> None:
    assert find_free_letter(used_mask=0) == "Z"
    only_q = 0xFFFFFFFF & ~(1 << (ord("Q") - ord("A")))
    assert find_free_letter(used_mask=only_q) == "Q"


def test_find_free_letter_returns_none_when_full() -> None:
    assert find_free_letter(used_mask=0xFFFFFFFF) is None


def test_folder_stats_counts_nested_files(tmp_path: Path) -> None:
    folder = tmp_path / "EFI" / "ubuntu"
    (folder / "nested").mkdir(parents=True)
    (folder / "grubx64.efi").write_bytes(b"0" * 100)
    (folder / "nested" / "grub.cfg").write_bytes(b"0" * 50)
    size, count = folder_stats(folder)
    assert size == 150
    assert count == 2


def test_assert_safe_to_delete_accepts_top_level_folder(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    resolved = esp.assert_safe_to_delete(tmp_path / "EFI" / "ubuntu")
    assert resolved.name == "ubuntu"


@pytest.mark.parametrize("name", ["Microsoft", "Boot", "microsoft"])
def test_protected_folders_are_refused(tmp_path: Path, name: str) -> None:
    esp = make_esp(tmp_path)
    target = tmp_path / "EFI" / name
    target.mkdir(parents=True, exist_ok=True)
    with pytest.raises(UnsafePathError, match="protected"):
        esp.assert_safe_to_delete(target)


def test_nested_folders_are_refused(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    nested = tmp_path / "EFI" / "ubuntu" / "deeper"
    nested.mkdir(parents=True)
    with pytest.raises(UnsafePathError, match="top-level"):
        esp.assert_safe_to_delete(nested)


def test_paths_outside_the_esp_are_refused(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    with pytest.raises(UnsafePathError, match="outside"):
        esp.assert_safe_to_delete(tmp_path / "Windows")


def test_dry_run_deletion_keeps_the_folder(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    target = tmp_path / "EFI" / "ubuntu"
    assert esp.delete_folder(target, dry_run=True) is False
    assert target.is_dir()
    assert any("DRY-RUN" in message for _level, message in esp.messages)


def test_real_deletion_removes_the_folder(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    target = tmp_path / "EFI" / "ubuntu"
    (target / "grubx64.efi").write_bytes(b"data")
    assert esp.delete_folder(target) is True
    assert not target.exists()


def test_deleting_a_missing_folder_is_a_no_op(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    assert esp.delete_folder(tmp_path / "EFI" / "gone") is False


def test_copy_folder_creates_a_restorable_backup(tmp_path: Path) -> None:
    esp = make_esp(tmp_path)
    source = tmp_path / "EFI" / "ubuntu"
    (source / "grubx64.efi").write_bytes(b"payload")
    destination = tmp_path / "backup" / "efi_files"
    copied = esp.copy_folder(source, destination)
    assert (copied / "grubx64.efi").read_bytes() == b"payload"
