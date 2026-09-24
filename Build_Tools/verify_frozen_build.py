"""Build the app and run a non-interactive fixture with its PyInstaller spec."""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from binary_policy import minimal_build_env, verify_collected_runtime


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = PROJECT_ROOT / "Build_Tools" / "Resize_File_Dialogs.spec"
FIXTURE_NAME = "Resize_File_Dialogs_Smoke"


def main() -> None:
    if Path(sys.prefix).resolve() != (PROJECT_ROOT / ".venv").resolve():
        raise RuntimeError("Run verification with the project .venv Python")
    with tempfile.TemporaryDirectory(prefix="rfd-frozen-smoke-") as temp:
        temp_dir = Path(temp)
        work = temp_dir / "work"
        dist = temp_dir / "dist"
        env = minimal_build_env()
        env["RFD_FROZEN_SMOKE"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--workpath", str(work), "--distpath", str(dist), str(SPEC)],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=300,
        )
        if result.returncode:
            raise RuntimeError(f"Fixture build failed ({result.returncode}):\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")

        toc_path = work / SPEC.stem / "COLLECT-00.toc"
        if not toc_path.is_file():
            raise RuntimeError("Missing COLLECT-00.toc")
        (entries,) = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
        verify_collected_runtime(entries, PROJECT_ROOT)
        print(f"COLLECT verified: {len(entries)} entries")

        exe = dist / FIXTURE_NAME / f"{FIXTURE_NAME}.exe"
        env.pop("RFD_FROZEN_SMOKE", None)
        env["QT_QPA_PLATFORM"] = "offscreen"
        smoke = subprocess.run(
            [str(exe)], cwd=exe.parent, env=env, capture_output=True,
            text=True, timeout=30,
        )
        print(f"Exit: {smoke.returncode}; stdout: {smoke.stdout.strip()}; stderr: {smoke.stderr.strip()}")
        if smoke.returncode or "FROZEN_SMOKE_OK" not in smoke.stdout:
            raise RuntimeError("Frozen import fixture failed")

        full_work = temp_dir / "full_work"
        full_dist = temp_dir / "full_dist"
        full_build = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--workpath", str(full_work), "--distpath", str(full_dist), str(SPEC)],
            cwd=PROJECT_ROOT, env=minimal_build_env(), text=True,
            capture_output=True, timeout=300,
        )
        if full_build.returncode:
            raise RuntimeError(f"Application build failed ({full_build.returncode}):\n{full_build.stdout[-3000:]}\n{full_build.stderr[-3000:]}")
        full_toc = full_work / SPEC.stem / "COLLECT-00.toc"
        if not full_toc.is_file():
            raise RuntimeError("Missing application COLLECT-00.toc")
        (full_entries,) = ast.literal_eval(full_toc.read_text(encoding="utf-8"))
        verify_collected_runtime(full_entries, PROJECT_ROOT)
        full_exe = full_dist / "Resize_File_Dialogs" / "Resize_File_Dialogs.exe"
        if not full_exe.is_file():
            raise RuntimeError("Application EXE is missing from the isolated build")
        import win32api

        expected_version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        actual_version = win32api.GetFileVersionInfo(
            str(full_exe), r"\StringFileInfo\040904B0\FileVersion"
        )
        if actual_version != expected_version:
            raise RuntimeError(f"EXE version {actual_version} does not match VERSION {expected_version}")
        print(f"Application COLLECT verified: {len(full_entries)} entries; EXE size: {full_exe.stat().st_size}")


if __name__ == "__main__":
    main()
