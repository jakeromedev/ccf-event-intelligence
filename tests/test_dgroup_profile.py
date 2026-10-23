import unittest
from unittest.mock import Mock

from app.aggregation import participant_ministry_and_shirt_metrics


class DgroupProfileTests(unittest.TestCase):
    def metrics(self, *rows):
        db = Mock(is_mysql=False)
        db.execute.return_value.fetchall.return_value = [
            dict(curated_id=1, leadership_status="", legacy_leader="",
                 years_leading="", shirt_size="", downlines="") | row
            for row in rows
        ]
        return participant_ministry_and_shirt_metrics(db, 1)

    def test_timothy_only_profile_excludes_leadership_answers(self):
        result = self.metrics(dict(
            leadership_status="Timothy / Dgroup member", legacy_leader="Yes",
            years_leading="1-2 years", downlines="5",
        ))
        self.assertEqual(1, result["dgroup_profile"]["total"])
        self.assertEqual(100, result["dgroup_profile"]["items"][2]["percentage"])
        for key in ("leadership", "years_leading", "leadership_downlines"):
            self.assertEqual(0, result[key]["total"])
            self.assertEqual(0, result[key]["unreported"])

    def test_deduplication_conflicts_and_legacy_fallback(self):
        result = self.metrics(
            dict(curated_id=1, legacy_leader="Yes", years_leading="N/A"),
            dict(curated_id=1, legacy_leader="Yes", years_leading="N/A"),
            dict(curated_id=2, leadership_status="D12 Leader", years_leading="3-5 years"),
            dict(curated_id=2, leadership_status="Timothy / Dgroup member"),
            dict(curated_id=3, leadership_status="Unrecognized", legacy_leader="Yes"),
        )
        self.assertEqual(1, result["dgroup_profile"]["total"])
        self.assertEqual(1, result["dgroup_profile"]["conflicts"])
        self.assertEqual(1, result["dgroup_profile"]["unreported"])
        self.assertEqual(1, result["leadership"]["total"])
        self.assertEqual(0, result["years_leading"]["total"])
        self.assertEqual(1, result["years_leading"]["unreported"])

    def test_empty_batch_includes_profile(self):
        result = participant_ministry_and_shirt_metrics(None, None)
        self.assertEqual(0, result["dgroup_profile"]["total"])
        self.assertEqual(3, len(result["dgroup_profile"]["items"]))
