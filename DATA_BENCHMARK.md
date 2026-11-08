# Dataset benchmark

Generated: `2026-11-08T09:26:35.538770+00:00`

## Coverage

| Metric | Value |
| --- | ---: |
| `total_pending_proposals` | 149 |
| `finally_adopted` | 107 |
| `finally_rejected` | 1 |
| `unresolved` | 145 |
| `matched_to_sfs` | 83 |
| `adopted_without_sfs_match` | 42 |
| `orphan_sfs` | 38 |
| `rejected_with_sfs` | 0 |
| `chronology_errors` | 1 |
| `unknown_sfs_operations` | 28 |
| `regression_cases` | 8 |
| `regression_passed` | 8 |
| `secondary_cases` | 8 |
| `secondary_passed` | 8 |

## Regression cases

| Case | Result |
| --- | --- |
| test-a-1991-rejection | PASS (7/7) |
| test-b-sfs-2022-1600 | PASS (8/8) |
| test-c-1896-1897-tf | PASS (5/5) |
| test-d-1885-1888-rf-6 | PASS (6/6) |
| test-e-1975-motion-not-first | PASS (5/5) |
| test-f-1975-1976-tf-final-adoption | PASS (12/12) |
| test-g-1990-2017-candidate-audit | PASS (29/29) |
| test-h-1921-1979-so-decision-chains | PASS (98/98) |

## Secondary-source fixtures

| Case | Result |
| --- | --- |
| benchmark-2026-current-queue | PASS (22/22) |
| benchmark-2025-ku2 | PASS (1/1) |
| benchmark-2025-ku8 | PASS (1/1) |
| benchmark-2022-utlandsspioneri | PASS (1/1) |
| benchmark-2022-riksbanken | PASS (1/1) |
| benchmark-2018-mediegrundlagar | PASS (1/1) |
| benchmark-2010-reformerad-grundlag | PASS (1/1) |
| benchmark-1960-forkastad | PASS (1/1) |

## Ferenda snapshots

Checked: `15`; exact: `0`; normalized: `0`; mismatches: `0`.

A regression failure is retained as data and should be investigated before a snapshot is described as complete.
