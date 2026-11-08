"""Refresh parliamentary developments without rebuilding the historical corpus.

The full builder owns SFS/history. This bounded update discovers new KU reports,
rechecks the monitored first/final reports, and rebuilds the shared output model.
Network failures stop publication, leaving the last snapshot intact.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

if __package__:
    from .build_dataset import DATA, document_list, extract_document, now, write_outputs, normalize_citation
else:
    from build_dataset import DATA, document_list, extract_document, now, write_outputs, normalize_citation


def main(since: str | None = None) -> None:
    snapshot = json.loads((DATA / "changes.json").read_text())
    payload = json.loads((DATA / "riksdag-documents.json").read_text())
    documents = {item["documentId"]: item for item in payload["documents"]}
    previous_update = snapshot.get("currentRefreshedAt") or snapshot["generatedAt"]
    # Overlap catches late-indexed publications and changes to the agenda.
    date_from = since or (datetime.fromisoformat(previous_update).date() - timedelta(days=7)).isoformat()
    candidates = {}
    for query in ("vilande", "grundlagsbeslut"):
        for record in document_list(query, date_from=date_from):
            candidates[record["dok_id"].upper()] = record
    for proposal in snapshot["proposals"]:
        if proposal.get("status") == "pending" or proposal.get("parliamentaryProgress"):
            for field in ("firstDecision", "finalDecision", "nextDecision"):
                document_id = (proposal.get(field) or {}).get("documentId")
                if document_id:
                    candidates.setdefault(document_id, {})
    for document_id, record in sorted(candidates.items()):
        documents[document_id] = extract_document(document_id, ["current-parliamentary-refresh"], record, refresh=True)
    print(f"Discovered and checked {len(candidates)} reports since {date_from}.", flush=True)
    # Discover the earlier report from the follow-up report's explicit text
    # citation, including when it predates the incremental discovery window.
    by_citation = {normalize_citation(f"{item.get('riksmote')}:{item.get('designation')}"): item
                   for item in documents.values() if item.get("kind") == "bet"}
    for document in list(documents.values()):
        if document["documentId"] not in candidates:
            continue
        for link in document.get("firstDecisionLinks", []):
            existing = by_citation.get(link["normalized"])
            if existing:
                document_id = existing["documentId"]
                if document_id not in candidates:
                    documents[document_id] = extract_document(document_id, ["explicit-first-decision-citation"], refresh=True)
                    candidates[document_id] = {}
                continue
            year = link["date"][:4]
            for record in document_list(link["citation"], date_from=f"{year}-01-01", date_to=f"{int(year) + 1}-12-31"):
                if normalize_citation(f"{record.get('rm')}:{record.get('beteckning')}") != link["normalized"]:
                    continue
                document_id = record["dok_id"].upper()
                documents[document_id] = extract_document(document_id, ["explicit-first-decision-citation"], record, refresh=True)
                by_citation[link["normalized"]] = documents[document_id]
                candidates[document_id] = record
    existing_ids = {doc["documentId"] for doc in payload["documents"]}
    retained = [item for item in documents.values() if item["documentId"] in existing_ids
                or item["classification"]["stage"] in {"first", "final"}]
    refreshed_at = now()
    write_outputs(
        retained, snapshot["changes"], snapshot["versionCatalog"], snapshot["election"]["dates"],
        payload.get("errors", []), len(retained), snapshot["coverage"].get("ferendaSfsPropositionSeeds", 0),
        {"currentRefreshedAt": refreshed_at,
         "historicalSnapshotAt": snapshot.get("historicalSnapshotAt") or snapshot["generatedAt"],
         "refreshScope": {"parliamentaryFrom": date_from, "documentsRechecked": len(candidates),
                          "note": "Current parliamentary reports refreshed; historical SFS and version catalog retained."}},
    )
    print(f"Current parliamentary data checked at {refreshed_at}; {len(candidates)} reports refreshed.")


if __name__ == "__main__":
    main()
