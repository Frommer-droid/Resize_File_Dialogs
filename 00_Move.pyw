# -*- coding: utf-8 -*-
r"""
Update the portable Resize_File_Dialogs folder.

The script copies the already prepared <project root>\\Resize_File_Dialogs folder to
D:\Portable_soft\Resize_File_Dialogs. Resource preparation is handled by Build_Tools.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path


APP_NAME = "Resize_File_Dialogs"
EXE_NAME = f"{APP_NAME}.exe"
DESTINATION_PARENT = Path(r"D:\Portable_soft")

REQUIRED_SOURCE_FILES = (
    EXE_NAME,
    "VERSION",
    "logo.ico",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    os.path.join("AutoHotkey", "AutoHotkey.exe"),
    os.path.join("AutoHotkey", "license.txt"),
)
REQUIRED_SOURCE_DIRS = (
    "_internal",
    "AutoHotkey",
)
PRESERVED_RUNTIME_FILES = (
    "settings.json",
    "ahk_resizer_generator_settings.json",
    "generated_resizer.ahk",
)


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as exc:
        print(f"Could not remove {path}: {exc}")


def show_popup(message: str = "Done", is_error: bool = False) -> None:
    try:
        root = tk.Tk()
        root.attributes("-topmost", True)

        if is_error:
            root.title("Error")
            bg_color = "#ffcccc"
        else:
            root.overrideredirect(True)
            bg_color = "#e6ffe6"

        root.configure(bg=bg_color)
        width = 560 if is_error else 460
        height = 220 if is_error else 130
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")

        label = tk.Label(
            root,
            text=message,
            font=("Arial", 11),
            bg=bg_color,
            wraplength=width - 30,
        )
        label.pack(expand=True, padx=20, pady=18)

        if is_error:
            button = tk.Button(root, text="Close", command=root.destroy)
            button.pack(pady=(0, 14))
        else:
            root.after(3500, root.destroy)
            root.bind("<Button-1>", lambda _event: root.destroy())
            label.bind("<Button-1>", lambda _event: root.destroy())

        root.mainloop()
    except Exception:
        print(message)


def kill_process_smart(process_name: str, path_filter: str | None = None) -> None:
    print(f"--- Checking process: {process_name} ---")
    process_name_no_ext = process_name.removesuffix(".exe")

    for _attempt in range(3):
        if path_filter:
            escaped_path = path_filter.replace("'", "''")
            escaped_name = process_name_no_ext.replace("'", "''")
            ps_command = (
                f"$name = '{escaped_name}'; "
                f"$target = [System.IO.Path]::GetFullPath('{escaped_path}'); "
                "if (-not $target.EndsWith([System.IO.Path]::DirectorySeparatorChar)) "
                "{ $target += [System.IO.Path]::DirectorySeparatorChar }; "
                "Get-Process -Name $name -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Path -and "
                "([System.IO.Path]::GetFullPath($_.Path)).StartsWith($target, "
                "[System.StringComparison]::OrdinalIgnoreCase) } | "
                "Stop-Process -Force"
            )
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps_command,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        time.sleep(0.5)


def _resolve_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def ensure_target_is_safe(target_path: Path) -> None:
    parent = _resolve_path(DESTINATION_PARENT)
    target = _resolve_path(target_path)
    parent_with_sep = parent if parent.endswith(os.sep) else parent + os.sep

    if target == parent or not target.startswith(parent_with_sep):
        raise ValueError(f"Unsafe target path: {target_path}")


def validate_source_folder(source_folder: Path) -> dict[str, list[str]]:
    missing_files: list[str] = []
    missing_dirs: list[str] = []

    for relative_file in REQUIRED_SOURCE_FILES:
        if not (source_folder / relative_file).is_file():
            missing_files.append(relative_file)

    for relative_dir in REQUIRED_SOURCE_DIRS:
        if not (source_folder / relative_dir).is_dir():
            missing_dirs.append(relative_dir)

    return {"files": missing_files, "directories": missing_dirs}


def format_missing_items(missing: dict[str, list[str]]) -> str:
    lines: list[str] = []
    if missing["files"]:
        lines.append("Missing files:")
        lines.extend(f"- {name}" for name in missing["files"])
    if missing["directories"]:
        lines.append("Missing directories:")
        lines.extend(f"- {name}" for name in missing["directories"])
    return "\n".join(lines)


def remove_existing_folder(target_folder: Path) -> bool:
    if not target_folder.exists():
        print(f"Target folder does not exist, skipping removal: {target_folder}")
        return True

    print(f"Removing old target folder: {target_folder}")
    for attempt in range(1, 4):
        try:
            shutil.rmtree(target_folder, onerror=remove_readonly)
        except OSError as exc:
            print(f"Removal attempt {attempt}/3 failed: {exc}")
        if not target_folder.exists():
            return True
        print(f"Removal attempt {attempt}/3 left target in place.")
        time.sleep(1)

    return not target_folder.exists()


def copy_release_folder(source_folder: Path, target_folder: Path) -> None:
    shutil.copytree(
        source_folder,
        target_folder,
        dirs_exist_ok=target_folder.exists(),
    )


def preserve_runtime_files(source_folder: Path, target_folder: Path) -> Path | None:
    if not target_folder.is_dir():
        return None

    backup_dir: Path | None = None
    for relative_file in PRESERVED_RUNTIME_FILES:
        target_file = target_folder / relative_file
        if not target_file.is_file():
            continue

        if backup_dir is None:
            backup_dir = Path(tempfile.mkdtemp(prefix=f"{APP_NAME}_portable_backup_"))

        shutil.copy2(target_file, backup_dir / target_file.name)
        print(f"[INFO] Preserved runtime file: {target_file.name}")

    return backup_dir


def restore_runtime_files(backup_dir: Path | None, target_folder: Path) -> None:
    if not backup_dir or not backup_dir.is_dir():
        return

    for backup_file in backup_dir.iterdir():
        target_file = target_folder / backup_file.name
        shutil.copy2(backup_file, target_file)
        print(f"[OK] Restored preserved runtime file: {target_file.name}")


def cleanup_backup_dir(backup_dir: Path | None) -> None:
    if backup_dir and backup_dir.is_dir():
        shutil.rmtree(backup_dir, ignore_errors=True)


def manage_folders() -> None:
    base_dir = Path(__file__).resolve().parent
    source_folder = base_dir / APP_NAME
    target_folder = DESTINATION_PARENT / APP_NAME

    print(f"Source: {source_folder}")
    print(f"Target: {target_folder}")

    if not source_folder.is_dir():
        show_popup(
            "Portable source folder was not found:\n"
            f"{source_folder}\n\n"
            "Build the application first with Build_Tools/SpecCompiler.pyw.",
            is_error=True,
        )
        return

    missing = validate_source_folder(source_folder)
    if missing["files"] or missing["directories"]:
        show_popup(
            "Portable source folder is incomplete.\n\n"
            f"{format_missing_items(missing)}",
            is_error=True,
        )
        return

    try:
        ensure_target_is_safe(target_folder)
    except ValueError as exc:
        show_popup(str(exc), is_error=True)
        return

    DESTINATION_PARENT.mkdir(parents=True, exist_ok=True)

    kill_process_smart(EXE_NAME, path_filter=str(target_folder))
    time.sleep(1)

    try:
        preserved_runtime_dir = preserve_runtime_files(source_folder, target_folder)
    except OSError as exc:
        show_popup(
            "Could not preserve existing portable runtime files:\n"
            f"{exc}\n\n"
            "Portable folder was not changed.",
            is_error=True,
        )
        return

    if not remove_existing_folder(target_folder):
        print(
            "[WARN] Could not fully remove the old portable folder. "
            "Copying the prepared build over remaining locked files."
        )

    try:
        print(f"Copying {source_folder} -> {target_folder}")
        copy_release_folder(source_folder, target_folder)
        restore_runtime_files(preserved_runtime_dir, target_folder)
    except OSError as exc:
        message = f"Copy failed:\n{exc}"
        if preserved_runtime_dir:
            message += f"\n\nPreserved runtime backup:\n{preserved_runtime_dir}"
        show_popup(message, is_error=True)
        return
    finally:
        cleanup_backup_dir(preserved_runtime_dir)

    show_popup(f"Portable folder updated:\n{target_folder}")


if __name__ == "__main__":
    manage_folders()
