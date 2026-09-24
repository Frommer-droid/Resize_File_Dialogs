"""Runtime helpers for applying UI scale to Qt widget trees."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLayout, QWidget

from app.ui_scale import scale_px


QWIDGETSIZE_MAX = 16777215
_BASE_LAYOUT_MARGINS = "_ui_scale_base_layout_margins"
_BASE_LAYOUT_SPACING = "_ui_scale_base_layout_spacing"
_BASE_WIDGET_MARGINS = "_ui_scale_base_widget_margins"
_BASE_WIDGET_MIN_SIZE = "_ui_scale_base_widget_min_size"
_BASE_WIDGET_MAX_SIZE = "_ui_scale_base_widget_max_size"
_BASE_WIDGET_ICON_SIZE = "_ui_scale_base_widget_icon_size"


def _store_property_once(obj: Any, name: str, value: Any) -> Any:
    stored = obj.property(name)
    if stored is None:
        obj.setProperty(name, value)
        return value
    return stored


def _scale_size(size: QSize, scale_factor: float, scale_maximum: bool = False) -> QSize:
    width = size.width()
    height = size.height()

    if scale_maximum:
        scaled_width = width if width >= QWIDGETSIZE_MAX else scale_px(width, scale_factor)
        scaled_height = height if height >= QWIDGETSIZE_MAX else scale_px(height, scale_factor)
    else:
        scaled_width = scale_px(width, scale_factor, minimum=0) if width > 0 else 0
        scaled_height = scale_px(height, scale_factor, minimum=0) if height > 0 else 0

    return QSize(scaled_width, scaled_height)


def apply_layout_scale(layout: QLayout | None, scale_factor: float) -> None:
    if layout is None:
        return

    margins = layout.contentsMargins()
    base_margins = _store_property_once(
        layout,
        _BASE_LAYOUT_MARGINS,
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
    )
    layout.setContentsMargins(
        scale_px(base_margins[0], scale_factor, minimum=0),
        scale_px(base_margins[1], scale_factor, minimum=0),
        scale_px(base_margins[2], scale_factor, minimum=0),
        scale_px(base_margins[3], scale_factor, minimum=0),
    )

    spacing = layout.spacing()
    base_spacing = _store_property_once(layout, _BASE_LAYOUT_SPACING, spacing)
    if base_spacing >= 0:
        layout.setSpacing(scale_px(base_spacing, scale_factor, minimum=0))

    for index in range(layout.count()):
        item = layout.itemAt(index)
        if child_layout := item.layout():
            apply_layout_scale(child_layout, scale_factor)
        if child_widget := item.widget():
            apply_widget_scale(child_widget, scale_factor)


def apply_widget_scale(widget: QWidget, scale_factor: float) -> None:
    margins = widget.contentsMargins()
    base_margins = _store_property_once(
        widget,
        _BASE_WIDGET_MARGINS,
        (margins.left(), margins.top(), margins.right(), margins.bottom()),
    )
    widget.setContentsMargins(
        scale_px(base_margins[0], scale_factor, minimum=0),
        scale_px(base_margins[1], scale_factor, minimum=0),
        scale_px(base_margins[2], scale_factor, minimum=0),
        scale_px(base_margins[3], scale_factor, minimum=0),
    )

    base_min_size = _store_property_once(widget, _BASE_WIDGET_MIN_SIZE, widget.minimumSize())
    base_max_size = _store_property_once(widget, _BASE_WIDGET_MAX_SIZE, widget.maximumSize())
    widget.setMinimumSize(_scale_size(base_min_size, scale_factor))
    widget.setMaximumSize(_scale_size(base_max_size, scale_factor, scale_maximum=True))

    if hasattr(widget, "iconSize") and hasattr(widget, "setIconSize"):
        icon_size = widget.iconSize()
        base_icon_size = _store_property_once(widget, _BASE_WIDGET_ICON_SIZE, icon_size)
        if base_icon_size.width() > 0 or base_icon_size.height() > 0:
            widget.setIconSize(_scale_size(base_icon_size, scale_factor))

    apply_layout_scale(widget.layout(), scale_factor)


def apply_widget_tree_scale(root: QWidget, scale_factor: float) -> None:
    apply_widget_scale(root, scale_factor)
    for child in root.findChildren(QWidget):
        apply_widget_scale(child, scale_factor)
