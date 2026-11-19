# Data contracts (UTF-8 CSV / JSON)

Three datasets can be imported from `data/example_*.csv`, from original user exports, or via JSON. The example files contain **invented records** and should not be used as business benchmarks.

## Feedback
`id,channel,product,market,rating,comment,created_at` — `rating` integer 1..5.

## Campaigns
`id,channel,name,market,spend,impressions,clicks,conversions,revenue` — numbers nonnegative with `conversions <= clicks <= impressions`. Monetary unit: one consistent account currency (not automatically converted).

## Creators
`id,handle,channel,market,followers,engagement,brand_fit,fee,fraud_flag` — `engagement` percent 0..100; `brand_fit` 0..100; `fraud_flag` 0 or 1. These are input ratings, not independently measured truth.

### Example JSON import

```bash
curl -X POST http://127.0.0.1:8765/api/datasets/feedback/ingest \
  -H 'Content-Type: application/json' \
  -d '[{"id":"F001","channel":"web","product":"Audio","market":"US","rating":2,"comment":"Failed to export recording","created_at":"2026-11-19"}]'
```

With `AGENTOPS_API_TOKEN`, add `-H 'Authorization: Bearer YOUR_TOKEN'`.

### API behavior
- No background sync is assumed; the operator supplies source records.
- Validates every record before transaction; IDs are upsert keys; all imports capped at 500 rows and 1 MB.
- Records are UTF-8; export escapes leading spreadsheet formula operators.
- KPI tables contain attributed totals, **not** counterfactual/causal incremental effectiveness.
