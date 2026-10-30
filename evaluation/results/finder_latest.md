# FinDER (retrieval) — 2026-10-25T15:55:32

25 random FinDER queries (seed 7) searched against 630 expert-annotated 10-K evidence passages; a hit means the exact annotated passage was retrieved. Dense model: gemini-embedding-001.

| config | n | recall@1 | recall@3 | recall@5 | recall@10 | recall@50 | mrr | ndcg@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| sparse | 25 | 36.0 | 52.0 | 52.0 | 64.0 | 92.0 | 0.462 | 0.497 | 10 | 15 |
| dense | 25 | 72.0 | 84.0 | 84.0 | 88.0 | 100.0 | 0.778 | 0.783 | 499 | 686 |
| hybrid | 25 | 60.0 | 68.0 | 68.0 | 72.0 | 96.0 | 0.663 | 0.665 | 522 | 870 |
| full | 25 | 64.0 | 76.0 | 76.0 | 88.0 | 96.0 | 0.713 | 0.748 | 3589 | 5288 |
