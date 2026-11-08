# Grundlagsmonitor

En statisk tidsmaskin för Sveriges fyra grundlagar. Frontendens snapshot byggs från Ferenda / lagen.nu och Riksdagens öppna data.

## Kör projektet

```bash
uv sync
uv run --locked scripts/update_data.py
uv run --locked scripts/generate_versions.py --git
uv run --locked scripts/benchmark_data.py
cd frontend
npm install
npm run dev
```

`npm run build` från `frontend/` skapar `frontend/dist/`, inklusive de genererade versionstexterna och patcharna i `frontend/public/versions/`.

## Refresh current parliamentary developments

```bash
uv run --locked scripts/refresh_current.py
uv run --locked -m unittest discover -s tests
uv run --locked scripts/benchmark_data.py
```

This bounded refresh discovers recent KU reports and re-fetches both text and status for monitored cases. It preserves the historical SFS and version catalog, with separate timestamps for the current check and historical snapshot. The daily workflow runs this update; weekly and manual runs also rebuild the full dataset and law versions. The frontend requires Node 20.19+ or 22.12+.

`dokaktivitet.aktivitet` distinguishes committee treatment (`JUS`, justering), debate (`BEH`) and chamber decisions (`BES`). Each event retains its date and whether the API marks it `planerat` or `inträffat`. A committee recommendation or an elapsed calendar date never counts as a completed chamber vote. Current reports expose these stages as `parliamentaryProgress`; an upcoming second decision is stored separately in `nextDecision`, while `finalDecision` requires a completed chamber event.

Discovery and content require no hand-maintained case list or AI service. The refresh searches the KU document API, rechecks previously discovered active reports, and follows explicit report citations under `Behandlade förslag` to find first decisions outside the discovery window. Both the report citation and the first decision's date must match. The source passage is preserved in `match.evidence`. Older cases without this explicit evidence retain their reference-matching method and are labelled accordingly in the interface.

Displayed summaries and notice headings are Riksdag-authored source text: `dokuppgift.uppgift[kod=utsknotis]` for committee proposals and `[kod=notis]` for completed decisions, with their respective headline fields. If neither is available, the script extracts the report's `Sammanfattning` section only when its boundaries are identifiable. If no source summary is available, the interface links to the report instead. HTML is converted to escaped plain text without rewriting the wording. `sourceText` retains the document ID, source URL and field. No editorial titles, summaries or effective dates are injected into case records.

The website puts upcoming second decisions and recent chamber outcomes before the searchable history. Native expandable entries show the official source text, the decision timeline, the first-decision citation and source links. The build projects only the fields the interface uses from the full legal dataset.

To rediscover and validate the last ten years against open-data outcomes:

```bash
uv run --locked scripts/validate_recent.py --refresh
```

The check writes `data/recent-validation-report.json` and exits unsuccessfully if a recent follow-up report lacks a verified first-decision link, disagrees with the recorded chamber outcome, or loses the distinction between planned and completed events. The daily workflow runs this validation against the refreshed snapshot before building the frontend and committing changes. `--from-year` selects a different validation window.

## Dataflöde

1. `pyproject.toml` deklarerar Python-version och beroenden; `uv.lock` låser körmiljön för lokalt arbete och CI.
2. `scripts/update_data.py` hämtar Ferendas SFS-register, amendments och versionskatalog för RF, TF, YGL och SO. Varje SFS-amendments förarbeten löses därefter via Ferendas dokumenterade JSON-API (`/api/v1/document`); den kanoniska postens `source_url` ger Riksdagens dokument-ID. Dessa ID:n används som en separat sekundär kontroll av beslutskedjan. Riksdagens dokumentlista, ärendestatus och dokumenttext används för att hitta första och slutliga beslut, deras referenser och beslutsgrafen.
3. Resultatet skrivs till `data/changes.json`, `data/riksdag-documents.json` och `data/document-graph.json`. `changes.json` är frontendens juridiska snapshot; dokumentgrafen behåller källproveniens.
4. `scripts/generate_versions.py` tolkar SFS-metadata till deklarativa operationer, bygger metadata-snapshots för varje känt ikraftdatum och hämtar Ferendas konsoliderade HTML som separat benchmark. `--git` sparar manifest, texter och normaliserade diffar i det separata bare-repot `.versions-git/`.
5. `scripts/benchmark_data.py` kör regressionsfallen i `data/regression-cases.json` och den statiska sekundärkällistan i `data/benchmark-cases.json`. Den skriver `DATA_BENCHMARK.md` samt `data/benchmark-report.json`.

## Vad som visas

- den explicita kön av vilande första beslut med mellanliggande val och villkoret för ett andra beslut;
- en interaktiv år-slider med fyra lagbanor och valbar SFS-händelse;
- en beslutsgraf som skiljer första beslut, slutligt beslut och promulgerad SFS;
- dokumentproveniens, strukturella referenser och textsignaler från Riksdagens öppna data;
- SFS-operationer på avsnittsnivå, Ferenda-API-referenser till förarbeten och normaliserade diffar när de finns;
- regressioner, sekundärkällor och öppna QA-luckor i samma vy.

## Begränsningar

Ferendas `/document/versions` är en katalog över exponerade konsoliderade versioner, inte en komplett fulltextversion per SFS-amendment. SFS-metadata ger stabil identitet, ikraftträdande, ersatta paragrafer och införda paragrafer, men räcker inte alltid för att applicera varje textändring deterministiskt. Därför markeras operationer med låg säkerhet och fulltext-applicering är uttryckligen `not_attempted` i versionsexperimentets rapport.

Riksdagen har ingen ensam `pending`-flagga. Ett första vilandebeslut kräver därför signal i utskottets operativa beslutsdel; formuleringar i motioner, historik och reservationer räknas inte som beslut. Ett senare beslut som ännu inte hittats är inte bevis på att ett förslag har fallit. Se [VERSIONING_REPORT.md](VERSIONING_REPORT.md) och [DATA_BENCHMARK.md](DATA_BENCHMARK.md) för körningsresultat.
