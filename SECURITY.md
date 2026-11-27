# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | Yes       |

## Reporting a vulnerability

Please **do not open a public issue** for anything that could delete data or
bypass the safety guardrails. Use GitHub's private vulnerability reporting:

<https://github.com/souradeepdutta/efi-boot-entry-cleaner/security/advisories/new>

Include the app version, Windows build, reproduction steps, and what you
expected the safety layer to do.

## What counts as a security issue

- A protected item (`{bootmgr}`, `{fwbootmgr}`, `{current}`, `{default}`,
  `{memdiag}`, the active Windows Boot Manager, `\EFI\Microsoft`, `\EFI\Boot`)
  becoming selectable or deletable.
- Deleting anything outside `<ESP>:\EFI\<folder>`.
- Deleting before the backup completes, or deleting without a backup.
- Dry-run mode modifying the system.
- Command injection through boot entry descriptions, paths or folder names.

## Threat model and design notes

- The app runs elevated by design. It launches `bcdedit` and `mountvol` with
  argument lists (never a shell string), validates paths before deleting, and
  does not use the network.
- No telemetry, accounts or analytics are included.
- Backups are written to `%LOCALAPPDATA%\EFIBootCleaner\backups`. They are not
  encrypted and contain copies of EFI binaries; treat them as system data.
- The ESP is mounted only for the lifetime of the app and unmounted on exit,
  crash (`atexit`) or `aboutToQuit`. If the app is killed with Task Manager
  during a mount, run `mountvol <letter>: /D` manually.

## If something went wrong

Every real removal creates a backup first:

1. Open the backup folder from the toolbar (`Open Backups`).
2. Re-import the BCD store with `bcdedit /import <backup>\bcd_backup`.
3. Copy the folders from `<backup>\efi_files` back into `<ESP>:\EFI`.
4. If the ESP is not mounted, use `mountvol Z: /S` (pick a free letter).

The app never deletes the backup folder.
