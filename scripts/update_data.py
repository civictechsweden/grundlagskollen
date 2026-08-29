"""Build the static data snapshot for Grundlagsmonitor.

Run locally with: uv run scripts/update_data.py
The script intentionally uses only Python's standard library so the nightly
GitHub Action does not need a dependency lock or a server-side runtime.
"""

from __future__ import annotations

import json
import html
import os
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover - uv supplies certifi in CI
    certifi = None

ROOT = Path(__file__).resolve().parents[1]
FERENDA = "https://ferenda.lagen.nu/api/v1"
RIKSDAG = "https://data.riksdagen.se/dokument/"
RIKSDAG_LIST = "https://data.riksdagen.se/dokumentlista/"
ABORTED_CASES = ROOT / "data/aborted-cases.json"
BENCHMARK_CASES = ROOT / "data/benchmark-cases.json"
SSL_CONTEXT = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or (certifi.where() if certifi else None))

# The current constitutional-change backlog began with the 2022 election. The
# curated file keeps cases across elections; this date limits automatic
# discovery to the current backlog and avoids mistaking old references to
# dormant proposals for still-pending cases.
LAST_ELECTION = "2022-09-11"
NEXT_ELECTION = "2026-09-13"
RIKSDAG_DISCOVERY_QUERIES = ("vilande grundlagsförslag", "grundlagsförslag")

CONSTITUTIONS = [
    {"id": "rf", "short": "RF", "title": "Regeringsformen", "sfs": "1974:152", "uri": "https://lagen.nu/1974:152"},
    {"id": "so", "short": "SO", "title": "Successionsordningen", "sfs": "1810:0926", "uri": "https://lagen.nu/1810:0926"},
    {"id": "tf", "short": "TF", "title": "Tryckfrihetsförordningen", "sfs": "1949:105", "uri": "https://lagen.nu/1949:105"},
    {"id": "ygl", "short": "YGL", "title": "Yttrandefrihetsgrundlagen", "sfs": "1991:1469", "uri": "https://lagen.nu/1991:1469"},
]


def fetch_json(url: str, params: dict[str, str] | None = None) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "grundlagsmonitor-data/0.1"})
    with urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        return json.load(response)


def collect_objects(value: object) -> list[dict]:
    """Collect nested API objects; Riksdag wraps some arrays one level deep."""
    found: list[dict] = []
    if isinstance(value, dict):
        if any(key in value for key in ("kod", "punkt", "votering_id")):
            found.append(value)
        for child in value.values():
            found.extend(collect_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_objects(child))
    return found


def as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def plain_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", " ", text)


def compact_text(value: object, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", plain_text(value)).strip()
    return text if len(text) <= limit else f"{text[:limit - 1].rstrip()}…"


def riksdag_document_list(query: str) -> list[dict]:
    """Return all matching records from Riksdagens paginated document API."""
    params = {
        "sok": query,
        "doktyp": "bet",
        "org": "KU",
        "from": LAST_ELECTION,
        "utformat": "json",
        "sort": "datum",
        "sortorder": "desc",
        "p": "1",
    }
    first = fetch_json(RIKSDAG_LIST, params)
    listing = first.get("dokumentlista", {})
    documents = list(as_list(listing.get("dokument")))
    try:
        total = int(listing.get("@traffar", len(documents)))
    except (TypeError, ValueError):
        total = len(documents)
    page_size = max(len(documents), 1)
    for page in range(2, (total + page_size - 1) // page_size + 1):
        page_params = dict(params)
        page_params["p"] = str(page)
        page_result = fetch_json(RIKSDAG_LIST, page_params)
        documents.extend(as_list(page_result.get("dokumentlista", {}).get("dokument")))
    return documents


def riksdag_proposals(status: dict) -> list[dict]:
    proposals = []
    for proposal in collect_objects(status.get("dokutskottsforslag")):
        if any(proposal.get(key) for key in ("punkt", "rubrik", "förslag", "forslag")):
            proposals.append(proposal)
    return proposals


def proposal_text(proposal: dict) -> str:
    return plain_text(" ".join(str(proposal.get(key, "")) for key in ("rubrik", "förslag", "forslag")))


def is_dormant_first_vote(proposal: dict) -> bool:
    return bool(re.search(r"antar(?:s|de)?\s+som\s+vilande|antogs\s+som\s+vilande", proposal_text(proposal), re.I))


def affected_constitutions(text: str) -> list[str]:
    names = (
        ("rf", r"regeringsformen"),
        ("so", r"successionsordningen"),
        ("tf", r"tryckfrihetsförordningen"),
        ("ygl", r"yttrandefrihetsgrundlagen"),
        ("ro", r"riksdagsordningen"),
    )
    return [constitution_id for constitution_id, pattern in names if re.search(pattern, text, re.I)]


def riksdag_detail(document_id: str) -> dict | None:
    try:
        return fetch_json(f"{RIKSDAG}{document_id}.json")
    except Exception as error:  # keep the snapshot usable if one source is temporarily down
        print(f"Riksdag fetch failed for {document_id}: {error}")
        return None


def enrich_pending(item: dict, riksdag_data: dict | None) -> dict:
    status = (riksdag_data or {}).get("dokumentstatus", {})
    document = status.get("dokument", {})
    activities = [entry for entry in collect_objects(status.get("dokaktivitet")) if entry.get("kod") == "BES"]
    decision = sorted(activities, key=lambda entry: entry.get("datum", ""))[0] if activities else {}
    proposals = riksdag_proposals(status)
    constitutional_proposal = next(
        (proposal for proposal in proposals if is_dormant_first_vote(proposal) or re.search(r"grundlagsförslag", proposal_text(proposal), re.I)),
        proposals[0] if proposals else {},
    )
    vote_table = (((constitutional_proposal.get("votering_sammanfattning_html") or {}).get("table") or {}).get("tfooter") or {}).get("tr") or {}
    vote_values = vote_table.get("td") if isinstance(vote_table.get("td"), list) else []
    evidence_text = " ".join(
        [
            str(document.get("titel", "")),
            str(document.get("summary", "")),
            str(item.get("title", "")),
            *(proposal_text(proposal) for proposal in proposals),
        ]
    )
    detected_laws = affected_constitutions(plain_text(evidence_text))
    declared_laws = unique([item.get("constitutionId", ""), *(item.get("alsoConstitutionIds") or [])])
    all_laws = unique([*detected_laws, *declared_laws])
    primary_law = next((law for law in all_laws if law != "ro"), item.get("constitutionId"))
    enriched = dict(item)
    enriched["status"] = "pending-first-vote"
    enriched["constitutionId"] = primary_law
    enriched["alsoConstitutionIds"] = [law for law in all_laws if law != primary_law]
    enriched["firstDecisionDate"] = iso_date(decision.get("datum")) or item.get("firstDecisionDate")
    enriched["firstDecisionUri"] = item.get("riksdagUrl") or (item.get("sources") or [None])[0]
    enriched["interveningElection"] = {
        "date": item.get("nextElection") or NEXT_ELECTION,
        "source": "https://www.val.se/sa-rostar-du/rosta-pa-valdagen",
    }
    enriched["secondDecision"] = {
        "status": "awaiting-new-parliament",
        "earliest": "Efter valet och sedan den nyvalda riksdagen har samlats",
        "note": "Det andra beslutet måste ha likalydande innehåll; något datum kan inte härledas säkert i förväg.",
    }
    enriched["riksdag"] = {
        "id": item.get("riksdagDocumentId"),
        "riksmote": document.get("rm"),
        "beteckning": document.get("beteckning"),
        "date": iso_date(document.get("datum")),
        "decisionDate": iso_date(decision.get("datum")),
        "proposal": constitutional_proposal.get("rubrik"),
        "proposalStatus": "vilande" if is_dormant_first_vote(constitutional_proposal) else None,
        "vote": {"yes": vote_values[0], "no": vote_values[1], "abstain": vote_values[2], "absent": vote_values[3]} if len(vote_values) >= 4 else None,
        "source": item.get("riksdagUrl") or f"https://data.riksdagen.se/dokument/{item.get('riksdagDocumentId')}",
        "detectedConstitutions": all_laws,
    }
    return enriched


def reference_key(value: str | None) -> str:
    return re.sub(r"[.\s]", "", (value or "").lower()).replace("skr", "rskr")


def sfs_number(uri: str) -> str:
    return uri.split("/")[-1]


def iso_date(value: str | None) -> str | None:
    return value[:10] if value else None


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def load_static_json(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    return value if isinstance(value, list) else []


history: list[dict] = []
version_catalog: dict[str, dict] = {}
for law in CONSTITUTIONS:
    document = fetch_json(f"{FERENDA}/document", {"uri": law["uri"]})
    versions_response = fetch_json(f"{FERENDA}/document/versions", {"uri": law["uri"]})
    versions = {version["version"]: version for version in versions_response.get("versions", [])}
    version_catalog[law["id"]] = {
        "constitutionId": law["id"],
        "sfs": law["sfs"],
        "uri": law["uri"],
        "source": "Ferenda / lagen.nu /document/versions",
        "versions": list(versions_response.get("versions", [])),
    }
    for amendment in document.get("artifact", {}).get("amendments", []):
        sfs = sfs_number(amendment.get("uri", ""))
        if not re.fullmatch(r"\d{4}:\d+", sfs) or sfs == law["sfs"]:
            continue
        version = versions.get(sfs, {})
        properties = amendment.get("properties", {})
        description = properties.get("rpubl:andrar") or "Ändring registrerad i konsolideringen"
        preparatory_works = list(dict.fromkeys(amendment.get("forarbeten", []) + version.get("forarbeten", [])))
        history.append({
            "id": f"{law['id']}-{sfs}",
            "constitutionId": law["id"],
            "status": "confirmed",
            "sfs": sfs,
            "date": version.get("ikraft") or properties.get("rpubl:ikrafttradandedatum"),
            "title": description if len(description) <= 120 else "Omfattande ändring och omtryck",
            "description": description,
            "preparatoryWorks": preparatory_works,
            "lawUrl": f"https://lagen.nu/{sfs}",
            "versionUrl": version.get("uri") or f"https://lagen.nu/{law['sfs']}/konsolidering/{sfs}",
            "sfsMetadataUrl": amendment.get("uri"),
            "sourceUrl": document.get("source_url"),
            "metadata": {
                "ikraft": version.get("ikraft") or properties.get("rpubl:ikrafttradandedatum"),
                "ersatter": properties.get("rpubl:ersatter", []),
                "inforsI": properties.get("rpubl:inforsI", []),
                "sfsIdentifier": properties.get("dcterms:identifier"),
            },
        })


pending_config = json.loads((ROOT / "data/pending-cases.json").read_text())
details_by_id: dict[str, dict] = {}
known_pending_ids = {item.get("riksdagDocumentId", "").upper(): item for item in pending_config}

# Riksdagens document-list API is the discovery layer. This is deliberately
# separate from the Ferenda search below: a parliamentary record can say that
# a proposal was adopted as dormant before anything exists in SFS.
discovered_records: dict[str, dict] = {}
for query in RIKSDAG_DISCOVERY_QUERIES:
    try:
        for record in riksdag_document_list(query):
            document_id = (record.get("dok_id") or record.get("id") or "").upper()
            if document_id:
                discovered_records[document_id] = record
    except Exception as error:
        print(f"Riksdag document search failed for {query}: {error}")

discovered_count = 0
riksdag_known_matches = 0
for document_id, record in discovered_records.items():
    metadata_text = " ".join(str(record.get(key, "")) for key in ("titel", "summary", "notis"))
    if not re.search(r"vilande", metadata_text, re.I):
        continue
    riksdag_data = details_by_id.get(document_id) or riksdag_detail(document_id)
    if not riksdag_data:
        continue
    details_by_id[document_id] = riksdag_data
    status = riksdag_data.get("dokumentstatus", {})
    proposals = [proposal for proposal in riksdag_proposals(status) if is_dormant_first_vote(proposal)]
    if not proposals:
        continue
    activities = [entry for entry in collect_objects(status.get("dokaktivitet")) if entry.get("kod") == "BES"]
    decision = sorted(activities, key=lambda entry: entry.get("datum", ""))[0] if activities else {}
    first_decision_date = iso_date(decision.get("datum")) or iso_date(record.get("beslutsdag")) or iso_date(record.get("datum"))
    if not first_decision_date or first_decision_date <= LAST_ELECTION:
        continue
    evidence_text = " ".join([record.get("titel", ""), record.get("notis", ""), *(proposal_text(proposal) for proposal in proposals)])
    affected = affected_constitutions(plain_text(evidence_text))
    four_laws = [constitution_id for constitution_id in affected if constitution_id != "ro"]
    if document_id in known_pending_ids:
        riksdag_known_matches += 1
    if not four_laws or document_id in known_pending_ids:
        continue
    riksdag_url = f"https://data.riksdagen.se/dokument/{document_id}"
    primary = four_laws[0]
    discovered_item = {
        "id": f"riksdag-{document_id.lower()}",
        "constitutionId": primary,
        "alsoConstitutionIds": affected[1:],
        "title": record.get("titel") or document_id,
        "summary": compact_text(record.get("notis") or record.get("summary") or "Riksdagen har antagit ett grundlagsförslag som vilande."),
        "riksdagDocumentId": document_id,
        "firstDecisionDate": first_decision_date,
        "riksdagUrl": riksdag_url,
        "nextElection": NEXT_ELECTION,
        "sources": [riksdag_url],
        "editorialNote": "Automatiskt upptäckt via Riksdagens öppna dokumentlista. Förslagstexten säger att grundlagsförslaget antas som vilande; den andra likalydande omröstningen behöver följas i kommande körningar.",
        "discovery": "riksdag-open-data-search",
    }
    pending_config.append(discovered_item)
    known_pending_ids[document_id] = discovered_item
    discovered_count += 1

pending: list[dict] = []
for item in pending_config:
    document_id = (item.get("riksdagDocumentId") or "").upper()
    if document_id and document_id not in details_by_id:
        riksdag_data = riksdag_detail(document_id)
        if riksdag_data:
            details_by_id[document_id] = riksdag_data
    pending.append(enrich_pending(item, details_by_id.get(document_id)))


signals: list[dict] = []
for query in ("vilande grundlagsändringar", "vilande grundlagsbeslut"):
    try:
        result = fetch_json(f"{FERENDA}/search", {"q": query, "source": "forarbete", "limit": "100"})
        for hit in result.get("results", []):
            text = f"{hit.get('title', '')} {' '.join(hit.get('highlight', []))}"
            if not re.search(r"vilande.*grundlag|grundlag.*vilande", text, re.I):
                continue
            if any(signal["uri"] == hit.get("uri") for signal in signals):
                continue
            matched = any(reference_key(work) == reference_key(hit.get("identifier")) for change in history for work in change.get("preparatoryWorks", []))
            signals.append({
                "uri": hit.get("uri"),
                "identifier": hit.get("identifier"),
                "title": hit.get("title"),
                "kind": hit.get("kind"),
                "resolution": "matched-to-confirmed-amendment" if matched else "unmatched-signal",
                "note": "Källan återfinns i en bekräftad SFS-konsolidering." if matched else "Ingen matchande SFS-konsolidering hittades automatiskt; detta är inte bevis på att förslaget föll.",
                "url": hit.get("uri"),
            })
    except Exception as error:
        print(f"Ferenda search failed for {query}: {error}")


history.sort(key=lambda item: item.get("date") or item.get("sfs", ""), reverse=True)
aborted = load_static_json(ABORTED_CASES)
benchmarks = load_static_json(BENCHMARK_CASES)
output = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "election": {"lastDate": LAST_ELECTION, "nextDate": NEXT_ELECTION, "source": "https://www.val.se/sa-rostar-du/rosta-pa-valdagen"},
    "constitutions": CONSTITUTIONS + [{"id": "ro", "short": "RO", "title": "Riksdagsordningen", "sfs": None, "note": "Mellanställning mellan grundlag och vanlig lag; visas som berörd i parlamentariska ärenden men ingår inte i de fyra grundlagarnas SFS-historik."}],
    "changes": history,
    "pending": pending,
    "aborted": aborted,
    "signals": signals,
    "benchmarks": benchmarks,
    "versionCatalog": version_catalog,
    "sources": {
        "ferendaOpenApi": "https://ferenda.lagen.nu/openapi.json",
        "ferendaApi": FERENDA,
        "riksdagOpenData": "https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/",
        "riksdagApi": "https://data.riksdagen.se/dokument/",
        "riksdagDocumentListApi": RIKSDAG_LIST,
    },
    "coverage": {
        "note": "Confirmed changes are derived from Ferenda artifact.amendments plus /document/versions. Pending cases are parliamentary records from Riksdagens open data and the Riksdag overview, not inferred from SFS.",
        "riksdagDiscovery": {
            "queries": list(RIKSDAG_DISCOVERY_QUERIES),
            "from": LAST_ELECTION,
            "recordsScanned": len(discovered_records),
            "knownPendingMatches": riksdag_known_matches,
            "discoveredCases": discovered_count,
            "method": "Fetch KU committee reports from the paginated document list, then inspect dokutskottsforslag for the phrase 'antar som vilande'.",
            "limitation": "Riksdagens API has no single authoritative pending-case field; pending status is inferred from the proposal wording. A missing later decision is not proof that a proposal fell.",
        },
        "historicalVersionsAreNotComplete": True,
        "abandonedProposalsAreNotProvenByAbsence": True,
        "sfsMetadata": {
            "fieldsUsed": ["rpubl:ikrafttradandedatum", "rpubl:ersatter", "rpubl:inforsI", "dcterms:identifier"],
            "note": "SFS metadata is used for event identity and effective dates; PDFs are not parsed by the updater.",
        },
    },
}
(ROOT / "data/changes.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
print(f"Wrote {len(history)} confirmed changes, {len(pending)} pending cases, {len(aborted)} aborted cases and {len(signals)} review signals.")
print(f"Riksdag open-data discovery added {discovered_count} pending cases.")
