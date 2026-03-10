import unittest

from controller.map.layout import (
    compute_map_list_names_target_height,
    compute_map_panel_metrics,
    snap_to_step,
)


class TestMapUILayout(unittest.TestCase):
    def test_snap_to_step_rounds_to_nearest_step(self):
        self.assertEqual(snap_to_step(23, step=10), 20)
        self.assertEqual(snap_to_step(26, step=10), 30)
        self.assertEqual(snap_to_step(25, step=10), 20)

    def test_map_list_names_height_respects_visible_row_bounds(self):
        target = compute_map_list_names_target_height(
            row_height=22,
            row_count=10,
            min_rows=2,
            max_rows=6,
            frame_width=1,
            extra_padding=8,
            min_height=40,
        )
        self.assertEqual(target, (6 * 22) + 2 + 8)

    def test_map_list_names_height_uses_min_rows_and_min_height(self):
        target = compute_map_list_names_target_height(
            row_height=3,
            row_count=1,
            min_rows=2,
            max_rows=6,
            frame_width=0,
            extra_padding=0,
            min_height=40,
        )
        self.assertEqual(target, 40)

    def test_panel_metrics_are_stable_and_clamped(self):
        metrics = compute_map_panel_metrics(650)
        self.assertGreaterEqual(metrics.soft_canvas, 160)
        self.assertLessEqual(metrics.soft_canvas, 320)
        self.assertGreaterEqual(metrics.panel_min_width, 210)
        self.assertLessEqual(metrics.panel_min_width, 360)
        self.assertGreaterEqual(metrics.panel_min_height, 220)
        self.assertGreaterEqual(metrics.frame_min_height, 150)
        self.assertLessEqual(metrics.frame_min_height, 420)


if __name__ == "__main__":
    unittest.main()
