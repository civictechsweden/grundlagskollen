"""Build the constitutional proposal and SFS dataset.

The source model follows CHATGPT_DISCUSSION.md:

    political proposal -> parliamentary decisions -> enacted SFS

Riksdagens document/status data is used to discover and classify first and
final decisions. Structured document references are kept as graph edges;
citations parsed from full text are kept separately. Ferenda is used for the
SFS/amendment index, but a missing match is reported rather than guessed.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / ".cache" / "riksdag"
FERENDA = "https://ferenda.lagen.nu/api/v1"
RIKSDAG_LIST = "https://data.riksdagen.se/dokumentlista/"
RIKSDAG_DOCUMENT = "https://data.riksdagen.se/dokument/"
START_DATE = "1975-01-01"
NEXT_ELECTION = "2026-09-13"
SSL_CONTEXT = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or (certifi.where() if certifi else None))

CONSTITUTIONS = [
    {"id": "rf", "short": "RF", "title": "Regeringsformen", "sfs": "1974:152", "uri": "https://lagen.nu/1974:152"},
    {"id": "so", "short": "SO", "title": "Successionsordningen", "sfs": "1810:0926", "uri": "https://lagen.nu/1810:0926"},
    {"id": "tf", "short": "TF", "title": "Tryckfrihetsförordningen", "sfs": "1949:105", "uri": "https://lagen.nu/1949:105"},
    {"id": "ygl", "short": "YGL", "title": "Yttrandefrihetsgrundlagen", "sfs": "1991:1469", "uri": "https://lagen.nu/1991:1469"},
]

DISCOVERY_QUERIES = (
    "grundlagsbeslut",
    "vilande",
    "hvilande",
    "grundlagsenlig behandling",
)

# These documents are named in the discussion and are deliberately fetched
# even though the modern discovery window starts in 1975.
REGRESSION_DOCUMENT_IDS = {
    "GF01KU13",  # 1991 final rejection
    "GE01KU22",  # 1991 first decision
    "CL10KU1",   # 1888 KU memorial
    "CL9O10",    # 1888 Second Chamber protocol
    "CU9O15",    # 1897 protocol
}

CONSTITUTION_PATTERNS = (
    ("rf", r"regeringsformen|regeringsform"),
    ("so", r"successionsordningen|successionsordning"),
    ("tf", r"tryckfrihetsförordningen|tryckfrihetsförordning"),
    ("ygl", r"yttrandefrihetsgrundlagen|yttrandefrihetsgrundlag"),
    ("ro", r"riksdagsordningen"),
)

FIRST_PATTERNS = (
    # Present-tense/infinitive wording is used for the operative proposal.
    # Past-tense "har antagit ... som vilande" generally recounts an earlier
    # decision in a later report and must not create a second first-decision
    # record.
    r"(?:som|såsom)\s+(?:vilande|hvilande)\s+(?:antar|antaga)",
    r"(?:antar|antaga)[^.]{0,220}?(?:som|såsom)\s+(?:vilande|hvilande)",
    r"(?:vilande|hvilande)\s+(?:antar|antaga)",
)
FINAL_ADOPT_PATTERNS = (
    r"riksdagen\s+(?:antar|antog|har\s+antagit)\s+slutligt",
    r"riksdagen\s+slutligt\s+(?:antar|antog|antagit)",
    r"riksdagen\s+(?:antar|antog|antagit)\s+slutligen",
)
FINAL_REJECT_PATTERNS = (
    r"(?:riksdagen|utskottet|kammaren)[\s\S]{0,260}?(?:det\s+)?(?:vilande\s+)?förslaget[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
    r"(?:det\s+)?vilande\s+förslaget[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
    r"för\s+slutligt\s+beslut[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
)


class VisibleText(HTMLParser):
    """Extract readable text from Riksdag's escaped HTML payload."""

    BREAK_TAGS = {"p", "pre", "h1", "h2", "h3", "h4", "li", "br", "div", "tr"}
    SKIP_TAGS = {"style", "script", "svg", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if not self.skip_depth and tag in self.BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.skip_depth and tag in self.BREAK_TAGS:
            self.parts.append("\n")
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path(url: str, suffix: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}{suffix}"


def fetch_bytes(url: str, accept: str = "application/json") -> bytes:
    suffix = ".json" if "json" in accept else ".xml"
    path = cache_path(url, suffix)
    if path.exists():
        return path.read_bytes()
    request = Request(url, headers={"Accept": accept, "User-Agent": "grundlagsmonitor/0.2"})
    with urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        value = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return value


def fetch_json(url: str) -> dict:
    return json.loads(fetch_bytes(url, "application/json").decode("utf-8"))


def fetch_riksdag_text(document_id: str) -> tuple[str, str]:
    url = f"{RIKSDAG_DOCUMENT}{document_id}/text"
    raw = fetch_bytes(url, "application/xml")
    try:
        root = ET.fromstring(raw)
        payload = root.findtext(".//html") or ""
    except ET.ParseError:
        payload = raw.decode("utf-8", "ignore")
    payload = html.unescape(payload)
    parser = VisibleText()
    parser.feed(payload)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, url


def as_list(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def values_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def unwrap(container: object, key: str, nested_key: str | None = None) -> list[dict]:
    if not isinstance(container, dict):
        return []
    value = container.get(key)
    if isinstance(value, dict):
        # The API normally returns {"dokreferens": {"referens": [...]}}
        # and {"dokaktivitet": {"aktivitet": [...]}}.  Older responses
        # sometimes omit the outer wrapper, hence the fallback keys.
        for child_key in (nested_key, "referens", "aktivitet", key):
            if child_key and child_key in value:
                value = value[child_key]
                break
    return as_list(value)


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    return match.group(1) if match else None


def normalize_id(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "")).lower()


def normalize_citation(value: str | None) -> str:
    return re.sub(r"[.\s]", "", (value or "")).lower()


def compact(value: str, limit: int = 360) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def snippets(text: str, patterns: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            values.append(compact(text[max(0, match.start() - 120):match.end() + 220]))
    return list(dict.fromkeys(values))


def document_list(query: str) -> list[dict]:
    params = {
        "sok": query,
        "doktyp": "bet",
        "org": "KU",
        "from": START_DATE,
        "utformat": "json",
        "sort": "datum",
        "sortorder": "desc",
        "p": "1",
    }
    first_url = f"{RIKSDAG_LIST}?{urlencode(params)}"
    first = fetch_json(first_url).get("dokumentlista", {})
    documents = as_list(first.get("dokument"))
    try:
        total = int(first.get("@traffar", len(documents)))
    except (TypeError, ValueError):
        total = len(documents)
    page_size = max(len(documents), 1)
    for page in range(2, (total + page_size - 1) // page_size + 1):
        page_params = dict(params)
        page_params["p"] = str(page)
        listing = fetch_json(f"{RIKSDAG_LIST}?{urlencode(page_params)}").get("dokumentlista", {})
        documents.extend(as_list(listing.get("dokument")))
    return documents


def candidate_from_record(record: dict, query: str) -> bool:
    if query == "grundlagsbeslut":
        return True
    title = " ".join(str(record.get(key, "")) for key in ("titel", "summary", "notis"))
    return bool(re.search(r"vilande|hvilande|regeringsformen|successionsordningen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|riksdagsordningen", title, re.I))


def constitution_ids(text: str) -> list[str]:
    return [identifier for identifier, pattern in CONSTITUTION_PATTERNS if re.search(pattern, text, re.I)]


def citations(text: str) -> list[dict]:
    patterns = (
        ("proposition", r"\bprop(?:osition)?\.?\s+(\d{4}(?:/\d{2})?:\d+)"),
        ("betänkande", r"\bbet(?:änkande)?\.?\s+(\d{4}/\d{2}:[A-Za-z]{1,10}\d+)"),
        ("protokoll", r"\bprot(?:okoll)?\.?\s+(\d{4}/\d{2}:\d+)"),
        ("riksdagsskrivelse", r"\brskr\.?\s+(\d{4}/\d{2}:\d+)"),
        ("skrivelse", r"\bskr(?:ivelse)?\.?\s+(\d{4}/\d{2}:\d+)"),
    )
    found: list[dict] = []
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            found.append({"kind": kind, "value": match.group(1), "normalized": normalize_citation(match.group(1))})
    unique: dict[tuple[str, str], dict] = {}
    for item in found:
        unique[(item["kind"], item["normalized"])] = item
    return list(unique.values())


def legal_target_hints(text: str) -> list[str]:
    """Keep compact, reviewable hints for the provision named in a decision."""
    patterns = (
        r"\b\d+\s*kap\.\s*\d+\s*§[^.\n]{0,120}(?:regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|successionsordningen)",
        r"(?:regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|successionsordningen)[^.\n]{0,120}\b\d+\s*kap\.\s*\d+\s*§",
        r"\b\d+\s*§\s*(?:\d+:[a-zåäö]+|\d+\s*:\s*\d+|\d+:[a-zåäö]+)?[^.\n]{0,100}(?:regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|successionsordningen)",
        r"§\s*\d+[^.\n]{0,100}(?:regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|successionsordningen)",
        r"(?:regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen|successionsordningen)[^.\n]{0,100}\b§\s*\d+",
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            found.append(compact(match.group(0), 220))
    return list(dict.fromkeys(found))[:12]


def vote_hints(text: str) -> list[dict]:
    """Extract numeric vote statements without treating them as full roll calls."""
    patterns = (
        r"(?P<yes>\d+)\s+ja[,;]?\s+(?:men\s+)?(?P<no>\d+)\s+nej",
        r"(?P<yes>\d+)\s+ja\s+(?:mot|men)\s+(?P<no>\d+)\s+nej",
        r"(?P<yes>\d+)\s+för\s+och\s+(?P<no>\d+)\s+emot",
    )
    found: list[dict] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            found.append({
                "yes": int(match.group("yes")),
                "no": int(match.group("no")),
                "evidence": compact(text[max(0, match.start() - 100):match.end() + 100]),
            })
    return list({(item["yes"], item["no"]): item for item in found}.values())[:8]


SWEDISH_MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def date_hints(text: str, default_year: str | None) -> list[str]:
    year_match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(default_year or ""))
    year = int(year_match.group(1)) if year_match else None
    if year is None:
        year_match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", text)
        year = int(year_match.group(1)) if year_match else None
    if year is None:
        return []
    values = []
    for match in re.finditer(r"\b(?:den\s+)?(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\b", text, re.I):
        values.append(f"{year:04d}-{SWEDISH_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}")
    return list(dict.fromkeys(values))[:20]


def sfs_anchor(value: str) -> dict | None:
    match = re.search(r"#K(?P<chapter>\d+)(?:P(?P<section>\d+))?", str(value), re.I)
    if not match:
        return None
    return {
        "chapter": match.group("chapter"),
        "section": match.group("section"),
        "fragment": match.group(0),
        "source": value,
    }


def sfs_operations(properties: dict, instruction_text: str) -> list[dict]:
    """Turn Ferenda's section anchors into conservative declarative patches."""
    replaces = [anchor for item in values_list(properties.get("rpubl:ersatter")) if (anchor := sfs_anchor(str(item)))]
    inserts = [anchor for item in values_list(properties.get("rpubl:inforsI")) if (anchor := sfs_anchor(str(item)))]
    operations: list[dict] = []
    if replaces and inserts:
        operation_type = "replace_multiple_sections"
    elif replaces:
        operation_type = "amend_section"
    elif inserts:
        operation_type = "add_section"
    elif re.search(r"upphäv|upphör", instruction_text, re.I):
        operation_type = "repeal_section"
    else:
        operation_type = "unknown_instruction"
    targets = replaces or inserts or [{}]
    for sequence, target in enumerate(targets, 1):
        operations.append({
            "sequence": sequence,
            "operationType": operation_type,
            "chapter": target.get("chapter"),
            "section": target.get("section"),
            "oldDesignation": target.get("fragment"),
            "newDesignation": None,
            "instructionText": instruction_text,
            "newText": None,
            "parserConfidence": 0.82 if target else 0.2,
            "manuallyVerified": False,
            "sourceMetadata": target.get("source"),
        })
    return operations


def structured_references(status: dict) -> list[dict]:
    container = status.get("dokumentstatus", {})
    return unwrap(container, "dokreferens", "referens") or unwrap(container, "referens")


def activities(status: dict) -> list[dict]:
    container = status.get("dokumentstatus", {})
    return unwrap(container, "dokaktivitet", "aktivitet") or unwrap(container, "aktivitet")


def decision_date(doc: dict, activity_list: list[dict]) -> str | None:
    preferred = [entry for entry in activity_list if entry.get("kod") in {"BES", "AVG", "BEH"} and iso_date(entry.get("datum"))]
    if preferred:
        # Prefer the actual decision if present; otherwise use the committee's
        # avgörande date, then the treatment date.
        preferred.sort(key=lambda entry: ({"BES": 0, "AVG": 1, "BEH": 2}.get(entry.get("kod"), 9), entry.get("datum", "")))
        return iso_date(preferred[0].get("datum"))
    return iso_date(doc.get("datum"))


def classify(title: str, text: str) -> dict:
    corpus = f"{title}\n{text}"
    first = snippets(corpus, FIRST_PATTERNS)
    # A reservation may contain an alternative "Riksdagen antar som vilande"
    # formulation.  It is not the committee's operative recommendation.  The
    # local evidence is retained for inspection, but such a reservation-only
    # hit is not promoted to a first decision.
    first = [
        item for item in first
        if not (
            re.search(r"\bvi\s+anser\b|reservanternas", item, re.I)
            and not re.search(r"utskottet\s+(?:föreslår|hemställer|tillstyrker)", item, re.I)
        )
    ]
    adopted = snippets(corpus, FINAL_ADOPT_PATTERNS)
    rejected = snippets(corpus, FINAL_REJECT_PATTERNS)
    final_context = bool(re.search(r"för slutligt beslut|slutligt beslut|slutbehandling|slutlig prövning", corpus, re.I))
    title_vilande = bool(re.search(r"vilande|hvilande", title, re.I))
    final_procedure = bool(re.search(r"(?:anmäl|anmäler|anmäld)[\s\S]{0,90}(?:för|till)\s+slutligt beslut[\s\S]{0,90}(?:vilande|hvilande)", corpus, re.I))
    legacy_chamber_vote = bool(re.search(r"(?:omröstningen visade|kammaren förkastat|kammaren alltså fattat beslut enligt ja-propositionens)", corpus, re.I))
    # A first-decision report may describe the future second vote. Require an
    # explicit final-procedure context before interpreting the same words as a
    # final decision.
    is_final = bool((adopted or rejected) and (title_vilande or final_procedure or legacy_chamber_vote) or (final_context and title_vilande))
    is_first = bool(first) and not is_final
    if is_final and rejected:
        # The operative proposal wins over rejection language in a reservation
        # or an opposition motion.  A final report can contain both.
        outcome = "adopted" if adopted else "rejected"
    elif is_final and adopted:
        outcome = "adopted"
    elif is_final:
        outcome = "unresolved"
    else:
        outcome = None
    stage = "final" if is_final else "first" if is_first else "candidate"
    return {
        "stage": stage,
        "firstSignals": first,
        "finalAdoptSignals": adopted,
        "finalRejectSignals": rejected,
        "outcome": outcome,
    }


def ref_key(ref: dict) -> str | None:
    kind = str(ref.get("ref_dok_typ") or "").lower()
    rm = str(ref.get("ref_dok_rm") or "")
    bet = str(ref.get("ref_dok_bet") or "")
    if rm and bet and kind:
        return normalize_citation(f"{kind}:{rm}:{bet}")
    return None


def ref_keys(document: dict) -> set[str]:
    values = {f"citation:{item['kind']}:{item['normalized']}" for item in document.get("citations", [])}
    for ref in document.get("structuredReferences", []):
        key = ref_key(ref)
        if key:
            values.add(f"structured:{key}")
        if ref.get("ref_dok_id"):
            values.add(f"document:{normalize_id(ref['ref_dok_id'])}")
    return values


def proposition_keys(document: dict) -> set[str]:
    """Return primary proposition references, preferring structured metadata."""
    structured = {
        f"citation:proposition:{normalize_citation(str(ref.get('ref_dok_rm')) + ':' + str(ref.get('ref_dok_bet')))}"
        for ref in document.get("structuredReferences", [])
        if str(ref.get("ref_dok_typ", "")).lower() == "prop" and ref.get("ref_dok_rm") and ref.get("ref_dok_bet")
    }
    if structured:
        return structured
    # Text citations include a long tail of historical background references.
    # In the absence of the API's structured proposition metadata, the first
    # proposition citation is the conservative primary-reference fallback.
    for item in document.get("citations", []):
        if item.get("kind") == "proposition":
            return {f"citation:proposition:{item['normalized']}"}
    return set()


def work_keys(works: list[str]) -> set[str]:
    values: set[str] = set()
    for work in works:
        normalized = normalize_citation(work)
        for prefix, kind in (("prop", "proposition"), ("bet", "betänkande"), ("rskr", "riksdagsskrivelse"), ("skr", "skrivelse")):
            if normalized.startswith(prefix):
                values.add(f"citation:{kind}:{normalized[len(prefix):]}")
    return values


def extract_document(document_id: str, discovery: list[str]) -> dict:
    status = fetch_json(f"{RIKSDAG_DOCUMENT}{document_id}.json")
    status_container = status.get("dokumentstatus", {})
    doc = status_container.get("dokument", {})
    text, text_url = fetch_riksdag_text(document_id)
    refs = structured_references(status)
    activity_list = activities(status)
    title = str(doc.get("titel") or document_id)
    classification = classify(title, text)
    return {
        "documentId": str(doc.get("dok_id") or document_id).upper(),
        "kind": str(doc.get("doktyp") or "bet"),
        "subkind": doc.get("subtyp"),
        "riksmote": doc.get("rm"),
        "designation": doc.get("beteckning"),
        "title": title,
        "publishedDate": iso_date(doc.get("datum")),
        "decisionDate": decision_date(doc, activity_list),
        "documentUrl": doc.get("dokument_url_html") or f"{RIKSDAG_DOCUMENT}{document_id}",
        "textUrl": text_url,
        "source": "Riksdagens öppna data",
        "discovery": discovery,
        "constitutionIds": constitution_ids(f"{title}\n{text}"),
        "structuredReferences": refs,
        "citations": citations(text),
        "legalTargetHints": legal_target_hints(text),
        "voteHints": vote_hints(text),
        "dateHints": date_hints(text, doc.get("rm")),
        "activity": [{"code": item.get("kod"), "name": item.get("namn"), "date": iso_date(item.get("datum")), "status": item.get("status")} for item in activity_list],
        "textLength": len(text),
        "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "classification": classification,
        "evidence": classification["firstSignals"] + classification["finalAdoptSignals"] + classification["finalRejectSignals"],
    }


def graph_for(documents: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    known_by_ref: dict[str, str] = {}
    for document in documents:
        node_id = f"riksdag:{normalize_id(document['documentId'])}"
        nodes[node_id] = {"id": node_id, "type": "document", "documentId": document["documentId"], "title": document["title"], "kind": document["kind"], "date": document["decisionDate"]}
        if document.get("riksmote") and document.get("designation"):
            kinds = {document["kind"]}
            if document["kind"] == "bet":
                kinds.add("betänkande")
            for kind in kinds:
                known_by_ref[normalize_citation(f"{kind}:{document['riksmote']}:{document['designation']}")] = node_id
    for document in documents:
        source_id = f"riksdag:{normalize_id(document['documentId'])}"
        for ref in document.get("structuredReferences", []):
            ref_id = str(ref.get("ref_dok_id") or "").upper()
            if not ref_id:
                continue
            target_id = f"riksdag:{normalize_id(ref_id)}"
            nodes.setdefault(target_id, {"id": target_id, "type": "document", "documentId": ref_id, "title": ref.get("ref_dok_titel"), "kind": ref.get("ref_dok_typ"), "date": None})
            edges.append({"from": source_id, "to": target_id, "type": "structured_reference", "relation": ref.get("referenstyp"), "sourceDocumentId": document["documentId"], "evidence": ref.get("uppgift")})
        for citation in document.get("citations", []):
            lookup = normalize_citation(f"{citation['kind']}:{citation['normalized']}")
            target_id = known_by_ref.get(lookup)
            if not target_id:
                target_id = f"citation:{citation['kind']}:{citation['normalized']}"
                nodes.setdefault(target_id, {"id": target_id, "type": "citation", "kind": citation["kind"], "value": citation["value"]})
            edges.append({"from": source_id, "to": target_id, "type": "citation_reference", "relation": "text_regex", "sourceDocumentId": document["documentId"], "evidence": citation["value"]})
    unique_edges = {(edge["from"], edge["to"], edge["type"], edge.get("relation"), edge.get("evidence")): edge for edge in edges}
    return {"generatedAt": now(), "nodes": list(nodes.values()), "edges": list(unique_edges.values())}


def load_known_pending() -> list[dict]:
    path = DATA / "pending-cases.json"
    if not path.exists():
        return []
    value = json.loads(path.read_text())
    return value if isinstance(value, list) else []


def pair_decisions(documents: list[dict], known_pending: list[dict]) -> list[dict]:
    firsts = [doc for doc in documents if doc["classification"]["stage"] == "first"]
    finals = [doc for doc in documents if doc["classification"]["stage"] == "final"]
    records: list[dict] = []
    used_first_ids = set()

    for first in firsts:
        first_date = first.get("decisionDate") or first.get("publishedDate") or "9999-99-99"
        first_keys = ref_keys(first)
        scored: list[tuple[int, dict]] = []
        for final in finals:
            final_date = final.get("decisionDate") or final.get("publishedDate") or "0000-00-00"
            if final_date <= first_date:
                continue
            shared = first_keys & ref_keys(final)
            shared_proposition = len(proposition_keys(first) & proposition_keys(final))
            shared_bet = len({key for key in shared if "betänkande" in key})
            shared_document = len({key for key in shared if key.startswith("document:")})
            # Constitution overlap alone is never evidence of a pair: a KU
            # report routinely cites many unrelated constitutional matters.
            score = shared_proposition * 50 + shared_bet * 12 + shared_document * 20
            if score:
                scored.append((score, final))
        scored.sort(key=lambda pair: (pair[0], pair[1].get("decisionDate") or ""), reverse=True)
        final = scored[0][1] if scored and scored[0][0] >= 12 else None
        if final:
            used_first_ids.add(first["documentId"])
        records.append(proposal_record(first, final, scored[0][0] if final and scored else 0))

    known_ids = {str(item.get("riksdagDocumentId") or "").upper() for item in known_pending}
    for item in known_pending:
        document_id = str(item.get("riksdagDocumentId") or "").upper()
        if not document_id or document_id in used_first_ids or any(record.get("firstDecision", {}).get("documentId") == document_id for record in records):
            continue
        records.append({
            "proposalId": f"curated:{document_id.lower()}",
            "title": item.get("title") or document_id,
            "constitutionIds": [item.get("constitutionId"), *(item.get("alsoConstitutionIds") or [])],
            "status": "pending",
            "temporal": "future",
            "firstDecision": {
                "status": "adopted_as_pending",
                "documentId": document_id,
                "date": item.get("firstDecisionDate"),
                "documentUrl": item.get("riksdagUrl") or f"https://data.riksdagen.se/dokument/{document_id}",
                "source": "curated Riksdag reference",
            },
            "finalDecision": None,
            "sfsIds": [],
            "match": {"method": "curated_pending_seed", "confidence": 0.7, "score": 0},
            "documentIds": [document_id],
            "provenance": [{"field": "status", "sourceUrl": item.get("riksdagUrl"), "method": "curated_pending_seed"}],
        })
    # The editorial queue is intentionally allowed to override an unresolved
    # historical-looking match. It records the current parliamentary state
    # supplied by the discussion's Riksdag overview; absence of a discovered
    # final document is not itself evidence of rejection.
    records_by_first = {record.get("firstDecision", {}).get("documentId"): record for record in records}
    for item in known_pending:
        document_id = str(item.get("riksdagDocumentId") or "").upper()
        record = records_by_first.get(document_id)
        if not record:
            continue
        record["title"] = item.get("title") or record["title"]
        record["constitutionIds"] = list(dict.fromkeys([item.get("constitutionId"), *(item.get("alsoConstitutionIds") or [])]))
        record["status"] = "pending"
        record["temporal"] = "future"
        record["finalDecision"] = None
        record["sfsIds"] = []
        record["match"] = {"method": "curated_pending_seed_override", "confidence": 0.7, "score": record.get("match", {}).get("score", 0)}
        record["provenance"].append({"field": "status", "sourceUrl": item.get("riksdagUrl"), "method": "curated_pending_seed_override"})
    return records


def proposal_record(first: dict, final: dict | None, score: int) -> dict:
    if final is None:
        status = "unresolved"
        temporal = "past" if (first.get("decisionDate") or "9999") < datetime.now().strftime("%Y-%m-%d") else "future"
    elif final["classification"]["outcome"] == "rejected":
        status, temporal = "rejected", "past"
    elif final["classification"]["outcome"] == "adopted":
        status, temporal = "adopted", "past"
    else:
        status, temporal = "unresolved", "past"
    first_refs = [ref.get("ref_dok_id") for ref in first.get("structuredReferences", []) if ref.get("ref_dok_id")]
    final_refs = [ref.get("ref_dok_id") for ref in final.get("structuredReferences", []) if ref.get("ref_dok_id")] if final else []
    return {
        "proposalId": f"riksdag:{normalize_id(first['documentId'])}",
        "title": first["title"],
        "constitutionIds": first.get("constitutionIds", []),
        "status": status,
        "temporal": temporal,
        "firstDecision": {
            "status": "adopted_as_pending",
            "documentId": first["documentId"],
            "date": first.get("decisionDate") or first.get("publishedDate"),
            "documentUrl": first["documentUrl"],
            "propositionReferences": [item for item in first.get("citations", []) if item["kind"] == "proposition"],
            "riksdagCitationReferences": [item for item in first.get("citations", []) if item["kind"] != "proposition"],
            "riksdagReferences": first_refs,
            "evidence": first.get("evidence", []),
        },
        "finalDecision": {
            "status": final["classification"]["outcome"],
            "documentId": final["documentId"],
            "date": final.get("decisionDate") or final.get("publishedDate"),
            "documentUrl": final["documentUrl"],
            "propositionReferences": [item for item in final.get("citations", []) if item["kind"] == "proposition"],
            "riksdagCitationReferences": [item for item in final.get("citations", []) if item["kind"] != "proposition"],
            "riksdagReferences": final_refs,
            "evidence": final.get("evidence", []),
        } if final else None,
        "sfsIds": [],
        "match": {"method": "shared_document_references", "confidence": min(1.0, score / 30), "score": score} if final else {"method": "no_final_match", "confidence": 0.0, "score": 0},
        "documentIds": list(dict.fromkeys([first["documentId"], *( [final["documentId"]] if final else [])])),
        "provenance": [
            {"field": "firstDecision", "sourceUrl": first["documentUrl"], "sourceDocumentId": first["documentId"], "method": "riksdag_status_and_text"},
            *([{ "field": "finalDecision", "sourceUrl": final["documentUrl"], "sourceDocumentId": final["documentId"], "method": "shared_document_references_and_text" }] if final else []),
        ],
    }


def fetch_ferenda_changes() -> tuple[list[dict], dict[str, dict]]:
    changes: list[dict] = []
    catalogs: dict[str, dict] = {}
    for law in CONSTITUTIONS:
        document = fetch_json(f"{FERENDA}/document?{urlencode({'uri': law['uri']})}")
        versions_response = fetch_json(f"{FERENDA}/document/versions?{urlencode({'uri': law['uri']})}")
        versions = {item.get("version"): item for item in versions_response.get("versions", []) if item.get("version")}
        catalogs[law["id"]] = {"constitutionId": law["id"], "sfs": law["sfs"], "source": "Ferenda / lagen.nu /document/versions", "versions": list(versions_response.get("versions", []))}
        for amendment in document.get("artifact", {}).get("amendments", []):
            uri = amendment.get("uri", "")
            sfs = uri.rstrip("/").split("/")[-1]
            if not re.fullmatch(r"\d{4}:\d+", sfs) or sfs == law["sfs"]:
                continue
            version = versions.get(sfs, {})
            properties = amendment.get("properties", {})
            works = list(dict.fromkeys(amendment.get("forarbeten", []) + version.get("forarbeten", [])))
            changes.append({
                "id": f"{law['id']}-{sfs}",
                "constitutionId": law["id"],
                "status": "confirmed",
                "temporal": "past",
                "sfs": sfs,
                "date": version.get("ikraft") or properties.get("rpubl:ikrafttradandedatum"),
                "title": properties.get("rpubl:andrar") or "Ändring registrerad i konsolideringen",
                "description": properties.get("rpubl:andrar") or "Ändring registrerad i konsolideringen",
                "preparatoryWorks": works,
                "lawUrl": f"https://lagen.nu/{sfs}",
                "versionUrl": version.get("uri") or f"https://lagen.nu/{law['sfs']}/konsolidering/{sfs}",
                "sfsMetadataUrl": uri,
                "metadata": {"ikraft": version.get("ikraft") or properties.get("rpubl:ikrafttradandedatum"), "ersatter": properties.get("rpubl:ersatter", []), "inforsI": properties.get("rpubl:inforsI", []), "sfsIdentifier": properties.get("dcterms:identifier")},
                "operations": sfs_operations(properties, properties.get("rpubl:andrar") or "Ändring registrerad i konsolideringen"),
            })
    return changes, catalogs


def attach_sfs(proposals: list[dict], changes: list[dict]) -> dict:
    adopted_without_sfs: list[str] = []
    orphan_sfs: list[str] = []
    rejected_with_sfs: list[str] = []
    chronology_errors: list[str] = []
    for proposal in proposals:
        if proposal["status"] != "adopted":
            continue
        decision = proposal.get("finalDecision") or proposal.get("firstDecision") or {}
        refs = {f"citation:{item['kind']}:{item['normalized']}" for item in decision.get("propositionReferences", [])}
        refs |= {f"citation:{item['kind']}:{item['normalized']}" for item in decision.get("riksdagCitationReferences", [])}
        refs |= {f"document:{normalize_id(value)}" for value in decision.get("riksdagReferences", []) if value}
        matches = []
        for change in changes:
            works = work_keys(change.get("preparatoryWorks", []))
            if refs & works:
                matches.append(change["sfs"])
        proposal["sfsIds"] = list(dict.fromkeys(matches))
        if not matches:
            adopted_without_sfs.append(proposal["proposalId"])
    for proposal in proposals:
        first_date = proposal.get("firstDecision", {}).get("date")
        final_date = (proposal.get("finalDecision") or {}).get("date")
        if first_date and final_date and final_date <= first_date:
            chronology_errors.append(proposal["proposalId"])
        if proposal.get("status") == "rejected" and proposal.get("sfsIds"):
            rejected_with_sfs.append(proposal["proposalId"])
    matched = {sfs for proposal in proposals for sfs in proposal.get("sfsIds", [])}
    orphan_sfs = [change["sfs"] for change in changes if change["sfs"] not in matched]
    for change in changes:
        change["proposalIds"] = [proposal["proposalId"] for proposal in proposals if change["sfs"] in proposal.get("sfsIds", [])]
    unknown_operations = [
        change["sfs"] for change in changes
        if any(operation.get("operationType") == "unknown_instruction" for operation in change.get("operations", []))
    ]
    return {
        "adoptedWithoutSfsMatch": adopted_without_sfs,
        "orphanSfs": orphan_sfs,
        "rejectedWithSfs": rejected_with_sfs,
        "chronologyErrors": chronology_errors,
        "unknownSfsOperations": unknown_operations,
        "twoWayValidation": {
            "riksdagToSfs": {"adopted": sum(1 for item in proposals if item.get("status") == "adopted"), "matched": sum(1 for item in proposals if item.get("status") == "adopted" and item.get("sfsIds")), "withoutMatch": len(adopted_without_sfs)},
            "sfsToRiksdag": {"changes": len(changes), "matched": len(changes) - len(orphan_sfs), "orphan": len(orphan_sfs)},
        },
    }


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    discovered: dict[str, dict] = {}
    for query in DISCOVERY_QUERIES:
        for record in document_list(query):
            document_id = str(record.get("dok_id") or record.get("id") or "").upper()
            if not document_id or not candidate_from_record(record, query):
                continue
            entry = discovered.setdefault(document_id, {"record": record, "queries": []})
            entry["queries"].append(query)
    for document_id in REGRESSION_DOCUMENT_IDS:
        discovered.setdefault(document_id, {"record": {"dok_id": document_id}, "queries": ["regression-fixture"]})
    for item in load_known_pending():
        document_id = str(item.get("riksdagDocumentId") or "").upper()
        if document_id:
            discovered.setdefault(document_id, {"record": {"dok_id": document_id, "titel": item.get("title")}, "queries": ["curated-pending-seed"]})

    documents: list[dict] = []
    errors: list[dict] = []
    for document_id, entry in sorted(discovered.items()):
        try:
            documents.append(extract_document(document_id, entry["queries"]))
        except Exception as error:
            errors.append({"documentId": document_id, "error": str(error), "discovery": entry["queries"]})

    # The broad `vilande` query also returns ordinary KU reports that merely
    # mention constitutional questions. Keep the search provenance, but only
    # publish documents that have a decision signal, an explicit vilande title,
    # a direct grundlagsbeslut hit, or are a named regression document.
    documents = [
        document for document in documents
        if (
            document["classification"]["stage"] in {"first", "final"}
            or "grundlagsbeslut" in document.get("discovery", [])
            or re.search(r"vilande|hvilande", document.get("title", ""), re.I)
            or document["documentId"] in REGRESSION_DOCUMENT_IDS
        )
    ]

    graph = graph_for(documents)
    proposals = pair_decisions(documents, load_known_pending())
    changes, catalogs = fetch_ferenda_changes()
    match_report = attach_sfs(proposals, changes)
    generated_at = now()
    output = {
        "generatedAt": generated_at,
        "scope": {"modernFrom": START_DATE, "note": "Modern discovery starts 1975; older documents are included when named by regression fixtures."},
        "election": {"nextDate": NEXT_ELECTION, "source": "https://www.val.se/sa-rostar-du/rosta-pa-valdagen"},
        "constitutions": CONSTITUTIONS + [{"id": "ro", "short": "RO", "title": "Riksdagsordningen", "sfs": None}],
        "proposals": proposals,
        "changes": sorted(changes, key=lambda item: (item.get("date") is not None, item.get("date") or "", item["sfs"]), reverse=True),
        "pending": [proposal for proposal in proposals if proposal["status"] in {"pending", "unresolved"} and proposal["temporal"] == "future"],
        "aborted": [proposal for proposal in proposals if proposal["status"] == "rejected"],
        "signals": [{"documentId": document["documentId"], "title": document["title"], "url": document["documentUrl"], "note": "Candidate or unresolved document; not classified as aborted."} for document in documents if document["classification"]["stage"] == "candidate"],
        "versionCatalog": catalogs,
        "sources": {"riksdagOpenData": "https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/", "riksdagApi": RIKSDAG_DOCUMENT, "riksdagDocumentListApi": RIKSDAG_LIST, "ferendaApi": FERENDA, "ferendaOpenApi": "https://ferenda.lagen.nu/openapi.json"},
        "coverage": {
            "discoveryQueries": list(DISCOVERY_QUERIES),
            "modernCandidateDocuments": len(discovered),
            "documentsFetched": len(documents),
            "documentFetchErrors": errors,
            "firstDecisions": sum(1 for proposal in proposals if proposal.get("firstDecision")),
            "finalDecisions": sum(1 for proposal in proposals if proposal.get("finalDecision")),
            "limitations": ["Riksdagens öppna data saknar ett enda authoritative pending-fält; klassning bygger på beslutstext och status.", "Äldre tvåkammarfall kräver kammarvisa beslut och kan inte reduceras till ett enda kammarresultat.", "Frånvaro av ett senare beslut klassas som unresolved/pending, aldrig automatiskt som rejected."],
            **match_report,
        },
    }
    (DATA / "changes.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    (DATA / "document-graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n")
    (DATA / "riksdag-documents.json").write_text(json.dumps({"generatedAt": generated_at, "documents": documents, "errors": errors}, ensure_ascii=False, indent=2) + "\n")
    riksdag_index = [
        {
            "documentId": document["documentId"],
            "title": document["title"],
            "documentUrl": document["documentUrl"],
            "constitutionIds": document.get("constitutionIds", []),
            "evidence": document.get("evidence", []),
            "structuredReferences": [
                {key: ref.get(key) for key in ("ref_dok_typ", "ref_dok_rm", "ref_dok_bet", "ref_dok_id")}
                for ref in document.get("structuredReferences", [])
                if str(ref.get("ref_dok_typ", "")).lower() in {"rskr", "skr", "prot"}
            ],
        }
        for document in documents
    ]
    (DATA / "riksdag-index.json").write_text(json.dumps({"generatedAt": generated_at, "documents": riksdag_index}, ensure_ascii=False, indent=2) + "\n")
    print(f"Fetched {len(documents)}/{len(discovered)} Riksdag candidate documents; built {len(proposals)} proposal records and {len(changes)} SFS changes.")
    print(f"First decisions: {sum(1 for proposal in proposals if proposal.get('firstDecision'))}; final decisions: {sum(1 for proposal in proposals if proposal.get('finalDecision'))}; rejected: {sum(1 for proposal in proposals if proposal['status'] == 'rejected')}; unresolved/pending: {sum(1 for proposal in proposals if proposal['status'] in {'pending', 'unresolved'})}.")


if __name__ == "__main__":
    main()
