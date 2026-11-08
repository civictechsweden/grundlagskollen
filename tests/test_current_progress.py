"""Guard the distinction between committee proposals and chamber decisions."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_dataset as builder


class CurrentProgressTests(unittest.TestCase):
    def report(self, document_id, chamber_status, chamber_date):
        return {
            "dokumentstatus": {
                "dokument": {"dok_id": document_id, "doktyp": "bet", "rm": "2026/27", "beteckning": "KU9",
                             "titel": "Ändring i regeringsformen (vilande grundlagsförslag)", "datum": "2026-11-05"},
                "dokaktivitet": {"aktivitet": [
                    {"kod": "JUS", "datum": "2026-11-05", "status": "inträffat"},
                    {"kod": "BEH", "datum": chamber_date, "status": chamber_status},
                    {"kod": "BES", "datum": chamber_date, "status": chamber_status},
                ]},
                "dokutskottsforslag": {"utskottsforslag": {"forslag": "Riksdagen antar slutligt det vilande förslaget.", "vinnare": "utskottet"}},
            },
        }

    def extract(self, chamber_status="planerat", chamber_date="2099-11-11"):
        text = "Utskottets förslag till riksdagsbeslut\nRiksdagen antar slutligt det vilande förslaget till lag om ändring i regeringsformen.\nStockholm den 5 november 2026"
        with patch.object(builder, "fetch_riksdag_text", return_value=(text, "https://example.test/text")), \
             patch.object(builder, "fetch_json", return_value=self.report("HE01KU9", chamber_status, chamber_date)):
            return builder.extract_document("HE01KU9", ["test"])

    def first(self):
        return {"documentId": "HD01KU34", "title": "Grundlagsförslaget", "kind": "bet", "decisionDate": "2026-05-20",
                "documentUrl": "https://example.test/first", "constitutionIds": ["rf"], "classification": {"stage": "first", "outcome": None}}

    def test_planned_vote_is_not_a_final_decision(self):
        final = self.extract()
        self.assertFalse(final["decisionCompleted"])
        self.assertEqual(final["classification"]["outcome"], "unresolved")
        self.assertNotEqual(final["decisionDate"], "2099-11-11")
        proposal = builder.proposal_record(self.first(), final, 50)
        self.assertEqual(proposal["status"], "pending")
        self.assertIsNone(proposal["finalDecision"])
        self.assertEqual(proposal["nextDecision"]["date"], "2099-11-11")
        self.assertIn("HE01KU9", proposal["documentIds"])

    def test_committee_recommendation_is_preserved_before_chamber_vote(self):
        final = self.extract()
        progress = builder.proposal_record(self.first(), final, 50)["parliamentaryProgress"]
        self.assertEqual(progress["committee"], {"date": "2026-11-05", "status": "completed", "recommendation": "adopt"})
        self.assertEqual(progress["chamber"]["status"], "planned")
        self.assertEqual(progress["debate"]["status"], "planned")

    def test_elapsed_calendar_date_does_not_prove_a_vote_happened(self):
        final = self.extract(chamber_date="2026-11-04")
        self.assertFalse(final["decisionCompleted"])
        self.assertEqual(final["parliamentaryProgress"]["chamber"]["status"], "planned")

    def test_future_date_marked_occurred_is_not_accepted(self):
        final = self.extract(chamber_status="inträffat")
        self.assertFalse(final["decisionCompleted"])
        self.assertEqual(final["parliamentaryProgress"]["chamber"]["status"], "unconfirmed")

    def test_completed_chamber_vote_can_be_adopted(self):
        final = self.extract(chamber_status="inträffat", chamber_date="2026-11-04")
        proposal = builder.proposal_record(self.first(), final, 50)
        self.assertEqual(proposal["status"], "adopted")
        self.assertEqual(proposal["finalDecision"]["date"], "2026-11-04")
        self.assertEqual(proposal["parliamentaryProgress"]["chamber"]["status"], "completed")

    def test_completed_recent_first_vote_stays_pending_before_follow_up_exists(self):
        first = {**self.first(), "documentId": "UNFAMILIAR-FIRST", "decisionCompleted": True}
        proposal, = builder.pair_decisions([first])
        self.assertEqual(proposal["status"], "pending")
        self.assertIsNone(proposal["finalDecision"])
        self.assertEqual(proposal["firstDecision"]["documentId"], "UNFAMILIAR-FIRST")

    def test_completed_decision_needs_no_editorial_seed(self):
        first = self.first()
        final = self.extract(chamber_status="inträffat", chamber_date="2026-11-04")
        first["citations"] = final["citations"] = [{"kind": "proposition", "value": "2025/26:78", "normalized": "2025/26:78"}]
        proposal, = builder.pair_decisions([first, final])
        self.assertEqual(proposal["status"], "adopted")
        self.assertEqual(proposal["finalDecision"]["documentId"], "HE01KU9")
        self.assertNotIn("summary", proposal)

    def test_opposition_win_does_not_inherit_committee_recommendation(self):
        status = self.report("HE01KU9", "inträffat", "2026-11-04")
        status["dokumentstatus"]["dokutskottsforslag"]["utskottsforslag"]["vinnare"] = "motförslaget"
        text = "Utskottets förslag till riksdagsbeslut\nRiksdagen antar slutligt det vilande förslaget till lag om ändring i regeringsformen.\nStockholm"
        with patch.object(builder, "fetch_riksdag_text", return_value=(text, "https://example.test/text")), \
             patch.object(builder, "fetch_json", return_value=status):
            final = builder.extract_document("HE01KU9", ["test"])
        self.assertEqual(final["classification"]["outcome"], "unresolved")
        first = self.first()
        first["citations"] = final["citations"] = [{"kind": "proposition", "value": "2025/26:78", "normalized": "2025/26:78"}]
        proposal, = builder.pair_decisions([first, final])
        self.assertEqual(proposal["status"], "unresolved")
        self.assertIsNotNone(proposal["finalDecision"])
        self.assertEqual(proposal["parliamentaryProgress"]["committee"]["recommendation"], "adopt")

    def test_expired_discovery_cache_is_refetched(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(builder, "CACHE", Path(directory)):
                path = builder.cache_path("https://example.test/list", ".json")
                path.write_text('{"stale":true}')
                with patch.object(builder, "urlopen") as request:
                    request.return_value.__enter__.return_value.read.return_value = b'{"fresh":true}'
                    self.assertEqual(builder.fetch_json("https://example.test/list", max_age=0), {"fresh": True})
                    request.assert_called_once()

    def test_current_snapshot_has_seven_distinct_cases_and_intermediate_steps(self):
        snapshot = json.loads((builder.DATA / "changes.json").read_text())
        by_first = {item["firstDecision"]["documentId"]: item for item in snapshot["proposals"]}
        expected = {"HA01KU32": "HE01KU2", "HB01KU22": "HE01KU3", "HD01KU2": "HE01KU4",
                    "HD01KU8": "HE01KU6", "HD01KU32": "HE01KU7", "HD01KU33": "HE01KU8", "HD01KU34": "HE01KU9"}
        for first_id, second_id in expected.items():
            with self.subTest(first_id=first_id):
                proposal = by_first[first_id]
                self.assertEqual(proposal["parliamentaryProgress"]["documentId"], second_id)
                self.assertEqual(proposal["match"]["method"], "explicit_first_decision_citation")
                self.assertEqual(proposal["parliamentaryProgress"]["committee"]["status"], "completed")
                self.assertIn(proposal["status"], {"pending", "adopted", "rejected"})
                if proposal["status"] == "pending":
                    self.assertIsNone(proposal["finalDecision"])
                    self.assertEqual(proposal["parliamentaryProgress"]["chamber"]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
