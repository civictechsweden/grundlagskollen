"""Generate an auditable experiment for constitutional law versions.

The experiment uses Ferenda's SFS metadata and consolidated HTML pages. It does
not attempt to reconstruct a law by applying PDF amendments. Where Ferenda
doesn't expose a consolidated page for an SFS event, the output records a
metadata-only snapshot and explains the gap in the report.

Example:
    uv run --locked scripts/generate_versions.py --git
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import re
import ssl
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/changes.json"
FERENDA_API = "https://ferenda.lagen.nu/api/v1"
FERENDA_WEB = "https://ferenda.lagen.nu"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where() if certifi else None)


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "grundlagsmonitor-version-experiment/0.1"})
    with urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        return json.load(response)


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "grundlagsmonitor-version-experiment/0.1"})
    with urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        return response.read()


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class LegalTextParser(HTMLParser):
    """Extract readable legal text without depending on BeautifulSoup."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self.main_depth += 1
        if tag in self.SKIP:
            self.skip_depth += 1
        if self.main_depth and not self.skip_depth and tag in {"p", "h1", "h2", "h3", "h4", "li", "tr", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.main_depth and not self.skip_depth and tag in {"p", "h1", "h2", "h3", "h4", "li", "tr", "br"}:
            self.parts.append("\n")
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "main" and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.main_depth and not self.skip_depth:
            self.parts.append(data)


def legal_text(raw: bytes) -> str:
    parser = LegalTextParser()
    parser.feed(raw.decode("utf-8", "ignore"))
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def ferenda_web_url(uri: str) -> str:
    if uri.startswith("https://lagen.nu"):
        return uri.replace("https://lagen.nu", FERENDA_WEB, 1)
    if uri.startswith("/"):
        return FERENDA_WEB + uri
    return uri


def load_catalog(snapshot: dict, law: dict) -> list[dict]:
    catalog = snapshot.get("versionCatalog", {}).get(law["id"], {})
    versions = catalog.get("versions", [])
    if versions:
        return versions
    uri = quote(law["uri"], safe="")
    return fetch_json(f"{FERENDA_API}/document/versions?uri={uri}").get("versions", [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "frontend/public/versions"), help="Directory for generated public artifacts")
    parser.add_argument("--git", action="store_true", help="Commit the generated output to a separate bare git repository")
    parser.add_argument("--git-dir", default=str(ROOT / ".versions-git"), help="Bare repository used with --git")
    args = parser.parse_args()

    snapshot = json.loads(DATA.read_text())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    report: dict = {
        "generatedAt": generated_at,
        "source": "Ferenda / lagen.nu",
        "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "laws": {},
        "limitations": [
            "Ferenda exposes a finite list of consolidated versions; it is not the same thing as one full text snapshot per SFS amendment.",
            "SFS metadata identifies effective dates, replaced provisions and inserted provisions, but does not by itself contain enough structure to apply every textual amendment deterministically.",
            "Events with missing effective-date metadata are retained as metadata-only records and are not silently assigned a date.",
            "A generated diff compares Ferenda HTML snapshots after text normalization; it is not a legally authoritative redline.",
        ],
    }
    patch_map: dict[str, dict] = {}
    all_history = snapshot.get("changes", [])

    for law in snapshot.get("constitutions", []):
        if not law.get("sfs"):
            continue
        law_id = law["id"]
        law_root = output / law_id
        html_dir = law_root / "html"
        text_dir = law_root / "text"
        patch_dir = output / "patches"
        for directory in (html_dir, text_dir, patch_dir):
            directory.mkdir(parents=True, exist_ok=True)

        versions = load_catalog(snapshot, law)
        versions = sorted(versions, key=lambda item: (item.get("ikraft") or "9999-99-99", item.get("version", "")))
        entries: list[dict] = []
        texts: list[tuple[dict, str]] = []
        errors: list[dict] = []

        for version in versions:
            version_id = version.get("version") or law["sfs"]
            source_url = ferenda_web_url(version.get("uri") or f"{FERENDA_WEB}/{law['sfs']}/konsolidering/{version_id}")
            key = slug(version_id)
            try:
                raw = fetch_bytes(source_url)
                normalized = legal_text(raw)
                html_path = html_dir / f"{key}.html"
                text_path = text_dir / f"{key}.txt"
                html_path.write_bytes(raw)
                text_path.write_text(normalized)
                entries.append({
                    "version": version_id,
                    "ikraft": version.get("ikraft"),
                    "forarbeten": version.get("forarbeten", []),
                    "sourceUrl": source_url,
                    "html": f"/versions/{law_id}/html/{key}.html",
                    "text": f"/versions/{law_id}/text/{key}.txt",
                    "sha256": hashlib.sha256(normalized.encode()).hexdigest(),
                    "characters": len(normalized),
                    "status": "fetched",
                })
                texts.append((version, normalized))
            except Exception as error:
                error_record = {"version": version_id, "sourceUrl": source_url, "error": str(error)}
                errors.append(error_record)
                entries.append({**error_record, "status": "error"})

        texts.sort(key=lambda item: (item[0].get("ikraft") or "9999-99-99", item[0].get("version", "")))
        patches: list[dict] = []
        for (before_meta, before_text), (after_meta, after_text) in zip(texts, texts[1:]):
            before_id = before_meta.get("version") or law["sfs"]
            after_id = after_meta.get("version") or law["sfs"]
            patch_name = f"{law_id}-{slug(before_id)}-to-{slug(after_id)}.diff"
            diff = "".join(difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"{law_id}/{before_id}",
                tofile=f"{law_id}/{after_id}",
            ))
            (patch_dir / patch_name).write_text(diff)
            patch_record = {
                "from": before_id,
                "to": after_id,
                "path": f"/versions/patches/{patch_name}",
                "changedLines": sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))),
                "characters": len(diff),
            }
            patches.append(patch_record)
            for history_item in all_history:
                if history_item.get("constitutionId") == law_id and history_item.get("sfs") == after_id:
                    patch_map[f"{law_id}:{after_id}"] = patch_record

        dated_history = [item for item in all_history if item.get("constitutionId") == law_id and item.get("date")]
        dated_events = sorted({item["date"] for item in dated_history})
        fetched_by_date = {item.get("ikraft") for item in entries if item.get("status") == "fetched" and item.get("ikraft")}
        snapshots: list[dict] = []
        for effective_date in dated_events:
            event_sfs = [item["sfs"] for item in dated_history if item.get("date") == effective_date]
            canonical = [item for item in entries if item.get("ikraft") == effective_date and item.get("status") == "fetched"]
            snapshots.append({
                "effectiveDate": effective_date,
                "events": event_sfs,
                "triggeringSfs": event_sfs,
                "status": "ferenda-reference" if canonical else "metadata-only",
                "canonicalVersions": [item["version"] for item in canonical],
                "generatedText": None,
                "note": "Ferenda-texten är en benchmarkreferens; den är inte producerad genom att applicera SFS-operationer." if canonical else "Ingen Ferenda-konsolidering exponerad för detta ikraftträdandedatum.",
            })

        missing_date_events = [item.get("sfs") for item in all_history if item.get("constitutionId") == law_id and not item.get("date")]
        sfs_patches = [
            {
                "sfs": item.get("sfs"),
                "effectiveDate": item.get("date"),
                "sourceUrl": item.get("sfsMetadataUrl"),
                "metadata": item.get("metadata", {}),
                "operations": item.get("operations", []),
                "preparatoryWorks": item.get("preparatoryWorks", []),
                "status": "parsed-metadata" if all(operation.get("operationType") != "unknown_instruction" for operation in item.get("operations", [])) else "needs-review",
            }
            for item in sorted(dated_history + [event for event in all_history if event.get("constitutionId") == law_id and not event.get("date")], key=lambda value: (value.get("date") or "9999-99-99", value.get("sfs") or ""))
        ]
        law_manifest = {
            "constitutionId": law_id,
            "baseSfs": law["sfs"],
            "source": "SFS metadata + Ferenda consolidated HTML",
            "versions": entries,
            "patches": patches,
            "sfsPatches": sfs_patches,
            "snapshots": snapshots,
            "generation": {
                "baseVersion": law["sfs"],
                "method": "SFS metadata operation ledger",
                "fullTextApplication": "not_attempted",
                "reason": "The metadata identifies targets and effective dates, but many amendments do not expose replacement text in metadata.",
            },
            "summary": {
                "catalogVersions": len(versions),
                "fetchedVersions": sum(1 for item in entries if item.get("status") == "fetched"),
                "fetchErrors": len(errors),
                "datedChangeBatches": len(dated_events),
                "canonicalChangeBatches": sum(1 for item in snapshots if item["status"] == "ferenda-reference"),
                "metadataOnlyChangeBatches": sum(1 for item in snapshots if item["status"] == "metadata-only"),
                "amendmentsMissingEffectiveDate": len(missing_date_events),
                "effectiveDateCoverage": round(sum(1 for item in snapshots if item["status"] == "ferenda-reference") / len(dated_events), 4) if dated_events else None,
                "sfsPatches": len(sfs_patches),
                "sfsPatchesNeedingReview": sum(1 for item in sfs_patches if item["status"] == "needs-review"),
            },
        }
        write_json(law_root / "manifest.json", law_manifest)
        report["laws"][law_id] = law_manifest["summary"]

    fetched_versions = sum(summary["fetchedVersions"] for summary in report["laws"].values())
    report["summary"] = {
        "fetchedVersions": fetched_versions,
        "exactMatches": 0,
        "normalizedMatches": 0,
        "mismatches": 0,
        "notComparable": fetched_versions,
        "fullTextApplication": "not_attempted",
    }
    version_report = {
        "generatedAt": generated_at,
        "laws": report["laws"],
        "patches": len(patch_map),
        "summary": report["summary"],
        "limitations": report["limitations"],
    }
    write_json(ROOT / "data/version-report.json", version_report)
    write_json(ROOT / "data/version-patches.json", {"generatedAt": generated_at, "patches": patch_map, "note": "Patch paths are relative to the static frontend root."})

    lines = [
        "# Version experiment",
        "",
        f"Generated: `{generated_at}`",
        "",
        "The experiment uses SFS metadata and Ferenda's consolidated HTML. It does not parse amendment PDFs.",
        "SFS operations are parsed into a reviewable ledger. Full-text application is intentionally reported as `not_attempted` until replacement text and a verified base snapshot are available.",
        "",
        "| Law | Ferenda versions | Fetched | Dated batches | Ferenda references | Metadata-only batches | SFS patches | Needs review | Missing dates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for law_id, summary in report["laws"].items():
        lines.append(f"| {law_id.upper()} | {summary['catalogVersions']} | {summary['fetchedVersions']} | {summary['datedChangeBatches']} | {summary['canonicalChangeBatches']} | {summary['metadataOnlyChangeBatches']} | {summary['sfsPatches']} | {summary['sfsPatchesNeedingReview']} | {summary['amendmentsMissingEffectiveDate']} |")
    lines += ["", "## Interpretation", "", "Ferenda-reference batches are dates for which a fetched Ferenda consolidated text exists. They are benchmark references, not generated snapshots. Metadata-only batches still have SFS event metadata but no deterministic full-text snapshot in this run.", "", "## Full-text comparison", "", f"Full-text application: `{report['summary']['fullTextApplication']}`. Comparable snapshots: `{report['summary']['notComparable']}`; exact: `{report['summary']['exactMatches']}`; normalized: `{report['summary']['normalizedMatches']}`; mismatches: `{report['summary']['mismatches']}`.", "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], ""]
    version_report_markdown = "\n".join(lines)
    (ROOT / "VERSIONING_REPORT.md").write_text(version_report_markdown)
    frontend_public = ROOT / "frontend/public"
    frontend_public.mkdir(parents=True, exist_ok=True)
    (frontend_public / "VERSIONING_REPORT.md").write_text(version_report_markdown)

    if args.git:
        git_dir = Path(args.git_dir).resolve()
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        if not (git_dir / "HEAD").exists():
            subprocess.run(["git", "init", "--bare", "-q", str(git_dir)], check=True)
        git_command = ["git", "--git-dir", str(git_dir), "--work-tree", str(output)]
        subprocess.run(git_command + ["add", "--all"], cwd=output, check=True)
        staged = subprocess.run(git_command + ["diff", "--cached", "--quiet"], cwd=output)
        if staged.returncode:
            subprocess.run(git_command + ["commit", "-m", "snapshot: generate constitutional versions"], cwd=output, check=False)

    fetched = sum(summary["fetchedVersions"] for summary in report["laws"].values())
    expected = sum(summary["catalogVersions"] for summary in report["laws"].values())
    print(f"Fetched {fetched}/{expected} Ferenda version documents; wrote {len(patch_map)} SFS patch links.")


if __name__ == "__main__":
    main()
