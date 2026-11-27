"""Non-negotiable safety rules.

Every destructive code path in this project funnels through these helpers.
They are intentionally small, pure and easy to unit test: if a guard breaks,
a test fails before an user can break their boot configuration.
"""

from __future__ import annotations

from core.efi_paths import normalize_efi_path

#: BCD identifiers that must never be deleted, even if the user asks for it.
PROTECTED_IDENTIFIERS = frozenset(
    {
        "{bootmgr}",
        "{fwbootmgr}",
        "{current}",
        "{default}",
        "{memdiag}",
    }
)

#: Top-level folders inside ``\EFI\`` that belong to Windows / the firmware.
PROTECTED_EFI_FOLDERS = frozenset({"microsoft", "boot"})

#: Paths that unambiguously belong to the active Windows Boot Manager.
WINDOWS_BOOT_MANAGER_PATHS = frozenset(
    {
        "\\efi\\microsoft\\boot\\bootmgfw.efi",
        "\\efi\\boot\\bootx64.efi",
    }
)


class ProtectedItemError(RuntimeError):
    """Raised when a caller tries to touch a hard-locked item."""


def normalize_identifier(identifier: str | None) -> str:
    """Return a comparable form of a BCD identifier."""
    return (identifier or "").strip().strip('"').casefold()


def is_protected_identifier(identifier: str | None) -> bool:
    """True for well-known identifiers that must never be deleted."""
    return normalize_identifier(identifier) in PROTECTED_IDENTIFIERS


def is_protected_folder_name(name: str | None) -> bool:
    """True for ``Microsoft`` / ``Boot`` (case-insensitive)."""
    cleaned = (name or "").strip().strip("\\/").casefold()
    return cleaned in PROTECTED_EFI_FOLDERS


def is_active_windows_boot_manager(
    identifier: str | None, description: str | None, path: str | None
) -> bool:
    """Detect the live Windows Boot Manager entry.

    ``{bootmgr}`` is the canonical identifier, but a duplicated entry that
    points at ``bootmgfw.efi`` is just as dangerous to remove, so both are
    treated as the active boot manager.
    """
    if normalize_identifier(identifier) == "{bootmgr}":
        return True
    return normalize_efi_path(path or "") in WINDOWS_BOOT_MANAGER_PATHS
