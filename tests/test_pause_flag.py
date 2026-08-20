import importlib.util
import os
from pathlib import Path
import unittest


os.environ["RESIZE_FILE_DIALOGS_SKIP_VENV_BOOTSTRAP"] = "1"


def load_app_module():
    module_path = Path(__file__).resolve().parents[1] / "Resize_File_Dialogs.pyw"
    spec = importlib.util.spec_from_file_location("resize_file_dialogs", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PauseFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_module = load_app_module()

    def _generate_script(self, paused: bool) -> str:
        window = self.app_module.AhkResizerGenerator.__new__(
            self.app_module.AhkResizerGenerator
        )
        window.rules = [
            {
                "name": "Test",
                "class": "TestClass",
                "width": 800,
                "height": 600,
                "position": "center",
                "titles": ["Test"],
            }
        ]
        window.exclude_titles = ["Exclude"]
        window.paused = paused
        return window._generate_ahk_script_text()

    def test_paused_script_stops_resizing(self):
        script = self._generate_script(paused=True)
        self.assertIn("Paused := true", script)
        self.assertIn("if (Paused)", script)
        self.assertIn("return", script)

    def test_active_script_has_pause_flag_disabled(self):
        script = self._generate_script(paused=False)
        self.assertIn("Paused := false", script)

    def test_paused_flag_skips_window_loop(self):
        script = self._generate_script(paused=True)
        pause_check = script.split("if (Paused)")[1].split("\n")[1]
        self.assertIn("return", pause_check)


if __name__ == "__main__":
    unittest.main()
