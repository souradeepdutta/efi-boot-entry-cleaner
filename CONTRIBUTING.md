# Contributing

Thanks for taking the time to improve EFI & Boot Entry Cleaner. This is a small
tool that runs with Administrator rights and edits boot configuration data, so
correctness matters more than cleverness.

## Development setup

```powershell
git clone https://github.com/souradeepdutta/efi-boot-entry-cleaner.git
cd efi-boot-entry-cleaner

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

You do **not** need an EFI System Partition or Administrator rights to work on
the UI:

```powershell
python main.py --demo
```

`--demo` uses simulated boot entries and folders, never mounts anything, and is
also what the screenshots are generated from.

## Running the tests

```powershell
python -m pytest -q
python -m ruff check .
```

The test suite is deliberately dependency-light: it mocks `bcdedit` output and
the file system, so it runs in CI without elevation.

## Safety rules for changes

- Never remove or weaken a check in `core/safety.py`. Protected identifiers,
  `\EFI\Microsoft`, `\EFI\Boot` and the active Windows Boot Manager are hard
  locked by design.
- Every destructive path must go through `AppController.remove`, which backs up
  first, then deletes. Do not call `bcdedit /delete` or `shutil.rmtree` from the
  UI.
- A new protected identifier or folder needs a unit test that proves it can
  never be flagged as deletable.
- Deletions must stay limited to direct children of `<ESP>:\EFI`.
- Dry-run mode must never write to the system or create a backup.

## Code style

- Python 3.11+, type hints on public functions, `from __future__ import annotations`.
- Ruff is the formatter/linter (`line-length = 100`).
- Keep modules focused and UI-free where possible; `core/` must not import Qt.
- Prefer clear names and small functions over comments that restate the code.

## Commit messages

Short imperative subject, optional body explaining the *why*:

```
Add Fedora shim detection to the correlator

bcdedit lists shimx64.efi for Secure Boot setups; matching the first
folder segment keeps those entries linked instead of orphaned.
```

## Pull requests

- Describe the user-visible change and how you tested it.
- Add or update tests for logic changes.
- Include a screenshot for UI changes.
- Confirm you have not touched the safety guardrails unless the PR is
  specifically about them.

## Reporting bugs

Open an issue with the bug report form. Include the Windows build, the app
version, and any relevant lines from the in-app console or
`%LOCALAPPDATA%\EFIBootCleaner\logs`. Do not attach backup `.efi` files or your
BCD store publicly.
