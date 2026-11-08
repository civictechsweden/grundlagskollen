"""Validate recent first/second decision chains against Riksdag source records.

Use --refresh to rediscover the full window through the public API before
checking it. Expected report IDs and outcomes are never supplied by a case list.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

if __package__:
    from . import build_dataset as builder, refresh_current
else:
    import build_dataset as builder
    import refresh_current


def validate(from_year: int) -> dict:
    snapshot = json.loads((builder.DATA / "changes.json").read_text())
    documents = json.loads((builder.DATA / "riksdag-documents.json").read_text())["documents"]
    reports = [item for item in documents if item.get("kind") == "bet"
               and item.get("classification", {}).get("stage") == "final"
               and (item.get("publishedDate") or "") >= f"{from_year}-01-01"]
    cases = []
    for report in reports:
        checks = []

        def check(name: str, passed: bool) -> None:
            checks.append({"name": name, "passed": bool(passed)})

        linked = [item for item in snapshot["proposals"] if report["documentId"] in item.get("documentIds", [])]
        check("first decision explicitly cited", bool(report.get("firstDecisionLinks")))
        check("follow-up linked to a first decision", bool(linked))
        for proposal in linked:
            check("first report and date match explicit citation", proposal["match"]["method"] == "explicit_first_decision_citation")
            check("committee and chamber stages present", bool(proposal.get("parliamentaryProgress", {}).get("committee"))
                  and bool(proposal.get("parliamentaryProgress", {}).get("chamber")))
            source = proposal.get("sourceText", {})
            check("source text has attribution", bool(source.get("sourceUrl")) and bool(source.get("sourceField")))
            check("no editorial fields", not {"shortTitle", "summary", "details", "proposedEffectiveDate", "contextSources"}.intersection(proposal))
            if report.get("decisionCompleted"):
                check("chamber result retained", bool(proposal.get("finalDecision")))
                status = builder.fetch_json(f"{builder.RIKSDAG_DOCUMENT}{report['documentId']}.json")["dokumentstatus"]
                fields = {item.get("kod"): item.get("text") for item in builder.unwrap(status, "dokuppgift", "uppgift")}
                # The API's chamber wording is independent of the committee
                # recommendation parser used by the matching pipeline.
                if fields.get("rdbeslut") == "Kammaren biföll utskottets förslag.":
                    check("outcome agrees with recorded chamber decision", proposal["status"] == "adopted")
                if source.get("kind") == "decision_notice":
                    check("decision text matches API notice", source["text"] == builder.plain_source_text(fields.get("notis", "")))
            else:
                check("planned chamber event remains pending", proposal["status"] == "pending" and proposal.get("finalDecision") is None)
                check("planned date matches source activity", proposal.get("nextDecision", {}).get("date") == report.get("plannedDecisionDate"))
        cases.append({"documentId": report["documentId"], "sourceUrl": report["documentUrl"],
                      "firstDecisionIds": [item["firstDecision"]["documentId"] for item in linked],
                      "passed": all(item["passed"] for item in checks), "checks": checks})
    return {"generatedAt": builder.now(), "fromYear": from_year,
            "discoveryQueries": ["vilande", "grundlagsbeslut"],
            "reportsChecked": len(cases), "reportsPassed": sum(item["passed"] for item in cases),
            "passed": bool(cases) and all(item["passed"] for item in cases), "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=datetime.now(timezone.utc).year - 10)
    parser.add_argument("--refresh", action="store_true", help="Rediscover and refresh all KU candidates in the validation window")
    args = parser.parse_args()
    if args.refresh:
        refresh_current.main(since=f"{args.from_year}-01-01")
    report = validate(args.from_year)
    (builder.DATA / "recent-validation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Recent decision chains: {report['reportsPassed']}/{report['reportsChecked']} reports passed since {args.from_year}.")
    for case in report["cases"]:
        if not case["passed"]:
            print(case["documentId"], [item["name"] for item in case["checks"] if not item["passed"]])
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
