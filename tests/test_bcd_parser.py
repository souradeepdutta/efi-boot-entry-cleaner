"""Tests for bcdedit output parsing and command construction."""

from __future__ import annotations

import pytest

from core.bcd_parser import (
    BcdEditError,
    CommandResult,
    delete_entry,
    export_store,
    parse_bcdedit_output,
)
from core.safety import ProtectedItemError
from tests.conftest import FIRMWARE_ENUM, PROTECTED_IDS


def test_parses_every_firmware_block() -> None:
    entries = parse_bcdedit_output(FIRMWARE_ENUM)
    assert len(entries) == 6
    assert [entry.identifier for entry in entries] == [
        "{fwbootmgr}",
        "{bootmgr}",
        "{memdiag}",
        "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}",
        "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}",
        "{c92e6b44-1f08-4d13-9a67-7de35c118022}",
    ]


def test_extracts_identifier_description_device_and_path() -> None:
    entries = {entry.identifier: entry for entry in parse_bcdedit_output(FIRMWARE_ENUM)}

    ubuntu = entries["{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}"]
    assert ubuntu.description == "Ubuntu"
    assert ubuntu.device == "partition=\\Device\\HarddiskVolume2"
    assert ubuntu.path == "\\EFI\\ubuntu\\grubx64.efi"
    assert ubuntu.label == "Ubuntu"

    bootmgr = entries["{bootmgr}"]
    assert bootmgr.description == "Windows Boot Manager"
    assert bootmgr.path == "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"


def test_multi_line_values_are_joined() -> None:
    entries = {entry.identifier: entry for entry in parse_bcdedit_output(FIRMWARE_ENUM)}
    displayorder = entries["{fwbootmgr}"].values["displayorder"].splitlines()
    assert displayorder == [
        "{bootmgr}",
        "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}",
        "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}",
    ]


def test_missing_description_falls_back_to_block_header() -> None:
    entries = {entry.identifier: entry for entry in parse_bcdedit_output(FIRMWARE_ENUM)}
    assert entries["{fwbootmgr}"].label == "Firmware Boot Manager"


def test_tolerates_crlf_tabs_and_trailing_spaces() -> None:
    text = FIRMWARE_ENUM.replace("\n", "\r\n")
    text = text.replace("identifier              {bootmgr}", "identifier\t\t{bootmgr}   ")
    entries = {entry.identifier: entry for entry in parse_bcdedit_output(text)}
    assert entries["{bootmgr}"].path == "\\EFI\\Microsoft\\Boot\\bootmgfw.efi"


def test_quoted_paths_are_cleaned() -> None:
    text = (
        "Ubuntu\n------\n"
        "identifier              {1111}\n"
        'path                    "\\EFI\\ubuntu\\grubx64.efi"\n'
        "description             Ubuntu\n"
    )
    entry = parse_bcdedit_output(text)[0]
    assert entry.clean_path == "\\EFI\\ubuntu\\grubx64.efi"


def test_empty_output_returns_no_entries() -> None:
    assert parse_bcdedit_output("") == []
    assert parse_bcdedit_output("   \r\n  ") == []


def test_error_output_raises_instead_of_returning_garbage() -> None:
    with pytest.raises(BcdEditError, match="could not be opened"):
        parse_bcdedit_output(
            "The boot configuration data store could not be opened.\r\nAccess is denied.\r\n"
        )


def test_protected_identifiers_can_never_be_deleted() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return CommandResult(args=list(command))

    for identifier in PROTECTED_IDS:
        with pytest.raises(ProtectedItemError):
            delete_entry(identifier, runner=runner)
    assert calls == []


def test_delete_runs_bcdedit_and_returns_result() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return CommandResult(args=list(command), stdout="The operation completed successfully.")

    result = delete_entry("{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}", runner=runner)
    assert result.ok
    assert calls == [["bcdedit", "/delete", "{4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}"]]


def test_delete_retries_with_force_when_needed() -> None:
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        if "/f" in command:
            return CommandResult(args=list(command), stdout="ok")
        return CommandResult(
            args=list(command),
            returncode=1,
            stderr="The specified entry is not valid for the current boot configuration.",
        )

    result = delete_entry("{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}", runner=runner)
    assert result.ok
    assert calls[0][-1] == "{8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}"
    assert calls[1][-1] == "/f"


def test_dry_run_never_invokes_the_runner() -> None:
    def runner(command):  # pragma: no cover - must not be called
        raise AssertionError("runner should not run in dry-run mode")

    result = delete_entry("{c92e6b44-1f08-4d13-9a67-7de35c118022}", dry_run=True, runner=runner)
    assert result.dry_run
    assert not result.stdout.startswith("The operation")


def test_export_store_requires_the_backup_file(tmp_path) -> None:
    def runner(command):
        target = command[command.index("/export") + 1]
        with open(target, "wb") as handle:
            handle.write(b"BCD")
        return CommandResult(args=list(command))

    path = export_store(tmp_path, runner=runner)
    assert path == tmp_path / "bcd_backup"
    assert path.read_bytes() == b"BCD"


def test_export_store_fails_when_bcdedit_fails(tmp_path) -> None:
    def runner(command):
        return CommandResult(args=list(command), returncode=1, stderr="Access is denied.")

    with pytest.raises(BcdEditError):
        export_store(tmp_path, runner=runner)
