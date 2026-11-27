"""Shared fixtures for the unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Captured shape of `bcdedit /enum firmware` on a dual-boot Windows 11 machine
# (Windows Boot Manager, Ubuntu, Fedora, cachyos). Not produced by the tests.
FIRMWARE_ENUM = r"""
Firmware Boot Manager
---------------------
identifier              {fwbootmgr}
displayorder            {bootmgr}
                        {4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}
                        {8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}
timeout                 1

Windows Boot Manager
--------------------
identifier              {bootmgr}
device                  partition=\Device\HarddiskVolume1
path                    \EFI\Microsoft\Boot\bootmgfw.efi
description             Windows Boot Manager
locale                  en-US
inherit                 {globalsettings}
default                 {current}
resumeobject            {9c1e4b5a-1111-2222-3333-444455556666}
displayorder            {current}
toolsdisplayorder       {memdiag}
timeout                 30

Windows Memory Diagnostic
-------------------------
identifier              {memdiag}
device                  partition=\Device\HarddiskVolume1
path                    \EFI\Microsoft\Boot\memtest.efi
description             Windows Memory Diagnostic
locale                  en-US

Ubuntu
------
identifier              {4f3c1a7e-9b52-11ef-8d31-806e6f6e6963}
device                  partition=\Device\HarddiskVolume2
path                    \EFI\ubuntu\grubx64.efi
description             Ubuntu

Fedora Linux
------------
identifier              {8a1d5c20-4e77-4b9a-b4d4-2ac70f1d9e51}
device                  partition=\Device\HarddiskVolume3
path                    \EFI\fedora\shimx64.efi
description             Fedora Linux

cachyos
-------
identifier              {c92e6b44-1f08-4d13-9a67-7de35c118022}
device                  partition=\Device\HarddiskVolume4
path                    \EFI\cachyos\grubx64.efi
description             cachyos
""".lstrip("\n")

PROTECTED_IDS = ("{bootmgr}", "{fwbootmgr}", "{current}", "{default}", "{memdiag}")
