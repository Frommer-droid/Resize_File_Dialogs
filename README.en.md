<p align="center"><img src="logo.ico" alt="Resize_File_Dialogs icon" width="96"></p>
<h1 align="center">Resize_File_Dialogs</h1>
<p align="center">Automatically resize and position selected windows on Windows.</p>
<p align="center"><a href="README.md">Русский</a> · <a href="https://github.com/Frommer-droid/Resize_File_Dialogs/releases/latest">Latest release</a></p>

Resize_File_Dialogs stores window rules, generates an AutoHotkey v2 script, and
runs it from a PySide6 interface. It is useful for file dialogs and other
windows that should open at a predictable size and position.

## Features

- Match windows by class and title fragments, then set their size and position.
- Temporarily disable rules or individual title matches.
- Exclude windows by title and inspect windows to find their class and title.
- Import and export rules as JSON.
- Pause or resume resizing from the system tray.
- Start at Windows sign-in and optionally start minimized to the tray.
- Adjust interface scale for the display and DPI.

## Quick start

### Install the application

1. Download the installer from the [latest release](https://github.com/Frommer-droid/Resize_File_Dialogs/releases/latest) and install it.
2. Run `Resize_File_Dialogs.exe` as administrator.
3. On the Rules tab, select `Добавить` (Add).
4. Enter a rule name, window class, title fragments, size, and position. The
   built-in Spy can fill in the window class and title.
5. Save the rule and select `Старт` (Start).

The generated script checks open windows and applies the first matching rule.
Windows on the exclusion list are left unchanged. A clean installation starts
with no rules or exclusions.

### Run from source

Use Windows 10 or 11 and Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe .\Resize_File_Dialogs.pyw
```

The application uses PySide6 and pywin32. The bundled AutoHotkey executable is
used to apply window rules. Administrative rights are required for full
functionality and the Windows sign-in task.

## Development

Run the existing checks with the project environment:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe .\Build_Tools\verify_frozen_build.py
```

The frozen check builds the application and a separate fixture without UAC,
checks both `COLLECT-00.toc` records, and runs GUI and native imports in the
fixture without opening the main application. See [DEVELOPER.md](DEVELOPER.md) for the application structure,
settings, build, and release process. Changes are described in
[RELEASE_NOTES.md](RELEASE_NOTES.md).

## Limitations

- The application runs on Windows only.
- Window matching by class and title can affect additional windows if a rule
  uses broad title fragments.
- Window movement is performed by AutoHotkey, not by a background Python loop.

## License

The project's own code is available under the [MIT License](LICENSE).
Bundled AutoHotkey and other dependencies retain their own license terms; see
the [third-party notices](THIRD_PARTY_NOTICES.md).
