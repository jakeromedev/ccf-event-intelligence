import unittest
from unittest.mock import Mock

from app.aggregation import participant_ministry_and_shirt_metrics


class LeadershipDownlineTests(unittest.TestCase):
    def test_unique_leaders_boundaries_and_excluded_answers(self):
        db = Mock(is_mysql=False)
        answers = [
            (1, "1"), (1, "1"), (2, "2"), (3, "3"), (4, "20"),
            (5, "0"), (6, None), (7, "unknown"), (8, "2"), (8, "3"),
        ]
        db.execute.return_value.fetchall.return_value = [
            {"curated_id": person, "leadership_status": "DGroup Leader",
             "legacy_leader": None, "years_leading": None, "shirt_size": None,
             "downlines": answer}
            for person, answer in answers
        ]
        result = participant_ministry_and_shirt_metrics(db, 1)["leadership_downlines"]
        self.assertEqual(4, result["total"])
        self.assertEqual([1, 2, 3, 20], [item["key"] for item in result["items"]])
        self.assertEqual([1, 1, 1, 1], [item["count"] for item in result["items"]])
        self.assertEqual([25, 25, 25, 25], [item["percentage"] for item in result["items"]])
        self.assertEqual(1, result["max_count"])
        for key in ("zero", "unreported", "invalid", "conflicts"):
            self.assertEqual(1, result[key], key)

    def test_empty_batch(self):
        result = participant_ministry_and_shirt_metrics(None, None)["leadership_downlines"]
        self.assertEqual(0, result["total"])
        self.assertEqual([], result["items"])
        self.assertEqual(0, result["max_count"])
