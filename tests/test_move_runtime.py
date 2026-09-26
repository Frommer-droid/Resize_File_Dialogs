import importlib.util
import shutil
import tempfile
from pathlib import Path
import unittest


class PortableRuntimeTests(unittest.TestCase):
    def test_existing_portable_settings_survive_copy(self):
        script = Path(__file__).resolve().parents[1] / "00_Move.pyw"
        spec = importlib.util.spec_from_file_location("portable_move", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory(prefix="portable-runtime-test-") as temp:
            base = Path(temp)
            source = base / "source"
            target = base / "target"
            source.mkdir()
            target.mkdir()
            (source / "settings.json").write_text("new build defaults", encoding="utf-8")
            (target / "settings.json").write_text("user settings", encoding="utf-8")
            (target / "generated_resizer.ahk").write_text("user script", encoding="utf-8")

            backup = module.preserve_runtime_files(source, target)
            try:
                shutil.rmtree(target)
                module.copy_release_folder(source, target)
                module.restore_runtime_files(backup, target)
                self.assertEqual((target / "settings.json").read_text(encoding="utf-8"), "user settings")
                self.assertEqual((target / "generated_resizer.ahk").read_text(encoding="utf-8"), "user script")
            finally:
                module.cleanup_backup_dir(backup)
