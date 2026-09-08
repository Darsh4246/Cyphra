"""Windows file association and icon registry for .cyphra and .cyphra-vault files."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_preferred_icon_path() -> Path:
    """Find the best available .ico icon file."""
    candidates = [
        Path(r"E:\Darsh\Cyphra\logo.ico"),
        Path(__file__).resolve().parent / "assets" / "logo.ico",
        Path(__file__).resolve().parent / "assets" / "cyphra_icon.ico",
        Path(sys.prefix) / "logo.ico",
        Path(__file__).resolve().parent.parent / "logo.ico",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()
    return candidates[0]


def register_file_associations() -> tuple[bool, str]:
    """Register .cyphra and .cyphra-vault extensions with Cyphra icon and handler in Windows HKCU."""
    if sys.platform != "win32":
        return False, "File association is only applicable to Windows."

    try:
        import ctypes
        import winreg

        ico_path = get_preferred_icon_path()
        if not ico_path.exists():
            return False, f"Icon file not found at {ico_path}"

        # Choose pythonw.exe to launch without console window if available
        py_exe = sys.executable
        pyw_exe = Path(sys.executable).with_name("pythonw.exe")
        launch_exe = str(pyw_exe) if pyw_exe.exists() else str(py_exe)
        
        main_pkg = "cyphra_gui.main"
        open_cmd = f'"{launch_exe}" -m {main_pkg} "%1"'

        associations = [
            (
                ".cyphra",
                "Cyphra.EncryptedContainer",
                "Cyphra Encrypted Container",
                f'"{ico_path}",0',
            ),
            (
                ".cyphra-vault",
                "Cyphra.VaultArchive",
                "Cyphra Encrypted Vault Archive",
                f'"{ico_path}",0',
            ),
        ]

        hkcu = winreg.HKEY_CURRENT_USER
        base_path = r"Software\Classes"

        for ext, prog_id, desc, icon_entry in associations:
            # 1. Register extension -> ProgID
            with winreg.CreateKey(hkcu, f"{base_path}\\{ext}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)
                winreg.SetValueEx(key, "Content Type", 0, winreg.REG_SZ, "application/x-cyphra")

            # 2. Register ProgID metadata, icon, and open command
            with winreg.CreateKey(hkcu, f"{base_path}\\{prog_id}") as prog_key:
                winreg.SetValueEx(prog_key, "", 0, winreg.REG_SZ, desc)
                winreg.SetValueEx(prog_key, "FriendlyTypeName", 0, winreg.REG_SZ, desc)

            # DefaultIcon
            with winreg.CreateKey(hkcu, f"{base_path}\\{prog_id}\\DefaultIcon") as icon_key:
                winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, icon_entry)

            # shell\open\command
            with winreg.CreateKey(hkcu, f"{base_path}\\{prog_id}\\shell\\open\\command") as cmd_key:
                winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, open_cmd)

            with winreg.CreateKey(hkcu, f"{base_path}\\{prog_id}\\shell\\open") as open_key:
                winreg.SetValueEx(open_key, "FriendlyAppName", 0, winreg.REG_SZ, "Cyphra Vault")

        # Notify Windows Shell that file associations and icon cache changed
        try:
            SHCNE_ASSOCCHANGED = 0x08000000
            SHCNF_IDLIST = 0x0000
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        except Exception:
            pass

        return True, f"Successfully associated .cyphra and .cyphra-vault with icon: {ico_path.name}"

    except Exception as error:  # noqa: BLE001
        return False, f"Failed to register file associations: {error}"
