import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["RESIZE_FILE_DIALOGS_SKIP_VENV_BOOTSTRAP"] = "1"


def load_app_module():
    module_path = Path(__file__).resolve().parents[1] / "Resize_File_Dialogs.pyw"
    spec = importlib.util.spec_from_file_location("resize_file_dialogs", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutostartPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_module = load_app_module()

    def test_startup_shortcut_creation_uses_system_path_first(self):
        system_startup = r"D:\Startup"
        default_startup = (
            r"C:\Users\Frommer\AppData\Roaming\Microsoft\Windows\Start Menu"
            r"\Programs\Startup"
        )

        with (
            patch.object(
                self.app_module,
                "get_user_startup_folder",
                return_value=system_startup,
            ),
            patch.object(
                self.app_module,
                "get_default_startup_folder",
                return_value=default_startup,
            ),
        ):
            primary_path = self.app_module.get_primary_startup_shortcut_path()
            cleanup_paths = self.app_module.get_startup_shortcut_paths()

        self.assertEqual(
            primary_path,
            rf"{system_startup}\{self.app_module.SHORTCUT_NAME}",
        )
        self.assertEqual(cleanup_paths[0], primary_path)
        self.assertEqual(
            cleanup_paths[1],
            rf"{default_startup}\{self.app_module.SHORTCUT_NAME}",
        )

    def test_startup_shortcut_creation_fails_without_system_path(self):
        messages = []

        with (
            patch.object(self.app_module, "get_user_startup_folder", return_value=""),
            patch.object(
                self.app_module,
                "get_default_startup_folder",
                return_value=r"C:\Users\Frommer\AppData\Roaming\Microsoft\Windows"
                r"\Start Menu\Programs\Startup",
            ),
        ):
            primary_path = self.app_module.get_primary_startup_shortcut_path(messages.append)
            cleanup_paths = self.app_module.get_startup_shortcut_paths(messages.append)

        self.assertEqual(primary_path, "")
        self.assertEqual(len(cleanup_paths), 1)
        self.assertIn("AppData", cleanup_paths[0])


if __name__ == "__main__":
    unittest.main()
