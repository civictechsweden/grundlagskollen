# Grundlagskollen

[Visit Grundlagskollen](https://grundlagskollen.mesu.re/).

A Swedish website for following changes to Sweden's constitutional laws: pending proposals, committee recommendations, parliamentary decisions, elections and published amendments. Each case has a timeline linking back to its sources.

The website is static. A Python pipeline builds its data from public APIs, and GitHub Actions refreshes current parliamentary developments daily and the full historical dataset weekly. Code changes and successful data updates automatically deploy to GitHub Pages. Displayed summaries are Riksdag's own text.

## Run locally

Use Node.js 22.12+ (`.nvmrc` selects Node 24). The repository includes a data snapshot, so no data download is needed to run the website.

```bash
git clone https://github.com/civictechsweden/grundlagskollen.git
cd grundlagskollen/frontend
npm ci
npm run dev
```

`npm run build` creates the static website in `frontend/dist/`.

To refresh the data, install Python 3.12+ and [uv](https://docs.astral.sh/uv/), then run from the repository root:

```bash
uv sync --locked
uv run --locked scripts/refresh_current.py
```

## Reuse the data

The generated JSON files are available directly, without running the pipeline:

- [Cases and SFS amendments](https://raw.githubusercontent.com/civictechsweden/grundlagskollen/main/data/changes.json): the website's dataset, including timelines, matching evidence and source references.
- [Parliamentary source records](https://raw.githubusercontent.com/civictechsweden/grundlagskollen/main/data/riksdag-documents.json): extracted document metadata and source text.
- [Document graph](https://raw.githubusercontent.com/civictechsweden/grundlagskollen/main/data/document-graph.json): references connecting parliamentary documents.

## How decisions are connected

[Riksdagens öppna data](https://data.riksdagen.se/) provides committee reports, document references, activity dates, event statuses and decision notices. The pipeline discovers constitutional cases and extracts the operative decision wording. Planned votes remain separate from completed chamber decisions; a committee recommendation is not treated as a parliamentary vote.

For current follow-up reports, the first decision is identified through the explicit report citation and decision date under `Behandlade förslag`. Both must match the earlier report's metadata. Older cases use shared document references and decision wording; the dataset records the matching method and supporting evidence. Structured references to preparatory works connect parliamentary decisions to SFS amendments in the [Ferenda / lagen.nu API](https://lagen.nu/om/api).

[Wikidata](https://www.wikidata.org/) supplies election dates and Swedish Wikipedia links. Ferenda's version catalogue supplies the fixed before-and-after comparisons. All discovery and matching runs in Python using API data, with no hand-maintained case list or website scraping. Missing or uncertain matches remain explicit rather than being guessed.

## Development

```bash
uv run --locked -m unittest discover -s tests
uv run --locked scripts/validate_recent.py
uv run --locked scripts/benchmark_data.py
```

For a full historical rebuild, run `uv run --locked scripts/update_data.py`. Use `scripts/generate_versions.py --git` to rebuild the separate consolidated-version experiment. See [DATA_BENCHMARK.md](DATA_BENCHMARK.md) and [VERSIONING_REPORT.md](VERSIONING_REPORT.md) for validation and coverage limits.

The code is licensed under [AGPL-3.0](LICENSE). Upstream source material retains its respective terms.
