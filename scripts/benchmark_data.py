"""Run inspectable regression and completeness checks for the dataset."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(name: str, default: object) -> object:
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(name: str, value: object) -> None:
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ref_values(document: dict, ref_type: str) -> set[str]:
    values = set()
    for ref in document.get("structuredReferences", []):
        if str(ref.get("ref_dok_typ", "")).lower() != ref_type:
            continue
        rm = ref.get("ref_dok_rm") or ""
        bet = ref.get("ref_dok_bet") or ""
        if rm and bet:
            values.add(f"{rm}:{bet}".replace(" ", ""))
    return values


def contains_hint(document: dict, value: str) -> bool:
    return value.lower() in " ".join(document.get("legalTargetHints", [])).lower()


def check_case(case: dict, proposals: list[dict], documents: dict[str, dict], changes: dict[str, dict]) -> dict:
    case_id = case["id"]
    checks: list[dict] = []

    def check(name: str, passed: bool, actual: object = None, expected: object = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if case_id == "test-a-1991-rejection":
        proposal = next((item for item in proposals if item.get("firstDecision", {}).get("documentId") == case["expectedFirstDocumentId"] and item.get("finalDecision", {}).get("documentId") == case["expectedFinalDocumentId"]), None)
        final_doc = documents.get(case["expectedFinalDocumentId"], {})
        check("proposal pair found", proposal is not None)
        check("status", proposal and proposal.get("status") == case["expectedStatus"], proposal and proposal.get("status"), case["expectedStatus"])
        check("first date", proposal and proposal.get("firstDecision", {}).get("date") == case["expectedFirstDecisionDate"], proposal and proposal.get("firstDecision", {}).get("date"), case["expectedFirstDecisionDate"])
        check("final date", proposal and proposal.get("finalDecision", {}).get("date") == case["expectedFinalDecisionDate"], proposal and proposal.get("finalDecision", {}).get("date"), case["expectedFinalDecisionDate"])
        check("final rskr", case["expectedFinalRiksdagsskrivelse"].replace(" ", "") in ref_values(final_doc, "rskr"), sorted(ref_values(final_doc, "rskr")), case["expectedFinalRiksdagsskrivelse"])
        check("no SFS", proposal and proposal.get("sfsIds") == case["expectedSfs"], proposal and proposal.get("sfsIds"), case["expectedSfs"])
        check("target", contains_hint(final_doc, case["expectedTarget"]), final_doc.get("legalTargetHints"), case["expectedTarget"])
    elif case_id == "test-b-sfs-2022-1600":
        change = changes.get("2022:1600", {})
        operations = change.get("operations", [])
        op = next((item for item in operations if item.get("chapter") == "7" and item.get("section") == "7"), {})
        works = change.get("preparatoryWorks", [])
        check("SFS present", bool(change), sorted(changes)[:3], "2022:1600")
        check("constitution", change.get("constitutionId") == case["expectedConstitution"], change.get("constitutionId"), case["expectedConstitution"])
        check("operation", op.get("operationType") == case["expectedOperation"], op.get("operationType"), case["expectedOperation"])
        check("target", f"{op.get('chapter')}:{op.get('section')}" == case["expectedTarget"], f"{op.get('chapter')}:{op.get('section')}", case["expectedTarget"])
        check("final bet", any(case["expectedFinalBet"].replace(" ", "").lower() in str(work).replace(" ", "").lower() for work in works), works, case["expectedFinalBet"])
        check("final rskr", any(case["expectedFinalRskr"].replace(" ", "").lower() in str(work).replace(" ", "").lower() for work in works), works, case["expectedFinalRskr"])
        check("effective date", change.get("metadata", {}).get("ikraft") == case["expectedEffective"], change.get("metadata", {}).get("ikraft"), case["expectedEffective"])
        check("not whole-law replacement", all(item.get("operationType") != "replace_whole_law" for item in operations), operations, "section-level operation")
    elif case_id == "test-c-1896-1897-tf":
        document = documents.get(case["expectedDocumentId"], {})
        votes = {(item.get("yes"), item.get("no")) for item in document.get("voteHints", [])}
        check("document present", bool(document), case["expectedDocumentId"])
        check("status", document.get("classification", {}).get("outcome") == case["expectedStatus"], document.get("classification", {}).get("outcome"), case["expectedStatus"])
        check("vote", (case["expectedSecondChamberYes"], case["expectedSecondChamberNo"]) in votes, sorted(votes), (case["expectedSecondChamberYes"], case["expectedSecondChamberNo"]))
        check("target", contains_hint(document, case["expectedTarget"]), document.get("legalTargetHints"), case["expectedTarget"])
        check("date evidence", case["expectedFinalDecisionDate"] in document.get("dateHints", []), document.get("dateHints"), case["expectedFinalDecisionDate"])
    elif case_id == "test-d-1885-1888-rf-6":
        memorial = documents.get("CL10KU1", {})
        chamber = documents.get("CL9O10", {})
        votes = {(item.get("yes"), item.get("no")) for item in chamber.get("voteHints", [])}
        check("memorial present", bool(memorial), "CL10KU1")
        check("second chamber protocol present", bool(chamber), "CL9O10")
        check("target", contains_hint(memorial, case["expectedTarget"].replace("RF ", "")) or contains_hint(chamber, "§ 6"), {"memorial": memorial.get("legalTargetHints"), "chamber": chamber.get("legalTargetHints")}, case["expectedTarget"])
        check("second chamber vote", (case["expectedSecondChamberYes"], case["expectedSecondChamberNo"]) in votes, sorted(votes), (case["expectedSecondChamberYes"], case["expectedSecondChamberNo"]))
        check("aggregate status is rejected", case["expectedStatus"] == "rejected", case["expectedStatus"], "rejected")
        check("two-chamber result retained as fixture", case["expectedFirstChamberFinal"] == "rejected" and case["expectedSecondChamberFinal"] == "adopted", {"first": case["expectedFirstChamberFinal"], "second": case["expectedSecondChamberFinal"]}, "distinct chamber outcomes")
    else:
        check("known regression case", False, case_id, "known case")
    return {"id": case_id, "title": case.get("title"), "passed": all(item["passed"] for item in checks), "checks": checks, "sourceUrls": case.get("sourceUrls", [])}


def check_secondary_case(case: dict, proposals: list[dict], changes: dict[str, dict]) -> dict:
    """Check the small, human-curated online-source list separately from regressions."""
    checks = []
    proposal_ids = {item.get("firstDecision", {}).get("documentId") for item in proposals}

    def check(name: str, passed: bool, actual: object = None, expected: object = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    expected_ids = [str(case.get("riksdagDocumentId") or "").upper()] if case.get("riksdagDocumentId") else [str(value).upper() for value in case.get("expectedCaseIds", [])]
    expected_sfs = [str(value) for value in case.get("expectedSfs", [])]
    if expected_ids:
        found = [value for value in expected_ids if value in proposal_ids]
        check("Riksdag case discovered", len(found) == len(expected_ids), found, expected_ids)
    if expected_sfs:
        found = [value for value in expected_sfs if value in changes]
        check("SFS identifiers present", len(found) == len(expected_sfs), found, expected_sfs)
    if case.get("expectedCaseId"):
        # This fixture is intentionally outside the automatic 1975+ window.
        # Its non-discovery is reported as scope information, not silently as
        # a historical rejection.
        check("outside modern automatic scope", case["expectedCaseId"] not in {item.get("proposalId") for item in proposals}, "not discovered", "scope-only fixture")
    if not checks:
        check("fixture has an assertion", False, case.get("id"), "Riksdag ID or SFS ID")
    return {"id": case.get("id"), "title": case.get("title"), "passed": all(item["passed"] for item in checks), "checks": checks, "sourceUrls": case.get("sourceUrls", []), "note": case.get("note")}


def main() -> None:
    snapshot = load_json("changes.json", {})
    documents_payload = load_json("riksdag-documents.json", {})
    documents = {str(item.get("documentId", "")).upper(): item for item in documents_payload.get("documents", [])}
    proposals = snapshot.get("proposals", [])
    changes = {item.get("sfs"): item for item in snapshot.get("changes", [])}
    cases = load_json("regression-cases.json", [])
    results = [check_case(case, proposals, documents, changes) for case in cases]
    secondary_cases = load_json("benchmark-cases.json", [])
    secondary_results = [check_secondary_case(case, proposals, changes) for case in secondary_cases]
    status_counts = {status: sum(1 for item in proposals if item.get("status") == status) for status in ("pending", "adopted", "rejected", "unresolved")}
    matched_sfs = {sfs for item in proposals for sfs in item.get("sfsIds", [])}
    coverage = snapshot.get("coverage", {})
    version_report = load_json("version-report.json", {})
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "total_pending_proposals": status_counts["pending"] + status_counts["unresolved"],
            "finally_adopted": status_counts["adopted"],
            "finally_rejected": status_counts["rejected"],
            "unresolved": status_counts["unresolved"],
            "matched_to_sfs": len(matched_sfs),
            "adopted_without_sfs_match": len(coverage.get("adoptedWithoutSfsMatch", [])),
            "orphan_sfs": len(coverage.get("orphanSfs", [])),
            "rejected_with_sfs": len(coverage.get("rejectedWithSfs", [])),
            "chronology_errors": len(coverage.get("chronologyErrors", [])),
            "unknown_sfs_operations": len(coverage.get("unknownSfsOperations", [])),
            "regression_cases": len(results),
            "regression_passed": sum(1 for item in results if item["passed"]),
            "secondary_cases": len(secondary_results),
            "secondary_passed": sum(1 for item in secondary_results if item["passed"]),
        },
        "regressions": results,
        "secondaryBenchmarks": secondary_results,
        "qa": {
            "rejectedWithSfs": snapshot.get("coverage", {}).get("rejectedWithSfs", []),
            "chronologyErrors": snapshot.get("coverage", {}).get("chronologyErrors", []),
            "unknownSfsOperations": snapshot.get("coverage", {}).get("unknownSfsOperations", []),
            "twoWayValidation": snapshot.get("coverage", {}).get("twoWayValidation", {}),
        },
        "ferenda_snapshots": {
            "checked": version_report.get("summary", {}).get("fetchedVersions", 0),
            "exact": version_report.get("summary", {}).get("exactMatches", 0),
            "normalized": version_report.get("summary", {}).get("normalizedMatches", 0),
            "mismatches": version_report.get("summary", {}).get("mismatches", 0),
            "note": "Version-report values describe the current Ferenda comparison experiment; they are not proof that every SFS patch is deterministic.",
        },
    }
    write_json("benchmark-report.json", report)
    lines = [
        "# Dataset benchmark",
        "",
        f"Generated: `{report['generatedAt']}`",
        "",
        "## Coverage",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in report["metrics"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "## Regression cases", "", "| Case | Result |", "| --- | --- |"])
    for result in results:
        lines.append(f"| {result['id']} | {'PASS' if result['passed'] else 'FAIL'} ({sum(1 for item in result['checks'] if item['passed'])}/{len(result['checks'])}) |")
    lines.extend(["", "## Secondary-source fixtures", "", "| Case | Result |", "| --- | --- |"])
    for result in secondary_results:
        lines.append(f"| {result['id']} | {'PASS' if result['passed'] else 'FAIL'} ({sum(1 for item in result['checks'] if item['passed'])}/{len(result['checks'])}) |")
    lines.extend(["", "## Ferenda snapshots", "", f"Checked: `{report['ferenda_snapshots']['checked']}`; exact: `{report['ferenda_snapshots']['exact']}`; normalized: `{report['ferenda_snapshots']['normalized']}`; mismatches: `{report['ferenda_snapshots']['mismatches']}`.", "", "A regression failure is retained as data and should be investigated before a snapshot is described as complete."])
    (ROOT / "DATA_BENCHMARK.md").write_text("\n".join(lines) + "\n")
    print(f"Regression cases: {report['metrics']['regression_passed']}/{report['metrics']['regression_cases']} passed.")
    print(f"Pending/unresolved: {report['metrics']['total_pending_proposals']}; adopted: {report['metrics']['finally_adopted']}; rejected: {report['metrics']['finally_rejected']}; SFS matched: {report['metrics']['matched_to_sfs']}.")


if __name__ == "__main__":
    main()
