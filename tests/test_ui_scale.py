import unittest

from app.ui_scale import (
    calculate_auto_percent,
    calculate_final_percent,
    legacy_percent_to_delta_percent,
    normalize_ui_scale_delta_percent,
    resolve_ui_scale,
    scale_px,
)


class UIScaleTests(unittest.TestCase):
    def test_reference_screen_is_100_percent(self):
        self.assertEqual(calculate_auto_percent(2560, 1440, 96.0), 100)

    def test_auto_percent_uses_available_screen_and_dpi(self):
        self.assertEqual(calculate_auto_percent(1920, 1080, 96.0), 80)
        self.assertEqual(calculate_auto_percent(3840, 2160, 96.0), 150)

    def test_delta_is_normalized_to_supported_range_and_step(self):
        self.assertEqual(normalize_ui_scale_delta_percent(27), 30)
        self.assertEqual(normalize_ui_scale_delta_percent(-70), -50)
        self.assertEqual(normalize_ui_scale_delta_percent(80), 50)
        self.assertEqual(normalize_ui_scale_delta_percent("bad"), 0)

    def test_final_percent_uses_auto_percent_as_reference(self):
        self.assertEqual(calculate_final_percent(100, 20), 120)
        self.assertEqual(calculate_final_percent(80, 20), 100)
        self.assertEqual(calculate_final_percent(150, -20), 120)

    def test_resolve_ui_scale_returns_full_state(self):
        state = resolve_ui_scale(2560, 1440, 96.0, 10)
        self.assertEqual(state.auto_percent, 100)
        self.assertEqual(state.delta_percent, 10)
        self.assertEqual(state.final_percent, 110)
        self.assertEqual(state.scale_factor, 1.1)

    def test_legacy_percent_migrates_to_delta(self):
        self.assertEqual(legacy_percent_to_delta_percent(130), 30)
        self.assertEqual(legacy_percent_to_delta_percent(40), -50)

    def test_scale_px_keeps_minimum(self):
        self.assertEqual(scale_px(10, 1.5), 15)
        self.assertEqual(scale_px(0, 0.5), 1)
        self.assertEqual(scale_px(0, 0.5, minimum=0), 0)


if __name__ == "__main__":
    unittest.main()
