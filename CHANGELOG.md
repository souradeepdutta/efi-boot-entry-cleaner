# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-11-27

### Added

- Dark Windows 11-style PySide6 interface with a colour-coded status table
  (`Linked`, `Orphaned Entry`, `Orphaned Folder`, `Protected`).
- Firmware boot entry parsing via `bcdedit /enum firmware`, including
  multi-line values and varying whitespace.
- ESP scanning with temporary `mountvol` mounting on a free drive letter
  (`Z:` down to `M:`) and guaranteed unmount on exit.
- Correlation of BCD paths to `\EFI\<folder>` and per-folder size calculation.
- One-click removal of selected boot entries and their ESP folders.
- Automatic timestamped backup: BCD export, firmware snapshot, and copies of
  every folder before it is deleted.
- Dry-run mode that logs the exact commands without changing anything.
- Confirmation dialog listing identifiers, paths, folder sizes and the backup
  destination.
- Hard-locked safety rules for `{bootmgr}`, `{fwbootmgr}`, `{current}`,
  `{default}`, `{memdiag}`, the active Windows Boot Manager,
  `\EFI\Microsoft` and `\EFI\Boot`.
- Shared-folder protection: a folder still used by an unselected boot entry is
  kept and reported.
- Live console with colour-coded command, stdout, stderr and status output.
- `build.ps1` producing a single-file, UAC-elevated Windows executable.
- Unit tests covering BCD parsing, correlation, safety rules, ESP deletion
  guards and the backup/removal sequence.
- Demo mode (`python main.py --demo`) for working on the UI without an ESP.
