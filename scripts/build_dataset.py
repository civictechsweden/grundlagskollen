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
import time
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
CHECKPOINT = DATA / ".cache" / "build-dataset-checkpoint.json"
CHECKPOINT_VERSION = "2026-08-30-parser-v6"
FETCH_METRICS = {"networkRequests": 0, "cacheHits": 0, "bytesDownloaded": 0}
FERENDA = "https://ferenda.lagen.nu/api/v1"
RIKSDAG_LIST = "https://data.riksdagen.se/dokumentlista/"
RIKSDAG_DOCUMENT = "https://data.riksdagen.se/dokument/"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
# Riksdag open data's digitised KU material begins in 1867.  Use the same
# discovery, classification and Riksdag-to-SFS validation path across the
# entire available parliamentary record.
START_DATE = "1867-01-01"
MAX_FINAL_DECISION_YEARS = 5
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
    "hvila",
    "grundlagsenlig behandling",
)

# These documents are named in the discussion and deliberately remain in the
# regression corpus alongside the complete 1867–present discovery window.
REGRESSION_DOCUMENT_IDS = {
    "GF01KU13",  # 1991 final rejection
    "GF01KU1",   # 1991 final adoption for GE01KU21
    "GF01KU2",   # 1991 final adoption for GE01KU20
    "GE01KU22",  # 1991 first decision
    "GE01KU20",  # genuine first decision without a proposition
    "GE01KU21",  # genuine first decision for YGL/TF/RF
    "GR01KU9",   # historical/procedural false positive
    "GS01KU27",  # rejected constitutional motions
    "GS01KU29",  # reservation false positive
    "GT01KU18",  # reservation false positive
    "H401KU30",  # historical-reference false positive
    "FZ01KU1",   # motion wording falsely resembling a pending decision
    "FZ01KU48",  # genuine first pending decision, TF 2 kap.
    "G001KU1",   # post-election committee report for the 1976 cases
    "G00923",     # chamber protocol with the final 1976-11-10 vote
    "CL10KU1",   # 1888 KU memorial
    "CL9O10",    # 1888 Second Chamber protocol
    "CU9O15",    # 1897 protocol
    # Successionsordningen decision chains. These are retained as named
    # regression fixtures because the historical corpus uses utlåtanden,
    # memorial, chamber protocols and Riksdagsbeslut rather than one stable
    # document type.
    "DH10KU19",   # 1921:21 first KU report
    "DI10KU4",    # 1921:21 pending-list memorial
    "DI90BESLUT", # 1921:21 final Riksdagsbeslut
    "DIK021",     # 1921:21 final Riksdagsskrivelse
    "DX10KU35",   # 1937:40 first KU report
    "DY10KU1",    # 1937:40 pending-list memorial
    "DYK018",     # 1937:40 final Riksdagsskrivelse
    "DY90BESLUT", # 1937:40 final Riksdagsbeslut
    "E910KU11",   # 1949:110 first KU report
    "EA10KU10",   # 1949:110 pending-list memorial
    "EA9C11",     # 1949:110 First Chamber final protocol
    "EA9O11",     # 1949:110 Second Chamber final protocol
    "EA91BESLUT", # 1949:110 final Riksdagsbeslut
    "EP10KU19",   # 1965:45 first KU report
    "EQ10KU1",    # 1965:45 pending-list memorial
    "EQ9C8",      # 1965:45 First Chamber final protocol
    "EQ9O8",      # 1965:45 Second Chamber final protocol
    "EQ91BESLUT", # 1965:45 final Riksdagsbeslut
    "FW01KU26",   # 1974:154 first KU report
    "FX01KU8",    # 1974:154 pending-list report
    "FX0930",     # 1974:154 final chamber protocol
    "G101KU36",   # 1979:935 first KU report
    "G301KU1",    # 1979:935 pending-list report
    "G30923",     # 1979:935 final chamber protocol
}

CONSTITUTION_PATTERNS = (
    ("rf", r"regerings[-\s]?formen|regerings[-\s]?form"),
    ("so", r"successions[-\s]?ordningen|successions[-\s]?ordning"),
    ("tf", r"tryckfrihets[-\s]?förordningen|tryckfrihets[-\s]?förordning"),
    ("ygl", r"yttrandefrihetsgrundlagen|yttrandefrihetsgrundlag"),
    ("ro", r"riksdags[-\s]?ordningen"),
)

FIRST_PATTERNS = (
    # Present-tense/infinitive wording is used for the operative proposal.
    # Past-tense "har antagit ... som vilande" generally recounts an earlier
    # decision in a later report and must not create a second first-decision
    # record.
    r"(?:som|såsom)\s+(?:vilande|hvilande)\s+(?:antar|antaga|antager|antages)",
    r"(?:som|såsom)\s+(?:vilande|hvilande)\s+(?:för|till)\s+(?:vidare\s+)?grundlagsenlig\s+behandling\s+(?:måtte\s+)?(?:antar|antaga|antager|antages)",
    r"(?:antar|antaga|antager|antages)[^.]{0,220}?(?:som|såsom)\s+(?:vilande|hvilande)",
    r"(?:vilande|hvilande)\s+(?:antar|antaga|antager|antages)",
    r"(?:vilande|hvilande)\s+(?:för|till)\s+(?:vidare\s+)?grundlagsenlig\s+behandling\s+(?:måtte\s+)?(?:antar|antaga|antager|antages)",
    r"(?:antar|antaga)[^.]{0,220}?att\s+hvila\s+till\s+grundlagsenlig\s+behandling",
)
FINAL_ADOPT_PATTERNS = (
    r"riksdagen\s+(?:antar|antog|har\s+antagit)\s+slutligt",
    r"riksdagen\s+slutligt\s+(?:antar|antog|antagit)",
    r"riksdagen\s+(?:antar|antog|antagit)\s+slutligen",
    r"(?:riksdagen|kammaren)\s+(?:har\s+)?(?:förehaft|företagit|upptagit)[\s\S]{0,180}(?:slutligt\s+avgörande|slutlig\s+prövning|slutlig\s+behandling)[\s\S]{0,180}(?:antagit|antagits)",
    r"(?:har\s+)?riksdagen[\s\S]{0,220}(?:förehaft|företagit|upptagit)[\s\S]{0,180}(?:slutligt\s+avgörande|slutlig\s+prövning|slutlig\s+behandling)[\s\S]{0,180}(?:antagit|antagits)",
    r"förehaft\s+till\s+slutligt\s+avgörande\s+och\s+antagit",
    r"(?:det|de)\s+vilande[\s\S]{0,180}(?:antogos|antogs|antagit|antagits|antaget)",
    r"vilande\s+grundlags(?:ändrings)?förslagen[\s\S]{0,180}(?:antogos|antogs|antagit|antagits)",
    r"slutligt\s+antar\s+de\s+vilande\s+förslagen",
    r"(?:förevarande|berörda)\s+förslag[\s\S]{0,180}(?:antagit|antogs|antagits)",
)

HISTORIC_DECISION_ADOPT_PATTERNS = (
    r"(?:ändrad|ändrat)\s+lydelse[\s\S]{0,180}successionsordningen[\s\S]{0,180}skrivelse\s+nr",
    r"successionsordningen[\s\S]{0,180}skrivelse\s+nr",
)
FINAL_REJECT_PATTERNS = (
    r"(?:det\s+)?vilande\s+förslaget[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
    r"(?:det\s+)?vilande\s+grundlagsbeslut(?:et)?[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
    r"för\s+slutligt\s+beslut[\s\S]{0,220}?förkast(?:as|ar|ade|at)",
    r"(?:riksdagen|kammaren)\s+(?:beslutar|beslöt|har\s+beslutat)\s+att\s+förkasta\s+(?:det\s+)?vilande\s+förslaget",
    r"(?:kammaren|riksdagen)\s+(?:hade\s+alltså\s+|alltså\s+)?(?:förkastat|förkastade|avslagit|afslagit)",
    r"(?:förslaget|grundlagsändringsförslaget)[\s\S]{0,180}(?:förkastats|förkastades|avslagits|afslaget)",
    r"omröstningen\s+visade[\s\S]{0,260}(?:förkastats|förkastades|avslagits|afslaget)",
)
REJECTED_BEFORE_FIRST_PATTERNS = (
    r"(?:utskottet|utskottets)[\s\S]{0,1200}(?:avstyrk(?:er|te|s)|avslår|föreslår\s+avslag|avvisar)[\s\S]{0,1000}(?:motion|yrkande)",
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


def load_build_checkpoint() -> dict:
    if not CHECKPOINT.exists():
        return {}
    try:
        value = json.loads(CHECKPOINT.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if value.get("parserVersion") == CHECKPOINT_VERSION else {}


def save_build_checkpoint(documents: list[dict], errors: list[dict], phase: str) -> None:
    """Atomically persist extraction progress so long runs can resume."""
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "parserVersion": CHECKPOINT_VERSION,
        "updatedAt": now(),
        "phase": phase,
        "documents": documents,
        "errors": errors,
    }
    temporary = CHECKPOINT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    temporary.replace(CHECKPOINT)


def cache_path(url: str, suffix: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}{suffix}"


def fetch_bytes(url: str, accept: str = "application/json", max_age: float | None = None) -> bytes:
    suffix = ".json" if "json" in accept else ".xml"
    path = cache_path(url, suffix)
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
        FETCH_METRICS["cacheHits"] += 1
        return path.read_bytes()
    request = Request(url, headers={"Accept": accept, "User-Agent": "grundlagsmonitor/0.2"})
    with urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        value = response.read()
    FETCH_METRICS["networkRequests"] += 1
    FETCH_METRICS["bytesDownloaded"] += len(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return value


def fetch_json(url: str, max_age: float | None = None) -> dict:
    return json.loads(fetch_bytes(url, "application/json", max_age).decode("utf-8"))


WIKIDATA_ELECTION_QUERY = """
SELECT DISTINCT ?election ?electionLabel ?date ?precision WHERE {
  ?election wdt:P31 wd:Q22266709;
            wdt:P17 wd:Q34;
            p:P585 ?dateStatement.
  FILTER NOT EXISTS { ?election wdt:P31 wd:Q71989553. }
  ?dateStatement ps:P585 ?date;
                 psv:P585/wikibase:timePrecision ?precision.
  FILTER(YEAR(?date) >= 1867)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "sv,en". }
}
ORDER BY ?date
""".strip()


def fetch_wikidata_elections() -> list[dict]:
    """Fetch Swedish general-election dates and retain Wikidata precision."""
    query_url = f"{WIKIDATA_SPARQL}?{urlencode({'format': 'json', 'query': WIKIDATA_ELECTION_QUERY})}"
    response = fetch_json(query_url, max_age=86400)
    elections: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for binding in response.get("results", {}).get("bindings", []):
        election_id = str(binding.get("election", {}).get("value", "")).rstrip("/").split("/")[-1]
        date = str(binding.get("date", {}).get("value", ""))[:10]
        if not election_id or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue
        key = (election_id, date)
        if key in seen:
            continue
        seen.add(key)
        precision = str(binding.get("precision", {}).get("value", ""))
        elections.append({
            "id": election_id,
            "date": date,
            "precision": int(precision) if precision.isdigit() else None,
            "label": binding.get("electionLabel", {}).get("value"),
            "source": f"https://www.wikidata.org/wiki/{election_id}",
        })
    return elections


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


def document_list(query: str, document_type: str = "bet", organization: str = "KU", date_from: str = START_DATE, date_to: str | None = None) -> list[dict]:
    params = {
        "sok": query,
        "doktyp": document_type,
        "from": date_from,
        "utformat": "json",
        "sort": "datum",
        "sortorder": "desc",
        "p": "1",
    }
    if organization:
        params["org"] = organization
    if date_to:
        params["tom"] = date_to
    first_url = f"{RIKSDAG_LIST}?{urlencode(params)}"
    first = fetch_json(first_url, max_age=86400).get("dokumentlista", {})
    documents = as_list(first.get("dokument"))
    try:
        total = int(first.get("@traffar", len(documents)))
    except (TypeError, ValueError):
        total = len(documents)
    page_size = max(len(documents), 1)
    for page in range(2, (total + page_size - 1) // page_size + 1):
        page_params = dict(params)
        page_params["p"] = str(page)
        listing = fetch_json(f"{RIKSDAG_LIST}?{urlencode(page_params)}", max_age=86400).get("dokumentlista", {})
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
        ("proposition", r"\bprop(?:osition)?\.?(?:en)?\s+(\d{4}(?:/\d{2})?:\d+)", ""),
        ("betänkande", r"\bbet(?:änkande)?\.?\s+(\d{4}/\d{2}:[A-Za-z]{1,10}\d+)", ""),
        ("betänkande", r"\bbet(?:änkande)?\.?\s+(\d{4}/\d{2}:\d+)", "contextual-KU"),
        # Older parliamentary prose writes the committee designation as
        # `KU 1976/77:1`, while the document model uses `1976/77:KU1`.
        ("betänkande", r"\bKU\s+(\d{4}/\d{2}:\d+)", "KU"),
        ("protokoll", r"\bprot(?:okoll)?\.?\s+(\d{4}/\d{2}:\d+)", ""),
        ("riksdagsskrivelse", r"\brskr\.?\s+(\d{4}/\d{2}:\d+)", ""),
        ("skrivelse", r"\bskr(?:ivelse)?\.?\s+(\d{4}/\d{2}:\d+)", ""),
    )
    found: list[dict] = []
    for kind, pattern, designation_prefix in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = match.group(1)
            prefix = designation_prefix
            if prefix == "contextual-KU":
                before = text[max(0, match.start() - 100):match.start()]
                prefix = "KU" if re.search(r"konsti[lt]utionsutskot|\bKU\b", before, re.I) else ""
            if prefix:
                meeting, number = value.split(":", 1)
                value = f"{meeting}:{prefix}{number}"
            found.append({"kind": kind, "value": value, "normalized": normalize_citation(value)})
    unique: dict[tuple[str, str], dict] = {}
    for item in found:
        unique[(item["kind"], item["normalized"])] = item
    values = list(unique.values())
    betänkande_values = {item["normalized"] for item in values if item["kind"] == "betänkande"}
    # OCR sometimes emits both `betänkande 1976/77:1` and `KU 1976/77:1`.
    # Keep the canonical committee designation when both refer to the same
    # document in one source.
    return [
        item for item in values
        if not (
            item["kind"] == "betänkande"
            and re.fullmatch(r"\d{4}/\d{2}:\d+", item["normalized"])
            and f"{item['normalized'].split(':', 1)[0]}:ku{item['normalized'].split(':', 1)[1]}" in betänkande_values
        )
    ]


def legacy_final_reference_terms(text: str, date: str | None, stage: str) -> list[str]:
    """Find pre-1975 report references in a final-treatment KU report.

    A historic final report often says, for example, “utlåtanden nr 6, 31
    och 32 … vid 1970 års riksdag”, rather than using today's ``1970/71:KU6``
    citation syntax.  These are primary-source links: they let the ordinary
    KU search retrieve and parse the original first-decision report.  They do
    not themselves create a proposal or an outcome.
    """
    if stage != "final":
        return []
    if (date or "") >= "1975-01-01":
        return []
    terms: list[str] = []
    for year_match in re.finditer(r"\b(?:vid|från)\s+(\d{4})\s+års\s+riksdag", text, re.I):
        year = year_match.group(1)
        context = text[max(0, year_match.start() - 700):year_match.start()]
        # References in the final report are normally introduced by the KU's
        # own “hänvisar till …” sentence.  Keeping that tail avoids treating
        # the report's masthead (for example “betänkande nr 5 år 1971”) as a
        # 1970 reference merely because it is nearby in the OCR text.
        introducers = list(re.finditer(r"\b(?:hänvisar|hänvisning)\b", context, re.I))
        if not introducers:
            continue
        context = context[introducers[-1].start():]
        for kind, labels, prefix in (
            ("betänkande", r"utlåtanden?|betänkanden?|memorial(?:en)?", "KU"),
            ("proposition", r"propositionerna?|propp?\.", ""),
        ):
            for reference in re.finditer(
                rf"\b(?:{labels})\s+(?:nr\.?\s*)?(\d+(?:(?:\s*,\s*|\s+och\s+)\d+)*)",
                context,
                re.I,
            ):
                for number in re.findall(r"\d+", reference.group(1)):
                    terms.append(f"{year}:{prefix}{number}")
    for reference in re.finditer(
        r"\bHänvisning\s*:\s*(?:Konstitutions[-\s]*)?utskottets\s+(?:utlåtande|utlåtanden|betänkande|memorial)\s+nr\.?\s*(\d+)\s+år\s+(\d{4})",
        text,
        re.I,
    ):
        terms.append(f"{reference.group(2)}:KU{reference.group(1)}")
    return list(dict.fromkeys(terms))


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
    today = datetime.now(timezone.utc).date().isoformat()
    preferred = [entry for entry in activity_list if entry.get("kod") in {"BES", "AVG", "BEH"}
                 and entry.get("status") != "planerat"
                 and iso_date(entry.get("datum")) and iso_date(entry["datum"]) <= today]
    if preferred:
        # Prefer the actual decision if present; otherwise use the committee's
        # avgörande date, then the treatment date.
        preferred.sort(key=lambda entry: ({"BES": 0, "AVG": 1, "BEH": 2}.get(entry.get("kod"), 9), entry.get("datum", "")))
        return iso_date(preferred[0].get("datum"))
    return iso_date(doc.get("datum"))


def parliamentary_progress(activity_list: list[dict], classification: dict) -> dict:
    """Keep committee work, debate and chamber decisions as separate events.

    JUS (justering) records completion of the committee report; BES records
    the chamber decision. A calendar date never proves an event took place.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    progress = {}
    for field, code in (("committee", "JUS"), ("debate", "BEH"), ("chamber", "BES")):
        entries = [item for item in activity_list if item.get("kod") == code and iso_date(item.get("datum"))]
        if not entries:
            continue
        item = max(entries, key=lambda entry: entry["datum"])
        date = iso_date(item["datum"])
        completed = item.get("status") == "inträffat" and date <= today
        progress[field] = {"date": date, "status": "completed" if completed else "planned" if item.get("status") == "planerat" else "unconfirmed"}
        if field == "committee" and completed:
            recommendation = classification.get("outcome")
            if classification.get("firstPendingDecision"):
                recommendation = "adopted"
            if recommendation in {"adopted", "rejected"}:
                progress[field]["recommendation"] = "adopt" if recommendation == "adopted" else "reject"
    return progress


def plain_source_text(value: str) -> str:
    """Decode source HTML and whitespace without rewriting its wording."""
    parser = VisibleText()
    parser.feed(value)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def report_section(text: str, heading: str) -> str | None:
    start = re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", text)
    if not start:
        return None
    tail = text[start.end():]
    end = re.search(r"(?im)^\s*(?:Behandlade förslag|Innehållsförteckning|Utskottets förslag till riksdagsbeslut)\s*$", tail)
    return tail[:end.start()].strip() if end else None


def source_summary(status: dict, text: str, document_id: str, completed: bool) -> dict | None:
    """Prefer Riksdag-authored API notices; otherwise extract a named section."""
    fields = {item.get("kod"): item for item in unwrap(status, "dokuppgift", "uppgift")}
    for code in (("notis", "utsknotis") if completed else ("utsknotis",)):
        value = fields.get(code, {}).get("text")
        if isinstance(value, str) and value.strip():
            return {"text": plain_source_text(value), "title": plain_source_text(str(fields.get(f"{code}rubrik", {}).get("text") or "")),
                    "documentId": document_id, "sourceUrl": f"{RIKSDAG_DOCUMENT}{document_id}.json",
                    "sourceField": f"dokumentstatus.dokuppgift.uppgift[kod={code}].text",
                    "kind": "decision_notice" if code == "notis" else "committee_notice"}
    section = report_section(text, "Sammanfattning")
    if section:
        return {"text": section, "title": "", "documentId": document_id,
                "sourceUrl": f"{RIKSDAG_DOCUMENT}{document_id}/text",
                "sourceField": "Sammanfattning", "kind": "report_summary"}
    return None


def first_decision_links(text: str, document_id: str) -> list[dict]:
    """Extract explicitly named pending decisions, excluding background citations."""
    section = report_section(text, "Behandlade förslag")
    if not section:
        return []
    links = []
    pattern = r"Vilande förslag (?:beslutat|beslutade) den\s+(\d{1,2})\s+(" + "|".join(SWEDISH_MONTHS) + r")\s+(\d{4})([\s\S]*?)(?=\n\s*\n|$)"
    for match in re.finditer(pattern, section, re.I):
        date = f"{int(match[3]):04d}-{SWEDISH_MONTHS[match[2].lower()]:02d}-{int(match[1]):02d}"
        for citation in re.finditer(r"\bbet\.\s*(\d{4}/\d{2}:KU\d+)\b", match[0], re.I):
            links.append({"citation": citation[1], "normalized": normalize_citation(citation[1]), "date": date,
                          "evidence": match[0], "sourceUrl": f"{RIKSDAG_DOCUMENT}{document_id}/text",
                          "sourceField": "Behandlade förslag"})
    return links


def committee_decision_text(text: str) -> str:
    """Return the committee's main decision section, excluding reservations.

    A full-text hit is not enough evidence of a first pending decision. The
    same wording commonly appears in motions and in reservations. Riksdag
    committee reports normally mark the operative section with a standalone
    ``Utskottet`` heading and put reservations after a standalone
    ``Reservationer`` heading.
    """
    folded = text.casefold()
    if not any(marker in folded for marker in ("vilande", "hvilande", "hvila", "grundlagsenlig behandling")):
        return ""

    # Modern reports expose the operative list as a heading. This section is
    # followed by the report/background or the committee's reasoning; taking
    # the whole document here would admit motion and reservation language.
    proposal_matches = list(re.finditer(r"(?im)^[ \t]*Utskottets förslag till riksdagsbeslut[ \t]*$", text))
    if proposal_matches:
        committee = proposal_matches[-1]
        tail = text[committee.end():committee.end() + 40000]
        end_matches = [
            match for pattern in (
                r"(?im)^[ \t]*Redogörelse för ärendet[ \t]*$",
                r"(?im)^[ \t]*Utskottets överväganden[ \t]*$",
                r"(?im)^[ \t]*Reservation(?:er)?[ \t]*$",
                r"(?im)^[ \t]*Bilaga\b.*$",
            )
            if (match := re.search(pattern, tail))
        ]
        end = committee.end() + min((match.start() for match in end_matches), default=len(tail))
        return text[committee.start():end]

    # Historical reports put the operative text under either a standalone
    # “Hemställan” heading or a sentence such as “utskottet ... hemställer”.
    # Find the first reservation boundary before choosing a candidate. This is
    # what keeps the 1973 main hemställan separate from its later reservations.
    reservation = re.search(
        r"(?im)^[ \t]*Reservation(?:er)?(?:\s+och\s+särskilda\s+yttranden)?[ \t]*$",
        text,
    )
    main_end = reservation.start() if reservation else len(text)

    # In historical reports the operative recommendation is normally near
    # the end. Search that tail first; the full-text Riksdag search has
    # already established that this document is worth inspecting.
    scan_start = max(0, main_end - 60000)
    operative_text = text[scan_start:main_end]
    # A contents page can contain an earlier “Hemställan” heading. The last
    # standalone heading is the operative one, so use the full document here
    # and let the section-boundary scan stop it at the real reservation.
    legacy_matches = list(re.finditer(r"(?im)^[ \t]*Hemställan[ \t]*$", text))
    if legacy_matches:
        proposal = legacy_matches[-1]
        return text[proposal.start():_operative_section_end(text, proposal.end())]

    # Allow intervening words such as “alltså”, and the older “får utskottet
    # alltså hemställa” construction. The candidate must lead to a pending
    # marker inside the main section; otherwise ordinary prose about motions
    # can become an operative slice.
    operative_matches = list(re.finditer(
        r"(?i)\butskottet\b[\s\S]{0,120}?\bhemställ(?:er|a|t)\b",
        operative_text,
    ))
    for candidate in reversed(operative_matches):
        candidate_start = scan_start + candidate.start()
        candidate_end = scan_start + candidate.end()
        candidate_text = text[candidate_start:min(main_end, candidate_start + 24000)]
        if snippets(candidate_text, FIRST_PATTERNS):
            end = min(_operative_section_end(text, candidate_end, main_end), candidate_start + 40000)
            return text[candidate_start:end]

    # Keep the committee slice for an operative rejection such as “avslår
    # motionen”, even when it contains no pending marker. This supports the
    # negative regression cases without reopening the whole document.
    if operative_matches:
        candidate = operative_matches[-1]
        candidate_start = scan_start + candidate.start()
        candidate_end = scan_start + candidate.end()
        end = min(_operative_section_end(text, candidate_end, main_end), candidate_start + 40000)
        return text[candidate_start:end]

    # No explicit operative section means there is no safe committee decision
    # slice. Returning the whole document here turns quoted motions and
    # historical discussion into false decisions, so leave it unclassified.
    return ""


def _operative_section_end(text: str, start: int, limit: int | None = None) -> int:
    """Find the end of a committee's operative section.

    OCR reports commonly put a ``Närvarande`` block between the main
    hemställan and reservations. Both are structural boundaries, unlike a
    keyword such as ``vilande`` which can occur throughout the report.
    """
    upper = min(limit if limit is not None else len(text), start + 40000)
    boundaries = [
        match.start()
        for pattern in (
            r"(?im)^[ \t]*Närvarande[ \t]*:?.*$",
            r"(?im)^[ \t]*Reservation(?:er)?(?:\s+och\s+särskilda\s+yttranden)?[ \t]*$",
            r"(?im)^[ \t]*Bilaga\b.*$",
        )
        if (match := re.search(pattern, text[start:upper]))
    ]
    return start + min(boundaries, default=upper - start)


def protocol_decision_signals(title: str, corpus: str, document_type: str = "") -> tuple[list[str], list[str]]:
    """Extract the chamber result from a protocol's vilande-proposal item."""
    if document_type != "prot" and not re.search(r"protokoll|kammaren", title, re.I):
        return [], []
    constitutional_terms = r"grundlag|successionsordningen|regeringsformen|riksdagsordningen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen"
    if not re.search(r"vilande|hvilande", corpus, re.I) or not re.search(constitutional_terms, corpus, re.I):
        return [], []
    # The older protocols use both modern and historical spellings, and the
    # outcome may be stated as “antogos”, “antagit förevarande förslag”, or a
    # decision according to the yes proposition. Do not treat the conditional
    # sentence “Vinner Nej ... förkastat” as an actual rejection.
    adopted_patterns = (
        r"förklarades\s+den\s+förra\s+propositionen\s+vara\s+med\s+över(?:\s|\xad)*vägande\s+ja\s+besvarad",
        r"(?:slutlig|slutliga)\s+prövning[\s\S]{0,180}(?:godkänt\s+och\s+)?antagit\s+(?:berörda\s+)?förslag",
        r"(?:de|det)\s+(?:under[\s\S]{0,80})?(?:vilande|hvilande)[\s\S]{0,180}(?:antogos|antogs|antagit|antagits)",
        r"(?:vilande|hvilande)\s+grundlags[\s\S]{0,180}(?:antogos|antogs|antagit|antagits)",
        r"(?:kammaren|riksdagen)\s+(?:hade\s+alltså\s+|alltså\s+)?(?:antagit|antog|bifallit)\b",
        r"(?:kammaren|riksdagen)\s+(?:hade\s+alltså\s+|alltså\s+)?bifallit\s+(?:utskottets\s+)?hemställan",
        r"(?:kammaren|riksdagen)\s+alltså\s+fattat\s+beslut\s+enligt\s+ja-propositionens",
        r"antog\s+kammaren[\s\S]{0,160}(?:förevarande|vilande|grundlagsändrings)?förslag",
        r"förklarade\s+(?:herr\s+)?talmannen[\s\S]{0,180}(?:propositionen|ja-propositionen)[\s\S]{0,100}(?:ja\s+besvarad|övervägande\s+ja)",
        r"antagit\s+förevarande\s+förslag",
    )
    rejected_patterns = (
        r"(?:kammaren|riksdagen)\s+(?:hade\s+alltså\s+|alltså\s+)?(?:förkastat|förkastade|avslagit|afslagit)\b",
        r"(?:förslaget|grundlagsändringsförslaget)[\s\S]{0,180}(?:förkastats|förkastades|avslagits|afslaget)",
        r"omröstningen\s+visade[\s\S]{0,260}(?:förkastats|förkastades|avslagits|afslaget)",
        r"(?:kammaren|riksdagen)\s+alltså\s+fattat\s+beslut\s+enligt\s+nej-propositionens",
    )

    def outcome_snippets(patterns: tuple[str, ...]) -> list[str]:
        found: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, corpus, re.I):
                # “Vinner Nej, har kammaren förkastat ...” is the fallback
                # branch of a voting proposition, not the recorded result.
                # The actual result is stated in a later sentence such as
                # “antog kammaren ...” or “fattat beslut enligt ...”.
                sentence_start = max(
                    corpus.rfind(".", 0, match.start()),
                    corpus.rfind("\n", 0, match.start()),
                ) + 1
                preceding = corpus[sentence_start:match.start()]
                if re.search(r"\bvinner\s+nej\b", preceding, re.I):
                    continue
                # A protocol contains many unrelated votes. Require a nearby
                # constitutional pending-proposal context before accepting a
                # result as a grundlag decision.
                context = corpus[max(0, match.start() - 2200):match.end() + 1000]
                if re.search(constitutional_terms, context, re.I):
                    found.append(compact(context, 520))
        return list(dict.fromkeys(found))

    return outcome_snippets(adopted_patterns), outcome_snippets(rejected_patterns)


def classify(title: str, text: str, document_type: str = "") -> dict:
    corpus = f"{title}\n{text}"
    committee_text = committee_decision_text(text)
    first = snippets(committee_text, FIRST_PATTERNS)
    # The word “förkastas” frequently occurs in the proposed text of a new
    # constitution.  Only an operative committee section (or a protocol) can
    # establish the outcome of a pending constitutional proposal.
    adopted = snippets(committee_text, FINAL_ADOPT_PATTERNS)
    rejected = snippets(committee_text, FINAL_REJECT_PATTERNS)
    protocol_adopted, protocol_rejected = protocol_decision_signals(title, corpus, document_type)
    adopted.extend(protocol_adopted)
    rejected.extend(protocol_rejected)
    adopted = list(dict.fromkeys(adopted))
    rejected = list(dict.fromkeys(rejected))
    final_context = bool(re.search(r"för slutligt beslut|slutligt beslut|slutbehandling|slutlig(?:t|a)?\s+(?:prövning|behandling|ställningstagande)|slutligt\s+avgörande", corpus, re.I))
    title_vilande = bool(re.search(r"vilande|hvilande", title, re.I))
    historic_final_title = bool(re.search(r"\b(?:uppgift|angående)\b[^\n]{0,100}\b(?:vilande|hvilande)\b[^\n]{0,100}\b(?:förslag|grundlags)", title, re.I))
    historic_final_report = bool(
        historic_final_title
        or (
            re.search(r"\bmemorial\b", title, re.I)
            and re.search(r"vilande|hvilande", corpus, re.I)
            and re.search(r"grundlag|grundlags|förslag", corpus, re.I)
        )
    )
    historic_decision_document = bool(
        re.search(r"riksdagsbeslut|riksdags\s+beslut", title, re.I)
        and re.search(r"successionsordningen|regeringsformen|tryckfrihetsförordningen|riksdagsordningen", corpus, re.I)
    )
    # Some old final records are not protocols and have no operative
    # ``Utskottet`` section. Their opening text is nevertheless an explicit
    # final-treatment record, so inspect the full text only after identifying
    # that document shape.
    if not adopted and (final_context or historic_final_report or historic_decision_document):
        adopted.extend(snippets(corpus, FINAL_ADOPT_PATTERNS))
        if historic_decision_document:
            adopted.extend(snippets(corpus, HISTORIC_DECISION_ADOPT_PATTERNS))
        adopted = list(dict.fromkeys(adopted))
    if not rejected and (final_context or historic_final_report or historic_decision_document):
        rejected.extend(snippets(corpus, FINAL_REJECT_PATTERNS))
        rejected = list(dict.fromkeys(rejected))
    final_procedure = bool(
        re.search(r"(?:anmäl|anmäler|anmäld|anmäla)[\s\S]{0,120}(?:för|till)\s+slutligt\s+beslut[\s\S]{0,120}(?:vilande|hvilande)", committee_text, re.I)
        or re.search(r"(?:vilande|hvilande)[\s\S]{0,160}(?:anmäl|anmäler|anmäld|anmäla)[\s\S]{0,120}(?:för|till)\s+slutligt\s+beslut", committee_text, re.I)
        or re.search(r"(?:det|de)\s+vilande\s+beslut(?:et|en)\s+anmäl(?:s|es)[\s\S]{0,100}(?:för|till)\s+slutligt\s+beslut", corpus, re.I)
    )
    legacy_chamber_vote = bool(protocol_adopted or protocol_rejected or re.search(r"(?:omröstningen visade|kammaren förkastat|kammaren alltså fattat beslut enligt ja-propositionens)", corpus, re.I))
    # A first-decision report may describe the future second vote. Require an
    # explicit final-procedure context before interpreting the same words as a
    # final decision.
    committee_final_context = bool(re.search(r"för slutligt beslut|slutligt beslut|slutbehandling|slutlig(?:t|a)?\s+(?:prövning|behandling|ställningstagande)|slutligt\s+avgörande", committee_text, re.I))
    historic_adoption_context = bool(re.search(r"förehaft[\s\S]{0,180}slutligt\s+avgörande[\s\S]{0,180}antagit", corpus, re.I))
    is_final = bool(
        historic_final_report
        or historic_decision_document
        or ((adopted or rejected) and (title_vilande or final_procedure or legacy_chamber_vote))
        or ((adopted or rejected) and final_context and (title_vilande or committee_final_context or historic_adoption_context))
        or (final_context and title_vilande)
    )
    is_first = bool(first) and not is_final
    rejected_before_first_signals = snippets(committee_text, REJECTED_BEFORE_FIRST_PATTERNS) if not first else []
    rejected_before_first = bool(rejected_before_first_signals)
    if is_final and rejected:
        # The operative proposal wins over rejection language in a reservation
        # or an opposition motion.  A final report can contain both.
        outcome = "adopted" if adopted else "rejected"
    elif is_final and adopted:
        outcome = "adopted"
    elif is_final:
        outcome = "unresolved"
    elif rejected_before_first:
        outcome = "rejected_before_first_constitutional_decision"
    else:
        outcome = None
    stage = "final" if is_final else "first" if is_first else "candidate"
    return {
        "stage": stage,
        "firstPendingDecision": is_first,
        "firstSignals": first,
        "finalAdoptSignals": adopted,
        "finalRejectSignals": rejected,
        "rejectedBeforeFirstSignals": rejected_before_first_signals,
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
    meeting = str(document.get("riksmote") or "")
    designation = str(document.get("designation") or "")
    number = re.search(r"\d+", designation)
    if document.get("kind") == "bet" and re.fullmatch(r"\d{4}", meeting) and number:
        values.add(f"citation:betänkande:{normalize_citation(f'{meeting}:KU{number.group(0)}')}")
    for term in document.get("legacyFinalReferenceTerms", []):
        kind = "betänkande" if re.fullmatch(r"\d{4}:KU\d+", term, re.I) else "proposition"
        values.add(f"citation:{kind}:{normalize_citation(term)}")
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


FERENDA_WORK_TYPES = (
    ("proposition", "prop", re.compile(r"^prop(?:osition)?\.?\s+(.+)$", re.I)),
    ("betänkande", "bet", re.compile(r"^bet(?:änkande)?\.?\s+(.+)$", re.I)),
    ("riksdagsskrivelse", "rskr", re.compile(r"^rskr\.?\s+(.+)$", re.I)),
    ("skrivelse", "skr", re.compile(r"^skr(?:ivelse)?\.?\s+(.+)$", re.I)),
)


def ferenda_work_uri(work: str) -> tuple[str, str] | None:
    value = re.sub(r"\s+", " ", str(work)).strip()
    for kind, path, pattern in FERENDA_WORK_TYPES:
        match = pattern.match(value)
        if not match:
            continue
        citation = re.sub(r"\s+", "", match.group(1))
        if not re.fullmatch(r"\d{4}/\d{2}:[A-Za-z0-9]+", citation):
            return None
        return kind, f"https://lagen.nu/{path}/{citation}"
    return None


def riksdag_document_id_from_source_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    match = re.search(r"data\.riksdagen\.se/dokument/([A-Za-z0-9]+)", str(source_url), re.I)
    return match.group(1).upper() if match else None


def resolve_ferenda_work(work: str, cache: dict[str, dict]) -> dict:
    """Resolve a Ferenda preparatory-work citation through the JSON API.

    The SFS artifact stores the printed citation, while the canonical Ferenda
    document record exposes the source Riksdag URL. No webpage scraping is
    involved: both values come from documented JSON endpoints.
    """
    value = re.sub(r"\s+", " ", str(work)).strip()
    if value in cache:
        return cache[value]
    parsed = ferenda_work_uri(value)
    result = {"citation": value, "ferendaUri": None, "sourceUrl": None, "riksdagDocumentId": None}
    if not parsed:
        cache[value] = result
        return result
    kind, uri = parsed
    result["ferendaUri"] = uri
    try:
        document = fetch_json(f"{FERENDA}/document?{urlencode({'uri': uri})}")
        source_url = document.get("source_url") or document.get("artifact", {}).get("source_url")
        result["sourceUrl"] = source_url
        result["riksdagDocumentId"] = riksdag_document_id_from_source_url(source_url)
        result["kind"] = kind
    except Exception as error:  # Keep an unresolved source visible in the snapshot.
        result["resolutionError"] = f"{type(error).__name__}: {error}"
    cache[value] = result
    return result


def resolve_ferenda_works(works: list[str], cache: dict[str, dict]) -> list[dict]:
    resolved = []
    seen = set()
    for work in works:
        item = resolve_ferenda_work(work, cache)
        key = item["citation"]
        if key in seen:
            continue
        seen.add(key)
        resolved.append(item)
    return resolved


def work_keys(works: list[object]) -> set[str]:
    values: set[str] = set()
    for work in works:
        if isinstance(work, dict):
            citation = work.get("citation") or work.get("label") or ""
            document_id = work.get("riksdagDocumentId")
            if document_id:
                values.add(f"document:{normalize_id(str(document_id))}")
            work = str(citation)
        normalized = normalize_citation(str(work))
        for prefix, kind in (("prop", "proposition"), ("bet", "betänkande"), ("rskr", "riksdagsskrivelse"), ("skr", "skrivelse")):
            if normalized.startswith(prefix):
                values.add(f"citation:{kind}:{normalized[len(prefix):]}")
    return values


def extract_document(document_id: str, discovery: list[str], record: dict | None = None, refresh: bool = False) -> dict:
    """Fetch and classify one result, deferring status JSON when possible.

    The document-list response already contains the title, date, type and
    designation needed for the first classification pass. Fetching the more
    expensive status document for every broad keyword hit doubled the number
    of requests, even though most hits are ordinary reports or protocols.
    Full text remains mandatory for classification; status JSON is fetched
    only after a first/final signal is found (or when list metadata is absent).
    """
    record = record or {}
    if refresh:
        # Current reports change after publication: invalidate both status and
        # text together so a scheduled vote cannot survive as a stale result.
        for url, suffix in ((f"{RIKSDAG_DOCUMENT}{document_id}.json", ".json"),
                            (f"{RIKSDAG_DOCUMENT}{document_id}/text", ".xml")):
            cache_path(url, suffix).unlink(missing_ok=True)
    text, text_url = fetch_riksdag_text(document_id)
    preliminary_title = str(record.get("titel") or document_id)
    preliminary_type = str(record.get("doktyp") or "")
    preliminary_classification = classify(preliminary_title, text, preliminary_type)
    needs_status = bool(
        preliminary_classification["stage"] in {"first", "final"}
        or not record.get("titel")
    )
    status = fetch_json(f"{RIKSDAG_DOCUMENT}{document_id}.json") if needs_status else {}
    refs = structured_references(status)
    activity_list = activities(status)
    status_container = status.get("dokumentstatus", {})
    doc = status_container.get("dokument", {}) or record
    # A status response is authoritative when present; list metadata is the
    # intentional fallback for ordinary keyword candidates.
    title = str(doc.get("titel") or preliminary_title)
    document_type = str(doc.get("doktyp") or preliminary_type)
    if title == preliminary_title and document_type == preliminary_type:
        classification = preliminary_classification
    else:
        classification = classify(title, text, document_type)
    resolved_decision_date = decision_date(doc, activity_list)
    progress = parliamentary_progress(activity_list, classification)
    decision_activities = [item for item in activity_list if item.get("kod") == "BES"]
    today = datetime.now(timezone.utc).date().isoformat()
    decision_completed = any(item.get("status") == "inträffat"
                             and (iso_date(item.get("datum")) or "9999") <= today
                             for item in decision_activities)
    planned_date = next((iso_date(item.get("datum")) for item in decision_activities
                         if item.get("status") == "planerat"), None)
    # Modern committee recommendations describe what should happen. Their
    # operative wording becomes a chamber result only after an actual vote.
    # Historical documents often have no activity metadata at all.
    if activity_list and not decision_completed:
        resolved_decision_date = None
        classification = {**classification, "outcome": "unresolved"}
    if decision_completed and classification["stage"] == "final":
        points = unwrap(status_container, "dokutskottsforslag", "utskottsforslag")
        relevant = [point for point in points if re.search(r"slutligt|vilande", html.unescape(str(point.get("forslag", ""))), re.I)]
        if relevant and any(point.get("vinnare") != "utskottet" for point in relevant):
            classification = {**classification, "outcome": "unresolved"}
    is_decision = classification["stage"] in {"first", "final"}
    source_text = source_summary(status_container, text, document_id, decision_completed) if is_decision else None
    operative_targets = constitution_ids(committee_decision_text(text)) if is_decision else []
    return {
        "documentId": str(doc.get("dok_id") or document_id).upper(),
        "kind": document_type or "bet",
        "subkind": doc.get("subtyp"),
        "riksmote": doc.get("rm"),
        "designation": doc.get("beteckning"),
        "title": title,
        "publishedDate": iso_date(doc.get("datum")),
        "decisionDate": resolved_decision_date,
        "decisionCompleted": decision_completed if activity_list else None,
        "plannedDecisionDate": planned_date,
        "parliamentaryProgress": progress,
        **({"sourceText": source_text} if source_text else {}),
        "firstDecisionLinks": first_decision_links(text, document_id) if is_decision else [],
        "documentUrl": doc.get("dokument_url_html") or record.get("dokument_url_html") or f"{RIKSDAG_DOCUMENT}{document_id}",
        "textUrl": text_url,
        "source": "Riksdagens öppna data",
        "discovery": discovery,
        "constitutionIds": operative_targets or constitution_ids(f"{title}\n{text}"),
        "structuredReferences": refs,
        # These secondary text indexes are only consumed for first/final
        # decisions. Skipping them for broad keyword candidates avoids four
        # additional full-document regex passes per ordinary OCR hit.
        "citations": citations(text) if is_decision else [],
        "legacyFinalReferenceTerms": legacy_final_reference_terms(text, resolved_decision_date, classification["stage"]) if is_decision else [],
        "legalTargetHints": legal_target_hints(text) if is_decision else [],
        "voteHints": vote_hints(text) if is_decision and document_type == "prot" else [],
        "dateHints": date_hints(text, doc.get("rm")) if is_decision else [],
        "activity": [{"code": item.get("kod"), "name": item.get("namn"), "date": iso_date(item.get("datum")), "status": item.get("status")} for item in activity_list],
        "textLength": len(text),
        "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "classification": classification,
        "evidence": classification["firstSignals"] + classification["finalAdoptSignals"] + classification["finalRejectSignals"] + classification["rejectedBeforeFirstSignals"],
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


def ferenda_betankande_search_terms(changes: list[dict]) -> list[str]:
    """Return proposition citations usable as supplementary KU search seeds.

    SFS is not a source of proposal records: rejected constitutional changes
    are absent from it.  These citations only expand the Riksdag betänkande
    discovery set after the independent keyword sweep has run.
    """
    terms: list[str] = []
    for change in changes:
        for reference in change.get("preparatoryWorkReferences", []):
            if reference.get("kind") != "proposition":
                continue
            match = re.search(r"\b(\d{4}/\d{2}:\d+)\b", str(reference.get("citation") or ""))
            if match:
                terms.append(match.group(1))
    return list(dict.fromkeys(terms))


def pair_decisions(documents: list[dict], changes: list[dict] | None = None) -> list[dict]:
    firsts = [doc for doc in documents if doc["classification"]["stage"] == "first" and doc.get("decisionCompleted") is not False]
    finals = [doc for doc in documents if doc["classification"]["stage"] == "final"]
    records: list[dict] = []

    def sfs_ids_for_document(document: dict) -> set[str]:
        if not changes:
            return set()
        keys = {
            f"document:{normalize_id(ref.get('ref_dok_id'))}"
            for ref in document.get("structuredReferences", [])
            if ref.get("ref_dok_id")
        }
        if not keys:
            keys = {
                f"citation:{item['kind']}:{item['normalized']}"
                for item in document.get("citations", [])
                if item.get("kind") and item.get("normalized")
            }
        return {
            change["sfs"]
            for change in changes
            if keys & work_keys(change.get("preparatoryWorkReferences") or change.get("preparatoryWorks", []))
        }

    for first in firsts:
        first_date = first.get("decisionDate") or first.get("publishedDate") or "9999-99-99"
        first_citation = normalize_citation(f"{first.get('riksmote')}:{first.get('designation')}")
        first_keys = ref_keys(first)
        first_sfs_ids = sfs_ids_for_document(first)
        scored: list[tuple[int, dict]] = []
        for final in finals:
            final_date = final.get("decisionDate") or final.get("publishedDate") or "0000-00-00"
            if final_date <= first_date:
                continue
            # A later report can quote a historic proposition without being
            # its post-election second decision.  Keep the generic reference
            # matcher within the longest possible ordinary electoral cycle;
            # broader historic pairing needs explicit chamber evidence.
            if int(final_date[:4]) - int(first_date[:4]) > MAX_FINAL_DECISION_YEARS:
                continue
            explicit_links = final.get("firstDecisionLinks", [])
            direct = [link for link in explicit_links if link["normalized"] == first_citation and link["date"] == first_date]
            # When a report explicitly names the decision it treats, a shared
            # background reference cannot connect it to a different case.
            if explicit_links and not direct:
                continue
            shared = first_keys & ref_keys(final)
            shared_proposition = len(proposition_keys(first) & proposition_keys(final))
            shared_bet = len({key for key in shared if "betänkande" in key})
            shared_document = len({key for key in shared if key.startswith("document:")})
            shared_sfs = first_sfs_ids & sfs_ids_for_document(final)
            # Constitution overlap alone is never evidence of a pair: a KU
            # report routinely cites many unrelated constitutional matters.
            # A shared Ferenda amendment is an independent secondary-source
            # signal, especially important for initiative cases without a
            # proposition (for example GE01KU20).
            score = (100000 if direct else 0) + shared_proposition * 50 + shared_bet * 12 + shared_document * 20 + len(shared_sfs) * 35
            if score:
                scored.append((score, final))
        scored.sort(key=lambda pair: (pair[0], pair[1].get("decisionDate") or ""), reverse=True)
        final = scored[0][1] if scored and scored[0][0] >= 12 else None
        # A historic “Riksdagsbeslutet” can contain the chamber's final vote
        # for several pending proposals while the KU memorial supplies the
        # item-by-item references to their first reports.  Join those two
        # primary records when they overlap in constitution and year.
        if final and final.get("kind") == "bet" and final.get("classification", {}).get("outcome") == "unresolved":
            final_year = (final.get("decisionDate") or "")[:4]
            protocol_candidates = [
                candidate for candidate in finals
                if candidate.get("kind") == "prot"
                and candidate.get("classification", {}).get("outcome") in {"adopted", "rejected"}
                and (candidate.get("decisionDate") or "")[:4] == final_year
                and set(first.get("constitutionIds", [])) & set(candidate.get("constitutionIds", []))
            ]
            if protocol_candidates:
                protocol_candidates.sort(key=lambda candidate: candidate.get("decisionDate") or "")
                final = protocol_candidates[0]
        committee = None
        if final and final.get("kind") != "bet":
            committee_candidates: list[tuple[int, dict]] = []
            for candidate in finals:
                if candidate["documentId"] == final["documentId"] or candidate.get("kind") != "bet":
                    continue
                candidate_date = candidate.get("decisionDate") or candidate.get("publishedDate") or "0000-00-00"
                final_date = final.get("decisionDate") or final.get("publishedDate") or "9999-99-99"
                if not (first_date < candidate_date <= final_date):
                    continue
                shared = ref_keys(candidate) & ref_keys(final)
                shared_proposition = len(proposition_keys(first) & proposition_keys(candidate))
                shared_bet = len({key for key in shared if "betänkande" in key})
                if shared_proposition or shared_bet:
                    committee_candidates.append((shared_proposition * 50 + shared_bet * 12, candidate))
            if committee_candidates:
                committee_candidates.sort(key=lambda pair: (pair[0], pair[1].get("decisionDate") or ""), reverse=True)
                committee = committee_candidates[0][1]
        records.append(proposal_record(first, final, scored[0][0] if final and scored else 0, committee))

    return records


def confirm_historic_first_decisions(documents: list[dict]) -> None:
    """Promote only KU reports explicitly named by a later final report.

    Before 1975 the first KU report did not always repeat the word
    ``vilande`` in its operative clause.  The subsequent KU final-treatment
    report can, however, identify that exact report as one of the pending
    decisions.  This records that direct parliamentary evidence without
    treating SFS metadata, a title, or a bare keyword as proof.
    """
    by_historic_ku_term: dict[str, dict] = {}
    for document in documents:
        meeting = str(document.get("riksmote") or "")
        designation = str(document.get("designation") or "")
        number = re.search(r"\d+", designation)
        if document.get("kind") == "bet" and re.fullmatch(r"\d{4}", meeting) and number:
            by_historic_ku_term[f"{meeting}:KU{number.group(0)}".upper()] = document

    for final in documents:
        if final.get("classification", {}).get("stage") != "final":
            continue
        final_date = final.get("decisionDate") or final.get("publishedDate") or ""
        for term in final.get("legacyFinalReferenceTerms", []):
            first = by_historic_ku_term.get(term.upper())
            if not first:
                continue
            first_date = first.get("decisionDate") or first.get("publishedDate") or ""
            if not first_date or not final_date or first_date >= final_date:
                continue
            classification = first["classification"]
            if classification["stage"] != "candidate" or classification.get("outcome"):
                continue
            evidence = (
                f"{final['documentId']} identifies {term} as a proposal adopted "
                f"as pending before its final parliamentary treatment."
            )
            classification.update({
                "stage": "first",
                "firstPendingDecision": True,
                "firstSignals": [*classification.get("firstSignals", []), evidence],
            })
            first["evidence"] = [*first.get("evidence", []), evidence]
            first["historicFinalConfirmation"] = {
                "term": term,
                "finalDocumentId": final["documentId"],
                "finalDocumentUrl": final["documentUrl"],
            }


def proposal_record(first: dict, final: dict | None, score: int, committee: dict | None = None) -> dict:
    next_decision = None
    progress = None
    source_text = (final or {}).get("sourceText") or first.get("sourceText")
    explicit = next((link for link in (final or {}).get("firstDecisionLinks", [])
                     if link["normalized"] == normalize_citation(f"{first.get('riksmote')}:{first.get('designation')}")
                     and link["date"] == first.get("decisionDate")), None)
    match = ({"method": "explicit_first_decision_citation", "evidence": explicit}
             if explicit else {"method": "shared_document_references", "confidence": min(1.0, score / 30), "score": score}
             if final else {"method": "no_final_match", "confidence": 0.0, "score": 0})
    if final and final.get("parliamentaryProgress"):
        progress = {**final["parliamentaryProgress"], "documentId": final["documentId"],
                    "documentUrl": final["documentUrl"],
                    "designation": f"{final.get('riksmote')}:{final.get('designation')}"}
    if final and final.get("decisionCompleted") is False:
        next_decision = {
            "documentId": final["documentId"],
            "documentUrl": final["documentUrl"],
            "date": final.get("plannedDecisionDate"),
            "status": "planned" if final.get("plannedDecisionDate") else "awaiting_decision",
        }
        final = None
    if next_decision:
        status, temporal = "pending", "future"
    elif final is None:
        # An explicitly completed modern first vote adopts the proposal as
        # pending. Keep it visible before a follow-up report is published;
        # do not promote unmatched historical records into a current queue.
        first_year = int((first.get("decisionDate") or "0000")[:4])
        recent_first = first.get("decisionCompleted") is True and 0 <= datetime.now(timezone.utc).year - first_year <= MAX_FINAL_DECISION_YEARS
        status = "pending" if recent_first else "unresolved"
        temporal = "future" if recent_first else "past"
    elif final["classification"]["outcome"] == "rejected":
        status, temporal = "rejected", "past"
    elif final["classification"]["outcome"] == "adopted":
        status, temporal = "adopted", "past"
    else:
        status, temporal = "unresolved", "past"
    first_refs = [ref.get("ref_dok_id") for ref in first.get("structuredReferences", []) if ref.get("ref_dok_id")]
    final_refs = [ref.get("ref_dok_id") for ref in final.get("structuredReferences", []) if ref.get("ref_dok_id")] if final else []
    committee_refs = []
    if committee and committee.get("riksmote") and committee.get("designation"):
        committee_value = f"{committee['riksmote']}:{committee['designation']}"
        committee_refs = [{
            "kind": "betänkande",
            "value": committee_value,
            "normalized": normalize_citation(committee_value),
        }]
    final_decision = None
    if final:
        final_decision = {
            "status": final["classification"]["outcome"],
            "documentId": final["documentId"],
            "date": final.get("decisionDate") or final.get("publishedDate"),
            "documentUrl": final["documentUrl"],
            "propositionReferences": [item for item in final.get("citations", []) if item["kind"] == "proposition"],
            "riksdagCitationReferences": [item for item in final.get("citations", []) if item["kind"] != "proposition"],
            "riksdagReferences": final_refs,
            "evidence": final.get("evidence", []),
        }
        if committee:
            final_decision.update({
                "committeeDocumentId": committee["documentId"],
                "committeeDocumentUrl": committee["documentUrl"],
                "committeeDecisionDate": committee.get("decisionDate") or committee.get("publishedDate"),
                "committeeReferences": committee_refs,
            })
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
        "finalDecision": final_decision,
        **({"sourceText": source_text} if source_text else {}),
        **({"nextDecision": next_decision} if next_decision else {}),
        **({"parliamentaryProgress": progress} if progress else {}),
        "sfsIds": [],
        "match": match,
        "documentIds": list(dict.fromkeys([first["documentId"], *([committee["documentId"]] if committee else []), *([final["documentId"]] if final else []), *([next_decision["documentId"]] if next_decision else [])])),
        "provenance": [
            {"field": "firstDecision", "sourceUrl": first["documentUrl"], "sourceDocumentId": first["documentId"], "method": "riksdag_status_and_text"},
            *([{ "field": "finalDecision.committeeDocumentId", "sourceUrl": committee["documentUrl"], "sourceDocumentId": committee["documentId"], "method": "shared_document_references_and_text" }] if committee else []),
            *([{ "field": "finalDecision", "sourceUrl": final["documentUrl"], "sourceDocumentId": final["documentId"], "method": "shared_document_references_and_text" }] if final else []),
            *([{ "field": "parliamentaryProgress", "sourceUrl": progress["documentUrl"], "sourceDocumentId": progress["documentId"], "method": "riksdag_activity_status_and_committee_text" }] if progress else []),
            *([{ "field": "sourceText", "sourceUrl": source_text["sourceUrl"], "sourceDocumentId": source_text["documentId"], "sourceField": source_text["sourceField"], "method": "source_text_without_rewriting" }] if source_text else []),
        ],
    }


def fetch_ferenda_changes() -> tuple[list[dict], dict[str, dict]]:
    changes: list[dict] = []
    catalogs: dict[str, dict] = {}
    preparatory_work_cache: dict[str, dict] = {}
    for law in CONSTITUTIONS:
        document = fetch_json(f"{FERENDA}/document?{urlencode({'uri': law['uri']})}", max_age=86400)
        versions_response = fetch_json(f"{FERENDA}/document/versions?{urlencode({'uri': law['uri']})}", max_age=86400)
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
            work_references = resolve_ferenda_works(works, preparatory_work_cache)
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
                "preparatoryWorkReferences": work_references,
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

    def decision_keys(decision: dict | None) -> set[str]:
        if not decision:
            return set()
        # Structured Riksdag IDs are the reliable bridge to Ferenda. Text
        # citations contain historical/background references as well, which
        # would otherwise attach unrelated SFS amendments to one case.
        values = {
            f"document:{normalize_id(value)}"
            for value in decision.get("riksdagReferences", [])
            if value
        }
        if not values:
            values = {
                f"citation:{item['kind']}:{item['normalized']}"
                for field in ("propositionReferences", "riksdagCitationReferences")
                for item in decision.get(field, [])
                if item.get("kind") and item.get("normalized")
            }
        return values

    for proposal in proposals:
        first_keys = decision_keys(proposal.get("firstDecision"))
        final_keys = decision_keys(proposal.get("finalDecision"))
        first_matches = []
        final_matches = []
        evidence = []
        for change in changes:
            works = work_keys(change.get("preparatoryWorkReferences") or change.get("preparatoryWorks", []))
            first_overlap = first_keys & works
            final_overlap = final_keys & works
            if first_overlap or final_overlap:
                if first_overlap:
                    first_matches.append(change["sfs"])
                if final_overlap:
                    final_matches.append(change["sfs"])
                evidence.append({
                    "sfs": change["sfs"],
                    "match": "first" if first_overlap and not final_overlap else "final" if final_overlap and not first_overlap else "first_and_final",
                    "matchedKeys": sorted(first_overlap | final_overlap),
                    "preparatoryWorks": change.get("preparatoryWorkReferences", []),
                    "sourceUrl": change.get("sfsMetadataUrl"),
                })
        # Prefer the SFS amendments cited by the first decision. A final KU
        # report can settle several independent first decisions in one
        # riksdagsskrivelse, so using its references alone is too broad.
        matches = list(dict.fromkeys(first_matches or final_matches))
        proposal["sfsIds"] = matches
        proposal["sfsValidation"] = {
            "source": "Ferenda SFS amendment metadata via documented JSON API",
            "firstDecisionConfirmed": bool(first_matches),
            "finalDecisionConfirmed": bool(final_matches),
            "firstDecisionSfsIds": list(dict.fromkeys(first_matches)),
            "finalDecisionSfsIds": list(dict.fromkeys(final_matches)),
            "evidence": evidence,
        }
        if proposal["status"] == "adopted" and not matches:
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
            "firstDecisionSfsConfirmation": sum(1 for item in proposals if item.get("sfsValidation", {}).get("firstDecisionConfirmed")),
            "sfsToRiksdag": {"changes": len(changes), "matched": len(changes) - len(orphan_sfs), "orphan": len(orphan_sfs)},
        },
    }


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    # Fetch SFS metadata first, but use it only to supplement Riksdag keyword
    # discovery.  It must never decide whether a parliamentary case exists.
    changes, catalogs = fetch_ferenda_changes()
    elections = fetch_wikidata_elections()
    discovered: dict[str, dict] = {}

    def add_discovered(record: dict, discovery: str, force: bool = False) -> None:
        document_id = str(record.get("dok_id") or record.get("id") or "").upper()
        if not document_id or (not force and not candidate_from_record(record, discovery)):
            return
        entry = discovered.setdefault(document_id, {"record": record, "queries": []})
        entry["queries"].append(discovery)

    for query in DISCOVERY_QUERIES:
        for record in document_list(query):
            # The Riksdag API has already matched this document's full text
            # against the discovery keyword.  Older KU reports often have a
            # generic title and an empty summary, so a second metadata filter
            # would silently remove genuine first-decision reports.
            add_discovered(record, query, force=True)
    sfs_seed_citations = ferenda_betankande_search_terms(changes)
    for citation in sfs_seed_citations:
        for record in document_list(citation):
            add_discovered(record, f"ferenda-sfs-proposition:{citation}", force=True)
    for law in CONSTITUTIONS:
        law_query = f"{law['title']} vilande"
        for record in document_list(law_query):
            add_discovered(record, f"ferenda-sfs-law-discovery:{law['id']}", force=True)
    for document_id in REGRESSION_DOCUMENT_IDS:
        discovered.setdefault(document_id, {"record": {"dok_id": document_id}, "queries": ["regression-fixture"]})
    checkpoint = load_build_checkpoint()
    refresh_from = f"{datetime.now(timezone.utc).year - MAX_FINAL_DECISION_YEARS}-01-01"
    recent_ids = {document["documentId"] for document in checkpoint.get("documents", [])
                  if (document.get("publishedDate") or "") >= refresh_from}
    documents_by_id = {
        str(document.get("documentId", "")).upper(): document
        for document in checkpoint.get("documents", [])
        if document.get("documentId") and document["documentId"] not in recent_ids
    }
    errors_by_id = {
        str(error.get("documentId", "")).upper(): error
        for error in checkpoint.get("errors", [])
        if error.get("documentId")
    }
    if documents_by_id:
        print(f"Resuming from checkpoint: {len(documents_by_id)} documents already classified.", flush=True)

    def save_progress(phase: str) -> None:
        save_build_checkpoint(list(documents_by_id.values()), list(errors_by_id.values()), phase)

    def extract_pending(entries: list[tuple[str, dict]], phase: str) -> None:
        pending = [(document_id, entry) for document_id, entry in entries if document_id not in documents_by_id]
        total = len(pending)
        for index, (document_id, entry) in enumerate(pending, 1):
            try:
                refresh = document_id in recent_ids or str(entry.get("record", {}).get("datum") or "") >= refresh_from
                documents_by_id[document_id] = extract_document(document_id, entry["queries"], entry.get("record"), refresh=refresh)
                errors_by_id.pop(document_id, None)
            except Exception as error:
                errors_by_id[document_id] = {"documentId": document_id, "error": str(error), "discovery": entry["queries"]}
            if index == total or index % 25 == 0:
                save_progress(phase)
                print(f"{phase}: {index}/{total} documents processed; {len(documents_by_id)} total classified.", flush=True)

    extract_pending(sorted(discovered.items()), "initial extraction")
    save_progress("initial extraction complete")

    # Historic final-treatment reports provide the old-style KU/proposition
    # references needed to find their original first-decision reports.  Run
    # that small, explicit second discovery pass before pairing—not from SFS,
    # and never by inventing a link from a law amendment.
    documents = list(documents_by_id.values())
    extracted_ids = set(documents_by_id)
    for document in documents:
        for citation in document.get("legacyFinalReferenceTerms", []):
            for record in document_list(citation):
                add_discovered(record, f"historic-final-reference:{document['documentId']}:{citation}", force=True)
        if document.get("classification", {}).get("stage") == "final":
            decision_date = document.get("decisionDate") or ""
            if decision_date < "1976-01-01" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", decision_date):
                year = decision_date[:4]
                for record in document_list(
                    "vilande grundlag",
                    document_type="prot",
                    organization="",
                    date_from=f"{year}-01-01",
                    date_to=f"{year}-12-31",
                ):
                    add_discovered(record, f"historic-final-protocol:{document['documentId']}", force=True)
    extract_pending(
        [(document_id, entry) for document_id, entry in sorted(discovered.items()) if document_id not in extracted_ids],
        "historic supplemental extraction",
    )
    documents = list(documents_by_id.values())
    errors = list(errors_by_id.values())
    save_progress("document extraction complete")

    confirm_historic_first_decisions(documents)
    save_progress("classification complete")

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

    write_outputs(documents, changes, catalogs, elections, errors, len(discovered), len(sfs_seed_citations))
    save_build_checkpoint(documents, errors, "complete")


def write_outputs(documents: list[dict], changes: list[dict], catalogs: dict, elections: list[dict],
                  errors: list[dict], candidate_count: int, sfs_seed_count: int,
                  refresh_metadata: dict | None = None) -> None:
    """Publish the same snapshot, graph and indexes for full and recent updates."""
    graph = graph_for(documents)
    proposals = pair_decisions(documents, changes)
    match_report = attach_sfs(proposals, changes)
    generated_at = now()
    output = {
        "generatedAt": generated_at,
        **(refresh_metadata or {}),
        "fetchMetrics": dict(FETCH_METRICS),
        "scope": {"parliamentaryFrom": START_DATE, "note": "Riksdag KU discovery runs from the first digitised parliamentary year (1867). Ferenda SFS is secondary confirmation for the resulting decision chains."},
        "election": {
            "dates": elections,
            "source": "Wikidata Swedish general elections",
            "queryUrl": WIKIDATA_SPARQL,
        },
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
            "ferendaSfsPropositionSeeds": sfs_seed_count,
            "modernCandidateDocuments": candidate_count,
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
    print(f"Published {len(documents)} Riksdag documents; built {len(proposals)} proposal records and {len(changes)} SFS changes.")
    print(f"First decisions: {sum(1 for proposal in proposals if proposal.get('firstDecision'))}; final decisions: {sum(1 for proposal in proposals if proposal.get('finalDecision'))}; rejected: {sum(1 for proposal in proposals if proposal['status'] == 'rejected')}; unresolved/pending: {sum(1 for proposal in proposals if proposal['status'] in {'pending', 'unresolved'})}.")


if __name__ == "__main__":
    main()
