# Grundlagsmonitor

En statisk tidsmaskin för Sveriges fyra grundlagar. Frontendens snapshot byggs från Ferenda / lagen.nu och Riksdagens öppna data.

## Kör projektet

```bash
uv run --with certifi scripts/update_data.py
uv run scripts/benchmark_data.py
uv run --with certifi scripts/generate_versions.py --git
npm install
npm run dev
```

`npm run build` skapar `dist/`, inklusive de genererade versionstexterna och patcharna i `public/versions/`.

## Dataflöde

1. `scripts/update_data.py` hämtar Ferendas SFS-register, amendments och versionskatalog för RF, TF, YGL och SO. Det hämtar också Riksdagens dokumentlista, ärendestatus och voteringar för att hitta första beslut som uttryckligen antar ett grundlagsförslag som vilande.
2. Resultatet skrivs till `data/changes.json`. Den filen är frontendens enda juridiska snapshot.
3. `scripts/benchmark_data.py` jämför snapshoten med den statiska kontrollistan i `data/benchmark-cases.json` och skriver `DATA_BENCHMARK.md` samt `data/benchmark-report.json`.
4. `scripts/generate_versions.py` använder SFS-metadata och Ferendas konsoliderade HTML för att skapa textversioner, normaliserade unified diffs, manifest och `VERSIONING_REPORT.md`. `--git` sparar snapshotens historik i det separata bare-repot `.versions-git/`, medan `public/versions/` förblir rena statiska tillgångar.

## Vad som visas

- sju aktuella vilande första beslut med första beslut, mellanliggande val och villkoret för ett andra beslut;
- historiska, bekräftade SFS-händelser med sökning, filtrering, metadata och länkar till Ferenda;
- en interaktiv år-slider med fyra lagbanor och valt händelsekort;
- ett uttryckligen belagt historiskt förkastat förslag;
- omatchade Ferenda-träffar som granskningssignaler, aldrig som automatiskt avbrutna ärenden;
- genererade textpatchar när Ferenda exponerar två jämförbara konsoliderade versioner.

## Begränsningar

Ferendas `/document/versions` är en katalog över exponerade konsoliderade versioner, inte en komplett fulltextversion per SFS-amendment. SFS-metadata ger stabil identitet, ikraftträdande, ersatta paragrafer och införda paragrafer, men räcker inte alltid för att applicera varje textändring deterministiskt. I senaste versionsexperimentet hämtades 15 av 15 Ferenda-sidor; SO hade inga exponerade versioner och flera äldre ändringshändelser saknar ikraftträdandedatum i källmetadata.

Riksdagen har ingen ensam `pending`-flagga. Kön bygger på dokumentlistans KU-träffar och förslagstexten `antar som vilande`. Ett senare beslut som ännu inte hittats är inte bevis på att ett förslag har fallit. Se [VERSIONING_REPORT.md](VERSIONING_REPORT.md) och [DATA_BENCHMARK.md](DATA_BENCHMARK.md) för körningsresultat.
