# Architecture

```mermaid
flowchart LR
  A[CSV / JSON / Operator HTTPS CSV] --> B[Validation + SQLite]
  B --> C[Deterministic Workflow Engine]
  C --> D[Run Snapshot + Evidence IDs]
  C --> E[Human Approval Queue]
  E --> F[Append-only Review Event]
  C --> G[Executive Brief / REST API]
  B --> H[Optional LLM Copilot]
```

**Input**: real user-supplied CSV/JSON. Default database is empty. Sample data only with `AGENTOPS_SEED_SAMPLE=1`.

**DTC/VOC**: transparent multilingual keyword groups, rating-dependent priorities. Not an ML classifier or verified defect detection.

**Ads**: ROAS=attributed revenue/spend, CPA=spend/conversions, CTR=clicks/impressions, CVR=conversions/clicks. No causal incremental-ROAS claim.

**KOL**: a disclosed weighted screening score, not fraud detection or predictive sales forecasting.

**Idempotency**: SHA-256 snapshot of selected normalized input tables + algorithm version. Same snapshot/workflow reuses the last run unless `force=true`. SQLite is single-writer, best suited to one-operator use.

**Human review**: recommendation records are created only on new analyses. Approvals store a time-stamped event. Approval does not call external marketing APIs.

**Optional inference**: OpenAI-compatible chat-completions endpoint for interpretation; separate and clearly marked. No claim of a vector-RAG system or guaranteed answer correctness.

**Scale boundary**: missing organization accounts, roles, OAuth, queues, streaming, rate limiting and cross-user isolation. Do not deploy to public internet without adding these controls.
