# DEVELOPER.md

## 1. Назначение проекта

`Resize_File_Dialogs` — desktop-приложение на `PySide6` для генерации и запуска AutoHotkey-скрипта, который меняет размер и позицию целевых окон по наборам правил.

## 2. Окружение разработки

- ОС: Windows 10/11.
- Python: 3.12 для разработки, тестов и релизной сборки.
- Основные зависимости:
  - `PySide6`
  - `pywin32` (опционально, для Spy-функций)
  - `PyInstaller` (для сборки)
  - `ruff` (для релизной проверки)
- Для запуска из исходников использовать проектную `.venv`; зависимости зафиксированы в `requirements.txt`.
- Если `.venv` существует, `Resize_File_Dialogs.pyw` автоматически перезапускает dev-запуск через `.venv\Scripts\pythonw.exe`, чтобы GUI не открывал консольное окно и не зависел от глобального Python.

## 3. Структура проекта

- `Resize_File_Dialogs.pyw` — основной GUI-модуль (точка входа).
- `app/version.py` — чтение версии из `VERSION`.
- `VERSION` — единый источник версии.
- `Build_Tools/Resize_File_Dialogs.spec` — спецификация PyInstaller.
- `Build_Tools/post_build.py` — пост-обработка сборки.
- `Build_Tools/SpecCompiler.pyw` — GUI для запуска PyInstaller.
- `Build_Tools/binary_policy.py` — проверка происхождения бинарников и согласованности MSVC runtime Qt.
- `Build_Tools/verify_frozen_build.py` — отдельная сборка и запуск неинтерактивной frozen-фикстуры.
- `.github/workflows/verify.yml` — те же lint, unit- и frozen-проверки на Windows в CI.
- `app/ui/theme/colors.py` — единые токены палитры One Dark для приложения и сборщика.
- `00_CrRel-setup.pyw` — создание installer `.exe` через Inno Setup из корневой собранной папки `Resize_File_Dialogs`; очистка runtime-файлов выполняется только в staging-копии.
- `00_Move.pyw` — обновление portable-папки `D:\Portable_soft\Resize_File_Dialogs` копированием корневой собранной папки; исходная папка не переносится.

## 4. Версионирование

1. Менять версию только в `VERSION`.
2. В приложении использовать `from app.version import __version__`.
3. Для frozen-режима `VERSION` включается в сборку через `.spec` и записывается в Windows FileVersion/ProductVersion EXE.

## 5. Сборка приложения

1. Запустить `Build_Tools/SpecCompiler.pyw` из проектной `.venv`.
2. Выбрать `Build_Tools/Resize_File_Dialogs.spec`.
3. Запустить сборку.
4. Убедиться, что автоматически отработал `Build_Tools/post_build.py`.
5. Выполнить `.\.venv\Scripts\python.exe .\Build_Tools\verify_frozen_build.py`.

Сборщик формирует минимальный доверенный `PATH`. Spec отклоняет любые бинарные
зависимости вне проекта, выбранного Python, PySide6 и каталога Windows;
набор `CONCRT140`, `MSVCP140*` и `VCRUNTIME140*` берётся в согласованных версиях из PySide6. До удаления
work-папки `post_build.py` проверяет `COLLECT-00.toc`. Проверочный скрипт также
собирает полный EXE в отдельной временной папке и проверяет его TOC. Frozen-фикстура
импортирует PySide6 и pywin32, захватывает stdout/stderr, проверяет exit status;
основное приложение с UAC не запускается.

`post_build.py` выполняет:
- перенос собранной папки из `Build_Tools/dist/<APP_NAME>` в корень проекта;
- удаление временных папок сборки;
- копирование `VERSION`;
- копирование `LICENSE`;
- копирование `logo.ico`;
- копирование папки `AutoHotKey` в `AutoHotkey`;
- копирование всех `*.json` из корня проекта;
- проверку наличия итогового `.exe` без запуска приложения.

## 6. Работа с путями и настройками

- Используются абсолютные пути, вычисляемые от расположения `exe`/скрипта.
- Основной файл настроек: `settings.json` (в корне приложения).
- При миграции поддерживается fallback на `ahk_resizer_generator_settings.json`.
- В `settings.json` сохраняются параметры окна (`x`, `y`, `width`, `height`, `maximized`). Состояния сплиттеров не сохраняются: стартовые размеры колонок задаются в `showEvent`/`_apply_default_splitter_sizes` при первом показе окна.
- Правила хранят флаг `enabled` («Правило активно») и заголовки как список словарей `{"text", "enabled"}`; старые строковые заголовки нормализуются `_normalize_rule_titles`. Отключённые правила и заголовки пропускаются при генерации AHK-скрипта.
- Масштаб интерфейса хранится в `settings.json` через `ui_scale_mode`, `ui_scale_delta_percent` и диагностический `ui_scale_percent`.
- Импорт/экспорт правил использует JSON с полями `rules` и `exclude_titles`; импорт заменяет текущие правила после подтверждения.
- Если файл настроек отсутствует, приложение стартует с пустыми правилами и пустым списком исключений.
- Настройки дополнительно сохраняются при `QApplication.aboutToQuit` (включая завершение сессии Windows/перезагрузку).
- Изменения правил и исключений сохраняются сразу после изменения (не только при ручном выходе через трей).

## 7. Иконка и Windows AppUserModelID

- Иконка проекта: `logo.ico` (корень проекта).
- Для корректного отображения на панели задач задается `SetCurrentProcessExplicitAppUserModelID`.
- Для AHK-скрипта используется `#NoTrayIcon`, чтобы не дублировать иконки в системном трее.
- Собранный `Resize_File_Dialogs.exe` должен требовать права администратора через `uac_admin=True` в `Build_Tools/Resize_File_Dialogs.spec`.
- В `Resize_File_Dialogs.pyw` есть runtime-проверка прав: если приложение стартовало без административного токена, оно пробует перезапуск через `runas`, а при невозможности показывает ошибку и завершается.

## 8. Релизный процесс

1. Классифицировать изменения (features/fixes/docs/refactor/tests/chore).
2. Обновить `VERSION`.
3. Обновить `RELEASE_NOTES.md` и `README.md`.
4. Проверить `.gitignore` и санитарно убрать лишние артефакты из индекса.
5. Запустить `python -m ruff check .`.
6. Проверить тесты (если есть).
7. Подготовить команду релизного коммита:
   - `ct vX.Y.Z "краткое описание"`
8. Для стадии installer/copy после сборки использовать отдельные скрипты:
   - `00_CrRel-setup.pyw` — собрать installer из папки `Resize_File_Dialogs`, не изменяя саму корневую собранную папку;
   - `00_Move.pyw` — скопировать папку `Resize_File_Dialogs` в `D:\Portable_soft\Resize_File_Dialogs`;
   - `00_Move.pyw` всегда сохраняет существующие portable-настройки и сгенерированный AHK-скрипт при обновлении папки;
   - release-скрипты не запускают приложение после сборки, установки или копирования, чтобы не блокировать `.exe` и DLL при следующих шагах;
   - `.rar`, `.zip`, `.7z` не создавать без явного запроса пользователя.

## 9. Автозагрузка и трей

- В приложении есть вкладка `Система` с двумя независимыми настройками:
  - `Автозапуск при входе в Windows` сохраняет `autostart_enabled`;
  - `Запускать свернутым в трей` сохраняет `start_minimized`.
- На вкладке `Система` есть группа `Масштаб интерфейса`; комбобокс показывает `50%..150%`, а в настройках хранится delta `-50..50`.
- `autostart_enabled` создает или удаляет задачу планировщика Windows `Resize_File_Dialogs`.
- Задача запускается при входе текущего пользователя в Windows с `InteractiveToken`, `RunLevel=HighestAvailable` и задержкой 15 секунд.
- В frozen-сборке задача указывает на `Resize_File_Dialogs.exe`; в dev-режиме — на `pythonw.exe` с аргументом пути к `Resize_File_Dialogs.pyw`.
- Старый Startup-ярлык `Resize_File_Dialogs.lnk` удаляется после успешного создания задачи планировщика.
- Если `schtasks.exe` недоступен, остается fallback на ярлык в пользовательской папке Windows Startup.
- Папка Startup для fallback определяется только через системные источники Windows: `SHGetKnownFolderPath(FOLDERID_Startup)`, затем registry fallback `Explorer\User Shell Folders\Startup` / `Explorer\Shell Folders\Startup`.
- Жесткий путь `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` не используется для создания ярлыка; он остается только для удаления старого ярлыка, созданного предыдущими версиями.
- Fallback-ярлык создается через временный VBScript и `cscript`, без зависимости от `pywin32`.
- При `start_minimized = true` окно сначала штатно создается и показывается, затем после создания `QSystemTrayIcon` скрывается в трей через `QTimer`.
- Закрытие окна крестиком скрывает приложение в трей. Реальный выход выполняется через пункт `Выход` в меню трея.
- В контекстном меню трея есть переключатель «Пауза / Возобновить» (checkable-пункт): при включенной паузе генерируемый AHK-скрипт получает флаг `Paused := true` и `CheckAllWindows` сразу выходит, поэтому размеры и позиции окон не изменяются. Если скрипт уже запущен, он перезапускается с новым флагом. Пауза хранится только в памяти и не сохраняется в `settings.json`.
