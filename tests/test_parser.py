"""Regression tests for operative constitutional-decision classification."""

from __future__ import annotations

import unittest

from scripts.build_dataset import classify, protocol_decision_signals


class ParserRegressionTests(unittest.TestCase):
    def test_historical_first_decision_wording(self) -> None:
        cases = (
            (
                "DH10KU19",
                "Konstitutionsutskottets utlåtande Nr 19",
                "Hemställan\nPå grund av det anförda får utskottet alltså hemställa, att riksdagen måtte såsom vilande till vidare grundlagsenlig behandling antaga följande förslag till ändrad lydelse av §§ 6 och 7 successionsordningen.",
            ),
            (
                "DX10KU35",
                "Konstitutionsutskottets utlåtande Nr 35",
                "Hemställan\nUtskottet finner förslaget böra bifallas och hemställer alltså, att riksdagen såsom vilande för vidare grundlagsenlig behandling måtte antaga följande förslag till ändrad lydelse av § 5 successionsordningen.",
            ),
            (
                "E910KU11",
                "Konstitutionsutskottets utlåtande nr 11",
                "Hemställan\nUtskottet hemställer, att riksdagen måtte såsom vilande antaga följande förslag till ändrad lydelse av § 2 successionsordningen.",
            ),
            (
                "EP10KU19",
                "Konstitutionsutskottets utlåtande nr 19 år 1964",
                "Hemställan\nUtskottet hemställer, att riksdagen måtte såsom vilande för vidare grundlagsenlig behandling antaga följande förslag till ändrad lydelse av § 2 successionsordningen.",
            ),
            (
                "FW01KU26",
                "Konstitutionsutskottets betänkande",
                "Hemställan\nUtskottet hemställer\nG. att riksdagen såsom vilande för vidare grundlagsenlig behandling antar de i bilaga 1 intagna grundlagsförslagen.\nBilaga 1",
            ),
            (
                "G101KU36",
                "Konstitutionsutskottets betänkande",
                "Hemställan\n3. att riksdagen som vilande antar den ändrade lydelse av § 4 successionsordningen som föreslås i propositionen.\n4. att riksdagen som vilande antar propositionens förslag till lag om ändring i successionsordningen.",
            ),
        )
        for document_id, title, text in cases:
            with self.subTest(document_id=document_id):
                result = classify(title, text, "bet")
                self.assertEqual(result["stage"], "first")
                self.assertTrue(result["firstPendingDecision"])
                self.assertTrue(result["firstSignals"])

    def test_reservation_does_not_create_first_decision(self) -> None:
        result = classify(
            "Konstitutionsutskottets betänkande",
            "Hemställan\nUtskottet hemställer att riksdagen avslår motionen.\nNärvarande\nReservation\nRiksdagen såsom vilande antager motionens förslag till ändring i regeringsformen.",
            "bet",
        )
        self.assertFalse(result["firstPendingDecision"])
        self.assertEqual(result["stage"], "candidate")

    def test_historical_final_report_is_not_chamber_outcome(self) -> None:
        result = classify(
            "Konstitutionsutskottets memorial Nr 4",
            "Till slutligt beslut anmäles det vid föregående riksdag såsom vilande antagna förslaget till ändrad lydelse av successionsordningen.",
            "bet",
        )
        self.assertEqual(result["stage"], "final")
        self.assertEqual(result["outcome"], "unresolved")

    def test_riksdagsskrivelse_final_wording_is_adoption(self) -> None:
        result = classify(
            "Riksdagens skrivelse",
            "Successionsordningen har riksdagen numera förehaft till slutligt avgörande och antagit förslaget.",
            "skr",
        )
        self.assertEqual(result["stage"], "final")
        self.assertEqual(result["outcome"], "adopted")
        self.assertTrue(result["finalAdoptSignals"])

    def test_old_protocol_yes_proposition_is_adoption(self) -> None:
        title = "Riksdagens protokoll"
        text = (
            "Vilande förslag till ändring i successionsordningen. "
            "Propositioner gavs på antagande eller förkastande. "
            "Antog kammaren förevarande förslag."
        )
        result = classify(title, text, "prot")
        self.assertEqual(result["stage"], "final")
        self.assertEqual(result["outcome"], "adopted")

    def test_conditional_no_proposition_is_not_rejection(self) -> None:
        adopted, rejected = protocol_decision_signals(
            "Riksdagens protokoll",
            "Vilande förslag till ändring i successionsordningen. Vinner Nej, har kammaren förkastat förslaget.",
            "prot",
        )
        self.assertEqual(adopted, [])
        self.assertEqual(rejected, [])

    def test_historical_ocr_protocol_rejection_and_vote(self) -> None:
        result = classify(
            "RIKSDAGENS PROTOKOLL",
            "Det från 1896 års riksdag hvilande förslaget om ändring i 2 § 4:o tryckfrihetsförordningen skall antagas. Vinner nej, har kammaren förkastat nämnda förslag. Omröstningen visade 77 ja, men 134 nej; och hade sålunda det ifrågavarande förslaget af kammaren förkastats.",
            "prot",
        )
        self.assertEqual(result["stage"], "final")
        self.assertEqual(result["outcome"], "rejected")


if __name__ == "__main__":
    unittest.main()
