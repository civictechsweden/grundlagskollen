# Version experiment

Generated: `2026-08-29T18:11:09.103041+00:00`

The experiment uses SFS metadata and Ferenda's consolidated HTML. It does not parse amendment PDFs.
SFS operations are parsed into a reviewable ledger. Full-text application is intentionally reported as `not_attempted` until replacement text and a verified base snapshot are available.

| Law | Ferenda versions | Fetched | Dated batches | Ferenda references | Metadata-only batches | SFS patches | Needs review | Missing dates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RF | 6 | 6 | 13 | 5 | 8 | 47 | 8 | 8 |
| SO | 0 | 0 | 0 | 0 | 0 | 10 | 10 | 10 |
| TF | 4 | 4 | 12 | 4 | 8 | 52 | 8 | 26 |
| YGL | 5 | 5 | 7 | 4 | 3 | 12 | 2 | 2 |

## Interpretation

Ferenda-reference batches are dates for which a fetched Ferenda consolidated text exists. They are benchmark references, not generated snapshots. Metadata-only batches still have SFS event metadata but no deterministic full-text snapshot in this run.

## Full-text comparison

Full-text application: `not_attempted`. Comparable snapshots: `15`; exact: `0`; normalized: `0`; mismatches: `0`.

## Limitations

- Ferenda exposes a finite list of consolidated versions; it is not the same thing as one full text snapshot per SFS amendment.
- SFS metadata identifies effective dates, replaced provisions and inserted provisions, but does not by itself contain enough structure to apply every textual amendment deterministically.
- Events with missing effective-date metadata are retained as metadata-only records and are not silently assigned a date.
- A generated diff compares Ferenda HTML snapshots after text normalization; it is not a legally authoritative redline.
