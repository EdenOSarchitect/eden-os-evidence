import unittest

from chrysalis import evaluate, net_resource_cost


class ChrysalisTests(unittest.TestCase):
    def test_net_resource_cost_charges_all_overheads(self):
        self.assertEqual(
            net_resource_cost({
                "active": 70,
                "metadata": 5,
                "recovery": 2,
                "regeneration": 3,
                "orchestration": 4,
            }),
            84.0,
        )

    def test_selects_lowest_cost_candidate_that_meets_quality(self):
        result = evaluate({
            "baseline": {"quality": 1.0, "total": 100},
            "policy": {
                "minimum_quality": 0.995,
                "minimum_net_reduction_fraction": 0.10,
            },
            "candidates": [
                {"id": "fast-but-bad", "quality": 0.90, "total": 50},
                {"id": "good", "quality": 0.999, "active": 70, "metadata": 3, "recovery": 1, "regeneration": 4, "orchestration": 2},
                {"id": "better", "quality": 0.998, "active": 65, "metadata": 3, "recovery": 1, "regeneration": 4, "orchestration": 2},
            ],
        })
        self.assertEqual(result["status"], "SELECTED")
        self.assertEqual(result["selected"]["id"], "better")
        self.assertAlmostEqual(result["selected"]["net_resource_cost"], 75.0)
        self.assertTrue(result["selected"]["qualifies"])

    def test_returns_no_candidate_when_quality_fails(self):
        result = evaluate({
            "baseline": {"quality": 1.0, "total": 100},
            "policy": {"minimum_quality": 0.995},
            "candidates": [{"id": "bad", "quality": 0.90, "total": 10}],
        })
        self.assertEqual(result["status"], "NO_QUALIFYING_CANDIDATE")
        self.assertIsNone(result["selected"])


if __name__ == "__main__":
    unittest.main()
