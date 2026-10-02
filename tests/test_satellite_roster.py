import unittest
from unittest.mock import patch

from app.satellite_roster import satellite_participant_table


class SatelliteParticipantTableTests(unittest.TestCase):
    def rows(self):
        return [
            dict(curated_id=index, directory_id=directory, satellite=satellite,
                 hub_id=1, group_id=1, hub="Hub", hub_group="Group",
                 first_name="Alex", last_name="Person {:03}".format(index),
                 registration_code="R-{:03}".format(index), source_id=str(index),
                 link_status="Linked" if directory else "Needs Mapping")
            for index, directory, satellite in
            [(i, 1, "Alpha") for i in range(60)] + [(60, 2, "Beta"), (61, None, "Unassigned")]
        ]

    @patch("app.satellite_roster.satellite_roster_rows")
    def test_search_is_intersection_with_satellite_and_keeps_options(self, read_rows):
        read_rows.return_value = self.rows()
        result = satellite_participant_table(None, 1, 1, satellite="directory:1", query="R-060")
        self.assertEqual([], result["rows"])
        self.assertEqual(3, len(result["options"]))
        result = satellite_participant_table(None, 1, 1, satellite="directory:2", query="r-060")
        self.assertEqual([60], [row["curated_id"] for row in result["rows"]])
        self.assertEqual("directory:2", result["satellite"])

    @patch("app.satellite_roster.satellite_roster_rows")
    def test_grouped_pagination_and_unassigned_filter(self, read_rows):
        read_rows.return_value = list(reversed(self.rows()))
        result = satellite_participant_table(None, 1, 1, page=2, per_page=50)
        self.assertEqual(62, result["pagination"]["total"])
        self.assertEqual(["Alpha"] * 10 + ["Beta", "Unassigned"],
                         [row["satellite"] for row in result["rows"]])
        result = satellite_participant_table(None, 1, 1, satellite="unmapped:Unassigned")
        self.assertEqual([61], [row["curated_id"] for row in result["rows"]])

    @patch("app.satellite_roster.satellite_roster_rows")
    def test_overview_filters_still_constrain_table(self, read_rows):
        read_rows.return_value = self.rows()
        result = satellite_participant_table(None, 1, 1, overview_filters={"satellite_id": 2})
        self.assertEqual([60], [row["curated_id"] for row in result["rows"]])
        result = satellite_participant_table(None, 1, 1, overview_filters={"link_status": "needs_mapping"})
        self.assertEqual([61], [row["curated_id"] for row in result["rows"]])

    @patch("app.satellite_roster.satellite_roster_rows")
    def test_contact_search_and_partial_birth_date(self, read_rows):
        rows = self.rows()
        rows[-2].update(source_data_json='{"Email Address":"alex@example.com","Mobile Number":"09123456789"}',
                        birth_month="January", birth_year="1990")
        read_rows.return_value = rows
        for query in ("ALEX@EXAMPLE.COM", "09123456789"):
            result = satellite_participant_table(None, 1, 1, satellite="directory:2", query=query)
            self.assertEqual([60], [row["curated_id"] for row in result["rows"]])
            self.assertEqual("January 1990", result["rows"][0]["date_of_birth"])
            self.assertEqual("09123456789", result["rows"][0]["mobile_number"])
            other = satellite_participant_table(None, 1, 1, satellite="directory:1", query=query)
            self.assertEqual([], other["rows"])
