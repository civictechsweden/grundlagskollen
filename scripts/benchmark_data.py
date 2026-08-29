"""Benchmark the generated constitutional-change snapshot against static cases.

The benchmark is deliberately small and inspectable. It measures whether known
cases are present and whether the expected SFS identifiers are present; it does
not pretend that a finite fixture proves completeness of all Swedish
constitutional history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


snapshot = json.loads((DATA / "changes.json").read_text())
fixtures = json.loads((DATA / "benchmark-cases.json").read_text())
changes = snapshot.get("changes", [])
pending = snapshot.get("pending", [])
aborted = snapshot.get("aborted", [])

pending_by_id = {str(item.get("riksdagDocumentId", "")).upper(): item for item in pending}
confirmed_sfs = {item.get("sfs") for item in changes}
aborted_by_id = {item.get("id"): item for item in aborted}

case_results: list[dict] = []
expected_units = 0
matched_units = 0

for fixture in fixtures:
    expected_status = fixture.get("expectedStatus")
    if fixture.get("expectedCaseIds"):
        expected_ids = [str(value).upper() for value in fixture["expectedCaseIds"]]
        found_ids = [value for value in expected_ids if value in pending_by_id]
        missing_ids = [value for value in expected_ids if value not in pending_by_id]
        expected_units += len(expected_ids)
        matched_units += len(found_ids)
        case_results.append({
            "id": fixture["id"],
            "expectedStatus": expected_status,
            "status": "matched" if not missing_ids else "partial",
            "expected": len(expected_ids),
            "matched": len(found_ids),
            "missing": missing_ids,
            "sourceUrls": fixture.get("sourceUrls", []),
        })
        continue

    if expected_status == "pending-first-vote":
        expected_id = str(fixture.get("riksdagDocumentId", "")).upper()
        matched = expected_id in pending_by_id
        expected_units += 1
        matched_units += int(matched)
        case_results.append({
            "id": fixture["id"],
            "expectedStatus": expected_status,
            "status": "matched" if matched else "missing",
            "expectedId": expected_id,
            "sourceUrls": fixture.get("sourceUrls", []),
        })
        continue

    if expected_status == "confirmed":
        expected_sfs = fixture.get("expectedSfs", [])
        found_sfs = [sfs for sfs in expected_sfs if sfs in confirmed_sfs]
        missing_sfs = [sfs for sfs in expected_sfs if sfs not in confirmed_sfs]
        expected_units += len(expected_sfs)
        matched_units += len(found_sfs)
        case_results.append({
            "id": fixture["id"],
            "expectedStatus": expected_status,
            "status": "matched" if not missing_sfs else "partial",
            "expectedSfs": expected_sfs,
            "matchedSfs": found_sfs,
            "missingSfs": missing_sfs,
            "sourceUrls": fixture.get("sourceUrls", []),
        })
        continue

    if expected_status == "aborted":
        expected_id = fixture.get("expectedCaseId")
        matched = expected_id in aborted_by_id
        expected_units += 1
        matched_units += int(matched)
        case_results.append({
            "id": fixture["id"],
            "expectedStatus": expected_status,
            "status": "matched" if matched else "missing",
            "expectedId": expected_id,
            "sourceUrls": fixture.get("sourceUrls", []),
        })

pending_fixture = next((item for item in fixtures if item.get("id") == "benchmark-2026-current-queue"), {})
expected_pending_ids = {str(value).upper() for value in pending_fixture.get("expectedCaseIds", [])}
generated_pending_ids = set(pending_by_id)
unexpected_pending_ids = sorted(generated_pending_ids - expected_pending_ids)

report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "snapshotGeneratedAt": snapshot.get("generatedAt"),
    "fixtureCount": len(fixtures),
    "caseResults": case_results,
    "metrics": {
        "evidenceRecall": {"matched": matched_units, "expected": expected_units, "rate": round(matched_units / expected_units, 4) if expected_units else None},
        "currentPendingRecall": {"matched": len(generated_pending_ids & expected_pending_ids), "expected": len(expected_pending_ids), "rate": round(len(generated_pending_ids & expected_pending_ids) / len(expected_pending_ids), 4) if expected_pending_ids else None},
        "currentPendingPrecisionAgainstFixture": {"matched": len(generated_pending_ids - set(unexpected_pending_ids)), "generated": len(generated_pending_ids), "unexpected": unexpected_pending_ids, "rate": round((len(generated_pending_ids) - len(unexpected_pending_ids)) / len(generated_pending_ids), 4) if generated_pending_ids else None},
        "confirmedSfsInSnapshot": len(confirmed_sfs),
        "abortedCasesInSnapshot": len(aborted),
    },
    "limitations": [
        "The fixtures are a regression set, not an exhaustive catalogue of every historical proposal.",
        "A Ferenda search hit without a matching SFS is reported as an unresolved signal, not as an aborted proposal.",
        "Confirmed-case recall is measured only for the SFS identifiers named in the fixtures.",
    ],
}

write_json(DATA / "benchmark-report.json", report)
rate = report["metrics"]["evidenceRecall"]["rate"]
markdown = [
    "# Data benchmark",
    "",
    f"Generated: `{report['generatedAt']}`",
    "",
    f"Evidence recall: **{matched_units}/{expected_units} ({rate:.1%})**.",
    "",
    "This is a regression benchmark over the static cases in `data/benchmark-cases.json`; it is not a claim of complete constitutional history.",
    "",
    "| Case | Expected | Result | Missing |",
    "|---|---|---|---|",
]
for result in case_results:
    missing = result.get("missing", result.get("missingSfs", []))
    markdown.append(f"| {result['id']} | {result['expectedStatus']} | {result['status']} | {', '.join(missing) or '—'} |")
markdown.extend([
    "",
    "## Limitations",
    "",
    *[f"- {limitation}" for limitation in report["limitations"]],
    "",
])
(ROOT / "DATA_BENCHMARK.md").write_text("\n".join(markdown))
print(f"Benchmark evidence recall: {matched_units}/{expected_units} ({rate:.1%})")
