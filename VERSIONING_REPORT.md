# Version experiment

Generated: `2026-08-29T15:28:43.589821+00:00`

The experiment uses SFS metadata and Ferenda's consolidated HTML. It does not parse amendment PDFs.

| Law | Ferenda versions | Fetched | Dated batches | Canonical batches | Metadata-only batches | Missing dates |
|---|---:|---:|---:|---:|---:|---:|
| RF | 6 | 6 | 13 | 5 | 8 | 8 |
| SO | 0 | 0 | 0 | 0 | 0 | 10 |
| TF | 4 | 4 | 12 | 4 | 8 | 26 |
| YGL | 5 | 5 | 7 | 4 | 3 | 2 |

## Interpretation

Canonical batches are the dates for which a fetched Ferenda consolidated text exists. Metadata-only batches still have SFS event metadata but no deterministic full-text snapshot in this run.

## Limitations

- Ferenda exposes a finite list of consolidated versions; it is not the same thing as one full text snapshot per SFS amendment.
- SFS metadata identifies effective dates, replaced provisions and inserted provisions, but does not by itself contain enough structure to apply every textual amendment deterministically.
- Events with missing effective-date metadata are retained as metadata-only records and are not silently assigned a date.
- A generated diff compares Ferenda HTML snapshots after text normalization; it is not a legally authoritative redline.
