# Verification record (2026-11-19)

Scope: independent local open-source AgentOps Studio, not a HISONG-operated or connected system.

- `AGENTOPS_SEED_SAMPLE=0 python -m pytest -q`: **14 passed** locally (Python 3.13, FastAPI 0.128.2).
- `node --check web/app.js`: passed syntax check.
- `python -m compileall -q app`: passed.
- HTTP integration test using a running Uvicorn process and a fresh empty SQLite database:
  - Authenticated health and overview endpoints worked; protected endpoint without token returned 401.
  - JSON records for VOC, ad campaigns and creators were ingested; imported campaign data calculated ROAS 4.2.
  - All four workflows returned `completed`; second run returned `cached` without duplicate approval suggestions.
  - Approval decision persisted, and audit event was readable.
  - CEO Markdown report generated successfully.
- GUI Chromium testing **was not completed** in this environment: browser navigation to localhost returned `ERR_BLOCKED_BY_ADMINISTRATOR`. The prior screenshot files reflect earlier test/demonstration states; they are not proof of a fresh end-to-end UI run of this release.
- No real Shopify, Meta or TikTok credentials were used; no external APIs were modified.

Limitations: single-operator prototype, rules-based analysis; not enterprise production security or experimentally verified ad optimization.
