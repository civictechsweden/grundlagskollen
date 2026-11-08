"""Source provenance and matching rules, independent of current case IDs."""

import json
import unittest

from scripts import build_dataset as builder


class SourceDataTests(unittest.TestCase):
    def test_notices_use_source_wording_and_switch_after_chamber_decision(self):
        status = {"dokuppgift": {"uppgift": [
            {"kod": "notis", "text": "<p>Riksdagen sa ja.</p>", "namn": "Beslut i korthet"},
            {"kod": "notisrubrik", "text": "Beslutets rubrik"},
            {"kod": "utsknotis", "text": "<p>Utskottet föreslår ja.</p>"},
            {"kod": "utsknotisrubrik", "text": "Utskottets rubrik"},
        ]}}
        pending = builder.source_summary(status, "", "NEW-REPORT", False)
        completed = builder.source_summary(status, "", "NEW-REPORT", True)
        self.assertEqual(pending["text"], "Utskottet föreslår ja.")
        self.assertEqual(pending["title"], "Utskottets rubrik")
        self.assertIn("kod=utsknotis", pending["sourceField"])
        self.assertEqual(completed["text"], "Riksdagen sa ja.")
        self.assertEqual(completed["title"], "Beslutets rubrik")
        self.assertEqual(completed["documentId"], "NEW-REPORT")

    def test_missing_notice_uses_exact_summary_section(self):
        source = "Header\nSammanfattning\n\nFörslaget gäller regeringsformen.\n\nBehandlade förslag\nOther text"
        summary = builder.source_summary({}, source, "UNFAMILIAR", False)
        self.assertEqual(summary["text"], "Förslaget gäller regeringsformen.")
        self.assertEqual(summary["sourceField"], "Sammanfattning")

    def test_missing_or_unbounded_summary_is_not_invented(self):
        self.assertIsNone(builder.source_summary({}, "No summary", "NEW", False))
        self.assertIsNone(builder.source_summary({}, "Sammanfattning\nNo end heading", "NEW", False))

    def test_explicit_links_exclude_background_references_and_accept_plural(self):
        source = ("Background: bet. 2009/10:KU19\nBehandlade förslag\n\n"
                  "Vilande förslag beslutade den 1 juni 2022 till lag om ändring i regeringsformen "
                  "(bet. 2021/22:KU15, rskr. 2021/22:341).\n\nInnehållsförteckning\nMore text")
        link, = builder.first_decision_links(source, "REPORT")
        self.assertEqual(link["citation"], "2021/22:KU15")
        self.assertEqual(link["date"], "2022-06-01")
        self.assertIn(link["evidence"], source)
        self.assertEqual(link["sourceField"], "Behandlade förslag")

    def test_explicit_first_citation_wins_over_shared_background_references(self):
        citation = {"kind": "proposition", "value": "2021/22:41", "normalized": "2021/22:41"}
        first = {"documentId": "UNKNOWN-FIRST", "kind": "bet", "riksmote": "2021/22", "designation": "KU15",
                 "title": "Source title", "decisionDate": "2022-06-01", "constitutionIds": ["rf"],
                 "documentUrl": "https://example.test/first", "citations": [citation],
                 "classification": {"stage": "first", "outcome": None}}
        decoy = {**first, "documentId": "DECOY", "designation": "KU16"}
        text = "Behandlade förslag\nVilande förslag beslutade den 1 juni 2022 till lag om ändring i regeringsformen (bet. 2021/22:KU15).\nInnehållsförteckning"
        final = {**first, "documentId": "UNKNOWN-FOLLOW-UP", "riksmote": "2022/23", "designation": "KU9",
                 "decisionDate": "2022-11-23", "decisionCompleted": True,
                 "firstDecisionLinks": builder.first_decision_links(text, "UNKNOWN-FOLLOW-UP"),
                 "classification": {"stage": "final", "outcome": "adopted"}}
        by_id = {item["firstDecision"]["documentId"]: item for item in builder.pair_decisions([first, decoy, final])}
        self.assertEqual(by_id["UNKNOWN-FIRST"]["status"], "adopted")
        self.assertEqual(by_id["UNKNOWN-FIRST"]["match"]["method"], "explicit_first_decision_citation")
        self.assertIsNone(by_id["DECOY"]["finalDecision"])

    def test_snapshot_contains_no_editorial_case_fields(self):
        snapshot = json.loads((builder.DATA / "changes.json").read_text())
        for proposal in snapshot["proposals"]:
            with self.subTest(proposal=proposal["proposalId"]):
                self.assertFalse({"shortTitle", "summary", "details", "editorialNote", "proposedEffectiveDate", "contextSources"}.intersection(proposal))


if __name__ == "__main__":
    unittest.main()
