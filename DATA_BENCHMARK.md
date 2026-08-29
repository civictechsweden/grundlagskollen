# Data benchmark

Generated: `2026-08-29T15:28:43.485211+00:00`

Evidence recall: **17/17 (100.0%)**.

This is a regression benchmark over the static cases in `data/benchmark-cases.json`; it is not a claim of complete constitutional history.

| Case | Expected | Result | Missing |
|---|---|---|---|
| benchmark-2026-current-queue | pending-first-vote | matched | — |
| benchmark-2025-ku2 | pending-first-vote | matched | — |
| benchmark-2025-ku8 | pending-first-vote | matched | — |
| benchmark-2022-utlandsspioneri | confirmed | matched | — |
| benchmark-2022-riksbanken | confirmed | matched | — |
| benchmark-2018-mediegrundlagar | confirmed | matched | — |
| benchmark-2010-reformerad-grundlag | confirmed | matched | — |
| benchmark-1960-forkastad | aborted | matched | — |

## Limitations

- The fixtures are a regression set, not an exhaustive catalogue of every historical proposal.
- A Ferenda search hit without a matching SFS is reported as an unresolved signal, not as an aborted proposal.
- Confirmed-case recall is measured only for the SFS identifiers named in the fixtures.
