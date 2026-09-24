# -*- coding: utf-8 -*-
"""
POST-BUILD CLEANUP SCRIPT
Копирует ключевые файлы и убирает временные директории.
"""

import os
import shutil
import sys
import ast
from pathlib import Path

from binary_policy import verify_collected_runtime

# Force UTF-8 for stdout
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

# ========================================================
# 🔧 CONFIGURATION SECTION
# ========================================================
# Имя папки в dist (должно совпадать с именем в .spec файле)
APP_NAME = "Resize_File_Dialogs"

# Список файлов для копирования в финальную папку приложения
# (исходный_путь_от_корня, имя_файла_в_папке_приложения)
FILES_TO_COPY = [
    ("VERSION", "VERSION"),
    ("LICENSE", "LICENSE"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    ("logo.ico", "logo.ico"),
    ("AutoHotKey", "AutoHotkey"),
]

# ========================================================
def safe_copy(src: str, dst: str, label: str) -> None:
    if os.path.exists(src):
        try:
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            print(f"[OK] Copied {label}")
        except Exception as e:
            print(f"[ERROR] Failed to copy {label}: {e}")
    else:
        print(f"[SKIP] {label} not found at {src}")


def copy_root_json_files(project_root: str, final_app_dir: str) -> None:
    """Копирует все .json файлы из корня проекта в папку приложения."""
    json_files = [
        name for name in os.listdir(project_root)
        if name.lower().endswith(".json") and os.path.isfile(os.path.join(project_root, name))
    ]
    if not json_files:
        print("[INFO] JSON-файлы в корне проекта не найдены.")
        return

    for file_name in json_files:
        src = os.path.join(project_root, file_name)
        dst = os.path.join(final_app_dir, file_name)
        safe_copy(src, dst, file_name)


def main() -> None:
    print("\n" + "=" * 60)
    print(f"POST-BUILD CLEANUP: {APP_NAME}")
    print("=" * 60)

    script_dir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    dist_app_dir = os.path.join(script_dir, "dist", APP_NAME)
    final_app_dir = os.path.join(project_root, APP_NAME)

    # Keep work files until the native origins and Qt runtime have been checked.
    toc_path = Path(script_dir) / "build" / "Resize_File_Dialogs" / "COLLECT-00.toc"
    if not toc_path.is_file():
        raise RuntimeError(f"Missing build provenance record: {toc_path}")
    (entries,) = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    verify_collected_runtime(entries, Path(project_root))
    print(f"[OK] COLLECT provenance checked: {len(entries)} entries")

    # 1. Переносим собранное приложение
    if os.path.exists(dist_app_dir):
        try:
            if os.path.exists(final_app_dir):
                shutil.rmtree(final_app_dir)
                print(f"[OK] Removed old {APP_NAME}/")
            shutil.move(dist_app_dir, final_app_dir)
            print(f"[OK] Moved to: {final_app_dir}")
        except Exception as e:
            print(f"[ERROR] Failed to move: {e}")
            return
    else:
        print(f"[ERROR] dist/{APP_NAME} not found! Build might have failed.")
        return

    # 2. Удаляем временные директории
    print("\n[CLEANUP] Removing temporary directories...")
    temp_folders = [
        os.path.join(script_dir, "build"),
        os.path.join(script_dir, "dist"),
        os.path.join(script_dir, "__pycache__"),
        os.path.join(project_root, "dist"),
        os.path.join(project_root, "build"),
        os.path.join(project_root, "__pycache__"),
        os.path.join(final_app_dir, "__pycache__"),
    ]

    for folder_path in temp_folders:
        if folder_path and os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
                print(f"[OK] Removed {folder_path}")
            except Exception as e:
                print(f"[ERROR] Failed to remove {folder_path}: {e}")

    # 3. Копируем дополнительные файлы
    print("\n[COPY] Copying additional files...")
    for src_rel, dst_rel in FILES_TO_COPY:
        src = os.path.join(project_root, src_rel)
        dst = os.path.join(final_app_dir, dst_rel)
        safe_copy(src, dst, src_rel)

    # 4. Всегда копируем все JSON-файлы из корня проекта
    print("\n[COPY] Copying root JSON files...")
    copy_root_json_files(project_root, final_app_dir)

    print("\n" + "=" * 60)
    print(f"DONE! App location: {final_app_dir}")
    print("=" * 60)

    # 5. Проверяем готовый exe, но не запускаем его:
    # release-скрипты не должны блокировать файлы сборки.
    exe_path = os.path.join(final_app_dir, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        print(f"\n[OK] Executable ready: {exe_path}")
    else:
        print(f"[ERROR] Executable not found: {exe_path}")


if __name__ == "__main__":
    main()
