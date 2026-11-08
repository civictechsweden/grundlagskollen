"""Source provenance and matching rules, independent of current case IDs."""

import json
import unittest

from scripts import build_dataset as builder


class SourceDataTests(unittest.TestCase):
    def test_printed_versions_use_official_archives_within_their_coverage(self):
        self.assertEqual(builder.printed_sfs_url("2022:1566"), "https://svenskforfattningssamling.se/doc/20221566.html")
        self.assertEqual(builder.printed_sfs_url("2018:160"), "https://svenskforfattningssamling.se/doc/2018160.html")
        self.assertEqual(builder.printed_sfs_url("2018:159"), "https://rkrattsdb.gov.se/SFSdoc/18/180159.PDF")
        self.assertEqual(builder.printed_sfs_url("2002:905"), "https://rkrattsdb.gov.se/SFSdoc/02/020905.PDF")
        self.assertEqual(builder.printed_sfs_url("1998:306"), "https://rkrattsdb.gov.se/SFSdoc/98/980306.PDF")
        self.assertIsNone(builder.printed_sfs_url("1998:305"))
        self.assertIsNone(builder.printed_sfs_url("1976:871"))
        self.assertIsNone(builder.printed_sfs_url("invalid"))

    def test_comparisons_fix_both_versions_and_use_numeric_sfs_order(self):
        law_uri = "https://lagen.nu/1974:152"
        versions = {sfs: {} for sfs in ["2022:1600", "2018:1903", "2022:1566"]}
        self.assertEqual(builder.version_comparison_urls(law_uri, versions), {
            "2022:1566": f"{law_uri}/konsolidering/2022:1566?diff=2018%3A1903",
            "2022:1600": f"{law_uri}/konsolidering/2022:1600?diff=2022%3A1566",
        })
        self.assertEqual(builder.version_comparison_urls(law_uri, {"2022:10": {}, "2022:9": {}}), {
            "2022:10": f"{law_uri}/konsolidering/2022:10?diff=2022%3A9",
        })
        self.assertEqual(builder.version_comparison_urls(law_uri, {}), {})
        self.assertEqual(builder.version_comparison_urls(law_uri, {"2022:1600": {}}), {})

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

    def test_source_html_retains_paragraphs_and_list_items(self):
        markup = '<p>Förslaget innebär följande:</p><ul><li>Första punkten.</li><li>Andra punkten.</li></ul><p>Lagändringen träder i kraft.</p>'
        status = {"dokuppgift": {"uppgift": {"kod": "notis", "text": markup}}}
        summary = builder.source_summary(status, "", "SOURCE", True)
        self.assertEqual(summary["html"], markup)
        self.assertIn("Första punkten.", summary["text"])
        self.assertNotIn("<li>", summary["text"])

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
