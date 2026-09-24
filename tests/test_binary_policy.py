import sys
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "Build_Tools"))
from binary_policy import RUNTIME_NAMES, prefer_qt_runtime, validate_binaries  # noqa: E402


class BinaryPolicyTests(unittest.TestCase):
    def test_foreign_binary_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="foreign-dll-test-") as temp:
            foreign = Path(temp) / "foreign.dll"
            foreign.write_bytes(b"fixture")
            with self.assertRaisesRegex(RuntimeError, "Untrusted PyInstaller binary"):
                validate_binaries([("foreign.dll", str(foreign), "BINARY")], PROJECT_ROOT)
            with self.assertRaisesRegex(RuntimeError, "Untrusted PyInstaller binary"):
                prefer_qt_runtime([("vcruntime140.dll", str(foreign), "BINARY")], PROJECT_ROOT)

    def test_qt_runtime_pair_is_selected(self):
        binaries = prefer_qt_runtime([], PROJECT_ROOT)
        self.assertEqual(
            {dest.lower() for dest, _source, _type in binaries},
            set(RUNTIME_NAMES),
        )
        self.assertTrue(all("PySide6" in source for _dest, source, _type in binaries))
