import unittest

from chrononav import choose_workers, schedule


class ChronoNavSchedulerTests(unittest.TestCase):
    def test_selects_lowest_workers_meeting_deadline(self):
        self.assertEqual(choose_workers({1: 1.2, 2: 0.8, 4: 0.4}, 0.9), 2)

    def test_falls_back_to_fastest_when_deadline_unreachable(self):
        self.assertEqual(choose_workers({1: 1.2, 2: 0.8, 4: 0.4}, 0.2), 4)

    def test_truth_boundary_is_explicit(self):
        result = schedule({"predicted_seconds": {"1": 1.2, "2": 0.8}, "deadline_seconds": 1.0})
        self.assertEqual(result["selected_workers"], 2)
        self.assertFalse(result["evidence"]["physically_measured"])
        self.assertIn("physical energy saving", result["truth"]["not_claimed"])


if __name__ == "__main__":
    unittest.main()
