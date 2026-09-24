import sys
import os
import json
import time
import subprocess
import ctypes
import tempfile
import traceback
from copy import deepcopy
from datetime import datetime
from typing import Dict, Any, List, Optional
from xml.sax.saxutils import escape as xml_escape


def _windowed_python_executable(executable: str) -> str:
    """Return pythonw.exe next to python.exe for Windows GUI relaunches."""
    if sys.platform != "win32":
        return executable
    if os.path.basename(executable).lower() != "python.exe":
        return executable

    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return executable


def _bootstrap_project_venv() -> None:
    """Rerun source launches through the project venv when it is available."""
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("RESIZE_FILE_DIALOGS_SKIP_VENV_BOOTSTRAP") == "1":
        return

    project_root = os.path.dirname(os.path.abspath(__file__))
    scripts_dir = os.path.join(project_root, ".venv", "Scripts")
    venv_python = os.path.join(scripts_dir, "pythonw.exe")
    if not os.path.exists(venv_python):
        venv_python = os.path.join(scripts_dir, "python.exe")
    if not os.path.exists(venv_python):
        return

    current_executable = os.path.normcase(os.path.realpath(sys.executable))
    target_executable = os.path.normcase(os.path.realpath(venv_python))
    if current_executable == target_executable:
        return

    os.execv(venv_python, [venv_python, os.path.abspath(__file__), *sys.argv[1:]])


_bootstrap_project_venv()

from app.version import __version__  # noqa: E402 - venv bootstrap must run before project imports.
from app.ui_scale import (  # noqa: E402
    UIScaleState,
    legacy_percent_to_delta_percent,
    normalize_ui_scale_delta_percent,
    normalize_ui_scale_mode,
    normalize_ui_scale_percent,
    resolve_ui_scale_from_screen,
    scale_point_size,
    scale_px,
)
from app.ui_scale_runtime import apply_widget_tree_scale  # noqa: E402
from app.ui.theme import THEME_COLORS  # noqa: E402

# Класс-заглушка для работы без pywin32, определен на уровне модуля.
class Dummy:
    """Класс-заглушка, который имитирует отсутствующую библиотеку, чтобы приложение не падало."""
    def __getattr__(self, _):
        if _ == 'GetAsyncKeyState':
            return lambda _: 0
        return lambda *args, **kwargs: None

# Попытка импорта pywin32 для специфичных функций Windows
try:
    import win32api
    import win32con
    import win32gui
except ImportError:
    # Если импорт не удался, присваиваем переменным экземпляры глобально определенной заглушки.
    win32api = win32con = win32gui = Dummy()
    print("ПРЕДУПРЕЖДЕНИЕ: Библиотека pywin32 не найдена. Инспектор окон и проверка прав администратора будут отключены.")
    print("Для полной функциональности, пожалуйста, установите ее: pip install pywin32")


try:
    from PySide6.QtCore import Qt, QTimer, QByteArray
    from PySide6.QtGui import QIcon, QAction, QFont, QBrush, QColor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QListWidget, QLineEdit, QSplitter, QMessageBox, QFileDialog,
        QStatusBar, QFormLayout, QSpinBox, QComboBox, QTextEdit,
        QTabWidget, QLabel, QListWidgetItem, QGroupBox, QSystemTrayIcon, QMenu,
        QCheckBox, QSizePolicy
    )
except ModuleNotFoundError as exc:
    if exc.name == "PySide6":
        message = (
            "PySide6 не найден в текущем Python.\n\n"
            "Запускайте исходники через проектное окружение:\n"
            r".\.venv\Scripts\pythonw.exe .\Resize_File_Dialogs.pyw"
            "\n\nЕсли .venv отсутствует, создайте его и установите зависимости:\n"
            r"py -3.12 -m venv .venv"
            "\n"
            r".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
        )
        print(message)
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "Resize_File_Dialogs", 0x10)
        except Exception:
            pass
        sys.exit(1)
    raise


def app_base_path() -> str:
    """
    Возвращает папку приложения:
    - в frozen-режиме: папка рядом с .exe;
    - в dev-режиме: папка текущего скрипта.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_BASE_PATH = app_base_path()
ADMIN_RELAUNCH_ARG = "--resize-file-dialogs-admin-relaunch"


def resource_path(relative_path: str) -> str:
    """Строит абсолютный путь к ресурсу рядом с приложением."""
    return os.path.join(APP_BASE_PATH, relative_path)


def is_running_as_admin() -> bool:
    """Возвращает True, если процесс запущен с административным токеном."""
    if sys.platform != "win32":
        return True

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _show_admin_required_message(details: str = "") -> None:
    message = (
        "Resize_File_Dialogs должен быть запущен от имени администратора.\n\n"
        "Проверьте, что текущая учетная запись входит в группу Администраторы. "
        "Если UAC отключен политикой, Windows может не выполнить elevation для "
        "обычной учетной записи."
    )
    if details:
        message += f"\n\nДетали: {details}"

    try:
        ctypes.windll.user32.MessageBoxW(None, message, "Resize_File_Dialogs", 0x10)
    except Exception:
        print(message)


def _strip_admin_relaunch_arg() -> bool:
    attempted = ADMIN_RELAUNCH_ARG in sys.argv
    if attempted:
        sys.argv[:] = [arg for arg in sys.argv if arg != ADMIN_RELAUNCH_ARG]
    return attempted


def ensure_admin_or_exit() -> None:
    """Перезапускает приложение с elevation или завершает его с понятной ошибкой."""
    if sys.platform != "win32":
        return

    relaunch_attempted = _strip_admin_relaunch_arg()
    if is_running_as_admin():
        return

    if relaunch_attempted:
        _show_admin_required_message("повторный запуск через runas не дал прав администратора")
        sys.exit(1)

    if getattr(sys, "frozen", False):
        executable = sys.executable
        arguments = [*sys.argv[1:], ADMIN_RELAUNCH_ARG]
    else:
        executable = _windowed_python_executable(sys.executable)
        arguments = [os.path.abspath(sys.argv[0]), *sys.argv[1:], ADMIN_RELAUNCH_ARG]

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            subprocess.list2cmdline(arguments),
            APP_BASE_PATH,
            1,
        )
    except Exception as exc:
        _show_admin_required_message(str(exc))
        sys.exit(1)

    if result > 32:
        sys.exit(0)

    _show_admin_required_message(f"ShellExecuteW вернул код {result}")
    sys.exit(1)


FOLDERID_STARTUP = (
    0xB97D20BB,
    0xF46A,
    0x4C97,
    (0xBA, 0x10, 0x5E, 0x36, 0x08, 0x43, 0x08, 0x54),
)
SHORTCUT_NAME = "Resize_File_Dialogs.lnk"
SCHEDULED_TASK_NAME = "Resize_File_Dialogs"
AUTOSTART_TASK_DELAY = "PT15S"


class GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    )


def build_guid(guid_parts) -> GUID:
    data1, data2, data3, data4 = guid_parts
    return GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))


def get_known_folder_path(guid_parts) -> str:
    folder_id = build_guid(guid_parts)
    path_ptr = ctypes.POINTER(ctypes.c_wchar)()

    shell32 = ctypes.windll.shell32
    shell32.SHGetKnownFolderPath.argtypes = (
        ctypes.POINTER(GUID),
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_wchar)),
    )
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long

    ole32 = ctypes.windll.ole32
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    ole32.CoTaskMemFree.restype = None

    hr = shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id),
        0,
        None,
        ctypes.byref(path_ptr),
    )
    try:
        if hr != 0:
            raise OSError(f"SHGetKnownFolderPath failed: HRESULT 0x{hr & 0xFFFFFFFF:08X}")
        return os.path.normpath(ctypes.wstring_at(path_ptr))
    finally:
        if path_ptr:
            ole32.CoTaskMemFree(ctypes.cast(path_ptr, ctypes.c_void_p))


def get_default_startup_folder() -> str:
    """Legacy default path used only to clean up shortcuts created by older builds."""
    appdata = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"),
        "AppData",
        "Roaming",
    )
    return os.path.normpath(
        os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
    )


def get_registry_startup_folder(log_func=print) -> str:
    if sys.platform != "win32":
        return ""

    try:
        import winreg
    except ImportError as exc:
        log_func(f"Не удалось открыть реестр Windows для Startup: {exc}")
        return ""

    registry_locations = (
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    )
    for subkey in registry_locations:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Startup")
        except FileNotFoundError:
            continue
        except OSError as exc:
            log_func(f"Не удалось прочитать Startup из реестра Windows ({subkey}): {exc}")
            continue

        startup_folder = os.path.normpath(os.path.expandvars(str(value)))
        if startup_folder:
            return startup_folder

    return ""


def get_user_startup_folder(log_func=print) -> str:
    try:
        startup_folder = get_known_folder_path(FOLDERID_STARTUP)
        if startup_folder:
            return startup_folder
    except Exception as exc:
        log_func(f"Не удалось получить Startup через Windows Shell API: {exc}")

    startup_folder = get_registry_startup_folder(log_func)
    if startup_folder:
        return startup_folder

    log_func("ОШИБКА: не удалось определить системную Startup-папку Windows.")
    return ""


def get_primary_startup_shortcut_path(log_func=print) -> str:
    startup_folder = get_user_startup_folder(log_func)
    if not startup_folder:
        return ""
    return os.path.join(startup_folder, SHORTCUT_NAME)


def get_startup_shortcut_paths(log_func=print) -> list[str]:
    primary_path = get_primary_startup_shortcut_path(log_func)
    fallback_path = os.path.join(get_default_startup_folder(), SHORTCUT_NAME)
    if not primary_path:
        return [fallback_path]
    if os.path.normcase(primary_path) == os.path.normcase(fallback_path):
        return [primary_path]
    return [primary_path, fallback_path]


def vbs_string(value: str) -> str:
    return value.replace('"', '""')


def resolve_app_shortcut_command() -> tuple[str, str, str]:
    if getattr(sys, "frozen", False):
        target_path = os.path.normpath(sys.executable)
        return target_path, "", os.path.dirname(target_path)

    script_path = os.path.normpath(os.path.abspath(sys.argv[0]))
    target_path = os.path.normpath(_windowed_python_executable(sys.executable))
    return target_path, subprocess.list2cmdline([script_path]), APP_BASE_PATH


def subprocess_no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def process_output(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip()


def get_current_user_id(log_func=print) -> str:
    try:
        result = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            creationflags=subprocess_no_window_flags(),
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if output := process_output(result):
            log_func(f"Не удалось определить пользователя через whoami: {output}")
    except Exception as exc:
        log_func(f"Не удалось определить пользователя через whoami: {exc}")

    username = os.environ.get("USERNAME") or os.path.basename(os.path.expanduser("~"))
    domain = os.environ.get("USERDOMAIN")
    if domain and username:
        return f"{domain}\\{username}"
    return username


def build_autostart_task_xml(
    target_path: str,
    arguments: str,
    working_directory: str,
    user_id: str,
) -> str:
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{xml_escape(created_at)}</Date>
    <Author>{xml_escape(user_id)}</Author>
    <Description>Запуск Resize File Dialogs при входе пользователя в Windows.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{xml_escape(user_id)}</UserId>
      <Delay>{AUTOSTART_TASK_DELAY}</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{xml_escape(user_id)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{xml_escape(target_path)}</Command>
      <Arguments>{xml_escape(arguments)}</Arguments>
      <WorkingDirectory>{xml_escape(working_directory)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def run_schtasks(args: list[str], log_func=print):
    try:
        return subprocess.run(
            ["schtasks", *args],
            capture_output=True,
            text=True,
            creationflags=subprocess_no_window_flags(),
            check=False,
        )
    except FileNotFoundError:
        log_func("ОШИБКА: schtasks.exe не найден.")
    except Exception as exc:
        log_func(f"ОШИБКА запуска schtasks.exe: {exc}")
    return None


def create_autostart_task(log_func=print) -> bool:
    target_path, arguments, working_directory = resolve_app_shortcut_command()

    if not os.path.exists(target_path):
        log_func(f"ОШИБКА: файл приложения не найден: {target_path}")
        return False
    if working_directory and not os.path.isdir(working_directory):
        log_func(f"ОШИБКА: рабочая папка приложения не найдена: {working_directory}")
        return False

    user_id = get_current_user_id(log_func)
    task_xml = build_autostart_task_xml(
        target_path,
        arguments,
        working_directory,
        user_id,
    )
    xml_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-16",
            suffix=".xml",
            delete=False,
        ) as file:
            xml_path = file.name
            file.write(task_xml)

        result = run_schtasks(
            ["/Create", "/TN", SCHEDULED_TASK_NAME, "/XML", xml_path, "/F"],
            log_func,
        )
        if result is None:
            return False
        if result.returncode != 0:
            output = process_output(result)
            log_func(f"ОШИБКА создания задачи автозагрузки: {output}")
            return False

        log_func(f"Автозагрузка включена через планировщик задач: {SCHEDULED_TASK_NAME}")
        return True
    except Exception as exc:
        log_func(f"ОШИБКА создания задачи автозагрузки: {exc}")
        log_func(traceback.format_exc())
        return False
    finally:
        if xml_path:
            try:
                os.remove(xml_path)
            except OSError:
                pass


def is_missing_scheduled_task_message(output: str) -> bool:
    output = output.lower()
    return any(
        pattern in output
        for pattern in (
            "cannot find",
            "does not exist",
            "не удается найти",
            "не найден",
            "не существует",
            "файл не найден",
        )
    )


def delete_autostart_task(log_func=print) -> bool:
    result = run_schtasks(["/Delete", "/TN", SCHEDULED_TASK_NAME, "/F"], log_func)
    if result is None:
        return False
    if result.returncode == 0:
        log_func("Задача автозагрузки удалена из планировщика.")
        return True

    output = process_output(result)
    if is_missing_scheduled_task_message(output):
        return True

    log_func(f"ОШИБКА удаления задачи автозагрузки: {output}")
    return False


def create_startup_shortcut(log_func=print) -> bool:
    shortcut_path = get_primary_startup_shortcut_path(log_func)
    if not shortcut_path:
        log_func("ОШИБКА: Startup-ярлык не создан, системная Startup-папка не определена.")
        return False

    shortcut_paths = get_startup_shortcut_paths(log_func)

    os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
    target_path, arguments, working_directory = resolve_app_shortcut_command()

    if not os.path.exists(target_path):
        log_func(f"ОШИБКА: файл приложения не найден: {target_path}")
        return False

    icon_path = resource_path("logo.ico")
    icon_line = ""
    if os.path.exists(icon_path):
        icon_line = f'oLink.IconLocation = "{vbs_string(icon_path)},0"\n'

    arguments_line = ""
    if arguments:
        arguments_line = f'oLink.Arguments = "{vbs_string(arguments)}"\n'

    vbs_script = f"""Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{vbs_string(shortcut_path)}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{vbs_string(target_path)}"
{arguments_line}oLink.WorkingDirectory = "{vbs_string(working_directory)}"
oLink.Description = "Resize File Dialogs"
{icon_line}oLink.Save
"""

    vbs_path = os.path.join(tempfile.gettempdir(), "create_resize_file_dialogs_shortcut.vbs")
    try:
        with open(vbs_path, "w", encoding="utf-16") as file:
            file.write(vbs_script)

        result = subprocess.run(
            ["cscript", "//Nologo", vbs_path],
            capture_output=True,
            text=True,
            creationflags=subprocess_no_window_flags(),
            check=False,
        )
        if result.returncode != 0:
            log_func(f"ОШИБКА cscript: {process_output(result)}")
            return False

        if not os.path.exists(shortcut_path):
            log_func("ОШИБКА: ярлык автозагрузки не создан.")
            return False

        for stale_shortcut_path in shortcut_paths[1:]:
            if os.path.exists(stale_shortcut_path):
                os.remove(stale_shortcut_path)

        log_func(f"Автозагрузка включена через Startup-ярлык: {shortcut_path}")
        return True
    except Exception as exc:
        log_func(f"ОШИБКА создания ярлыка автозагрузки: {exc}")
        log_func(traceback.format_exc())
        return False
    finally:
        try:
            if os.path.exists(vbs_path):
                os.remove(vbs_path)
        except OSError:
            pass


def remove_startup_shortcuts(log_func=print, log_success: bool = True) -> bool:
    shortcut_paths = get_startup_shortcut_paths(log_func)
    removed = False
    for path in shortcut_paths:
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
            removed = True
        except Exception as exc:
            log_func(f"ОШИБКА удаления ярлыка автозагрузки: {exc}")
            return False

    if removed and log_success:
        log_func("Startup-ярлык автозагрузки удален.")
    return True


def set_autostart(enabled: bool, log_func=print) -> bool:
    if enabled:
        if create_autostart_task(log_func):
            remove_startup_shortcuts(log_func, log_success=False)
            return True

        log_func("Планировщик задач недоступен, пробую fallback через Startup-ярлык.")
        return create_startup_shortcut(log_func)

    task_removed = delete_autostart_task(log_func)
    shortcuts_removed = remove_startup_shortcuts(log_func)
    return task_removed and shortcuts_removed


class AhkResizerGenerator(QMainWindow):
    """
    Приложение для генерации и управления скриптом AutoHotkey v2 для автоматического
    изменения размера и положения окон на основе заданных правил.
    Приведено в соответствие с universal_python_desktop_guide.md.
    """
    SETTINGS_FILE = "settings.json"
    LEGACY_SETTINGS_FILE = "ahk_resizer_generator_settings.json"
    ICON_FILE = "logo.ico"
    AHK_SCRIPT_FILE = "generated_resizer.ahk"
    RULES_EXPORT_SCHEMA = "resize_file_dialogs_rules"
    RULES_EXPORT_SCHEMA_VERSION = 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Resize_File_Dialogs v{__version__}")
        self.setWindowIcon(QIcon(resource_path(self.ICON_FILE)))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._base_window_minimum_size = (950, 700)
        self.setMinimumSize(*self._base_window_minimum_size)
        self.settings_path = resource_path(self.SETTINGS_FILE)
        self.legacy_settings_path = resource_path(self.LEGACY_SETTINGS_FILE)
        self.ahk_script_path = resource_path(self.AHK_SCRIPT_FILE)
        self.rules: List[Dict[str, Any]] = []
        self.exclude_titles: List[str] = []
        self.autostart_enabled = False
        self.start_minimized = False
        self.ui_scale_mode = "auto"
        self.ui_scale_delta_percent = 0
        self.ui_scale_percent = 100
        self.ahk_process: Optional[subprocess.Popen] = None
        self.paused = False
        self.tray_pause_action: Optional[QAction] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._ui_scale_state: Optional[UIScaleState] = None
        self._ui_scale_factor = 1.0
        self._ui_scale_screen = None
        self._ui_scale_app_hooks_installed = False
        self._ui_scale_window_hook_installed = False
        self._is_exiting = False
        self._splitters_initialized = False

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._load_settings()
        self.apply_ui_scale(allow_window_resize=False, reason="startup")
        self._populate_ui_from_settings()
        if app := QApplication.instance():
            app.aboutToQuit.connect(self._on_about_to_quit)

        self.log_message("Готов к работе.", "info")
        QTimer.singleShot(100, lambda: self.toggle_button.setChecked(True))
        QTimer.singleShot(0, self._finish_startup)

    def showEvent(self, event):
        """Задаёт стартовые размеры колонок при первом показе окна."""
        super().showEvent(event)
        if self._splitters_initialized:
            return
        self._splitters_initialized = True
        QTimer.singleShot(0, self._apply_default_splitter_sizes)

    def _apply_default_splitter_sizes(self):
        """Размеры колонок: слева вкладки правил, справа кнопки/логи."""
        self.main_splitter.setSizes([700, 300])
        self.right_splitter.setSizes([300, 250])
        self.rules_splitter.setSizes([220, 430])

    def _create_widgets(self):
        """Создание всех элементов интерфейса (виджетов)."""
        self.central_widget = QWidget()
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.rules_panel = QWidget()
        self.rules_panel_layout = QVBoxLayout(self.rules_panel)
        self.rules_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.rules_list = QListWidget()
        self.rules_list.setMinimumWidth(100)
        self.rules_splitter.setChildrenCollapsible(False)
        self.rule_form = QWidget()
        self.rule_form.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.rule_form_layout = QFormLayout(self.rule_form)
        self.rule_form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.rule_name_edit = QLineEdit()
        self.class_name_edit = QLineEdit()
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(100, 10000)
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(100, 10000)
        self.position_combo = QComboBox()
        self.position_combo.addItems([
            "center", "left", "right", "top-left", "top-center", "top-right",
            "bottom-left", "bottom-center", "bottom-right"
        ])
        self.titles_list = QListWidget()
        self.add_title_edit = QLineEdit()
        self.add_title_edit.setPlaceholderText("Заголовок для добавления...")
        self.add_title_btn = QPushButton("Добавить")
        self.remove_title_btn = QPushButton("Удалить выбранные")
        self.rule_enabled_checkbox = QCheckBox("Правило активно")
        self.rule_enabled_checkbox.setChecked(True)
        self.rule_form_layout.addRow(self.rule_enabled_checkbox)
        self.rule_form_layout.addRow("Имя правила:", self.rule_name_edit)
        self.rule_form_layout.addRow("Класс окна:", self.class_name_edit)
        self.rule_form_layout.addRow("Ширина:", self.width_spinbox)
        self.rule_form_layout.addRow("Высота:", self.height_spinbox)
        self.rule_form_layout.addRow("Позиция:", self.position_combo)
        self.rule_form_layout.addRow(QLabel("Заголовки для срабатывания (снимите галочку, чтобы временно отключить):"))
        self.rule_form_layout.addRow(self.titles_list)
        title_buttons_layout = QHBoxLayout()
        title_buttons_layout.addWidget(self.add_title_edit)
        title_buttons_layout.addWidget(self.add_title_btn)
        title_buttons_layout.addWidget(self.remove_title_btn)
        self.rule_form_layout.addRow(title_buttons_layout)
        self.exclusions_tab = QWidget()
        self.exclusions_layout = QVBoxLayout(self.exclusions_tab)
        self.exclusions_list = QListWidget()
        add_exclusion_layout = QHBoxLayout()
        self.exclusion_edit = QLineEdit()
        self.exclusion_edit.setPlaceholderText("Введите заголовок для исключения...")
        self.add_exclusion_btn = QPushButton("Добавить")
        self.remove_exclusion_btn = QPushButton("Удалить выбранное")
        add_exclusion_layout.addWidget(self.exclusion_edit)
        add_exclusion_layout.addWidget(self.add_exclusion_btn)
        self.exclusions_layout.addWidget(QLabel("Окна, содержащие эти заголовки, будут проигнорированы:"))
        self.exclusions_layout.addWidget(self.exclusions_list)
        self.exclusions_layout.addLayout(add_exclusion_layout)
        self.exclusions_layout.addWidget(self.remove_exclusion_btn)
        self.system_tab = QWidget()
        self.system_layout = QVBoxLayout(self.system_tab)
        self.startup_group = QGroupBox("Запуск")
        startup_group_layout = QVBoxLayout()
        self.autostart_checkbox = QCheckBox("Автозапуск при входе в Windows")
        self.start_minimized_checkbox = QCheckBox("Запускать свернутым в трей")
        startup_group_layout.addWidget(self.autostart_checkbox)
        startup_group_layout.addWidget(self.start_minimized_checkbox)
        self.startup_group.setLayout(startup_group_layout)
        self.ui_scale_group = QGroupBox("Масштаб интерфейса")
        ui_scale_layout = QFormLayout()
        self.ui_scale_combo = QComboBox()
        for delta_percent in range(-50, 51, 10):
            self.ui_scale_combo.addItem(f"{100 + delta_percent}%", delta_percent)
        self.ui_scale_info_label = QLabel("Авто: 100% | Поправка: 100% | Итог: 100%")
        ui_scale_layout.addRow("Масштаб:", self.ui_scale_combo)
        ui_scale_layout.addRow(self.ui_scale_info_label)
        self.ui_scale_group.setLayout(ui_scale_layout)
        self.system_layout.addWidget(self.startup_group)
        self.system_layout.addWidget(self.ui_scale_group)
        self.system_layout.addStretch()
        self.control_panel = QWidget()
        self.control_layout = QVBoxLayout(self.control_panel)
        self.toggle_button = QPushButton("Старт")
        self.toggle_button.setObjectName("start_btn")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setFixedHeight(40)
        self.rules_group = QGroupBox("Управление правилами")
        rules_group_layout = QVBoxLayout()
        self.add_rule_btn = QPushButton("Новое правило")
        self.remove_rule_btn = QPushButton("Удалить правило")
        self.remove_rule_btn.setObjectName("danger_btn")
        self.import_rules_btn = QPushButton("Импорт правил")
        self.export_rules_btn = QPushButton("Экспорт правил")
        rules_group_layout.addWidget(self.add_rule_btn)
        rules_group_layout.addWidget(self.remove_rule_btn)
        rules_group_layout.addWidget(self.import_rules_btn)
        rules_group_layout.addWidget(self.export_rules_btn)
        self.rules_group.setLayout(rules_group_layout)
        self.spy_group = QGroupBox("Инспектор окон (Spy)")
        spy_group_layout = QVBoxLayout()
        self.spy_button = QPushButton("Начать инспекцию")
        self.spy_button.setCheckable(True)
        self.save_rule_btn = QPushButton("Сохранить изменения в правиле")
        self.save_rule_btn.setObjectName("success_btn")
        spy_group_layout.addWidget(QLabel("1. Нажмите кнопку «Начать инспекцию».\n2. Кликните левой кнопкой мыши по окну.\n3. Данные появятся в форме слева."))
        spy_group_layout.addWidget(self.spy_button)
        spy_group_layout.addWidget(self.save_rule_btn)
        self.spy_group.setLayout(spy_group_layout)
        self.log_panel = QWidget()
        self.log_layout = QVBoxLayout(self.log_panel)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.clear_log_btn = QPushButton("Очистить лог")
        self.log_layout.addWidget(QLabel("Лог событий:"))
        self.log_layout.addWidget(self.log_edit)
        self.log_layout.addWidget(self.clear_log_btn)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        admin_status = "АДМИНИСТРАТОР" if self._check_admin_rights() else "Обычный пользователь"
        self.admin_status_label = QLabel(f"  Права: {admin_status}  ")
        self.status_bar.addPermanentWidget(self.admin_status_label)

    def _create_layout(self):
        """Компоновка созданных виджетов в окне."""
        self.rules_splitter.addWidget(self.rules_list)
        self.rules_splitter.addWidget(self.rule_form)
        self.rules_panel_layout.addWidget(self.rules_splitter)
        self.control_layout.addWidget(self.toggle_button)
        self.control_layout.addWidget(self.rules_group)
        self.control_layout.addWidget(self.spy_group)
        self.control_layout.addStretch()
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.rules_panel, "Правила")
        self.tab_widget.addTab(self.exclusions_tab, "Исключения")
        self.tab_widget.addTab(self.system_tab, "Система")
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.addWidget(self.tab_widget)
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setSizes([650, 300])
        self.right_splitter.addWidget(self.control_panel)
        self.right_splitter.addWidget(self.log_panel)
        self.right_splitter.setSizes([300, 250])
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.addWidget(self.main_splitter)
        self.setCentralWidget(self.central_widget)

    def _connect_signals(self):
        """Подключение сигналов к слотам (обработчикам)."""
        self.toggle_button.toggled.connect(self._on_toggle_scan)
        self.clear_log_btn.clicked.connect(self.log_edit.clear)
        self.rules_list.currentItemChanged.connect(self._display_rule_details)
        self.add_rule_btn.clicked.connect(self._add_new_rule)
        self.remove_rule_btn.clicked.connect(self._remove_selected_rule)
        self.save_rule_btn.clicked.connect(self._save_current_rule)
        self.import_rules_btn.clicked.connect(self._import_rules)
        self.export_rules_btn.clicked.connect(self._export_rules)
        self.add_exclusion_btn.clicked.connect(self._add_exclusion)
        self.remove_exclusion_btn.clicked.connect(self._remove_selected_exclusion)
        self.autostart_checkbox.toggled.connect(self._on_autostart_changed)
        self.start_minimized_checkbox.toggled.connect(self._on_start_minimized_changed)
        self.ui_scale_combo.currentIndexChanged.connect(self._on_ui_scale_delta_changed)
        self.spy_button.toggled.connect(self._on_toggle_spy)
        self.rule_enabled_checkbox.toggled.connect(self._on_rule_enabled_toggled)
        self.titles_list.itemChanged.connect(self._on_title_item_changed)
        self.add_title_btn.clicked.connect(self._add_title)
        self.remove_title_btn.clicked.connect(self._remove_selected_titles)
        self.spy_timer = QTimer(self)
        self.spy_timer.setInterval(200)
        self.spy_timer.timeout.connect(self._spy_on_window)

    def _apply_styles(self):
        """Применяет QSS стили в соответствии со стандартом."""
        scale_factor = self.get_ui_scale_factor()
        t = THEME_COLORS
        font = QFont("Tahoma")
        font.setPointSizeF(scale_point_size(15, scale_factor))
        if font.family().lower() != "tahoma":
            font = QFont("Segoe UI")
            font.setPointSizeF(scale_point_size(15, scale_factor))

        if app := QApplication.instance():
            app.setFont(font)
        self.setFont(font)

        qss = f"""
            QWidget {{
                background-color: {t['background']}; color: {t['text_strong']};
                font-family: Tahoma, "Segoe UI", Aptos, sans-serif;
                font-size: {scale_point_size(15, scale_factor)}pt;
            }}
            QMainWindow, QMenu {{ background-color: {t['background']}; }}
            QGroupBox {{
                padding: {scale_px(25, scale_factor)}px {scale_px(8, scale_factor)}px {scale_px(8, scale_factor)}px {scale_px(8, scale_factor)}px;
                margin-top: {scale_px(15, scale_factor)}px;
                border: {scale_px(1, scale_factor)}px solid {t['border']};
                border-radius: {scale_px(8, scale_factor)}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top center;
                padding: {scale_px(5, scale_factor)}px {scale_px(10, scale_factor)}px;
                background-color: {t['accent_pressed']};
                color: {t['text_strong']};
                border-radius: {scale_px(8, scale_factor)}px;
            }}
            QPushButton {{
                background-color: {t['surface_hover']}; color: {t['text_strong']};
                border: {scale_px(1, scale_factor)}px solid {t['border']};
                padding: {scale_px(8, scale_factor)}px {scale_px(16, scale_factor)}px;
                border-radius: {scale_px(8, scale_factor)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['primary_hover']}; }}
            QPushButton:pressed, QPushButton:checked {{ background-color: {t['surface_pressed']}; }}
            QPushButton:disabled {{ background-color: {t['disabled_background']}; color: {t['disabled_text']}; border-color: {t['disabled_border']}; }}
            QPushButton#start_btn {{ background-color: {t['accent']}; color: {t['on_accent']}; }}
            QPushButton#start_btn:hover {{ background-color: {t['accent_hover']}; }}
            QPushButton#start_btn:pressed, QPushButton#start_btn:checked {{ background-color: {t['accent_pressed']}; }}
            QPushButton#start_btn:disabled {{ background-color: {t['disabled_background']}; color: {t['disabled_text']}; }}
            QPushButton#danger_btn {{ background-color: {t['danger']}; color: {t['on_accent']}; }}
            QPushButton#danger_btn:hover {{ background-color: {t['danger_text']}; }}
            QPushButton#danger_btn:pressed {{ background-color: {t['danger_surface']}; color: {t['danger_text']}; }}
            QPushButton#danger_btn:disabled {{ background-color: {t['disabled_background']}; color: {t['disabled_text']}; }}
            QPushButton#success_btn {{ background-color: {t['success']}; color: {t['on_accent']}; }}
            QPushButton#success_btn:hover {{ border-color: {t['text_strong']}; }}
            QPushButton#success_btn:pressed {{ background-color: {t['surface_pressed']}; color: {t['success']}; }}
            QPushButton#success_btn:disabled {{ background-color: {t['disabled_background']}; color: {t['disabled_text']}; }}
            QLineEdit, QTextEdit, QSpinBox, QComboBox {{
                background-color: {t['surface_alt']};
                border: {scale_px(1, scale_factor)}px solid {t['border']};
                border-radius: {scale_px(6, scale_factor)}px;
                padding: {scale_px(5, scale_factor)}px;
                color: {t['text_strong']};
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: {scale_px(2, scale_factor)}px solid {t['focus']};
            }}
            QListWidget {{
                background-color: {t['surface_alt']};
                border: {scale_px(1, scale_factor)}px solid {t['border']};
            }}
            QListWidget::item:selected {{ background-color: {t['selection']}; color: {t['text_strong']}; font-weight: bold; }}
            QListWidget::indicator, QListView::indicator {{
                width: {scale_px(16, scale_factor)}px;
                height: {scale_px(16, scale_factor)}px;
            }}
            QTabWidget::pane {{
                border: {scale_px(1, scale_factor)}px solid {t['border']};
                border-top: none;
            }}
            QTabBar::tab {{
                background-color: {t['background']};
                border: {scale_px(1, scale_factor)}px solid {t['border']};
                border-bottom: none;
                padding: {scale_px(8, scale_factor)}px {scale_px(20, scale_factor)}px;
                margin-right: {scale_px(2, scale_factor)}px;
                border-top-left-radius: {scale_px(6, scale_factor)}px;
                border-top-right-radius: {scale_px(6, scale_factor)}px;
            }}
            QTabBar::tab:hover {{ background-color: {t['surface_hover']}; }}
            QTabBar::tab:selected {{ background-color: {t['selection']}; color: {t['text_strong']}; font-weight: bold; }}
            QTabBar::tab:!selected {{ color: {t['muted']}; }}
            QSplitter::handle {{ background-color: {t['border']}; }}
            QSplitter::handle:horizontal {{ width: {scale_px(2, scale_factor)}px; }}
            QSplitter::handle:vertical {{ height: {scale_px(2, scale_factor)}px; }}
            QCheckBox::indicator {{
                width: {scale_px(16, scale_factor)}px;
                height: {scale_px(16, scale_factor)}px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t['surface_alt']};
                color: {t['text_strong']};
                selection-background-color: {t['selection']};
                selection-color: {t['text_strong']};
            }}
            QScrollBar:vertical {{
                background: {t['background']};
                width: {scale_px(14, scale_factor)}px;
            }}
            QScrollBar:horizontal {{
                background: {t['background']};
                height: {scale_px(14, scale_factor)}px;
            }}
            QScrollBar::handle {{
                background: {t['border']};
                border-radius: {scale_px(6, scale_factor)}px;
                min-height: {scale_px(24, scale_factor)}px;
                min-width: {scale_px(24, scale_factor)}px;
            }}
            QStatusBar {{
                background-color: {t['background']};
                color: {t['text_strong']};
                border-top: {scale_px(1, scale_factor)}px solid {t['border']};
            }}
            QStatusBar QLabel {{
                background-color: transparent;
            }}
            QMenu::item:selected {{ background-color: {t['selection']}; }}
            QMessageBox {{ background-color: {t['background']}; }}
        """
        if app := QApplication.instance():
            app.setStyleSheet(qss)
        else:
            self.setStyleSheet(qss)

        self.log_edit.setStyleSheet(
            f"background-color: {t['surface']}; color: {t['text_strong']}; "
            "font-family: Consolas, 'Courier New', monospace; "
            f"font-size: {scale_point_size(11, scale_factor)}pt; "
            f"padding: {scale_px(4, scale_factor)}px;"
        )
        admin_color = t["success"] if self._check_admin_rights() else t["warning"]
        self.admin_status_label.setStyleSheet(
            f"color: {admin_color}; font-weight: bold; background-color: transparent;"
        )

    def get_ui_scale_factor(self) -> float:
        return self._ui_scale_factor

    def _active_screen(self):
        if window := self.windowHandle():
            if screen := window.screen():
                return screen
        if app := QApplication.instance():
            return app.primaryScreen()
        return None

    def _update_ui_scale_info_label(self):
        if not self._ui_scale_state:
            return
        correction_percent = 100 + self._ui_scale_state.delta_percent
        self.ui_scale_info_label.setText(
            f"Авто: {self._ui_scale_state.auto_percent}% | "
            f"Поправка: {correction_percent}% | "
            f"Итог: {self._ui_scale_state.final_percent}%"
        )

    def _resize_window_for_scale(self, old_factor: float, new_factor: float) -> None:
        if self.isMaximized() or old_factor <= 0 or abs(old_factor - new_factor) < 0.001:
            return

        ratio = new_factor / old_factor
        current_size = self.size()
        minimum_size = self.minimumSize()
        new_width = max(minimum_size.width(), scale_px(current_size.width(), ratio))
        new_height = max(minimum_size.height(), scale_px(current_size.height(), ratio))

        if screen := self._active_screen():
            available = screen.availableGeometry()
            new_width = min(new_width, max(minimum_size.width(), available.width()))
            new_height = min(new_height, max(minimum_size.height(), available.height()))

        self.resize(new_width, new_height)

    def _rescale_splitters(self, old_factor: float, new_factor: float) -> None:
        if old_factor <= 0 or abs(old_factor - new_factor) < 0.001:
            return

        ratio = new_factor / old_factor
        for splitter in (self.main_splitter, self.right_splitter, self.rules_splitter):
            sizes = splitter.sizes()
            if sizes and any(size > 0 for size in sizes):
                splitter.setSizes([scale_px(size, ratio, minimum=0) for size in sizes])

    def apply_ui_scale(self, allow_window_resize: bool = False, reason: str = "runtime") -> None:
        old_factor = self._ui_scale_factor
        state = resolve_ui_scale_from_screen(self._active_screen(), self.ui_scale_delta_percent)
        self._ui_scale_state = state
        self._ui_scale_factor = state.scale_factor
        self.ui_scale_mode = "auto"
        self.ui_scale_delta_percent = state.delta_percent
        self.ui_scale_percent = state.final_percent

        self._apply_styles()
        apply_widget_tree_scale(self, state.scale_factor)
        self._rescale_splitters(old_factor, state.scale_factor)
        self._update_ui_scale_info_label()

        if allow_window_resize and reason in {"startup", "manual-delta"}:
            self._resize_window_for_scale(old_factor, state.scale_factor)

    def install_ui_scale_screen_hooks(self) -> None:
        if app := QApplication.instance():
            if not self._ui_scale_app_hooks_installed:
                app.primaryScreenChanged.connect(self._on_ui_scale_topology_changed)
                app.screenAdded.connect(self._on_ui_scale_topology_changed)
                app.screenRemoved.connect(self._on_ui_scale_topology_changed)
                self._ui_scale_app_hooks_installed = True

        if window := self.windowHandle():
            if not self._ui_scale_window_hook_installed:
                window.screenChanged.connect(self._on_ui_scale_window_screen_changed)
                self._ui_scale_window_hook_installed = True

        self._connect_ui_scale_screen(self._active_screen())

    def _connect_ui_scale_screen(self, screen) -> None:
        if screen is self._ui_scale_screen:
            return

        if self._ui_scale_screen is not None:
            for signal_name in (
                "logicalDotsPerInchChanged",
                "geometryChanged",
                "availableGeometryChanged",
            ):
                try:
                    getattr(self._ui_scale_screen, signal_name).disconnect(
                        self._on_ui_scale_screen_metrics_changed
                    )
                except (RuntimeError, TypeError):
                    pass

        self._ui_scale_screen = screen
        if screen is None:
            return

        for signal_name in (
            "logicalDotsPerInchChanged",
            "geometryChanged",
            "availableGeometryChanged",
        ):
            signal = getattr(screen, signal_name, None)
            if signal is not None:
                try:
                    signal.connect(self._on_ui_scale_screen_metrics_changed)
                except (RuntimeError, TypeError):
                    pass

    def _on_ui_scale_window_screen_changed(self, screen) -> None:
        self._connect_ui_scale_screen(screen)
        self.apply_ui_scale(allow_window_resize=False, reason="screen-changed")

    def _on_ui_scale_screen_metrics_changed(self, *_):
        self.apply_ui_scale(allow_window_resize=False, reason="screen-metrics")

    def _on_ui_scale_topology_changed(self, *_):
        self._connect_ui_scale_screen(self._active_screen())
        self.apply_ui_scale(allow_window_resize=False, reason="screen-topology")

    def _load_settings(self):
        """Загружает настройки из JSON-файла."""
        try:
            settings_path = self.settings_path
            if not os.path.exists(settings_path) and os.path.exists(self.legacy_settings_path):
                settings_path = self.legacy_settings_path

            if not os.path.exists(settings_path):
                self.log_message("Файл настроек не найден. Загружаю стандартные.", "warn")
                self._load_default_settings()
                return
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self.rules = settings.get("rules", [])
            for rule in self.rules:
                rule["titles"] = self._normalize_rule_titles(rule.get("titles", []))
            self.exclude_titles = settings.get("exclude_titles", [])
            self.autostart_enabled = bool(settings.get("autostart_enabled", False))
            self.start_minimized = bool(settings.get("start_minimized", False))
            self.ui_scale_mode = normalize_ui_scale_mode(settings.get("ui_scale_mode", "auto"))
            if "ui_scale_delta_percent" in settings:
                self.ui_scale_delta_percent = normalize_ui_scale_delta_percent(
                    settings.get("ui_scale_delta_percent")
                )
            else:
                self.ui_scale_delta_percent = legacy_percent_to_delta_percent(
                    settings.get("ui_scale_percent", 100)
                )
            self.ui_scale_percent = normalize_ui_scale_percent(
                settings.get("ui_scale_percent", 100)
            )

            if window_state := settings.get("window_state"):
                x = int(window_state.get("x", 0))
                y = int(window_state.get("y", 0))
                width = int(window_state.get("width", 0))
                height = int(window_state.get("height", 0))
                if width > 100 and height > 100:
                    self.setGeometry(x, y, width, height)
                if window_state.get("maximized"):
                    QTimer.singleShot(0, self.showMaximized)
            elif geometry_b64 := settings.get("geometry"):
                self.restoreGeometry(QByteArray.fromBase64(geometry_b64.encode('ascii')))
            self.log_message(f"Настройки успешно загружены из '{os.path.basename(settings_path)}'.", "success")
        except (json.JSONDecodeError, Exception) as e:
            QMessageBox.warning(self, "Ошибка загрузки настроек", f"Не удалось прочитать файл '{self.settings_path}'.\nБудут использованы настройки по умолчанию.\n\nОшибка: {e}")
            self._load_default_settings()

    def _save_settings(self):
        """Сохраняет текущее состояние приложения в JSON-файл."""
        try:
            if self.rules_list.currentItem():
                self._update_rules_from_ui(show_warnings=False)

            current_geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
            settings = {
                "geometry": self.saveGeometry().toBase64().data().decode('ascii'),
                "window_state": {
                    "x": current_geometry.x(),
                    "y": current_geometry.y(),
                    "width": current_geometry.width(),
                    "height": current_geometry.height(),
                    "maximized": self.isMaximized(),
                },
                "rules": self.rules,
                "exclude_titles": self.exclude_titles,
                "autostart_enabled": self.autostart_enabled,
                "start_minimized": self.start_minimized,
                "ui_scale_mode": self.ui_scale_mode,
                "ui_scale_delta_percent": self.ui_scale_delta_percent,
                "ui_scale_percent": self.ui_scale_percent,
            }
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            self.log_message("Настройки сохранены.", "info")
        except Exception as e:
            self.log_message(f"Ошибка сохранения настроек: {e}", "error")
            if not self._is_exiting:
                QMessageBox.critical(self, "Ошибка Сохранения", f"Не удалось сохранить настройки:\n{e}")

    def _load_default_settings(self):
        """Загружает пустые правила и исключения для чистого старта."""
        self.rules = []
        self.exclude_titles = []
        self.autostart_enabled = False
        self.start_minimized = False
        self.ui_scale_mode = "auto"
        self.ui_scale_delta_percent = 0
        self.ui_scale_percent = 100

    def _rules_export_payload(self) -> dict[str, Any] | None:
        if self.rules_list.currentItem() and not self._update_rules_from_ui():
            return None

        return {
            "schema": self.RULES_EXPORT_SCHEMA,
            "schema_version": self.RULES_EXPORT_SCHEMA_VERSION,
            "app": "Resize_File_Dialogs",
            "app_version": __version__,
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "rules": deepcopy(self.rules),
            "exclude_titles": deepcopy(self.exclude_titles),
        }

    @staticmethod
    def _coerce_text_list(value: Any, field_name: str) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = value.splitlines()
        elif isinstance(value, list):
            raw_items = value
        else:
            raise ValueError(f"Поле '{field_name}' должно быть списком строк.")

        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = str(item).strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    @staticmethod
    def _normalize_rule_titles(value: Any) -> list[dict[str, Any]]:
        """Нормализует заголовки правила в список словарей {'text', 'enabled'}."""
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str):
            raw_items = value.splitlines()
        else:
            raw_items = []

        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_items:
            if isinstance(item, dict):
                text = str(item.get("text", item.get("title", ""))).strip()
                enabled = bool(item.get("enabled", True))
            else:
                text = str(item).strip()
                enabled = True
            if text and text not in seen:
                result.append({"text": text, "enabled": enabled})
                seen.add(text)
        return result

    @staticmethod
    def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    @staticmethod
    def _unique_rule_name(name: str, used_names: set[str], fallback: str) -> str:
        base_name = name.strip() or fallback
        candidate = base_name
        suffix = 2
        while candidate in used_names:
            candidate = f"{base_name} ({suffix})"
            suffix += 1
        used_names.add(candidate)
        return candidate

    def _parse_rules_import_payload(self, payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
        if isinstance(payload, list):
            raw_rules = payload
            raw_exclusions = []
        elif isinstance(payload, dict):
            raw_rules = payload.get("rules")
            raw_exclusions = payload.get("exclude_titles", payload.get("exclusions", []))
        else:
            raise ValueError("Файл должен содержать JSON-объект или список правил.")

        if not isinstance(raw_rules, list):
            raise ValueError("В файле нет корректного поля 'rules'.")

        valid_positions = {
            self.position_combo.itemText(index)
            for index in range(self.position_combo.count())
        }
        used_names: set[str] = set()
        imported_rules: list[dict[str, Any]] = []

        for index, raw_rule in enumerate(raw_rules, start=1):
            if not isinstance(raw_rule, dict):
                raise ValueError(f"Правило #{index} должно быть JSON-объектом.")

            position = str(raw_rule.get("position", "center")).strip()
            if position not in valid_positions:
                position = "center"

            imported_rules.append(
                {
                    "name": self._unique_rule_name(
                        str(raw_rule.get("name", "")),
                        used_names,
                        f"Импортированное правило {index}",
                    ),
                    "class": str(raw_rule.get("class", "")).strip(),
                    "width": self._coerce_int(raw_rule.get("width"), 1024, 100, 10000),
                    "height": self._coerce_int(raw_rule.get("height"), 768, 100, 10000),
                    "position": position,
                    "titles": self._normalize_rule_titles(raw_rule.get("titles", [])),
                    "enabled": bool(raw_rule.get("enabled", True)),
                }
            )

        imported_exclusions = self._coerce_text_list(raw_exclusions, "exclude_titles")
        return imported_rules, imported_exclusions

    def _export_rules(self):
        payload = self._rules_export_payload()
        if payload is None:
            return

        default_path = os.path.join(APP_BASE_PATH, "resize_file_dialogs_rules.json")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт правил",
            default_path,
            "JSON files (*.json);;All files (*)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".json"):
            file_path += ".json"

        try:
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=4)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось экспортировать правила:\n{exc}")
            self.log_message(f"Ошибка экспорта правил: {exc}", "error")
            return

        message = (
            f"Экспортировано правил: {len(payload['rules'])}\n"
            f"Экспортировано исключений: {len(payload['exclude_titles'])}\n\n"
            f"{file_path}"
        )
        QMessageBox.information(self, "Экспорт правил", message)
        self.log_message(f"Правила экспортированы: {file_path}", "success")

    def _import_rules(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт правил",
            APP_BASE_PATH,
            "JSON files (*.json);;All files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as file:
                payload = json.load(file)
            imported_rules, imported_exclusions = self._parse_rules_import_payload(payload)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка импорта", f"Не удалось импортировать правила:\n{exc}")
            self.log_message(f"Ошибка импорта правил: {exc}", "error")
            return

        if self.rules or self.exclude_titles:
            reply = QMessageBox.question(
                self,
                "Импорт правил",
                "Текущие правила и исключения будут заменены импортированными.\n\nПродолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.rules = imported_rules
        self.exclude_titles = imported_exclusions
        self._populate_ui_from_settings()
        self._persist_changes()

        message = (
            f"Импортировано правил: {len(imported_rules)}\n"
            f"Импортировано исключений: {len(imported_exclusions)}"
        )
        QMessageBox.information(self, "Импорт правил", message)
        self.log_message(f"Правила импортированы: {file_path}", "success")

    def _generate_ahk_script_text(self) -> str:
        """Генерирует текст .ahk скрипта на основе текущих правил."""
        settings_map = ""

        def escape_ahk(value: str) -> str:
            return value.replace("`", "``").replace('"', '""')

        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            rule_name = rule.get("name", "rule").replace(" ", "_").replace("\"", "'")
            ahk_class = rule.get("class", "")
            width, height = rule.get("width", 1024), rule.get("height", 768)
            position = rule.get("position", "center")
            titles_list = ', '.join([f'"{escape_ahk(entry["text"])}"' for entry in self._normalize_rule_titles(rule.get("titles", [])) if entry["enabled"]])
            settings_map += f"""
WindowSettings["{rule_name}"] := {{class: "{ahk_class}", width: {width}, height: {height}, position: "{position}", titles: [{titles_list}]}}"""
        exclude_list = ', '.join([f'"{escape_ahk(title)}"' for title in self.exclude_titles])

        return f"""
#Requires AutoHotkey v2.0
#SingleInstance Force
#NoTrayIcon

WindowSettings := Map()
{settings_map}

ExcludeTitles := [{exclude_list}]
ProcessedWindows := Map()
Paused := {str(self.paused).lower()}

CheckAllWindows() {{
    try {{
        if (Paused)
            return
        for hwnd in WinGetList() {{
            try {{
                if (ProcessedWindows.Has(hwnd) || !WinExist("ahk_id " . hwnd))
                    continue
                title := WinGetTitle("ahk_id " . hwnd)
                windowClass := WinGetClass("ahk_id " . hwnd)
                if (IsExcludedTitle(title))
                    continue
                for _, settings in WindowSettings {{
                    if (windowClass = settings.class && IsTargetTitle(title, settings.titles)) {{
                        ResizeWindow(hwnd, settings.width, settings.height, settings.position)
                        ProcessedWindows[hwnd] := A_TickCount
                        break
                    }}
                }}
            }} catch {{
                continue
            }}
        }}
        CleanupOldWindows()
    }} catch {{
        ; Этот пустой блок catch необходим для синтаксической корректности.
    }}
}}

IsTargetTitle(title, titlesList) {{
    for _, targetTitle in titlesList
        if InStr(title, targetTitle)
            return true
    return false
}}

IsExcludedTitle(title) {{
    for _, excludeTitle in ExcludeTitles
        if InStr(title, excludeTitle) > 0
            return true
    return false
}}

ResizeWindow(hwnd, targetWidth, targetHeight, position) {{
    try {{
        WinGetPos(&x, &y, &width, &height, "ahk_id " . hwnd)
        local newX, newY, topOffset := 40
        switch position {{
            case "left": newX := 0, newY := (A_ScreenHeight - targetHeight) // 2
            case "center": newX := (A_ScreenWidth - targetWidth) // 2, newY := (A_ScreenHeight - targetHeight) // 2
            case "right": newX := A_ScreenWidth - targetWidth, newY := (A_ScreenHeight - targetHeight) // 2
            case "top-left": newX := 0, newY := topOffset
            case "top-center": newX := (A_ScreenWidth - targetWidth) // 2, newY := topOffset
            case "top-right": newX := A_ScreenWidth - targetWidth, newY := topOffset
            case "bottom-left": newX := 0, newY := A_ScreenHeight - targetHeight
            case "bottom-center": newX := (A_ScreenWidth - targetWidth) // 2, newY := A_ScreenHeight - targetHeight
            case "bottom-right": newX := A_ScreenWidth - targetWidth, newY := A_ScreenHeight - targetHeight
            default: newX := (A_ScreenWidth - targetWidth) // 2, newY := (A_ScreenHeight - targetHeight) // 2
        }}
        if (width != targetWidth || height != targetHeight || x != newX || y != newY) {{
            ; WinActivate("ahk_id " . hwnd)
            ; Sleep(50)
            WinMove(newX, newY, targetWidth, targetHeight, "ahk_id " . hwnd)
        }}
    }} catch {{
    }}
}}

CleanupOldWindows() {{
    toRemove := []
    for hwnd, timestamp in ProcessedWindows
        if (!WinExist("ahk_id " . hwnd) || (A_TickCount - timestamp > 30000))
            toRemove.Push(hwnd)
    for _, hwnd in toRemove
        ProcessedWindows.Delete(hwnd)
}}

SetTimer(CheckAllWindows, 1000)
return
"""

    def _check_admin_rights(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _finish_startup(self):
        self.show()
        QApplication.processEvents()
        self.install_ui_scale_screen_hooks()
        self.apply_ui_scale(allow_window_resize=True, reason="startup")
        QTimer.singleShot(200, self._create_tray_icon)
        if self.start_minimized:
            QTimer.singleShot(800, self._hide_to_tray_on_startup)

    def _create_tray_icon(self):
        if self.tray_icon is not None:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QTimer.singleShot(1000, self._create_tray_icon)
            return

        self.tray_icon = QSystemTrayIcon(QIcon(resource_path(self.ICON_FILE)), self)
        self.tray_icon.setToolTip("Resize File Dialogs")
        tray_menu = QMenu(self)
        self.tray_pause_action = QAction("Пауза", self)
        self.tray_pause_action.setCheckable(True)
        self.tray_pause_action.setChecked(self.paused)
        self.tray_pause_action.toggled.connect(self._on_tray_pause_toggled)
        tray_menu.addAction(self.tray_pause_action)
        tray_menu.addSeparator()
        actions = {"Показать": self._show_window, "Скрыть": self.hide, "Выход": self.exit_application}
        for text, func in actions.items():
            if text == "Выход":
                tray_menu.addSeparator()
            action = QAction(text, self)
            action.triggered.connect(func)
            tray_menu.addAction(action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_icon_activated)
        self.tray_icon.show()

    def _on_tray_pause_toggled(self, paused: bool):
        self.paused = paused
        self._update_tray_pause_action_text()
        if paused:
            self.log_message("Пауза включена: регулировка размеров окон приостановлена.", "warn")
        else:
            self.log_message("Пауза снята: регулировка размеров окон возобновлена.", "success")
        self._regenerate_and_restart_ahk_if_running()

    def _update_tray_pause_action_text(self):
        if self.tray_pause_action is not None:
            self.tray_pause_action.setText("Возобновить" if self.paused else "Пауза")

    def _tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _hide_to_tray_on_startup(self):
        if self.tray_icon is None:
            QTimer.singleShot(500, self._hide_to_tray_on_startup)
            return
        self.hide()
        self.log_message("Приложение запущено свернутым в трей.", "info")

    def log_message(self, message: str, level: str = "normal"):
        color_map = {"normal": "text_strong", "info": "accent", "success": "success", "warn": "warning", "error": "danger"}
        color = THEME_COLORS[color_map.get(level, "text_strong")]
        timestamp = time.strftime("%H:%M:%S")
        self.log_edit.append(f'<span style="color: {color};">[{timestamp}] {message}</span>')

    def _populate_ui_from_settings(self):
        self.rules_list.clear()
        self.exclusions_list.clear()
        self.autostart_checkbox.blockSignals(True)
        self.start_minimized_checkbox.blockSignals(True)
        self.ui_scale_combo.blockSignals(True)
        self.autostart_checkbox.setChecked(self.autostart_enabled)
        self.start_minimized_checkbox.setChecked(self.start_minimized)
        scale_index = self.ui_scale_combo.findData(self.ui_scale_delta_percent)
        self.ui_scale_combo.setCurrentIndex(max(0, scale_index))
        self.autostart_checkbox.blockSignals(False)
        self.start_minimized_checkbox.blockSignals(False)
        self.ui_scale_combo.blockSignals(False)
        self._update_ui_scale_info_label()
        for i, rule in enumerate(self.rules):
            item = QListWidgetItem(self._rule_list_text(rule))
            item.setData(Qt.ItemDataRole.UserRole, i)
            if not rule.get("enabled", True):
                item.setForeground(QBrush(QColor(THEME_COLORS["muted"])))
            self.rules_list.addItem(item)
        self.exclusions_list.addItems(self.exclude_titles)
        if self.rules_list.count() > 0:
            self.rules_list.setCurrentRow(0)
        else:
            self._clear_rule_form()

    def _on_toggle_scan(self, checked: bool):
        if checked:
            script_text = self._generate_ahk_script_text()
            try:
                with open(self.ahk_script_path, "w", encoding="utf-8") as f:
                    f.write(script_text)
                ahk_path = "autohotkey"
                if os.path.exists(local_ahk_path := resource_path("AutoHotkey/AutoHotkey.exe")):
                    ahk_path = local_ahk_path
                self.ahk_process = subprocess.Popen(
                    [ahk_path, self.ahk_script_path],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    cwd=APP_BASE_PATH,
                )
                self.log_message(f"Запущен процесс AHK с PID: {self.ahk_process.pid}", "success")
                self.toggle_button.setText("Стоп")
                self.statusBar().showMessage("Скрипт AutoHotkey запущен.")
            except FileNotFoundError:
                QMessageBox.critical(self, "Ошибка Запуска", "Не удалось найти 'AutoHotkey.exe'.\nУбедитесь, что AutoHotkey v2 установлен и добавлен в PATH, либо поместите его в папку 'AutoHotkey' рядом с .exe приложения.")
                self.log_message("Ошибка: AutoHotkey.exe не найден.", "error")
                self.toggle_button.setChecked(False)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Произошла ошибка при запуске скрипта:\n{e}")
                self.log_message(f"Ошибка запуска AHK: {e}", "error")
                self.toggle_button.setChecked(False)
        else:
            if self.ahk_process:
                try:
                    self.ahk_process.terminate()
                    self.log_message(f"Процесс AHK {self.ahk_process.pid} остановлен.", "info")
                    self.ahk_process = None
                except Exception as e:
                    self.log_message(f"Ошибка остановки процесса AHK: {e}", "error")
            self.toggle_button.setText("Старт")
            self.statusBar().showMessage("Скрипт AutoHotkey остановлен.")

    def _regenerate_and_restart_ahk_if_running(self):
        if self.toggle_button.isChecked():
            self.log_message("Настройки изменились. Перезапускаю скрипт AHK...", "info")
            self.toggle_button.setChecked(False)
            QTimer.singleShot(250, lambda: self.toggle_button.setChecked(True))

    def _persist_changes(self):
        """Сохраняет настройки и перезапускает AHK-скрипт при необходимости."""
        self._save_settings()
        self._regenerate_and_restart_ahk_if_running()

    def _log_autostart_message(self, message: str):
        level = "error" if "ОШИБКА" in message else "info"
        self.log_message(message, level)

    def _on_autostart_changed(self, enabled: bool):
        previous_value = self.autostart_enabled
        self.autostart_enabled = enabled
        self._save_settings()

        if set_autostart(enabled, log_func=self._log_autostart_message):
            state_text = "включена" if enabled else "отключена"
            self.statusBar().showMessage(f"Автозагрузка {state_text}.", 3000)
            return

        self.autostart_enabled = previous_value
        self.autostart_checkbox.blockSignals(True)
        self.autostart_checkbox.setChecked(previous_value)
        self.autostart_checkbox.blockSignals(False)
        self._save_settings()
        QMessageBox.warning(
            self,
            "Автозагрузка",
            "Не удалось изменить автозагрузку. Подробности записаны в лог.",
        )

    def _on_start_minimized_changed(self, enabled: bool):
        self.start_minimized = enabled
        self._save_settings()
        state_text = "включен" if enabled else "отключен"
        self.statusBar().showMessage(f"Запуск свернутым {state_text}.", 3000)

    def _on_ui_scale_delta_changed(self):
        self.ui_scale_delta_percent = normalize_ui_scale_delta_percent(
            self.ui_scale_combo.currentData()
        )
        self.apply_ui_scale(allow_window_resize=True, reason="manual-delta")
        self._save_settings()
        self.statusBar().showMessage(
            f"Масштаб интерфейса: {self.ui_scale_percent}%.",
            3000,
        )

    def _on_toggle_spy(self, checked: bool):
        if checked:
            self.spy_timer.start()
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.log_message("Инспектор окон активирован. Кликните на целевое окно.", "info")
        else:
            self.spy_timer.stop()
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _spy_on_window(self):
        if not isinstance(win32api, Dummy):
            if self.spy_button.isChecked() and (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000):
                try:
                    pos = win32gui.GetCursorPos()
                    hwnd = win32gui.WindowFromPoint(pos)
                    hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT) or hwnd
                    title, class_name = win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd)
                    if title:
                        self.class_name_edit.setText(class_name)
                        existing_titles = {self.titles_list.item(i).text() for i in range(self.titles_list.count())}
                        if title not in existing_titles:
                            title_item = QListWidgetItem(title)
                            title_item.setFlags(title_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                            title_item.setCheckState(Qt.CheckState.Checked)
                            self.titles_list.addItem(title_item)
                        self.log_message(f"Инспектор: Класс='{class_name}', Заголовок='{title}'", "success")
                except Exception as e:
                    self.log_message(f"Ошибка инспектора: {e}", "error")
                finally:
                    self.spy_button.setChecked(False)

    def _display_rule_details(self, current_item, _):
        if not current_item:
            self._clear_rule_form()
            return
        rule_index = current_item.data(Qt.ItemDataRole.UserRole)
        if rule_index is not None and 0 <= rule_index < len(self.rules):
            rule = self.rules[rule_index]
            self.rule_enabled_checkbox.blockSignals(True)
            self.rule_enabled_checkbox.setChecked(rule.get("enabled", True))
            self.rule_enabled_checkbox.blockSignals(False)
            self.rule_name_edit.setText(rule.get("name", ""))
            self.class_name_edit.setText(rule.get("class", ""))
            self.width_spinbox.setValue(rule.get("width", 800))
            self.height_spinbox.setValue(rule.get("height", 600))
            self.position_combo.setCurrentText(rule.get("position", "center"))
            self.titles_list.blockSignals(True)
            self.titles_list.clear()
            for entry in self._normalize_rule_titles(rule.get("titles", [])):
                title_item = QListWidgetItem(entry["text"])
                title_item.setFlags(title_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                title_item.setCheckState(Qt.CheckState.Checked if entry["enabled"] else Qt.CheckState.Unchecked)
                self.titles_list.addItem(title_item)
            self.titles_list.blockSignals(False)

    def _clear_rule_form(self):
        self.rule_enabled_checkbox.blockSignals(True)
        self.rule_enabled_checkbox.setChecked(True)
        self.rule_enabled_checkbox.blockSignals(False)
        self.rule_name_edit.clear()
        self.class_name_edit.clear()
        self.width_spinbox.setValue(1024)
        self.height_spinbox.setValue(768)
        self.position_combo.setCurrentIndex(0)
        self.titles_list.blockSignals(True)
        self.titles_list.clear()
        self.titles_list.blockSignals(False)
        self.add_title_edit.clear()

    def _add_new_rule(self):
        if self.rules_list.currentItem() and not self._update_rules_from_ui():
            return
        name = f"Новое правило {len(self.rules) + 1}"
        new_rule = {"name": name, "class": "", "width": 1024, "height": 768, "position": "center", "titles": [], "enabled": True}
        self.rules.append(new_rule)
        self._populate_ui_from_settings()
        self.rules_list.setCurrentRow(self.rules_list.count() - 1)
        self.log_message(f"Добавлено новое правило '{name}'.", "info")
        self._persist_changes()

    def _remove_selected_rule(self):
        if not (item := self.rules_list.currentItem()):
            return
        rule_name = item.text().removesuffix(" (выкл)")
        reply = QMessageBox.question(self, "Подтверждение удаления", f"Вы уверены, что хотите удалить правило '{rule_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            del self.rules[self.rules_list.row(item)]
            self._populate_ui_from_settings()
            self.log_message(f"Правило '{rule_name}' удалено.", "info")
            self._persist_changes()

    def _save_current_rule(self):
        if not self.rules_list.currentItem():
            QMessageBox.warning(self, "Нет выбора", "Пожалуйста, выберите правило для сохранения.")
            return
        if not self._update_rules_from_ui():
            return
        self.log_message(f"Правило '{self.rule_name_edit.text()}' сохранено.", "success")
        self._persist_changes()

    def _update_rules_from_ui(self, show_warnings: bool = True) -> bool:
        if not (item := self.rules_list.currentItem()):
            return False
        idx = self.rules_list.row(item)
        if not (0 <= idx < len(self.rules)):
            return False
        if not (name := self.rule_name_edit.text().strip()):
            if show_warnings:
                QMessageBox.warning(self, "Ошибка валидации", "Имя правила не может быть пустым.")
            return False
        for i, r in enumerate(self.rules):
            if r.get("name") == name and i != idx:
                if show_warnings:
                    QMessageBox.warning(self, "Ошибка валидации", "Правило с таким именем уже существует.")
                return False
        self.rules[idx] = {
            "name": name, "class": self.class_name_edit.text(), "width": self.width_spinbox.value(),
            "height": self.height_spinbox.value(), "position": self.position_combo.currentText(),
            "titles": [
                {"text": self.titles_list.item(i).text(),
                 "enabled": self.titles_list.item(i).checkState() == Qt.CheckState.Checked}
                for i in range(self.titles_list.count())
            ],
            "enabled": self.rule_enabled_checkbox.isChecked(),
        }
        item.setText(self._rule_list_text(self.rules[idx]))
        return True

    @staticmethod
    def _rule_list_text(rule: dict[str, Any]) -> str:
        name = rule.get("name", "Unnamed Rule")
        return f"{name} (выкл)" if not rule.get("enabled", True) else name

    def _on_rule_enabled_toggled(self, checked: bool):
        if not (item := self.rules_list.currentItem()):
            return
        idx = self.rules_list.row(item)
        if not (0 <= idx < len(self.rules)):
            return
        self.rules[idx]["enabled"] = checked
        item.setText(self._rule_list_text(self.rules[idx]))
        if checked:
            item.setForeground(QBrush())
        else:
            item.setForeground(QBrush(QColor(THEME_COLORS["muted"])))
        state_text = "включено" if checked else "отключено"
        self.log_message(f"Правило '{self.rules[idx].get('name', '')}' временно {state_text}.", "info")
        self._persist_changes()

    def _on_title_item_changed(self, item: QListWidgetItem):
        if not self.rules_list.currentItem():
            return
        idx = self.rules_list.row(self.rules_list.currentItem())
        if not (0 <= idx < len(self.rules)):
            return
        state_text = "активен" if item.checkState() == Qt.CheckState.Checked else "отключен"
        self.log_message(
            f"Заголовок '{item.text()}' {state_text} в правиле '{self.rules[idx].get('name', '')}'.",
            "info",
        )
        self._persist_changes()

    def _add_title(self):
        if not self.rules_list.currentItem():
            QMessageBox.warning(self, "Нет правила", "Сначала выберите правило, в которое нужно добавить заголовок.")
            return
        text = self.add_title_edit.text().strip()
        if not text:
            return
        existing_titles = {self.titles_list.item(i).text() for i in range(self.titles_list.count())}
        if text in existing_titles:
            self.log_message(f"Заголовок '{text}' уже добавлен в правило.", "warn")
            self.add_title_edit.clear()
            return
        title_item = QListWidgetItem(text)
        title_item.setFlags(title_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        title_item.setCheckState(Qt.CheckState.Checked)
        self.titles_list.addItem(title_item)
        self.add_title_edit.clear()
        self.log_message(f"Заголовок '{text}' добавлен в правило.", "info")
        self._persist_changes()

    def _remove_selected_titles(self):
        if not self.rules_list.currentItem():
            return
        removed = False
        for item in self.titles_list.selectedItems():
            self.titles_list.takeItem(self.titles_list.row(item))
            self.log_message(f"Заголовок '{item.text()}' удален из правила.", "info")
            removed = True
        if removed:
            self._persist_changes()

    def _add_exclusion(self):
        if (title := self.exclusion_edit.text().strip()) and title not in self.exclude_titles:
            self.exclude_titles.append(title)
            self.exclusions_list.addItem(title)
            self.exclusion_edit.clear()
            self.log_message(f"Добавлено исключение '{title}'.", "info")
            self._persist_changes()

    def _remove_selected_exclusion(self):
        if not (item := self.exclusions_list.currentItem()):
            return
        self.exclude_titles.remove(item.text())
        self.exclusions_list.takeItem(self.exclusions_list.row(item))
        self.log_message(f"Удалено исключение '{item.text()}'.", "info")
        self._persist_changes()

    def closeEvent(self, event):
        self._save_settings()
        if self._is_exiting:
            event.accept()
        else:
            event.ignore()
            self.hide()
            if self.tray_icon is not None:
                self.tray_icon.showMessage(
                    "Приложение работает",
                    "Resize File Dialogs свернут в трей.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

    def _on_about_to_quit(self):
        """Гарантирует сохранение настроек при завершении приложения/сессии."""
        self._is_exiting = True
        self._save_settings()
        if self.ahk_process:
            try:
                self.ahk_process.terminate()
            except Exception:
                pass
            finally:
                self.ahk_process = None

    def exit_application(self):
        self.log_message("Завершение работы...", "info")
        self._is_exiting = True
        if self.ahk_process:
            try:
                self.ahk_process.terminate()
                self.log_message("Процесс AHK остановлен перед выходом.", "info")
            except Exception as e:
                self.log_message(f"Ошибка остановки AHK перед выходом: {e}", "error")
            finally:
                self.ahk_process = None
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if app := QApplication.instance():
            app.quit()
        else:
            self.close()

if __name__ == "__main__":
    ensure_admin_or_exit()
    myappid = 'frommer.resize_file_dialogs.desktop'
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(resource_path(AhkResizerGenerator.ICON_FILE)))
    window = AhkResizerGenerator()
    sys.exit(app.exec())
