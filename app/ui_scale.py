"""UI scale calculation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BASE_LOGICAL_DPI = 96.0
REFERENCE_WIDTH = 2560
REFERENCE_HEIGHT = 1440
MIN_AUTO_PERCENT = 70
MAX_AUTO_PERCENT = 200
AUTO_STEP_PERCENT = 10
MIN_DELTA_PERCENT = -50
MAX_DELTA_PERCENT = 50
DELTA_STEP_PERCENT = 10
MIN_FINAL_PERCENT = 35
MAX_FINAL_PERCENT = 300
FINAL_STEP_PERCENT = 5
MIN_MANUAL_SCALE_REFERENCE_PERCENT = 100


@dataclass(frozen=True)
class UIScaleState:
    auto_percent: int
    delta_percent: int
    final_percent: int
    scale_factor: float


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def normalize_ui_scale_mode(_value: Any) -> str:
    return "auto"


def normalize_ui_scale_delta_percent(value: Any) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = 0

    percent = round_to_step(percent, DELTA_STEP_PERCENT)
    return clamp(percent, MIN_DELTA_PERCENT, MAX_DELTA_PERCENT)


def normalize_ui_scale_percent(value: Any) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = 100

    percent = round_to_step(percent, FINAL_STEP_PERCENT)
    return clamp(percent, MIN_FINAL_PERCENT, MAX_FINAL_PERCENT)


def legacy_percent_to_delta_percent(value: Any) -> int:
    return normalize_ui_scale_delta_percent(normalize_ui_scale_percent(value) - 100)


def calculate_auto_percent(
    available_width: int,
    available_height: int,
    logical_dpi: float,
) -> int:
    if available_width <= 0 or available_height <= 0:
        return 100

    dpi = logical_dpi if logical_dpi > 0 else BASE_LOGICAL_DPI
    normalized_width = available_width * dpi / BASE_LOGICAL_DPI
    normalized_height = available_height * dpi / BASE_LOGICAL_DPI
    ratio = min(normalized_width / REFERENCE_WIDTH, normalized_height / REFERENCE_HEIGHT)
    return clamp(
        round_to_step(ratio * 100, AUTO_STEP_PERCENT),
        MIN_AUTO_PERCENT,
        MAX_AUTO_PERCENT,
    )


def calculate_final_percent(auto_percent: int, delta_percent: int) -> int:
    delta_reference = max(auto_percent, MIN_MANUAL_SCALE_REFERENCE_PERCENT)
    raw_final = auto_percent + delta_reference * delta_percent / 100.0
    return clamp(
        round_to_step(raw_final, FINAL_STEP_PERCENT),
        MIN_FINAL_PERCENT,
        MAX_FINAL_PERCENT,
    )


def calculate_scale_factor(final_percent: int) -> float:
    return final_percent / 100.0


def resolve_ui_scale(
    available_width: int,
    available_height: int,
    logical_dpi: float,
    delta_percent: Any,
) -> UIScaleState:
    normalized_delta = normalize_ui_scale_delta_percent(delta_percent)
    auto_percent = calculate_auto_percent(available_width, available_height, logical_dpi)
    final_percent = calculate_final_percent(auto_percent, normalized_delta)
    return UIScaleState(
        auto_percent=auto_percent,
        delta_percent=normalized_delta,
        final_percent=final_percent,
        scale_factor=calculate_scale_factor(final_percent),
    )


def resolve_ui_scale_from_screen(screen: Any, delta_percent: Any) -> UIScaleState:
    if screen is None:
        return resolve_ui_scale(REFERENCE_WIDTH, REFERENCE_HEIGHT, BASE_LOGICAL_DPI, delta_percent)

    geometry = screen.availableGeometry()
    return resolve_ui_scale(
        geometry.width(),
        geometry.height(),
        float(screen.logicalDotsPerInch()),
        delta_percent,
    )


def scale_px(value: int | float, scale_factor: float, minimum: int = 1) -> int:
    return max(minimum, int(round(value * scale_factor)))


def scale_point_size(value: int | float, scale_factor: float, minimum: float = 8.0) -> float:
    return max(minimum, round(float(value) * scale_factor, 2))
