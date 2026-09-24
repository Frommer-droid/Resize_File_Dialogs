# -*- coding: utf-8 -*-
r"""
Create an Inno Setup installer from the prepared Resize_File_Dialogs folder.

Expected input:
  <project root>\\Resize_File_Dialogs

Generated setup:
  D:\Desktop\Resize_File_Dialogs_v<VERSION>_Setup.exe
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path


APP_NAME = "Resize_File_Dialogs"
APP_PUBLISHER = "Frommer-droid"
APP_ID = "5D8C3187-3D9C-46BE-BE8D-574BDF49C6F5"
EXE_NAME = f"{APP_NAME}.exe"

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = SCRIPT_DIR / APP_NAME
WORK_DIR = SCRIPT_DIR / "_release_work" / "installer"
def resolve_desktop_dir() -> Path:
    """Use the current user's Windows Desktop, including a relocated Desktop."""
    import ctypes
    import winreg

    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _kind = winreg.QueryValueEx(key, "Desktop")
        path = Path(os.path.expandvars(value)).expanduser()
        if path.is_dir():
            return path
    except (OSError, ValueError):
        pass
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer) == 0:
        return Path(buffer.value)
    return Path.home() / "Desktop"


DESKTOP_DIR = resolve_desktop_dir()

REQUIRED_RELEASE_FILES = (
    EXE_NAME,
    "VERSION",
    "logo.ico",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    os.path.join("AutoHotkey", "AutoHotkey.exe"),
    os.path.join("AutoHotkey", "license.txt"),
)
REQUIRED_RELEASE_DIRS = (
    "_internal",
    "AutoHotkey",
)
ROOT_RUNTIME_NOISE_FILES = {
    ".env",
    "settings.json",
    "ahk_resizer_generator_settings.json",
    "generated_resizer.ahk",
}
ISCC_CANDIDATE_PATHS = (
    os.environ.get("INNO_SETUP_ISCC", ""),
    shutil.which("ISCC.exe") or "",
    r"D:\dev\tools\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
)


def _configure_stdout() -> None:
    if sys.stdout:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def find_iscc_path() -> str:
    for path in ISCC_CANDIDATE_PATHS:
        if path and os.path.isfile(path):
            return path
    return ""


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as exc:
        print(f"Could not remove {path}: {exc}")


def show_popup(message: str, is_error: bool = False) -> None:
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
        width = 620 if is_error else 520
        height = 240 if is_error else 150
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


def validate_release_source(source_dir: Path) -> dict[str, list[str]]:
    missing_files: list[str] = []
    missing_dirs: list[str] = []

    for relative_file in REQUIRED_RELEASE_FILES:
        if not (source_dir / relative_file).is_file():
            missing_files.append(relative_file)

    for relative_dir in REQUIRED_RELEASE_DIRS:
        if not (source_dir / relative_dir).is_dir():
            missing_dirs.append(relative_dir)

    return {"files": missing_files, "directories": missing_dirs}


def format_missing_release_items(missing: dict[str, list[str]]) -> str:
    lines: list[str] = []
    if missing["files"]:
        lines.append("Missing files:")
        lines.extend(f"- {name}" for name in missing["files"])
    if missing["directories"]:
        lines.append("Missing directories:")
        lines.extend(f"- {name}" for name in missing["directories"])
    return "\n".join(lines)


def should_remove_root_file(path: Path) -> bool:
    name_lower = path.name.lower()
    return (
        name_lower in ROOT_RUNTIME_NOISE_FILES
        or name_lower.endswith(".log")
        or ".log." in name_lower
    )


def prepare_release_folder(source: Path, destination: Path) -> bool:
    print(f"--- Preparing installer staging from {source} ---")

    if destination.exists():
        try:
            shutil.rmtree(destination, onerror=remove_readonly)
        except Exception:
            pass

    try:
        shutil.copytree(source, destination)
    except Exception as exc:
        print(f"Copy failed: {exc}")
        return False

    for item in destination.iterdir():
        if item.is_file() and should_remove_root_file(item):
            try:
                item.unlink()
                print(f"Removed runtime file from staging: {item.name}")
            except Exception as exc:
                print(f"Could not remove {item}: {exc}")

    return True


def read_version(version_file: Path) -> str:
    if not version_file.exists():
        return "0.0.0"

    version = version_file.read_text(encoding="utf-8").strip()
    return version or "0.0.0"


def _escape_iss_path(path: str) -> str:
    return path.rstrip("\\")


def _code_section() -> str:
    return r"""
[Code]
const
  DRIVE_FIXED = 3;

function GetDriveType(lpRootPathName: string): Integer;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function FindAlternateFixedDriveRoot: string;
var
  DriveCode: Integer;
  DriveRoot: string;
begin
  Result := '';
  for DriveCode := 65 to 90 do
  begin
    DriveRoot := Chr(DriveCode) + ':\';
    if (DriveRoot = 'C:\') or (DriveRoot = 'D:\') then
    begin
    end
    else if GetDriveType(DriveRoot) = DRIVE_FIXED then
    begin
      Result := DriveRoot;
      exit;
    end;
  end;
end;

function GetDefaultInstallDir(Param: string): string;
var
  AlternateDriveRoot: string;
begin
  if GetDriveType('D:\') = DRIVE_FIXED then
    Result := 'D:\Apps\Resize_File_Dialogs'
  else
  begin
    AlternateDriveRoot := FindAlternateFixedDriveRoot();
    if AlternateDriveRoot <> '' then
      Result := Copy(AlternateDriveRoot, 1, 2) + '\Apps\Resize_File_Dialogs'
    else
      Result := 'C:\Apps\Resize_File_Dialogs';
  end;
end;
"""


def build_iss_content(version: str, icon_line: str) -> str:
    template = r"""; Inno Setup script for Resize_File_Dialogs.
; Generated by 00_CrRel-setup.pyw.

#define MyAppName "__APP_NAME__"
#define MyAppVersion "__VERSION__"
#define MyAppPublisher "__APP_PUBLISHER__"
#define MyAppExeName "__EXE_NAME__"

[Setup]
AppId={{__APP_ID__}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={code:GetDefaultInstallDir}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=no
OutputDir=__OUTPUT_DIR__
OutputBaseFilename={#MyAppName}_v{#MyAppVersion}_Setup
__ICON_LINE__
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
VersionInfoVersion={#MyAppVersion}.0
VersionInfoTextVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
UninstallDisplayIcon={app}\logo.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Dirs]
Name: "{app}"; Permissions: users-modify

[Files]
Source: "__WORK_DIR__\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

__CODE_SECTION__
"""

    return (
        template.replace("__APP_NAME__", APP_NAME)
        .replace("__VERSION__", version)
        .replace("__APP_PUBLISHER__", APP_PUBLISHER)
        .replace("__EXE_NAME__", EXE_NAME)
        .replace("__APP_ID__", APP_ID)
        .replace("__OUTPUT_DIR__", _escape_iss_path(str(DESKTOP_DIR)))
        .replace("__ICON_LINE__", icon_line)
        .replace("__WORK_DIR__", _escape_iss_path(str(WORK_DIR)))
        .replace("__CODE_SECTION__", _code_section())
    )


def main() -> None:
    _configure_stdout()
    print(f"--- Creating {APP_NAME} setup installer ---")

    iscc_path = find_iscc_path()
    if not iscc_path:
        show_popup(
            "Inno Setup compiler was not found.\n"
            "Install Inno Setup 6 or set INNO_SETUP_ISCC to ISCC.exe.",
            is_error=True,
        )
        return

    if not SOURCE_DIR.is_dir():
        show_popup(
            "Portable folder was not found:\n"
            f"{SOURCE_DIR}\n\n"
            "Build the application first with Build_Tools/SpecCompiler.pyw.",
            is_error=True,
        )
        return

    missing = validate_release_source(SOURCE_DIR)
    if missing["files"] or missing["directories"]:
        show_popup(
            "Portable folder is incomplete.\n\n"
            f"{format_missing_release_items(missing)}",
            is_error=True,
        )
        return

    kill_process_smart(EXE_NAME, path_filter=str(SOURCE_DIR))

    if not prepare_release_folder(SOURCE_DIR, WORK_DIR):
        show_popup("Failed to prepare installer staging folder.", is_error=True)
        return

    version = read_version(SOURCE_DIR / "VERSION")
    staged_icon_path = WORK_DIR / "logo.ico"
    icon_line = (
        f"SetupIconFile={_escape_iss_path(str(staged_icon_path))}"
        if staged_icon_path.exists()
        else ""
    )
    iss_content = build_iss_content(version, icon_line)

    iss_path = Path(tempfile.gettempdir()) / "resize_file_dialogs_installer.iss"
    iss_path.write_text(iss_content, encoding="utf-8")

    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    command = [iscc_path, str(iss_path)]
    print("Command:", " ".join(command))

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        show_popup(
            "Inno Setup failed.\n\n"
            f"{exc.stderr or exc.stdout or exc}",
            is_error=True,
        )
        return
    finally:
        try:
            iss_path.unlink()
        except OSError:
            pass
        try:
            shutil.rmtree(WORK_DIR, onerror=remove_readonly)
        except OSError:
            pass

    if result.stdout:
        print(result.stdout)

    setup_name = f"{APP_NAME}_v{version}_Setup.exe"
    show_popup(f"Setup is ready:\n{DESKTOP_DIR / setup_name}")


if __name__ == "__main__":
    main()
