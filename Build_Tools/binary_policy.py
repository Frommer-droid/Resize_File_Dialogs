"""Fail-closed PyInstaller binary provenance and Qt runtime policy."""

from __future__ import annotations

import os
import sys
import ctypes
from pathlib import Path


RUNTIME_NAMES = (
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)


def _system_root() -> Path:
    value = ctypes.create_unicode_buffer(260)
    if not ctypes.windll.kernel32.GetWindowsDirectoryW(value, len(value)):
        raise RuntimeError("Cannot resolve the Windows directory")
    return Path(value.value)


def trusted_roots(project_root: Path) -> tuple[Path, ...]:
    roots = (project_root, Path(sys.prefix), Path(sys.base_prefix), _system_root())
    return tuple(root.resolve() for root in roots)


def minimal_build_env() -> dict[str, str]:
    """Keep inherited toolchain directories off the native DLL search path."""
    env = os.environ.copy()
    system_root = _system_root()
    env["SystemRoot"] = str(system_root)
    qt_dir = Path(sys.prefix) / "Lib" / "site-packages" / "PySide6"
    env["PATH"] = os.pathsep.join(str(path) for path in (
        Path(sys.prefix) / "Scripts",
        Path(sys.base_prefix),
        Path(sys.base_prefix) / "DLLs",
        qt_dir,
        system_root / "System32",
    ))
    return env


def validate_binaries(binaries, project_root: Path) -> None:
    """Reject missing binaries and every source outside the trusted roots."""
    roots = trusted_roots(project_root)
    for destination, source, _typecode in binaries:
        path = Path(source).resolve()
        if not path.is_file() or not any(path.is_relative_to(root) for root in roots):
            raise RuntimeError(f"Untrusted PyInstaller binary: {destination} <- {path}")


def _file_version(path: Path) -> tuple[int, int, int, int]:
    import win32api

    info = win32api.GetFileVersionInfo(str(path), "\\")
    ms, ls = info["FileVersionMS"], info["FileVersionLS"]
    return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF


def prefer_qt_runtime(binaries, project_root: Path):
    """Collect the complete MSVC runtime set from the selected PySide6 installation."""
    validate_binaries(binaries, project_root)
    qt_dir = Path(sys.prefix) / "Lib" / "site-packages" / "PySide6"
    runtime_paths = {name: qt_dir / name for name in RUNTIME_NAMES}
    if any(not path.is_file() for path in runtime_paths.values()):
        raise RuntimeError("The PySide6 MSVC runtime set is incomplete")
    if len({_file_version(path) for path in runtime_paths.values()}) != 1:
        raise RuntimeError("The PySide6 MSVC runtime set has inconsistent versions")

    kept = [entry for entry in binaries if Path(entry[0]).name.lower() not in RUNTIME_NAMES]
    kept.extend((name, str(path), "BINARY") for name, path in runtime_paths.items())
    validate_binaries(kept, project_root)
    return kept


def verify_collected_runtime(binaries, project_root: Path) -> None:
    """Validate COLLECT-00.toc before its build directory is removed."""
    binaries = [entry for entry in binaries if entry[2] in {"BINARY", "EXTENSION"}]
    validate_binaries(binaries, project_root)
    qt_dir = (Path(sys.prefix) / "Lib" / "site-packages" / "PySide6").resolve()
    runtime = {
        Path(dest).name.lower(): Path(source).resolve()
        for dest, source, _typecode in binaries
        if Path(dest).name.lower() in RUNTIME_NAMES
    }
    if set(runtime) != set(RUNTIME_NAMES):
        raise RuntimeError("COLLECT is missing a PySide6 MSVC runtime DLL")
    if any(path.parent != qt_dir for path in runtime.values()):
        raise RuntimeError("COLLECT contains an MSVC runtime outside PySide6")
    if len({_file_version(path) for path in runtime.values()}) != 1:
        raise RuntimeError("COLLECT has inconsistent MSVC runtime versions")
