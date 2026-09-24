"""Non-interactive frozen import fixture for the application build policy."""

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QWidget
import win32api
import win32gui

from app.ui.theme import THEME_COLORS


if __name__ == "__main__":
    app = QApplication([])
    widget = QWidget()
    assert widget.metaObject().className() == "QWidget"
    assert QCoreApplication.instance() is app
    assert win32api.GetVersionEx()
    assert hasattr(win32gui, "GetWindowText")
    assert THEME_COLORS["background"] == "#282C34"
    print("FROZEN_SMOKE_OK")
