# Grundlagsmonitor

En statisk tidsmaskin för Sveriges fyra grundlagar. Frontendens snapshot byggs från Ferenda / lagen.nu och Riksdagens öppna data.

## Kör projektet

```bash
uv sync
uv run --locked scripts/update_data.py
uv run --locked scripts/generate_versions.py --git
uv run --locked scripts/benchmark_data.py
npm install
npm run dev
```

`npm run build` skapar `dist/`, inklusive de genererade versionstexterna och patcharna i `public/versions/`.

## Dataflöde

1. `pyproject.toml` deklarerar Python-version och beroenden; `uv.lock` låser körmiljön för lokalt arbete och CI.
2. `scripts/update_data.py` hämtar Ferendas SFS-register, amendments och versionskatalog för RF, TF, YGL och SO. Det hämtar också Riksdagens dokumentlista, ärendestatus och dokumenttext för att hitta första och slutliga beslut, deras referenser och beslutsgrafen.
3. Resultatet skrivs till `data/changes.json`, `data/riksdag-documents.json` och `data/document-graph.json`. `changes.json` är frontendens juridiska snapshot; dokumentgrafen behåller källproveniens.
4. `scripts/generate_versions.py` tolkar SFS-metadata till deklarativa operationer, bygger metadata-snapshots för varje känt ikraftdatum och hämtar Ferendas konsoliderade HTML som separat benchmark. `--git` sparar manifest, texter och normaliserade diffar i det separata bare-repot `.versions-git/`.
5. `scripts/benchmark_data.py` kör de fyra regressionsfallen i `data/regression-cases.json` och den statiska sekundärkällistan i `data/benchmark-cases.json`. Den skriver `DATA_BENCHMARK.md` samt `data/benchmark-report.json`.

## Vad som visas

- den explicita kön av vilande första beslut med mellanliggande val och villkoret för ett andra beslut;
- en interaktiv år-slider med fyra lagbanor och valbar SFS-händelse;
- en beslutsgraf som skiljer första beslut, slutligt beslut och promulgerad SFS;
- dokumentproveniens, strukturella referenser och textsignaler från Riksdagens öppna data;
- SFS-operationer på avsnittsnivå, Ferenda-referenser och normaliserade diffar när de finns;
- regressioner, sekundärkällor och öppna QA-luckor i samma vy.

## Begränsningar

Ferendas `/document/versions` är en katalog över exponerade konsoliderade versioner, inte en komplett fulltextversion per SFS-amendment. SFS-metadata ger stabil identitet, ikraftträdande, ersatta paragrafer och införda paragrafer, men räcker inte alltid för att applicera varje textändring deterministiskt. Därför markeras operationer med låg säkerhet och fulltext-applicering är uttryckligen `not_attempted` i versionsexperimentets rapport.

Riksdagen har ingen ensam `pending`-flagga. Kön bygger på dokumentlistans KU-träffar och förslagstexten `antar som vilande`. Ett senare beslut som ännu inte hittats är inte bevis på att ett förslag har fallit. Se [VERSIONING_REPORT.md](VERSIONING_REPORT.md) och [DATA_BENCHMARK.md](DATA_BENCHMARK.md) för körningsresultat.
