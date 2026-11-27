## Summary

<!-- What does this PR change, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation / assets
- [ ] Safety or backup behaviour (requires extra review)

## How was it tested?

- [ ] `python -m pytest -q`
- [ ] `python -m ruff check .`
- [ ] Ran `python main.py --demo`
- [ ] Ran the packaged `.exe` as Administrator

## Safety checklist

- [ ] Protected identifiers and folders are still hard-locked.
- [ ] Deletions are still limited to `<ESP>:\EFI\<folder>`.
- [ ] A backup is still created before every real deletion.
- [ ] Dry-run mode still changes nothing.
- [ ] New logic is covered by a test.

## Screenshots

<!-- Required for UI changes. -->
